# SPDX-License-Identifier: GPL-2.0-or-later
import sys
import os
import json
from pathlib import Path
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N, full_export as E
BI.register()
OUT = ROOT / 'artifacts/legacy-cases'

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass

report = {}
for name in json.loads((OUT / 'cases.json').read_text()):
    scene = BI.legacy_import.import_file(str(OUT / (name + '.blend')))[0]
    bpy.context.window.scene = scene
    with N.LOCK:
        host = E.export_scene(bpy.context.evaluated_depsgraph_get(), Observer())
        pixels, width, height = host.render(1, 240, 150, Observer())
    reference = np.fromfile(str(OUT / (name + '.rgba')), np.float32).reshape((-1, 4))
    diff = np.abs(pixels-reference)
    report[name] = {'mean_absolute_error': float(diff.mean()), 'max_absolute_error': float(diff.max())}
    image = bpy.data.images.new('Port ' + name, width, height, alpha=True, float_buffer=True)
    image.pixels.foreach_set(pixels.ravel())
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    image.save_render(str(OUT / (name + '-port.png')), scene=scene)
    print('PORT_CASE', name, report[name], flush=True)
    (OUT / 'comparison.json').write_text(json.dumps(report, indent=2))
assert all(item['mean_absolute_error'] < 0.002 for item in report.values()), report
print('FULL_CASE_IMPORT_OK', len(report))
