# SPDX-License-Identifier: GPL-2.0-or-later
"""Blender Internal render controls; host-owned output panels remain native."""
import bpy
from . import render_settings as R

ENGINE = 'BLENDER_INTERNAL_PORT'


class RenderPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        p = context.scene.classic_internal
        return context.engine == ENGINE and p.backend == 'FULL'

    def settings(self, context):
        p = context.scene.classic_internal
        self.layout.use_property_split = True
        self.layout.use_property_decorate = False
        self.layout.active = p.source != 'ARCHIVE' or p.override_archive_render
        return p, p.legacy


class BI_OT_load_render_settings(bpy.types.Operator):
    bl_idname = 'render.internal_load_settings'
    bl_label = 'Load File Render Settings'
    bl_description = 'Copy render settings from the selected legacy file and enable editable overrides; the file is unchanged'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        p = context.scene.classic_internal
        return context.engine == ENGINE and p.backend == 'FULL' and p.source == 'ARCHIVE' and bool(p.archive_path)

    def execute(self, context):
        from . import full_native as N
        from .legacy_import import Reader
        p = context.scene.classic_internal
        try:
            with N.LOCK:
                reader = Reader(bpy.path.abspath(p.archive_path))
                handle = reader.lib.bi_full_scene_current(p.archive_scene.encode())
                if not handle:
                    raise RuntimeError(reader.lib.bi_full_error().decode())
                values = {name: reader.value(handle, 'render.' + name) for name in (*R.NATIVE_SETTINGS, *R.UNAVAILABLE)}
            for name, v in values.items():
                setattr(p.legacy, name, v)
            p.use_legacy_settings = True
            p.override_archive_render = True
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


class BI_PT_antialiasing(RenderPanel, bpy.types.Panel):
    bl_label = 'Anti-Aliasing'
    bl_options = set()
    bl_order = 1

    def draw_header(self, context):
        p, r = self.settings(context)
        self.layout.prop(p, 'render_antialiasing', text='')

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.active = self.layout.active and p.render_antialiasing
        self.layout.row().prop(p, 'render_samples', expand=True)
        self.layout.prop(r, 'pixel_filter_type', text='Pixel Filter')
        sub = self.layout.column()
        sub.active = r.pixel_filter_type != 'BOX'
        sub.prop(r, 'filter_size', text='Width')


class BI_PT_render_shading(RenderPanel, bpy.types.Panel):
    bl_label = 'Shading'
    bl_order = 2
    bl_options = set()

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.prop(p, 'render_shadows')
        for name, label in (('use_textures', 'Textures'), ('use_sss', 'Subsurface Scattering'),
                            ('use_envmaps', 'Environment Maps'), ('use_raytrace', 'Ray Tracing'),
                            ('use_world_space_shading', 'World Space Shading')):
            self.layout.prop(r, name, text=label)
        self.layout.prop(p, 'render_alpha')


class BI_PT_ray_acceleration(RenderPanel, bpy.types.Panel):
    bl_label = 'Ray Tracing'
    bl_order = 3

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.active = self.layout.active and r.use_raytrace
        self.layout.prop(r, 'raytrace_method', text='Acceleration Structure')
        if r.raytrace_method == 'OCTREE':
            self.layout.prop(r, 'octree_resolution', text='Resolution')
        else:
            self.layout.prop(r, 'use_instances', text='Instances')
        self.layout.prop(r, 'use_local_coords', text='Local Coordinates')


class BI_PT_render_performance(RenderPanel, bpy.types.Panel):
    bl_label = 'Performance'
    bl_order = 4

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.row().prop(r, 'threads_mode', expand=True)
        sub = self.layout.column()
        sub.active = r.threads_mode == 'FIXED'
        sub.prop(r, 'threads')
        self.layout.prop(r, 'tile_x', text='Tile Width')
        self.layout.prop(r, 'tile_y', text='Height')


class BI_PT_edges(RenderPanel, bpy.types.Panel):
    bl_label = 'Edge Enhancement'
    bl_order = 5

    def draw_header(self, context):
        p, r = self.settings(context)
        self.layout.prop(r, 'use_edge_enhance', text='')

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.active = self.layout.active and r.use_edge_enhance
        self.layout.prop(r, 'edge_threshold', text='Threshold')
        self.layout.prop(r, 'edge_color', text='Color')


class BI_PT_fields(RenderPanel, bpy.types.Panel):
    bl_label = 'Fields'
    bl_order = 6

    def draw_header(self, context):
        p, r = self.settings(context)
        self.layout.prop(p, 'render_fields', text='')

    def draw(self, context):
        p, r = self.settings(context)
        self.layout.active = self.layout.active and r.use_fields
        self.layout.row().prop(r, 'field_order', expand=True)
        sub = self.layout.column()
        sub.active = p.source == 'ARCHIVE'
        sub.prop(r, 'use_fields_still', text='Still Fields')
        if p.source == 'MODERN':
            self.layout.label(text='Still fields for current-scene geometry', icon='INFO')


class BI_PT_sampled_motion_blur(RenderPanel, bpy.types.Panel):
    bl_label = 'Sampled Motion Blur'
    bl_order = 7

    def draw_header(self, context):
        p, r = self.settings(context)
        self.layout.active = self.layout.active and p.source == 'ARCHIVE'
        self.layout.prop(r, 'use_motion_blur', text='')

    def draw(self, context):
        p, r = self.settings(context)
        if p.source == 'MODERN':
            self.layout.label(text='Requires Original Legacy File mode', icon='INFO')
            if r.use_motion_blur:
                self.layout.prop(r, 'use_motion_blur', text='Motion Blur (disable to render)')
            return
        self.layout.active = self.layout.active and r.use_motion_blur
        self.layout.prop(r, 'motion_blur_samples', text='Samples')
        self.layout.prop(r, 'motion_blur_shutter', text='Shutter')


class BI_PT_render_simplify(RenderPanel, bpy.types.Panel):
    bl_label = 'Simplify'
    bl_order = 8

    def draw_header(self, context):
        p, r = self.settings(context)
        self.layout.prop(r if p.source == 'ARCHIVE' else context.scene.render, 'use_simplify', text='')

    def draw(self, context):
        p, r = self.settings(context)
        owner = r if p.source == 'ARCHIVE' else context.scene.render
        self.layout.active = self.layout.active and owner.use_simplify
        self.layout.prop(owner, 'simplify_subdivision', text='Viewport Subdivision')
        self.layout.prop(owner, 'simplify_subdivision_render', text='Render Subdivision')
        self.layout.prop(r, 'simplify_shadow_samples', text='Shadow Samples')
        self.layout.prop(r, 'simplify_ao_sss', text='AO and SSS Quality')
        if p.source == 'ARCHIVE':
            self.layout.prop(r, 'simplify_child_particles', text='Child Particles')
            self.layout.prop(r, 'use_simplify_triangulate', text='Skip Quad to Tri Conversion')


class BI_PT_viewport(RenderPanel, bpy.types.Panel):
    bl_label = 'Viewport Preview'
    bl_order = 9

    def draw(self, context):
        self.layout.use_property_split = True
        p = context.scene.classic_internal
        self.layout.prop(p, 'viewport_pause')
        self.layout.prop(p, 'viewport_resolution')
        self.layout.prop(p.legacy, 'preview_start_resolution', text='Start Resolution')
        self.layout.label(text='Use Rendered viewport shading (Z, R).')
        if p.source == 'ARCHIVE':
            self.layout.label(text='Import the file and use Current Scene.', icon='INFO')


class BI_PT_render_support(RenderPanel, bpy.types.Panel):
    bl_label = 'Integration Status'
    bl_order = 100

    def draw(self, context):
        self.layout.label(text='Output, metadata and compositing:', icon='INFO')
        self.layout.label(text='Use Blender\'s Output Properties.')
        self.layout.label(text='Freestyle, baking, Full Sample and')
        self.layout.label(text='Save Buffers are not implemented.')
        p = context.scene.classic_internal
        for name in ('use_freestyle', 'use_full_sample', 'use_save_buffers'):
            if getattr(p.legacy, name):
                self.layout.prop(p.legacy, name)
        self.layout.label(text='Material thumbnails are not implemented.')


CLASSES = (BI_OT_load_render_settings, BI_PT_antialiasing, BI_PT_render_shading,
           BI_PT_ray_acceleration, BI_PT_render_performance, BI_PT_edges, BI_PT_fields,
           BI_PT_sampled_motion_blur, BI_PT_render_simplify, BI_PT_viewport, BI_PT_render_support)
