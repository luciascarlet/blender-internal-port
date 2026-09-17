# SPDX-License-Identifier: GPL-2.0-or-later
"""Modern host regression: passes, border/crop, stale handles and cancellation."""
from pathlib import Path
import sys
import os
import json
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N, full_export as E
from blender_internal.passes import PASSES
BI.register()
scene = BI.legacy_import.import_file(str(ROOT / 'artifacts/full-features/reference.blend'))[0]
bpy.context.window.scene = scene
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
for key in PASSES:
    setattr(bpy.context.view_layer.classic_internal, 'use_pass_' + key, True)

class Observer:
    cancelled = False
    def test_break(self): return self.cancelled
    def update_progress(self, value): pass

checks = {}
engine = Observer()
with N.LOCK:
    host = E.export_scene(bpy.context.evaluated_depsgraph_get(), engine)
    host.render(1, 240, 150, engine)
    for key, (name, channels) in PASSES.items():
        data = host.render_pass(name)
        assert data.shape == (240*150, len(channels)), (name, data.shape)
        assert np.isfinite(data).all(), name
        if name in ('Depth', 'Normal', 'Diffuse', 'Spec', 'Reflect', 'Refract'):
            assert np.count_nonzero(data) > 0, name
        checks[name] = {'shape': list(data.shape), 'nonzero': int(np.count_nonzero(data))}
    expired = host.handle
    other = N.Scene()
    try:
        other.set(expired, 'render.resolution_x', 42)
        raise AssertionError('Expired handle accepted')
    except RuntimeError:
        pass
    checks['expired_handle'] = True
    host = E.export_scene(bpy.context.evaluated_depsgraph_get(), engine)
    engine.cancelled = True
    try:
        host.render(1, 240, 150, engine)
        raise AssertionError('Cancellation ignored')
    except RuntimeError as error:
        assert 'cancel' in str(error).lower(), str(error)
    engine.cancelled = False
    host.render(1, 240, 150, engine)
    checks['cancel_then_render'] = True

# Real RenderEngine integration exercises registration and assignment of passes.
if hasattr(scene.render.image_settings, 'media_type'):
    scene.render.image_settings.media_type = 'MULTI_LAYER_IMAGE'
else:
    scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
scene.render.image_settings.color_depth = '32'
scene.render.filepath = str(ROOT / 'artifacts/full-passes.exr')
bpy.ops.render.render(write_still=True)
assert (ROOT / 'artifacts/full-passes.exr').stat().st_size > 10000
checks['host_multilayer_exr'] = True
reference = np.fromfile(str(ROOT / 'artifacts/full-features/reference.rgba'), np.float32).reshape((300, 480, 4))
scene.render.use_border = True
scene.render.border_min_x = 0.25
scene.render.border_max_x = 0.75
scene.render.border_min_y = 0.2
scene.render.border_max_y = 0.8
if hasattr(scene.render.image_settings, 'media_type'):
    scene.render.image_settings.media_type = 'IMAGE'
scene.render.image_settings.file_format = 'OPEN_EXR'
for crop in (True, False):
    scene.render.use_crop_to_border = crop
    scene.render.filepath = str(ROOT / ('artifacts/full-border-' + str(crop) + '.exr'))
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(scene.render.filepath)
    width, height = image.size
    data = np.array(image.pixels[:], np.float32).reshape((height, width, 4))
    if crop:
        assert (width, height) == (240, 180), (width, height)
    else:
        assert (width, height) == (480, 300), (width, height)
        assert not data[:60].any()
        data = data[60:240, 120:360]
    error = float(np.abs(data-reference[60:240, 120:360]).mean())
    assert error < 0.0001, (crop, error)
    checks['border_' + str(crop)] = error
(ROOT / 'artifacts/full-pipeline.json').write_text(json.dumps(checks, indent=2))
print('FULL_PIPELINE_OK', len(checks))
