# SPDX-License-Identifier: GPL-2.0-or-later
"""Legacy material RNA controls and native-executed legacy shader nodes."""
import json
from pathlib import Path
import bpy
from bpy import props

SCHEMA = json.loads((Path(__file__).parent / 'legacy_schema.json').read_text())
TREE = 'BlenderInternalNodeTree'
CLASSES = []

# These aliases keep files made by the initial adapter editable without changing
# their appearance. The UI never asks users to choose between two sets of colors.
MATERIAL_ALIASES = {
    'diffuse_color': 'color', 'specular_hardness': 'hardness',
    'specular_ior': 'ior', 'specular_slope': 'slope', 'emit': 'emission',
    'use_shadeless': 'shadeless', 'diffuse_toon_size': 'diffuse_size',
    'diffuse_toon_smooth': 'diffuse_smooth', 'diffuse_fresnel_factor': 'diffuse_size',
    'diffuse_fresnel': 'diffuse_smooth', 'specular_toon_size': 'specular_size',
    'specular_toon_smooth': 'specular_smooth',
}
SIMPLE_MATERIAL = set(MATERIAL_ALIASES) | {
    'specular_color', 'diffuse_shader', 'specular_shader', 'diffuse_intensity',
    'specular_intensity', 'roughness', 'darkness',
}

def context_material(context):
    space = context.space_data
    obj = context.object
    if space and space.type == 'NODE_EDITOR':
        if space.tree_type == TREE and space.pin:
            return space.id if isinstance(space.id, bpy.types.Material) else None
        # context.material in a Node Editor is derived from its *previous* ID.
        # Reading it here feeds that stale ID back into get_from_context and can
        # prevent the editor from ever following a new object or an empty slot.
        return obj.active_material if obj and hasattr(obj.data, 'materials') else None
    material = getattr(context, 'material', None)
    return material or (obj.active_material if obj and hasattr(obj.data, 'materials') else None)

def material_property(material, name):
    p = material.classic_internal
    if not p.use_legacy_settings and name in SIMPLE_MATERIAL:
        return p, MATERIAL_ALIASES.get(name, name)
    return p.legacy, name

def draw_material_property(layout, material, name, **kwargs):
    owner, prop = material_property(material, name)
    if 'text' not in kwargs:
        kwargs['text'] = next(p['name'] for p in SCHEMA['material'] if p['id'] == name)
    layout.prop(owner, prop, **kwargs)

def material_shader(material, specular=False):
    p = material.classic_internal
    name = 'specular_shader' if specular else 'diffuse_shader'
    value = getattr(p.legacy if p.use_legacy_settings else p, name)
    choices = ('COOKTORR', 'PHONG', 'BLINN', 'TOON', 'WARDISO') if specular else ('LAMBERT', 'OREN_NAYAR', 'TOON', 'MINNAERT', 'FRESNEL')
    return value if p.use_legacy_settings else choices[int(value)]

def draw_material_id(layout, obj):
    # Keep Blender's datablock browser and rename controls, but route both copy
    # buttons through our deep-copy action. The generic user-count button copies
    # only the material ID and would keep its external tree shading the old ID.
    row = layout.row(align=True)
    row.template_search(obj, 'active_material', bpy.data, 'materials')
    material = obj.active_material
    if material:
        tree = material.classic_internal.node_tree
        self_references = sum(getattr(n, 'material', None) == material for n in tree.nodes) if tree else 0
        users = material.users - self_references - int(material.use_fake_user)
        if users > 1:
            row.operator('material.internal_new_material', text=str(users))
        row.prop(material, 'use_fake_user', text='')
        row.operator('material.internal_new_material', text='', icon='DUPLICATE')
        row.operator('material.internal_unlink', text='', icon='X')
    else:
        row.operator('material.internal_new_material', text='New', icon='ADD')
    return row

def notify_edit(self, context):
    owner = getattr(self, 'id_data', None)
    if owner is not None:
        owner.update_tag()
    from . import viewport
    viewport.tag_update()


def add_update_callbacks(cls):
    # Operator properties are also assigned while drawing buttons (for example
    # the slot index on Remove/Edit Nodes). Treating those UI-only assignments
    # as material edits cancels the preview on every redraw indefinitely.
    if not issubclass(cls, (bpy.types.PropertyGroup, bpy.types.Node)):
        return
    for prop in cls.__dict__.get('__annotations__', {}).values():
        if hasattr(prop, 'keywords') and prop.function.__name__ != 'CollectionProperty':
            prop.keywords.setdefault('update', notify_edit)


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
    def update(self):
        from . import viewport
        viewport.tag_update()

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
        material = context_material(context)
        if material:
            return material.classic_internal.node_tree, material, obj
        return None, None, obj

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
                # Original Material nodes use the referenced material unless a
                # socket is linked. Editable defaults here misleadingly do nothing.
                if direction == 'inputs' and self.legacy_type in ('ShaderNodeMaterial', 'ShaderNodeMaterialExtended'):
                    socket.hide_value = True
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
                if name == 'material':
                    layout.template_ID(self, name, new='material.new')
                    if self.material:
                        draw_material_property(layout, self.material, 'diffuse_color', text='Color')
                        draw_material_property(layout, self.material, 'specular_color', text='Specular')
                        draw_material_property(layout, self.material, 'diffuse_intensity', text='Intensity')
                elif name == 'texture':
                    layout.template_ID(self, name, new='texture.new')
                else:
                    layout.prop(self, name)
        if self.legacy_type in ('ShaderNodeRGB', 'ShaderNodeValue'):
            layout.prop(self.outputs[0], 'default_value', text='')
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
        layout.context_pointer_set('internal_group_node', self)
        layout.template_ID(self, 'node_tree', new='node.internal_new_group')
        if self.node_tree:
            layout.operator('node.internal_group_edit', text='Edit Group', icon='NODETREE')

CLASSES.append(LegacyGroup)

def context_group_node(context):
    return getattr(context, 'internal_group_node', None) or getattr(context, 'active_node', None)

class BI_OT_new_group(bpy.types.Operator):
    bl_idname = 'node.internal_new_group'
    bl_label = 'New Internal Group'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        node = context_group_node(context)
        return node is not None and node.bl_idname == 'BI_ShaderNodeGroup'

    def execute(self, context):
        node = context_group_node(context)
        if node.node_tree:
            node.node_tree = node.node_tree.copy()
        else:
            tree = bpy.data.node_groups.new('Internal Group', TREE)
            tree.interface.new_socket(name='Color', in_out='INPUT', socket_type='NodeSocketColor')
            tree.interface.new_socket(name='Color', in_out='OUTPUT', socket_type='NodeSocketColor')
            source = tree.nodes.new('NodeGroupInput')
            source.location = (-250, 0)
            output = tree.nodes.new('NodeGroupOutput')
            tree.links.new(source.outputs[0], output.inputs[0])
            node.node_tree = tree
        return {'FINISHED'}

CLASSES.append(BI_OT_new_group)

class BI_OT_group_edit(bpy.types.Operator):
    bl_idname = 'node.internal_group_edit'
    bl_label = 'Edit Internal Group'
    bl_description = 'Enter the active Internal group, or return to its parent'

    @classmethod
    def poll(cls, context):
        space = context.space_data
        node = context_group_node(context)
        return bool(space and space.type == 'NODE_EDITOR' and space.tree_type == TREE and
                    ((node and node.bl_idname == 'BI_ShaderNodeGroup' and node.node_tree) or len(space.path) > 1))

    def execute(self, context):
        space = context.space_data
        node = context_group_node(context)
        if node and node.bl_idname == 'BI_ShaderNodeGroup' and node.node_tree:
            if any(p.node_tree == node.node_tree for p in space.path):
                self.report({'ERROR'}, 'A group cannot contain itself')
                return {'CANCELLED'}
            space.path.append(node.node_tree, node=node)
        elif len(space.path) > 1:
            space.path.pop()
        frame_tree(context, space.edit_tree, start=False)
        context.area.tag_redraw()
        return {'FINISHED'}

CLASSES.append(BI_OT_group_edit)

class BI_OT_new_material(bpy.types.Operator):
    bl_idname = 'material.internal_new_material'
    bl_label = 'New Material'
    bl_description = 'Create a material, or an independent copy of the current material and its Internal graph'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and hasattr(obj.data, 'materials') and obj.is_editable

    def execute(self, context):
        obj = context.object
        source = obj.active_material
        material = source.copy() if source else bpy.data.materials.new('Material')
        p = material.classic_internal
        if source and p.node_tree:
            p.node_tree = p.node_tree.copy()
            for node in p.node_tree.nodes:
                if getattr(node, 'material', None) == source:
                    node.material = material
        if p.ramp_storage:
            p.ramp_storage = p.ramp_storage.copy()
        if not obj.material_slots:
            bpy.ops.object.material_slot_add()
        obj.active_material = material
        return {'FINISHED'}

CLASSES.append(BI_OT_new_material)

class BI_OT_unlink_material(bpy.types.Operator):
    bl_idname = 'material.internal_unlink'
    bl_label = 'Unlink Material'
    bl_description = 'Clear this material slot without deleting its material'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return BI_OT_new_material.poll(context) and context.object.active_material is not None

    def execute(self, context):
        context.object.active_material = None
        return {'FINISHED'}

CLASSES.append(BI_OT_unlink_material)

class BI_OT_new_tree(bpy.types.Operator):
    bl_idname = 'material.internal_new_tree'
    bl_label = 'Create Legacy Nodes'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        space = context.space_data
        if space and space.type == 'NODE_EDITOR' and space.pin:
            return False
        return context_material(context) is not None or (obj is not None and hasattr(obj.data, 'materials'))

    def execute(self, context):
        material = context_material(context)
        if material is None:
            bpy.ops.material.internal_new_material()
            material = context.object.active_material
        material.classic_internal.use_nodes = True
        if material.classic_internal.node_tree:
            material.classic_internal.node_tree = material.classic_internal.node_tree.copy()
            frame_tree(context, material.classic_internal.node_tree)
            return {'FINISHED'}
        tree = bpy.data.node_groups.new(material.name + ' Internal', TREE)
        source = tree.nodes.new('BI_ShaderNodeMaterial')
        source.location = (-320, 100)
        source.width = 240
        source.material = material
        output = tree.nodes.new('BI_ShaderNodeOutput')
        output.location = (0, 100)
        tree.links.new(source.outputs[0], output.inputs[0])
        material.classic_internal.node_tree = tree
        frame_tree(context, tree)
        for area in context.screen.areas if context.screen else []:
            area.tag_redraw()
        return {'FINISHED'}

CLASSES.append(BI_OT_new_tree)

def frame_tree(context, tree, start=True):
    area = context.area
    if area and area.type == 'NODE_EDITOR' and area.spaces.active.tree_type == tree.bl_idname:
        if start:
            area.spaces.active.path.start(tree)
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        if region:
            with context.temp_override(region=region):
                if bpy.ops.node.view_all.poll():
                    bpy.ops.node.view_all()
        # New nodes do not have draw bounds until their first redraw. Framing
        # synchronously can leave the entire graph outside the visible canvas.
        if not bpy.app.background:
            window = context.window
            def after_draw():
                try:
                    if area not in list(window.screen.areas) or area.type != 'NODE_EDITOR':
                        return
                    if area.spaces.active.edit_tree != tree:
                        return
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    if region:
                        with bpy.context.temp_override(window=window, area=area, region=region):
                            if bpy.ops.node.view_all.poll():
                                bpy.ops.node.view_all()
                except ReferenceError:
                    pass  # The editor or material was closed before the redraw.
            bpy.app.timers.register(after_draw, first_interval=0.1)

def node_editor_area(context):
    areas = list(context.screen.areas)
    area = next((a for a in areas if a.type == 'NODE_EDITOR'), None)
    if area is None:
        candidates = [a for a in areas if a.type == 'VIEW_3D']
        if candidates:
            area = max(candidates, key=lambda a: a.width * a.height)
    return area

class BI_OT_edit_nodes(bpy.types.Operator):
    bl_idname = 'material.internal_edit_nodes'
    bl_label = 'Edit Internal Nodes'
    bl_description = 'Open this material in the Blender Internal node editor'

    @classmethod
    def poll(cls, context):
        return context.screen is not None and context_material(context) is not None

    def execute(self, context):
        material = context_material(context)
        area = node_editor_area(context)
        if area is None:
            self.report({'WARNING'}, 'Change an editor to Blender Internal Nodes using its editor-type menu')
            return {'CANCELLED'}
        area.type = 'NODE_EDITOR'
        area.ui_type = TREE
        area.spaces.active.pin = False
        area.spaces.active.node_tree = material.classic_internal.node_tree
        if material.classic_internal.node_tree:
            with context.temp_override(area=area):
                frame_tree(context, material.classic_internal.node_tree)
        area.tag_redraw()
        return {'FINISHED'}

CLASSES.append(BI_OT_edit_nodes)

class BI_OT_edit_texture_nodes(bpy.types.Operator):
    bl_idname = 'material.internal_edit_texture_nodes'
    bl_label = 'Edit Texture Nodes'
    bl_description = 'Open this texture graph in a pinned Texture Node Editor'
    index: props.IntProperty(min=0)

    @classmethod
    def poll(cls, context):
        return context.screen is not None and context_material(context) is not None

    def execute(self, context):
        slots = context_material(context).classic_internal.texture_slots
        if self.index >= len(slots) or not slots[self.index].texture:
            return {'CANCELLED'}
        texture = slots[self.index].texture
        area = node_editor_area(context)
        if area is None:
            return {'CANCELLED'}
        texture.use_nodes = True
        area.type = 'NODE_EDITOR'
        area.ui_type = 'TextureNodeTree'
        area.spaces.active.pin = True
        area.spaces.active.node_tree = texture.node_tree
        with context.temp_override(area=area):
            frame_tree(context, texture.node_tree)
        area.tag_redraw()
        return {'FINISHED'}

CLASSES.append(BI_OT_edit_texture_nodes)

def material_ramp_storage(material):
    p = material.classic_internal
    # Copies of a material initially share PointerProperty IDs. Detach storage
    # before an explicit ramp edit, just like making a node group single-user.
    if p.ramp_storage is None:
        p.ramp_storage = bpy.data.node_groups.new('.Internal Material Ramps', 'ShaderNodeTree')
        for name in ('diffuse_ramp', 'specular_ramp'):
            node = p.ramp_storage.nodes.new('ShaderNodeValToRGB')
            node.name = name
    elif p.ramp_storage.users > 1:
        p.ramp_storage = p.ramp_storage.copy()
    return p.ramp_storage

class BI_OT_material_ramps(bpy.types.Operator):
    bl_idname = 'material.internal_ramps'
    bl_label = 'Create Material Ramps'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context_material(context) is not None

    def execute(self, context):
        material_ramp_storage(context_material(context))
        return {'FINISHED'}

CLASSES.append(BI_OT_material_ramps)

class BI_OT_texture_slot(bpy.types.Operator):
    bl_idname = 'material.internal_texture_slot'
    bl_label = 'Add Legacy Texture Slot'
    bl_options = {'REGISTER', 'UNDO'}
    remove: props.IntProperty(default=-1)

    @classmethod
    def poll(cls, context):
        return context_material(context) is not None

    def execute(self, context):
        material = context_material(context)
        slots = material.classic_internal.texture_slots
        if self.remove >= 0:
            if self.remove >= len(slots):
                return {'CANCELLED'}
            slots.remove(self.remove)
        elif len(slots) < 18:
            slots.add()
        else:
            self.report({'ERROR'}, 'Blender Internal supports 18 texture slots')
            return {'CANCELLED'}
        notify_edit(material, context)
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

_original_header = None
_keymaps = []

def draw_header(self, context):
    space = context.space_data
    if space.tree_type == 'TextureNodeTree' and space.pin and context.engine == 'BLENDER_INTERNAL_PORT':
        texture = next((t for t in bpy.data.textures if t.node_tree == space.node_tree), None)
        if texture:
            from bl_ui.space_node import NODE_MT_editor_menus
            layout = self.layout
            layout.template_header()
            NODE_MT_editor_menus.draw_collapsible(context, layout)
            layout.separator_spacer()
            layout.prop(texture, 'name', text='', icon='TEXTURE')
            layout.prop(texture, 'use_nodes')
            layout.prop(space, 'pin', text='', emboss=False)
            if len(space.path) > 1:
                op = layout.operator('node.tree_path_parent', text='', icon='FILE_PARENT')
                op.parent_tree_index = len(space.path) - 2
            layout.separator_spacer()
            return
    if space.tree_type != TREE:
        return _original_header(self, context)
    from bl_ui.space_node import NODE_MT_editor_menus
    layout = self.layout
    layout.template_header()
    NODE_MT_editor_menus.draw_collapsible(context, layout)
    layout.separator_spacer()
    obj = context.object
    if space.pin:
        # A pinned editor is an independent tree browser, like Blender's other
        # node editors. Selecting a tree here must not change an object's material.
        layout.template_ID(space, 'node_tree')
    elif obj and hasattr(obj.data, 'materials'):
        layout.popover(panel='NODE_PT_material_slots', text='Slot')
        # The custom tree is an external ID, unlike Blender's embedded shader
        # tree. Our New action copies it and retargets self-material nodes too.
        draw_material_id(layout, obj)
        material = obj.active_material
        if material:
            layout.template_ID(material.classic_internal, 'node_tree', new='material.internal_new_tree')
            if material.classic_internal.node_tree:
                layout.prop(material.classic_internal, 'use_nodes')
        else:
            layout.operator('material.internal_new_tree', text='New Material Nodes')
    else:
        layout.label(text='Select an object with materials', icon='INFO')
    layout.prop(space, 'pin', text='', emboss=False)
    layout.separator_spacer()
    if len(space.path) > 1:
        op = layout.operator('node.tree_path_parent', text='', icon='FILE_PARENT')
        op.parent_tree_index = len(space.path) - 2
    layout.prop(space, 'show_region_ui', text='', icon='MENU_PANEL')

class BI_PT_node_material(bpy.types.Panel):
    bl_label = 'Material'
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Material'

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == TREE

    def draw(self, context):
        material = context_material(context)
        node = context.active_node
        if node and getattr(node, 'material', None):
            material = node.material
        if material:
            self.layout.label(text=material.name, icon='MATERIAL')
            for name in ('diffuse_color', 'diffuse_shader', 'diffuse_intensity', 'specular_color', 'specular_shader', 'specular_intensity', 'emit', 'use_shadeless'):
                draw_material_property(self.layout, material, name)
        else:
            self.layout.label(text='Select a Material node or an object')

CLASSES.append(BI_PT_node_material)

def register():
    global _original_header
    for cls in CLASSES:
        add_update_callbacks(cls)
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.append(draw_menu)
    # Replace only the built-in header callback. Preserve callbacks installed by
    # other add-ons and restore the original when disabling this add-on.
    callbacks = bpy.types.NODE_HT_header._dyn_ui_initialize()
    _original_header = callbacks[0]
    callbacks[0] = draw_header
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig:
        keymap = keyconfig.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
        item = keymap.keymap_items.new('node.internal_group_edit', 'TAB', 'PRESS', head=True)
        _keymaps.append((keymap, item))

def unregister():
    for keymap, item in _keymaps:
        keymap.keymap_items.remove(item)
    _keymaps.clear()
    callbacks = bpy.types.NODE_HT_header._dyn_ui_initialize()
    if draw_header in callbacks:
        callbacks[callbacks.index(draw_header)] = _original_header
    bpy.types.NODE_MT_add.remove(draw_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
