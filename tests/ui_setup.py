# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated GUI fixture; launch with --factory-startup --python tests/ui_setup.py.
Does not load, overwrite, or change the user's working scene or preferences.
"""
from pathlib import Path
import os
import sys
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
BI.register()
bpy.context.scene.render.engine = BI.ENGINE
bpy.context.scene.name = 'Internal UI verification'
obj = bpy.data.objects['Cube']
obj.data.materials.clear()
# Start with no material, exercising the same New control a user encounters.
for area in bpy.context.screen.areas:
    if area.type == 'PROPERTIES':
        area.spaces.active.context = 'MATERIAL'
    if area.type == 'DOPESHEET_EDITOR':
        area.type = 'NODE_EDITOR'
        area.ui_type = BI.legacy_ui.TREE
print('INTERNAL_UI_READY', flush=True)
