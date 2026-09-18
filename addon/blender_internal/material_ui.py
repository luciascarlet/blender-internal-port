# SPDX-License-Identifier: GPL-2.0-or-later
"""Material controls shared by new and migrated Blender Internal materials."""
import bpy
from . import legacy_ui as L

ENGINE = 'BLENDER_INTERNAL_PORT'


def draw_props(layout, material, names):
    layout.use_property_split = True
    for name in names:
        L.draw_material_property(layout, material, name)


def draw_diffuse(layout, material):
    draw_props(layout, material, ('diffuse_color', 'diffuse_intensity', 'diffuse_shader'))
    shader = L.material_shader(material)
    extra = {'OREN_NAYAR': ('roughness',), 'TOON': ('diffuse_toon_size', 'diffuse_toon_smooth'),
             'MINNAERT': ('darkness',), 'FRESNEL': ('diffuse_fresnel', 'diffuse_fresnel_factor')}
    draw_props(layout, material, extra.get(shader, ()))


def draw_specular(layout, material):
    draw_props(layout, material, ('specular_color', 'specular_intensity', 'specular_shader'))
    shader = L.material_shader(material, specular=True)
    extra = {'COOKTORR': ('specular_hardness',), 'PHONG': ('specular_hardness',),
             'BLINN': ('specular_hardness', 'specular_ior'),
             'TOON': ('specular_toon_size', 'specular_toon_smooth'), 'WARDISO': ('specular_slope',)}
    draw_props(layout, material, extra.get(shader, ()))


class MaterialPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        return context.engine == ENGINE and getattr(context, 'material', None) is not None

class BI_PT_material_slots(MaterialPanel, bpy.types.Panel):
    bl_label = ''
    bl_options = {'HIDE_HEADER'}
    bl_order = -100

    @classmethod
    def poll(cls, context):
        obj = context.object
        return context.engine == ENGINE and (getattr(context, 'material', None) is not None or (obj is not None and hasattr(obj.data, 'materials')))

    def draw(self, context):
        # Same list and slot operators as Blender's built-in material context
        # panel, with a New action that also copies the external legacy tree.
        layout = self.layout
        obj = context.object
        if obj and hasattr(obj.data, 'materials'):
            row = layout.row()
            sortable = len(obj.material_slots) > 1
            row.template_list('MATERIAL_UL_matslots', '', obj, 'material_slots', obj,
                              'active_material_index', rows=5 if sortable else 3)
            col = row.column(align=True)
            col.operator('object.material_slot_add', icon='ADD', text='')
            col.operator('object.material_slot_remove', icon='REMOVE', text='')
            col.separator()
            col.menu('MATERIAL_MT_context_menu', icon='DOWNARROW_HLT', text='')
            if sortable:
                col.separator()
                col.operator('object.material_slot_move', icon='TRIA_UP', text='').direction = 'UP'
                col.operator('object.material_slot_move', icon='TRIA_DOWN', text='').direction = 'DOWN'
            row = L.draw_material_id(layout, obj)
            if obj.material_slots:
                row.prop(obj.material_slots[obj.active_material_index], 'link', icon_only=True)
            if obj.mode == 'EDIT':
                row = layout.row(align=True)
                row.operator('object.material_slot_assign', text='Assign')
                if obj.type != 'FONT':
                    row.operator('object.material_slot_select', text='Select')
                    row.operator('object.material_slot_deselect', text='Deselect')
        elif context.material:
            layout.template_ID(context.space_data, 'pin_id')


class BI_PT_diffuse(MaterialPanel, bpy.types.Panel):
    bl_order = 0
    bl_label = 'Diffuse'

    def draw(self, context):
        draw_diffuse(self.layout, context.material)


class BI_PT_specular(MaterialPanel, bpy.types.Panel):
    bl_order = 1
    bl_label = 'Specular'

    def draw(self, context):
        draw_specular(self.layout, context.material)


class BI_PT_shading(MaterialPanel, bpy.types.Panel):
    bl_order = 2
    bl_label = 'Shading'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_props(self.layout, context.material, ('emit', 'ambient', 'translucency', 'use_shadeless',
                   'use_vertex_color_paint', 'use_vertex_color_light', 'use_object_color',
                   'use_cubic', 'use_tangent_shading'))


class BI_PT_transparency(MaterialPanel, bpy.types.Panel):
    bl_order = 3
    bl_label = 'Transparency'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(context.material.classic_internal.legacy, 'use_transparency', text='')

    def draw(self, context):
        p = context.material.classic_internal.legacy
        layout = self.layout
        layout.active = p.use_transparency
        draw_props(layout, context.material, ('transparency_method', 'alpha', 'specular_alpha'))
        if p.transparency_method == 'RAYTRACE':
            for prop in L.SCHEMA['nested']['raytrace_transparency']:
                layout.prop(p.raytrace_transparency, prop['id'])


class BI_PT_mirror(MaterialPanel, bpy.types.Panel):
    bl_order = 4
    bl_label = 'Mirror'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(context.material.classic_internal.legacy.raytrace_mirror, 'use', text='')

    def draw(self, context):
        p = context.material.classic_internal.legacy
        self.layout.use_property_split = True
        self.layout.active = p.raytrace_mirror.use
        self.layout.prop(p, 'mirror_color')
        for prop in L.SCHEMA['nested']['raytrace_mirror']:
            if prop['id'] != 'use':
                self.layout.prop(p.raytrace_mirror, prop['id'])


class BI_PT_sss(MaterialPanel, bpy.types.Panel):
    bl_order = 5
    bl_label = 'Subsurface Scattering'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(context.material.classic_internal.legacy.subsurface_scattering, 'use', text='')

    def draw(self, context):
        p = context.material.classic_internal.legacy.subsurface_scattering
        self.layout.use_property_split = True
        self.layout.active = p.use
        for prop in L.SCHEMA['nested']['subsurface_scattering']:
            if prop['id'] != 'use':
                self.layout.prop(p, prop['id'])


# Less frequently changed flags belong in collapsed, named sections, not in a
# second competing material inspector. All of these are exported in both modes.
class BI_PT_options(MaterialPanel, bpy.types.Panel):
    bl_order = 8
    bl_label = 'Options'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_props(self.layout, context.material, (
            'use_raytrace', 'use_full_oversampling', 'use_sky', 'use_mist',
            'invert_z', 'offset_z', 'use_face_texture', 'use_face_texture_alpha', 'use_uv_project'))
        self.layout.prop(context.material, 'pass_index')


class BI_PT_shadows(MaterialPanel, bpy.types.Panel):
    bl_order = 7
    bl_label = 'Shadow'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_props(self.layout, context.material, (
            'use_shadows', 'use_transparent_shadows', 'use_only_shadow', 'shadow_only_type',
            'use_cast_shadows', 'use_cast_shadows_only', 'use_cast_buffer_shadows',
            'use_cast_approximate', 'use_ray_shadow_bias', 'shadow_ray_bias', 'shadow_buffer_bias', 'shadow_cast_alpha'))

class BI_PT_ramps(MaterialPanel, bpy.types.Panel):
    bl_order = 9
    bl_label = 'Diffuse and Specular Ramps'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        material = context.material
        p = material.classic_internal
        if not p.ramp_storage:
            self.layout.operator('material.internal_ramps')
            return
        if p.ramp_storage.users > 1:
            self.layout.operator('material.internal_ramps', text='Make Ramps Single User')
        col = self.layout.column()
        col.active = p.ramp_storage.users == 1
        for kind in ('diffuse', 'specular'):
            col.prop(p.legacy, 'use_' + kind + '_ramp')
            sub = col.column()
            sub.active = getattr(p.legacy, 'use_' + kind + '_ramp')
            node = p.ramp_storage.nodes.get(kind + '_ramp')
            if node:
                sub.template_color_ramp(node, 'color_ramp', expand=True)
            for suffix in ('input', 'blend', 'factor'):
                sub.prop(p.legacy, kind + '_ramp_' + suffix)


CLASSES = [BI_PT_material_slots, BI_PT_diffuse, BI_PT_specular, BI_PT_shading, BI_PT_transparency, BI_PT_mirror,
           BI_PT_sss, BI_PT_options, BI_PT_shadows, BI_PT_ramps]


def nested_panel(name, label, material_type=None):
    def poll(cls, context):
        return MaterialPanel.poll(context) and (material_type is None or context.material.classic_internal.legacy.type == material_type)

    def draw(self, context):
        self.layout.use_property_split = True
        p = getattr(context.material.classic_internal.legacy, name)
        for prop in L.SCHEMA['nested'][name]:
            self.layout.prop(p, prop['id'])

    return type('BI_PT_' + name, (MaterialPanel, bpy.types.Panel), {
        'bl_label': label, 'bl_options': {'DEFAULT_CLOSED'}, 'poll': classmethod(poll), 'draw': draw})


CLASSES.extend((nested_panel('volume', 'Volume', 'VOLUME'), nested_panel('halo', 'Halo', 'HALO'),
                nested_panel('strand', 'Strands')))


def draw_texture(layout, slot, key):
    layout.template_ID(slot, 'texture', new='texture.new')
    texture = slot.texture
    if not texture:
        return
    layout.prop(texture, 'type')
    layout.prop(texture, 'use_nodes', text='Use Texture Nodes')
    if texture.use_nodes:
        layout.operator('material.internal_edit_texture_nodes', icon='NODETREE').index = int(key)
    if texture.type == 'IMAGE':
        layout.template_ID(texture, 'image', new='image.new', open='image.open')
    head, body = layout.panel('internal_texture_settings_' + key, default_closed=True)
    head.label(text='Texture Settings')
    if body:
        body.use_property_split = True
        for prop in L.SCHEMA['textures'].get(texture.type, []):
            if prop['id'] != 'type' and hasattr(texture, prop['id']):
                body.prop(texture, prop['id'])
        if texture.use_color_ramp:
            body.template_color_ramp(texture, 'color_ramp', expand=True)
    mapping = ('texture_coords', 'uv_layer', 'mapping', 'mapping_x', 'mapping_y', 'mapping_z',
               'offset', 'scale', 'use_from_dupli', 'use_map_to_bounds', 'use_from_original')
    for section, label, names in (
        ('mapping', 'Mapping', mapping),
        ('influence', 'Influence', [p['id'] for p in L.SCHEMA['texture_slot'] if p['id'] not in mapping and p['id'] != 'use']),
    ):
        head, body = layout.panel('internal_texture_' + key + '_' + section, default_closed=True)
        head.label(text=label)
        if body:
            body.use_property_split = True
            for name in names:
                body.prop(slot.settings, name)
