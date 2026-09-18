# SPDX-License-Identifier: GPL-2.0-or-later
"""Ownership and compatibility for renderer settings shown in Properties."""
from bpy.props import BoolProperty, EnumProperty

# Only settings consumed by the embedded renderer. Output, color management,
# metadata, the compositor and evaluated modifiers belong to the modern host.
NATIVE_SETTINGS = (
    'use_antialiasing', 'antialiasing_samples', 'pixel_filter_type', 'filter_size',
    'use_shadows', 'use_envmaps', 'use_sss', 'use_world_space_shading',
    'use_raytrace', 'use_textures', 'alpha_mode',
    'raytrace_method', 'octree_resolution', 'use_instances', 'use_local_coords',
    'use_edge_enhance', 'edge_threshold', 'edge_color',
    'threads_mode', 'threads', 'tile_x', 'tile_y',
    'use_motion_blur', 'motion_blur_samples', 'motion_blur_shutter',
    'use_fields', 'field_order', 'use_fields_still',
    'use_simplify', 'simplify_subdivision', 'simplify_subdivision_render',
    'simplify_child_particles', 'simplify_shadow_samples', 'simplify_ao_sss',
    'use_simplify_triangulate',
)
UNAVAILABLE = {'use_freestyle': 'Freestyle', 'use_full_sample': 'Full Sample',
               'use_save_buffers': 'Save Buffers'}
AA_SAMPLES = ('5', '8', '11', '16')
ALPHA_MODES = ('SKY', 'TRANSPARENT')


def value(settings, name):
    if not settings.use_legacy_settings:
        if name == 'use_antialiasing':
            return settings.samples != '1'
        if name == 'antialiasing_samples':
            return {'1': '5', '2': '5', '3': '8', '4': '16'}[settings.samples]
        if name == 'use_shadows':
            return settings.shadows
        if name == 'alpha_mode':
            return 'TRANSPARENT' if settings.id_data.render.film_transparent else 'SKY'
    return getattr(settings.legacy, name)


def set_value(settings, name, new_value):
    # Promote all early-adapter aliases together so changing AA does not reset
    # transparency or shadows in an existing file. Reading/drawing never mutates.
    if not settings.use_legacy_settings:
        for field in ('use_antialiasing', 'antialiasing_samples', 'use_shadows', 'alpha_mode'):
            setattr(settings.legacy, field, value(settings, field))
        settings.use_legacy_settings = True
    setattr(settings.legacy, name, new_value)
    if name == 'use_fields' and new_value and settings.source == 'MODERN':
        settings.legacy.use_fields_still = True


def bool_proxy(name, label):
    return BoolProperty(name=label, get=lambda self: value(self, name),
                        set=lambda self, v: set_value(self, name, v))


def enum_proxy(name, label, items):
    keys = tuple(i[0] for i in items)
    return EnumProperty(name=label, items=items,
                        get=lambda self: keys.index(value(self, name)),
                        set=lambda self, v: set_value(self, name, keys[v]))


PROPERTIES = {
    'render_fields': bool_proxy('use_fields', 'Fields'),
    'render_antialiasing': bool_proxy('use_antialiasing', 'Anti-Aliasing'),
    'render_samples': enum_proxy('antialiasing_samples', 'Samples', [(n, n, '') for n in AA_SAMPLES]),
    'render_shadows': bool_proxy('use_shadows', 'Shadows'),
    'render_alpha': enum_proxy('alpha_mode', 'Alpha', [
        ('SKY', 'Sky', 'Render the world background'),
        ('TRANSPARENT', 'Transparent', 'Transparent background; save an RGBA image to retain alpha')]),
}


def export(host, scene, archive=False, preview=False):
    p = scene.classic_internal
    if not archive or p.override_archive_render:
        for name in NATIVE_SETTINGS:
            host.set(host.handle, 'render.' + name, value(p, name))
        if not archive:
            for name in ('pixel_aspect_x', 'pixel_aspect_y', 'fps', 'fps_base',
                         'use_simplify', 'simplify_subdivision', 'simplify_subdivision_render'):
                host.set(host.handle, 'render.' + name, getattr(scene.render, name))
            # Geometry is already evaluated at the host's remapped time.
            host.set(host.handle, 'render.frame_map_old', 100)
            host.set(host.handle, 'render.frame_map_new', 100)
            if not preview and p.legacy.use_motion_blur:
                raise RuntimeError('Sampled motion blur requires Original Legacy File mode; current-scene temporal geometry export is not implemented')
            if not preview and p.legacy.use_fields and not p.legacy.use_fields_still:
                raise RuntimeError('Animated fields require Original Legacy File mode; enable Still Fields for the current scene')
        for name, label in UNAVAILABLE.items():
            if not preview and getattr(p.legacy, name):
                raise RuntimeError(label + ' is unavailable in this native build')
        # An explicit override can turn off unsupported flags stored in a file.
        for name in UNAVAILABLE:
            host.set(host.handle, 'render.' + name, False)
    elif not preview:
        from .legacy_import import Reader
        reader = Reader.__new__(Reader)
        reader.lib = host.lib
        for name, label in UNAVAILABLE.items():
            if reader.value(host.handle, 'render.' + name):
                raise RuntimeError(label + ' is unavailable; load the file render settings and disable it')
    # Never run the host's output pipeline a second time inside the library.
    for name in ('use_compositing', 'use_sequencer', 'use_stamp'):
        host.set(host.handle, 'render.' + name, False)
    host.set(host.handle, 'render.dither_intensity', 0)
