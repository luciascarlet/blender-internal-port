# SPDX-License-Identifier: GPL-2.0-or-later
"""Read Internal data using 2.79 RNA, then append editable modern datablocks.

The source file is never changed. Its old material DNA and shader trees are read
before Blender's current versioning code replaces them with modern materials.
"""
import ctypes as C
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
from . import full_native as N
from .legacy_ui import SCHEMA, TREE


class Reader:
    def __init__(self, path):
        self.lib = N.load()
        if not self.lib.bi_full_load(path.encode()):
            raise RuntimeError(self.lib.bi_full_error().decode())
        self.main = self.lib.bi_full_main()

    def value(self, handle, path):
        size = C.c_int()
        path = path.encode()
        kind = self.lib.bi_full_property_info(handle, path, C.byref(size))
        if not kind:
            raise RuntimeError(self.lib.bi_full_error().decode())
        if kind in (1, 2, 3):
            data = (C.c_double * (size.value or 1))()
            if not self.lib.bi_full_get_numbers(handle, path, data, len(data)):
                raise RuntimeError('Cannot read numeric legacy property')
            cast = {1: bool, 2: int, 3: float}[kind]
            return [cast(v) for v in data] if size.value else cast(data[0])
        if kind in (4, 5):
            buffer = C.create_string_buffer(1024)
            length = self.lib.bi_full_get_string(handle, path, buffer, len(buffer))
            if length > len(buffer):
                buffer = C.create_string_buffer(length)
                self.lib.bi_full_get_string(handle, path, buffer, length)
            return buffer.value.decode('utf8', errors='replace')
        if kind == 6:
            return self.lib.bi_full_get_pointer(handle, path)
        if kind == 7:
            return [self.lib.bi_full_collection_item(handle, path, i) for i in range(size.value)]

    def props(self, handle, schema, prefix=''):
        return {p['id']: self.value(handle, prefix + p['id']) for p in schema}

    def name(self, handle):
        return self.value(handle, 'name') if handle else None

    def ramp(self, handle):
        if not handle:
            return None
        return {'properties': {p: self.value(handle, p) for p in ('interpolation', 'color_mode', 'hue_interpolation')},
                'elements': [(self.value(p, 'position'), self.value(p, 'color')) for p in self.value(handle, 'elements')]}

    def tree(self, handle):
        if handle in self.trees:
            return handle
        result = {'name': self.name(handle), 'nodes': [], 'links': [], 'inputs': [], 'outputs': []}
        self.trees[handle] = result
        for direction in ('inputs', 'outputs'):
            for socket in self.value(handle, direction):
                result[direction].append(self.socket(socket))
        nodes = self.value(handle, 'nodes')
        sockets = {}
        for index, node in enumerate(nodes):
            kind = self.value(node, 'bl_idname')
            schema = SCHEMA['nodes'].get(kind)
            if schema is None and kind not in ('ShaderNodeGroup', 'NodeGroupInput', 'NodeGroupOutput', 'NodeReroute', 'NodeFrame'):
                raise RuntimeError('Unsupported original shader node: ' + kind)
            data = {'kind': kind, 'name': self.name(node), 'location': self.value(node, 'location'),
                    'label': self.value(node, 'label'), 'mute': self.value(node, 'mute'),
                    'properties': self.props(node, schema['properties']) if schema else {}}
            for direction in ('inputs', 'outputs'):
                data[direction] = []
                for si, socket in enumerate(self.value(node, direction)):
                    sockets[socket] = (index, si)
                    data[direction].append(self.socket(socket))
            for ptr in ('material', 'texture', 'lamp_object'):
                if schema and ptr in schema['pointers']:
                    data[ptr] = self.name(self.value(node, ptr))
            if kind == 'ShaderNodeGroup':
                data['tree'] = self.tree(self.value(node, 'node_tree'))
            if schema and 'color_ramp' in schema['pointers']:
                data['ramp'] = self.ramp(self.value(node, 'color_ramp'))
            if schema and 'mapping' in schema['pointers']:
                mapping = self.value(node, 'mapping')
                data['mapping'] = {p: self.value(mapping, p) for p in
                                   ('use_clip', 'clip_min_x', 'clip_min_y', 'clip_max_x', 'clip_max_y', 'black_level', 'white_level')}
                data['curves'] = [{'extend': self.value(c, 'extend'), 'points': [
                    (self.value(p, 'location'), self.value(p, 'handle_type')) for p in self.value(c, 'points')]}
                    for c in self.value(mapping, 'curves')]
            result['nodes'].append(data)
        for link in self.value(handle, 'links'):
            result['links'].append((sockets[self.value(link, 'from_socket')], sockets[self.value(link, 'to_socket')]))
        return handle

    def socket(self, handle):
        kind = self.value(handle, 'type')
        return {'name': self.name(handle), 'type': kind,
                'value': self.value(handle, 'default_value') if kind in ('VALUE', 'RGBA', 'VECTOR') else None}

    def snapshot(self):
        self.trees = {}
        materials, textures, lights, scenes = {}, {}, {}, {}
        for m in self.value(self.main, 'materials'):
            data = {'properties': self.props(m, SCHEMA['material']),
                    'nested': {k: self.props(m, v, k + '.') for k, v in SCHEMA['nested'].items()}, 'slots': []}
            tree = self.value(m, 'node_tree')
            if tree and self.value(m, 'use_nodes'):
                data['tree'] = self.tree(tree)
            enabled = self.value(m, 'use_textures')
            for i, slot in enumerate(self.value(m, 'texture_slots')):
                if slot:
                    data['slots'].append({'index': i, 'enabled': enabled[i],
                                          'texture': self.name(self.value(slot, 'texture')),
                                          'properties': self.props(slot, SCHEMA['texture_slot'])})
            materials[self.name(m)] = data
        for texture in self.value(self.main, 'textures'):
            kind = self.value(texture, 'type')
            if kind not in SCHEMA['textures']:
                raise RuntimeError('Legacy texture requires additional migration: ' + kind)
            textures[self.name(texture)] = {'properties': self.props(texture, SCHEMA['textures'][kind]),
                                           'ramp': self.ramp(self.value(texture, 'color_ramp'))}
        for lamp in self.value(self.main, 'lamps'):
            lights[self.name(lamp)] = self.props(lamp, SCHEMA['lights'][self.value(lamp, 'type')])
        for scene in self.value(self.main, 'scenes'):
            world = self.value(scene, 'world')
            scenes[self.name(scene)] = {'render': self.props(scene, SCHEMA['render'], 'render.'),
                'world': self.props(world, SCHEMA['world']) if world else {},
                'world_nested': {k: self.props(world, v, k + '.') for k, v in SCHEMA['world_nested'].items()} if world else {}}
        return {'materials': materials, 'textures': textures, 'lights': lights, 'scenes': scenes, 'trees': self.trees}


def assign(target, values, prefix=''):
    for key, value in values.items():
        # RNA shares Toon/Fresnel DNA fields. Only assign the active model.
        if key.startswith('diffuse_toon_') and values.get('diffuse_shader') != 'TOON':
            continue
        if key.startswith('diffuse_fresnel') and values.get('diffuse_shader') != 'FRESNEL':
            continue
        setattr(target, prefix + key, value)


def restore_ramp(ramp, data):
    if data is None:
        return
    assign(ramp, data['properties'])
    while len(ramp.elements) > 2:
        ramp.elements.remove(ramp.elements[-1])
    for i, (position, color) in enumerate(data['elements']):
        element = ramp.elements[i] if i < 2 else ramp.elements.new(position)
        element.position, element.color = position, color


def import_file(path):
    with N.LOCK:
        snapshot = Reader(path).snapshot()
    existing = set(bpy.data.user_map())
    try:
        return _import_snapshot(path, snapshot)
    except Exception:
        # Append/restore is one transaction. Never remove pre-existing user IDs.
        created = set(bpy.data.user_map()) - existing
        if created:
            bpy.data.batch_remove(ids=created)
        raise


def _import_snapshot(path, snapshot):
    # Explicitly append data lists together to retain original-name mappings even
    # when the destination already contains same-named materials or lights.
    with bpy.data.libraries.load(path, link=False) as (source, dest):
        names = {k: list(getattr(source, k)) for k in ('scenes', 'materials', 'textures', 'lights', 'objects')}
        for key, values in names.items():
            setattr(dest, key, list(values))
    maps = {key: dict(zip(names[key], getattr(dest, key))) for key in names}
    trees = {key: bpy.data.node_groups.new(data['name'] + ' Internal', TREE) for key, data in snapshot['trees'].items()}
    # Interfaces first, then nodes, then links; group users see complete sockets.
    for key, data in snapshot['trees'].items():
        for direction in ('inputs', 'outputs'):
            for s in data[direction]:
                socket = trees[key].interface.new_socket(name=s['name'], in_out='INPUT' if direction == 'inputs' else 'OUTPUT',
                    socket_type={'VALUE': 'NodeSocketFloat', 'RGBA': 'NodeSocketColor', 'VECTOR': 'NodeSocketVector'}[s['type']])
                socket.default_value = s['value']
    for key, data in snapshot['trees'].items():
        tree = trees[key]
        nodes = []
        for spec in data['nodes']:
            kind = spec['kind']
            node = tree.nodes.new('BI_' + kind if kind.startswith('Shader') else kind)
            nodes.append(node)
            node.name, node.location, node.label, node.mute = spec['name'], spec['location'], spec['label'], spec['mute']
            assign(node, spec['properties'], 'legacy_')
            if 'tree' in spec:
                node.node_tree = trees[spec['tree']]
            for ptr, category in (('material', 'materials'), ('texture', 'textures'), ('lamp_object', 'objects')):
                if spec.get(ptr):
                    setattr(node, ptr, maps[category][spec[ptr]])
            for direction in ('inputs', 'outputs'):
                for socket, value in zip(getattr(node, direction), spec[direction]):
                    if value['value'] is not None:
                        socket.default_value = value['value']
            if 'ramp' in spec:
                restore_ramp(node.storage.nodes[0].color_ramp, spec['ramp'])
            if 'mapping' in spec:
                mapping = node.storage.nodes[0].mapping
                assign(mapping, spec['mapping'])
                mapping.extend = spec['curves'][0]['extend']
                for curve, values in zip(mapping.curves, spec['curves']):
                    for i, (location, handle_type) in enumerate(values['points']):
                        point = curve.points[i] if i < 2 else curve.points.new(*location)
                        point.location, point.handle_type = location, handle_type
                mapping.update()
        for (a, out), (b, inp) in data['links']:
            tree.links.new(nodes[a].outputs[out], nodes[b].inputs[inp])
    for name, data in snapshot['materials'].items():
        props = maps['materials'][name].classic_internal
        props.use_legacy_settings = True
        assign(props.legacy, data['properties'])
        for key, values in data['nested'].items():
            assign(getattr(props.legacy, key), values)
        if 'tree' in data:
            props.node_tree = trees[data['tree']]
        for spec in data['slots']:
            while len(props.texture_slots) <= spec['index']:
                props.texture_slots.add().enabled = False
            slot = props.texture_slots[spec['index']]
            slot.enabled = spec['enabled']
            slot.texture = maps['textures'].get(spec['texture'])
            assign(slot.settings, spec['properties'])
    for name, data in snapshot['textures'].items():
        texture = maps['textures'][name]
        assign(texture, {k: v for k, v in data['properties'].items() if hasattr(texture, k)})
        restore_ramp(texture.color_ramp, data['ramp'])
    for name, data in snapshot['lights'].items():
        props = maps['lights'][name].classic_internal
        props.use_legacy_settings = True
        assign(props.legacy, data)
    for name, data in snapshot['scenes'].items():
        scene = maps['scenes'][name]
        scene.render.engine = 'BLENDER_INTERNAL_PORT'
        scene.render.film_transparent = data['render'].get('alpha_mode') == 'TRANSPARENT'
        props = scene.classic_internal
        props.use_legacy_settings, props.use_legacy_world = True, bool(data['world'])
        assign(props.legacy, data['render'])
        assign(props.world, data['world'])
        for key, values in data['world_nested'].items():
            assign(getattr(props.world, key), values)
    return list(maps['scenes'].values())


class BI_OT_import_legacy(bpy.types.Operator, ImportHelper):
    bl_idname = 'import_scene.blender_internal'
    bl_label = 'Import Blender Internal Scene'
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = '.blend'
    filter_glob: StringProperty(default='*.blend', options={'HIDDEN'})

    def execute(self, context):
        try:
            scenes = import_file(self.filepath)
            if scenes and context.window:
                context.window.scene = scenes[0]
            self.report({'INFO'}, 'Imported {} legacy scenes with original Internal settings'.format(len(scenes)))
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


def menu(self, context):
    self.layout.operator(BI_OT_import_legacy.bl_idname, text='Blender Internal 2.79 (.blend)')


def register():
    bpy.utils.register_class(BI_OT_import_legacy)
    bpy.types.TOPBAR_MT_file_import.append(menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu)
    bpy.utils.unregister_class(BI_OT_import_legacy)
