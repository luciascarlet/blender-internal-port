# SPDX-License-Identifier: GPL-2.0-or-later
"""Disposable windowed viewport workflow; never run in a user's working session."""
from pathlib import Path
import sys, os, json, traceback, time
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,os.environ.get('BI_TEST_ADDON_PATH',str(ROOT/'addon')))
import blender_internal as BI
BI.register()
from blender_internal import viewport as V
scene=bpy.context.scene
scene.render.engine=BI.ENGINE
obj=bpy.data.objects['Cube']
mat=bpy.data.materials.new('Viewport test')
obj.data.materials.clear();obj.data.materials.append(mat)
mat.classic_internal.color=(0.8,0.02,0.02)
mat.classic_internal.shadeless=True
window=bpy.context.window
area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
area.spaces.active.overlay.show_overlays=False
scene.classic_internal.viewport_resolution=30
area.spaces.active.shading.type='RENDERED'
node=None; phase=0;started=time.monotonic();baseline=None;expected=-1;checks=[]
report=ROOT/'artifacts/viewport-ui.json'

def tick():
    global phase,started,baseline,expected,node
    try:
        assert time.monotonic()-started<25, ('timeout',phase,[(s.serial,s.completed,s.message,s.error) for s in V.STATES])
        states=list(V.STATES)
        if not states:return 0.1
        state=states[0]
        assert not state.error,state.error
        if phase==9:
            if time.monotonic()-started<0.5:return 0.1
            assert state.publications==baseline
            scene.classic_internal.viewport_pause=False
            expected=state.serial-1
            phase=10;started=time.monotonic();return 0.1
        if state.completed!=state.serial or state.texture is None:return 0.1
        pixels=state.result[1].copy()
        if phase==0:
            assert pixels[:,0].max()>0.5
            baseline=pixels
            checks.append('Rendered shading displays a progressively refined GPU texture')
            mat.classic_internal.color=(0.02,0.8,0.02)
            expected=state.serial
        elif state.serial<=expected:return 0.1
        elif phase==1:
            assert np.max(np.abs(pixels-baseline))>0.4
            baseline=pixels
            checks.append('Material edits refresh the viewport without manual tagging')
            obj.location.x+=1.5
            expected=state.serial
        elif phase==2:
            assert np.max(np.abs(pixels-baseline))>0.1
            checks.append('Object transforms refresh the preview')
            baseline=pixels
            area.spaces.active.region_3d.view_distance*=1.4
            expected=state.serial
        elif phase==3:
            assert np.max(np.abs(pixels-baseline))>0.1
            checks.append('Viewport navigation changes the rendered camera')
            baseline=pixels
            area.spaces.active.region_3d.view_perspective='ORTHO'
            expected=state.serial
        elif phase==4:
            assert np.isfinite(pixels).all()
            checks.append('Orthographic viewport renders')
            tree=bpy.data.node_groups.new('Viewport nodes',BI.legacy_ui.TREE)
            node=tree.nodes.new('BI_ShaderNodeRGB')
            node.outputs[0].default_value=(0.02,0.02,0.8,1)
            output=tree.nodes.new('BI_ShaderNodeOutput')
            tree.links.new(node.outputs[0],output.inputs[0])
            mat.classic_internal.node_tree=tree
            expected=state.serial-1
        elif phase==5:
            assert pixels[:,2].max()>0.5
            baseline=pixels
            checks.append('Assigning a legacy node graph updates viewport shading')
            node.outputs[0].default_value=(0.8,0.8,0.02,1)
            expected=state.serial
        elif phase==6:
            assert np.max(np.abs(pixels-baseline))>0.4
            checks.append('Editing a legacy node socket refreshes the viewport')
            baseline=pixels
            obj.hide_set(True)
            expected=state.serial
        elif phase==7:
            assert np.max(np.abs(pixels-baseline))>0.1
            checks.append('Viewport visibility controls are respected')
            obj.hide_set(False)
            obj.hide_render=True
            expected=state.serial
        elif phase==8:
            assert np.max(np.abs(pixels-baseline))<0.001
            checks.append('An object hidden only from F12 remains visible in the viewport')
            obj.hide_render=False
            scene.classic_internal.viewport_pause=True
            # Deliberately edit while paused; no new result should be published.
            node.outputs[0].default_value=(0.05,0.4,0.8,1)
            baseline=state.publications
            phase+=1;started=time.monotonic();return 0.1
        elif phase==10:
            checks.append('Pause retains its image; resume renders pending edits')
            expected=state.serial
            scene.render.resolution_x=64;scene.render.resolution_y=64
            scene.render.resolution_percentage=100
            bpy.ops.render.render()
        elif phase==11:
            checks.append('F12 takes priority and the viewport resumes afterwards')
            with bpy.context.temp_override(window=window,area=area):
                bpy.ops.screen.area_split(direction='VERTICAL',factor=0.5)
            for view in window.screen.areas:
                if view.type=='VIEW_3D':view.spaces.active.shading.type='RENDERED'
            expected=-1
        elif phase==12:
            if len(states)<2 or any(s.completed!=s.serial or s.error for s in states):return 0.1
            checks.append('Two rendered viewports converge without starving or sharing native handles')
            # Shut down while a newly requested render may still be active.
            obj.location.z+=1
            for view in window.screen.areas:
                if view.type=='VIEW_3D':view.spaces.active.shading.type='SOLID'
            BI.unregister()
            assert not V.STATES and V._worker is None
            checks.append('Leaving rendered shading and unregistering stop the worker cleanly')
            report.write_text(json.dumps({'passed':True,'checks':checks},indent=2))
            print('VIEWPORT_UI_OK',len(checks),flush=True)
            bpy.ops.wm.quit_blender();return None
        phase+=1;started=time.monotonic()
        return 0.1
    except Exception:
        error=traceback.format_exc();print(error,flush=True)
        report.write_text(json.dumps({'passed':False,'phase':phase,'checks':checks,'error':error},indent=2))
        BI.unregister()
        bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(tick,first_interval=1)
