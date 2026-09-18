# SPDX-License-Identifier: GPL-2.0-or-later
"""Windowed regression: a visible texture panel must not cancel its own preview.

Run only in a disposable --factory-startup Blender process.
"""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
# Exercise drawing the slot's Remove and Edit Nodes buttons on every redraw.
BI.CLASSIC_PT_textures.bl_options = set()
BI.register()
from blender_internal import viewport as V
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
scene.classic_internal.viewport_resolution = 25
cube = bpy.data.objects['Cube']
cube.location.z = 1.1
red = bpy.data.materials.new('Reflection subject')
red.classic_internal.color = (.8, .03, .02)
red.classic_internal.shadeless = True
cube.data.materials.clear(); cube.data.materials.append(red)
bpy.ops.mesh.primitive_plane_add(size=12)
floor = bpy.context.object
material = bpy.data.materials.new('Mirror floor')
floor.data.materials.append(material)
p = material.classic_internal
p.legacy.raytrace_mirror.use = True
p.legacy.raytrace_mirror.reflect_factor = .8
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
properties = next(a for a in window.screen.areas if a.type == 'PROPERTIES')
properties.spaces.active.context = 'MATERIAL'
area.spaces.active.overlay.show_overlays = False
area.spaces.active.shading.type = 'RENDERED'
phase = 0
started = time.monotonic()
last = -1
baseline = None
texture = node = None
checks = []
report = ROOT / 'artifacts/texture-preview-ui.json'

def operator(**kwargs):
    with bpy.context.temp_override(window=window, area=properties):
        assert bpy.ops.material.internal_texture_slot(**kwargs) == {'FINISHED'}

def tick():
    global phase, started, last, baseline, texture, node
    try:
        assert time.monotonic() - started < 25, ('timeout', phase,
            [(s.serial, s.completed, s.message) for s in V.STATES])
        if not V.STATES: return .1
        state = next(iter(V.STATES))
        assert not state.error, state.error
        if phase == 7:
            if time.monotonic() - started < .8: return .1
            assert state.serial == last and state.completed == last, 'Idle panel restarted rendering'
            checks.append('Visible texture controls settle without render cancellation')
            operator(remove=0)
            phase = 8; started = time.monotonic(); return .1
        if state.completed != state.serial or state.texture is None or state.serial <= last:
            return .1
        pixels = state.result[1].copy()
        assert np.isfinite(pixels).all()
        delta = float(np.abs(pixels - baseline).mean()) if baseline is not None else None
        if phase in (1, 2, 3, 4, 5, 6):
            assert delta > 1e-5, (phase, delta)
        checks.append({'phase': phase, 'serial': state.serial, 'image_change': delta})
        baseline = pixels; last = state.serial
        if phase == 0:
            operator(remove=-1)
            slot = p.texture_slots[0]
            texture = bpy.data.textures.new('Musgrave bump', type='MUSGRAVE')
            slot.texture = texture
            slot.settings.use_map_color_diffuse = False
            slot.settings.use_map_normal = True
            slot.settings.normal_factor = .2
        elif phase == 1:
            texture.noise_scale = 1.2
        elif phase == 2:
            texture.use_nodes = True
            tree = texture.node_tree
            tree.nodes.clear()
            node = tree.nodes.new('TextureNodeTexMusgrave')
            output = tree.nodes.new('TextureNodeOutput')
            tree.links.new(node.outputs['Color'], output.inputs['Color'])
        elif phase == 3:
            node.inputs['Size'].default_value = .8
        elif phase == 4:
            tree = bpy.data.node_groups.new('Legacy shader texture', BI.legacy_ui.TREE)
            source = tree.nodes.new('BI_ShaderNodeTexture'); source.texture = texture
            output = tree.nodes.new('BI_ShaderNodeOutput')
            tree.links.new(source.outputs['Color'], output.inputs['Color'])
            p.node_tree = tree
        elif phase == 5:
            node.inputs['Size'].default_value = .13
        elif phase == 6:
            phase = 7; started = time.monotonic(); return .1
        elif phase == 8:
            assert len(p.texture_slots) == 0
            operator(remove=-1)
        elif phase == 9:
            assert len(p.texture_slots) == 1
            checks.append('Remove and re-add notify the viewport only when executed')
            report.write_text(json.dumps({'passed': True, 'checks': checks}, indent=2))
            BI.unregister(); print('TEXTURE_PREVIEW_UI_OK', flush=True)
            bpy.ops.wm.quit_blender(); return None
        phase += 1; started = time.monotonic(); return .1
    except Exception:
        error = traceback.format_exc()
        report.write_text(json.dumps({'passed': False, 'checks': checks, 'error': error}, indent=2))
        print(error, flush=True)
        BI.unregister(); bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(tick, first_interval=1)
