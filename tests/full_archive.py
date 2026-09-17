# SPDX-License-Identifier: GPL-2.0-or-later
"""Full original scene evaluation, including animation and particle strands."""
import sys
import os
import json
from pathlib import Path
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N
BI.register()
OUT = ROOT / 'artifacts/legacy-cases'

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass

report = {}
with N.LOCK:
    for name in json.loads((OUT / 'archive_cases.json').read_text()):
        host = N.Scene()
        host.check(host.lib.bi_full_load(str(OUT / (name + '.blend')).encode()))
        pixels, width, height = host.render(1, 240, 150, Observer())
        reference = np.fromfile(str(OUT / (name + '.rgba')), np.float32).reshape((-1, 4))
        delta = np.abs(pixels-reference)
        report[name] = {'mean_absolute_error': float(delta.mean()), 'max_absolute_error': float(delta.max())}
        assert np.isfinite(pixels).all(), name
        print('ARCHIVE_CASE', name, report[name], flush=True)
(OUT / 'archive-comparison.json').write_text(json.dumps(report, indent=2))
assert all(v['mean_absolute_error'] < 0.002 for v in report.values()), report

# Actual modern host path, without importing/replacing the user's current scene.
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
scene.render.resolution_x, scene.render.resolution_y = 240, 150
scene.render.resolution_percentage = 100
scene.classic_internal.source = 'ARCHIVE'
scene.classic_internal.archive_path = str(OUT / 'strands.blend')
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.render.filepath = str(OUT / 'strands-archive-port.png')
bpy.ops.render.render(write_still=True)
print('FULL_ARCHIVE_OK', len(report))
