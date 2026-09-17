# SPDX-License-Identifier: GPL-2.0-or-later
"""Legacy material RNA controls and native-executed legacy shader nodes."""
import json
from pathlib import Path
import bpy
from bpy import props

SCHEMA = json.loads((Path(__file__).parent / 'legacy_schema.json').read_text())
TREE = 'BlenderInternalNodeTree'
CLASSES = []

def make_property(p):
    kw = {'name': p['name'], 'description': p['description'], 'default': p['default']}
    kind = p['type']
    if kind in ('INT', 'FLOAT'):
        kw.update(min=p['min'], max=p['max'])
    if kind == 'ENUM':
        kw['items'] = [tuple(i) for i in p['items']]
        if kw['default'] not in [i[0] for i in kw['items']]:
            kw['default'] = kw['items'][0][0]
        return props.EnumProperty(**kw)
    if kind == 'STRING':
        return props.StringProperty(**kw)
    if p.get('size'):
        if p['size'] > 32:
            return None
        kw['size'] = p['size']
        subtype = p.get('subtype', 'NONE')
        if subtype in ('COLOR', 'COLOR_GAMMA', 'XYZ', 'EULER', 'TRANSLATION', 'DIRECTION', 'VELOCITY', 'ACCELERATION', 'QUATERNION', 'AXISANGLE'):
            kw['subtype'] = subtype
        return {'FLOAT': props.FloatVectorProperty, 'INT': props.IntVectorProperty,
                'BOOLEAN': props.BoolVectorProperty}[kind](**kw)
    return {'FLOAT': props.FloatProperty, 'INT': props.IntProperty, 'BOOLEAN': props.BoolProperty}[kind](**kw)


def group(name, properties):
    annotations = {}
    for prop in properties:
        value = make_property(prop)
        if value is not None:
            annotations[prop['id']] = value
    cls = type(name, (bpy.types.PropertyGroup,), {'__annotations__': annotations})
    CLASSES.append(cls)
    return cls

NESTED = {name: group('BI_' + name, items) for name, items in SCHEMA['nested'].items()}
LegacyMaterial = group('BI_LegacyMaterial', SCHEMA['material'])
for name, cls in NESTED.items():
    LegacyMaterial.__annotations__[name] = props.PointerProperty(type=cls)

LegacyTextureSettings = group('BI_LegacyTextureSettings', SCHEMA['texture_slot'])
LegacyLight = group('BI_LegacyLight', SCHEMA['light'])
LegacyRender = group('BI_LegacyRender', SCHEMA['render'])
WORLD_NESTED = {name: group('BI_World_' + name, items) for name, items in SCHEMA['world_nested'].items()}
LegacyWorld = group('BI_LegacyWorld', SCHEMA['world'])
for name, cls in WORLD_NESTED.items():
    LegacyWorld.__annotations__[name] = props.PointerProperty(type=cls)

class LegacyTextureSlot(bpy.types.PropertyGroup):
    enabled: props.BoolProperty(name='Enabled', default=True)
    texture: props.PointerProperty(name='Texture', type=bpy.types.Texture)
    settings: props.PointerProperty(type=LegacyTextureSettings)

CLASSES.append(LegacyTextureSlot)

class LegacyTree(bpy.types.NodeTree):
    bl_idname = TREE
    bl_label = 'Blender Internal Nodes'
    bl_icon = 'MATERIAL'

    def interface_update(self, context):
        for tree in bpy.data.node_groups:
            if tree.bl_idname == TREE:
                for node in tree.nodes:
                    if node.bl_idname == 'BI_ShaderNodeGroup' and node.node_tree == self:
                        node.update()

    @classmethod
    def get_from_context(cls, context):
        obj = context.object
        material = obj.active_material if obj else None
        if material:
            return material.classic_internal.node_tree, material, material
        return None, None, None

CLASSES.append(LegacyTree)

class LegacyNode:
    @classmethod
    def poll(cls, tree):
        return tree.bl_idname == TREE

    def init(self, context):
        schema = SCHEMA['nodes'][self.legacy_type]
        for direction in ('inputs', 'outputs'):
            for s in schema[direction]:
                socket = getattr(self, direction).new({'VALUE': 'NodeSocketFloat', 'RGBA': 'NodeSocketColor', 'VECTOR': 'NodeSocketVector'}[s['type']], s['name'])
                if s['default'] is not None:
                    socket.default_value = s['default']
        if self.legacy_type in ('ShaderNodeRGBCurve', 'ShaderNodeVectorCurve', 'ShaderNodeValToRGB'):
            store = bpy.data.node_groups.new('.Internal Node Storage', 'ShaderNodeTree')
            store.nodes.new(self.legacy_type)
            self.storage = store

    def draw_buttons(self, context, layout):
        for p in SCHEMA['nodes'][self.legacy_type]['properties']:
            if hasattr(self, 'legacy_' + p['id']):
                layout.prop(self, 'legacy_' + p['id'])
        for name in ('material', 'texture', 'lamp_object'):
            if hasattr(self, name):
                layout.prop(self, name)
        if self.storage:
            node = self.storage.nodes[0]
            if self.legacy_type == 'ShaderNodeValToRGB':
                layout.template_color_ramp(node, 'color_ramp', expand=True)
            else:
                layout.template_curve_mapping(node, 'mapping', type='COLOR' if self.legacy_type == 'ShaderNodeRGBCurve' else 'VECTOR')

    def copy(self, source):
        if getattr(source, 'storage', None):
            self.storage = source.storage.copy()

    def free(self):
        store = getattr(self, 'storage', None)
        if store:
            self.storage = None
            if store.users == 0:
                bpy.data.node_groups.remove(store)

for typename, schema in sorted(SCHEMA['nodes'].items()):
    annotations = {'storage': props.PointerProperty(type=bpy.types.NodeTree)}
    for p in schema['properties']:
        value = make_property(p)
        if value is not None:
            annotations['legacy_' + p['id']] = value
    for name, pointer_type in (('material', bpy.types.Material), ('texture', bpy.types.Texture), ('lamp_object', bpy.types.Object)):
        if name in schema['pointers']:
            annotations[name] = props.PointerProperty(type=pointer_type)
    cls = type('BI_' + typename, (LegacyNode, bpy.types.Node), {
        'bl_idname': 'BI_' + typename, 'bl_label': schema['name'],
        'legacy_type': typename, '__annotations__': annotations})
    CLASSES.append(cls)

class LegacyGroup(LegacyNode, bpy.types.NodeCustomGroup):
    bl_idname = 'BI_ShaderNodeGroup'
    bl_label = 'Legacy Group'
    legacy_type = 'ShaderNodeGroup'

    def init(self, context):
        pass

    def update(self):
        # Generic NodeCustomGroup has no built-in declaration callback. Preserve
        # sockets by interface identifier so edits keep existing links/values.
        group = self.node_tree
        for direction, sockets in (('INPUT', self.inputs), ('OUTPUT', self.outputs)):
            wanted = [s for s in group.interface.items_tree
                      if s.item_type == 'SOCKET' and s.in_out == direction] if group else []
            identifiers = {s.identifier for s in wanted}
            for socket in list(sockets):
                if socket.identifier not in identifiers:
                    sockets.remove(socket)
            for index, item in enumerate(wanted):
                socket = next((s for s in sockets if s.identifier == item.identifier), None)
                if socket is None or socket.bl_idname != item.socket_type:
                    if socket is not None:
                        sockets.remove(socket)
                    socket = sockets.new(item.socket_type, item.name, identifier=item.identifier)
                    if hasattr(socket, 'default_value') and hasattr(item, 'default_value'):
                        socket.default_value = item.default_value
                if socket.name != item.name:
                    socket.name = item.name
                current = list(sockets).index(socket)
                if current != index:
                    sockets.move(current, index)

    def draw_buttons(self, context, layout):
        layout.prop(self, 'node_tree')

CLASSES.append(LegacyGroup)

class BI_OT_new_tree(bpy.types.Operator):
    bl_idname = 'material.internal_new_tree'
    bl_label = 'Create Legacy Nodes'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        material = getattr(context, 'material', None) or context.object.active_material
        tree = bpy.data.node_groups.new(material.name + ' Internal', TREE)
        source = tree.nodes.new('BI_ShaderNodeMaterial')
        source.location = (-250, 0)
        source.material = material
        output = tree.nodes.new('BI_ShaderNodeOutput')
        tree.links.new(source.outputs[0], output.inputs[0])
        material.classic_internal.node_tree = tree
        return {'FINISHED'}

CLASSES.append(BI_OT_new_tree)

class BI_OT_texture_slot(bpy.types.Operator):
    bl_idname = 'material.internal_texture_slot'
    bl_label = 'Add Legacy Texture Slot'
    bl_options = {'REGISTER', 'UNDO'}
    remove: props.IntProperty(default=-1)

    def execute(self, context):
        slots = context.material.classic_internal.texture_slots
        if self.remove >= 0:
            slots.remove(self.remove)
        elif len(slots) < 18:
            slots.add()
        else:
            self.report({'ERROR'}, 'Blender Internal supports 18 texture slots')
            return {'CANCELLED'}
        return {'FINISHED'}

CLASSES.append(BI_OT_texture_slot)

class BI_MT_nodes(bpy.types.Menu):
    bl_idname = 'BI_MT_nodes'
    bl_label = 'Blender Internal'

    def draw(self, context):
        for typename, schema in sorted(SCHEMA['nodes'].items(), key=lambda kv: kv[1]['name']):
            op = self.layout.operator('node.add_node', text=schema['name'])
            op.type = 'BI_' + typename
            op.use_transform = True
        for kind, label in (('BI_ShaderNodeGroup', 'Group'), ('NodeGroupInput', 'Group Input'), ('NodeGroupOutput', 'Group Output')):
            op = self.layout.operator('node.add_node', text=label)
            op.type, op.use_transform = kind, True

CLASSES.append(BI_MT_nodes)

def draw_menu(self, context):
    if context.space_data.tree_type == TREE:
        self.layout.menu(BI_MT_nodes.bl_idname)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.append(draw_menu)

def unregister():
    bpy.types.NODE_MT_add.remove(draw_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
