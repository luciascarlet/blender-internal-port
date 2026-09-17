# SPDX-License-Identifier: GPL-2.0-or-later
"""Repeat native main replacement and rendering; check output and memory growth."""
from pathlib import Path
import os
import sys
import resource
import json
import numpy as np
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N
BI.register()

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass

reference = None
memory = []
with N.LOCK:
    for i in range(100):
        host = N.Scene()
        host.check(host.lib.bi_full_load(str(ROOT / 'artifacts/full-features/reference.blend').encode()))
        pixels, width, height = host.render(1, 120, 75, Observer())
        if reference is None:
            reference = pixels.copy()
        else:
            assert np.max(np.abs(reference-pixels)) < 1e-6, i
        if i in (9, 49, 99):
            memory.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            print('STRESS_ITERATION', i+1, 'max_rss', memory[-1], flush=True)
# macOS reports bytes (Linux reports KiB); this project currently validates macOS.
growth = memory[-1]-memory[0]
assert growth < 64*1024*1024, growth
report = {'renders': 100, 'max_rss_bytes_after_10_50_100': memory, 'growth_bytes': growth}
(ROOT / 'artifacts/full-stress.json').write_text(json.dumps(report, indent=2))
print('FULL_STRESS_OK', report)
