# SPDX-License-Identifier: GPL-2.0-or-later
"""Visible render controls, compatibility, archive overrides and pixel effects."""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sys
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N, full_export as E, render_settings as R, render_ui as U
from blender_internal.legacy_import import Reader
BI.register()
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
p = scene.classic_internal
checks = []

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass
observer = Observer()
reader = Reader.__new__(Reader)
reader.lib = N.load()

def export():
    scene.update_tag()
    bpy.context.view_layer.update()
    return E.export_scene(bpy.context.evaluated_depsgraph_get(), observer)

with N.LOCK:
    # Merely drawing the UI must not migrate existing files.
    for sample in ('1', '2', '3', '4'):
        p.samples = sample
        assert p.render_antialiasing == (sample != '1')
        assert p.render_samples == {'1': '5', '2': '5', '3': '8', '4': '16'}[sample]
        assert not p.use_legacy_settings
    p.samples = '3'
    p.shadows = False
    scene.render.film_transparent = True
    p.render_samples = '11'
    assert p.use_legacy_settings and p.legacy.antialiasing_samples == '11'
    assert p.render_antialiasing and not p.render_shadows and p.render_alpha == 'TRANSPARENT'
    p.render_antialiasing = False
    p.render_shadows = True
    p.render_alpha = 'SKY'
    host = export()
    for name, expected in [('use_antialiasing', False), ('antialiasing_samples', '11'),
                           ('use_shadows', True), ('alpha_mode', 'SKY')]:
        assert reader.value(host.handle, 'render.' + name) == expected
    checks.append('new UI edits preserve all old AA, shadow and alpha settings during promotion')

    # Advanced settings work even in files which never enabled the former switch.
    p.use_legacy_settings = False
    p.legacy.use_raytrace = False
    p.legacy.use_textures = False
    p.legacy.use_sss = False
    p.legacy.use_edge_enhance = True
    p.legacy.edge_threshold = 128
    p.legacy.edge_color = (0.2, 0.3, 0.4)
    p.legacy.pixel_filter_type = 'GAUSSIAN'
    p.legacy.filter_size = 1.7
    p.legacy.threads_mode = 'FIXED'
    p.legacy.threads = 2
    p.legacy.tile_x = 32
    p.legacy.tile_y = 48
    p.legacy.raytrace_method = 'OCTREE'
    p.legacy.octree_resolution = '64'
    scene.render.pixel_aspect_x = 2
    scene.render.pixel_aspect_y = 1
    scene.render.fps = 30
    scene.render.use_simplify = True
    scene.render.simplify_subdivision_render = 2
    scene.render.use_stamp = True
    p.legacy.use_stamp = True
    p.legacy.dither_intensity = 2
    host = export()
    for name in R.NATIVE_SETTINGS:
        expected = getattr(scene.render, name) if name in ('use_simplify', 'simplify_subdivision', 'simplify_subdivision_render') else R.value(p, name)
        actual = reader.value(host.handle, 'render.' + name)
        if isinstance(expected, (str, bool, int)):
            assert actual == expected, (name, actual, expected)
        else:
            assert np.allclose(actual, expected), (name, actual, expected)
    for name, expected in [('pixel_aspect_x', 2), ('fps', 30), ('use_stamp', False),
                           ('use_compositing', False), ('use_sequencer', False), ('dither_intensity', 0)]:
        assert reader.value(host.handle, 'render.' + name) == expected
    checks.append('every native control reaches RNA; host aspect, modifiers and output have correct ownership')

    for name in ('use_motion_blur', 'use_freestyle', 'use_full_sample', 'use_save_buffers', 'use_fields'):
        setattr(p.legacy, name, True)
        try:
            export()
            raise AssertionError('Unsupported feature silently accepted: ' + name)
        except RuntimeError:
            pass
        setattr(p.legacy, name, False)
    checks.append('unsupported imported features report an actionable error instead of silently doing nothing')

    # A colored cube on a different background makes AA/edge/alpha effects measurable.
    scene.render.pixel_aspect_x = 1
    scene.render.use_simplify = False
    p.render_alpha = 'SKY'
    p.render_antialiasing = False
    p.legacy.use_edge_enhance = False
    p.legacy.use_raytrace = True
    p.legacy.use_textures = True
    mat = bpy.data.materials.new('Render settings test')
    mat.classic_internal.shadeless = True
    mat.classic_internal.color = (0.8, 0.25, 0.08)
    obj = bpy.data.objects['Cube']
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    def pixels():
        host = export()
        return host.render(1, 80, 80, observer)[0]
    plain = pixels()
    p.render_antialiasing = True
    p.render_samples = '11'
    aa = pixels()
    assert np.max(np.abs(plain-aa)) > 0.01
    p.legacy.use_edge_enhance = True
    p.legacy.edge_threshold = 255
    p.legacy.edge_color = (0, 0, 0)
    edged = pixels()
    assert np.max(np.abs(edged-aa)) > 0.01
    p.render_alpha = 'TRANSPARENT'
    transparent = pixels()
    assert transparent[:, 3].min() == 0 and aa[:, 3].min() > 0.99
    p.render_fields = True
    assert p.legacy.use_fields_still
    assert np.isfinite(pixels()).all()
    p.legacy.use_fields = False
    checks.append('AA, edge enhancement and transparency change pixels; still-field rendering completes')

    # Loading archive settings is explicit and does not touch the original file.
    archive = ROOT / 'artifacts/full-features/reference.blend'
    p.source = 'ARCHIVE'
    p.archive_path = str(archive)
    reader2 = Reader(str(archive))
    handle = reader2.lib.bi_full_scene_current(b'')
    original_samples = reader2.value(handle, 'render.antialiasing_samples')
    original_aspect = reader2.value(handle, 'render.pixel_aspect_x')
    host = N.Scene()
    host.check(host.lib.bi_full_load(str(archive).encode()))
    host.handle = host.check(host.lib.bi_full_scene_current(b''))
    R.export(host, scene, archive=True)
    assert reader.value(host.handle, 'render.antialiasing_samples') == original_samples
    assert bpy.ops.render.internal_load_settings() == {'FINISHED'}
    assert p.override_archive_render and p.render_samples == original_samples
    p.render_samples = '11'
    p.legacy.use_motion_blur = True
    p.legacy.motion_blur_samples = 2
    host = N.Scene()
    host.check(host.lib.bi_full_load(str(archive).encode()))
    host.handle = host.check(host.lib.bi_full_scene_current(b''))
    R.export(host, scene, archive=True)
    assert reader.value(host.handle, 'render.antialiasing_samples') == '11'
    assert reader.value(host.handle, 'render.pixel_aspect_x') == original_aspect
    assert reader.value(host.handle, 'render.use_motion_blur')
    result = host.render(1, 80, 50, observer)[0]
    assert np.isfinite(result).all()
    checks.append('archive defaults remain authoritative; load/edit overrides and sampled blur reach native rendering')

# Validate every draw branch and enforce UI coverage for the native allowlist.
class Layout:
    active = True
    def __init__(self): self.seen = set()
    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, (type(data).__name__, name)
        self.seen.add(name)
    def operator(self, *args, **kwargs): return SimpleNamespace()
    def __getattr__(self, name): return lambda *args, **kwargs: self
layout = Layout()
context = SimpleNamespace(scene=scene, engine=BI.ENGINE)
panel = SimpleNamespace(layout=layout)
panel.settings = lambda ctx: U.RenderPanel.settings(panel, ctx)
for source in ('MODERN', 'ARCHIVE'):
    p.source = source
    for override in (True, False):
        p.override_archive_render = override
        for method in ('AUTO', 'OCTREE'):
            p.legacy.raytrace_method = method
            for cls in U.CLASSES:
                if issubclass(cls, bpy.types.Panel):
                    if hasattr(cls, 'draw_header'): cls.draw_header(panel, context)
                    cls.draw(panel, context)
            BI.CLASSIC_PT_render.draw(panel, context)
for name in R.NATIVE_SETTINGS:
    alias = {'use_antialiasing': 'render_antialiasing', 'antialiasing_samples': 'render_samples',
             'use_shadows': 'render_shadows', 'alpha_mode': 'render_alpha', 'use_fields': 'render_fields'}.get(name, name)
    assert alias in layout.seen, 'Supported native setting has no UI: ' + name
for name in ('RENDER_PT_time_stretching', 'RENDER_PT_post_processing', 'RENDER_PT_stamp', 'RENDER_PT_stamp_note', 'RENDER_PT_stamp_burn',
             'RENDER_PT_color_management_curves', 'RENDER_PT_color_management_white_balance'):
    assert BI.ENGINE in getattr(bpy.types, name).COMPAT_ENGINES, name
checks.append('all supported native settings exposed; every panel branch resolves valid RNA; host panels enabled')
p.source = 'MODERN'
p.render_samples = '11'
p.render_alpha = 'TRANSPARENT'
path = ROOT / 'artifacts/render-workflow.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
p = bpy.context.scene.classic_internal
assert p.render_samples == '11' and p.render_alpha == 'TRANSPARENT'
BI.unregister()
assert BI.ENGINE not in bpy.types.RENDER_PT_stamp.COMPAT_ENGINES
BI.register()
checks.append('settings survive save/reload and host panel compatibility unregisters cleanly')
(ROOT / 'artifacts/render-workflow.json').write_text(json.dumps(checks, indent=2))
print('RENDER_WORKFLOW_OK', len(checks))
