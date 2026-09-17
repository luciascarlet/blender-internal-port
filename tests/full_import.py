# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import sys
import os
import json
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
BI.register()
path = ROOT / 'artifacts/full-features/reference.blend'
# A mid-migration failure must remove only newly appended datablocks.
before = set(bpy.data.user_map())
real_assign = BI.legacy_import.assign
def fail_restore(*args, **kwargs):
    raise RuntimeError('Injected migration failure')
BI.legacy_import.assign = fail_restore
try:
    BI.legacy_import.import_file(str(path))
    raise AssertionError('Failure injection did not execute')
except RuntimeError as error:
    assert str(error) == 'Injected migration failure'
finally:
    BI.legacy_import.assign = real_assign
assert set(bpy.data.user_map()) == before, 'Failed import changed the existing datablock set'
scenes = BI.legacy_import.import_file(str(path))
scene = scenes[0]
bpy.context.window.scene = scene
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.render.filepath = str(ROOT / 'artifacts/full-features/imported.png')
bpy.ops.render.render(write_still=True)
result = bpy.data.images['Render Result']
scene.render.image_settings.file_format = 'OPEN_EXR'
scene.render.image_settings.color_depth = '32'
exr = str(ROOT / 'artifacts/full-features/imported.exr')
result.save_render(exr, scene=scene)
im = bpy.data.images.load(exr)
pixels = np.array(im.pixels[:], np.float32)
ref = np.fromfile(str(ROOT / 'artifacts/full-features/reference.rgba'), np.float32)
diff = np.abs(pixels-ref)
assert pixels.shape == ref.shape
report = {'mean_absolute_error': float(diff.mean()), 'max_absolute_error': float(diff.max())}
assert report['mean_absolute_error'] < 0.002, report
(ROOT / 'artifacts/full-import.json').write_text(json.dumps(report, indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'artifacts/full-import.blend'))
print('FULL_IMPORT_OK', report)
