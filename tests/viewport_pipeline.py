# SPDX-License-Identifier: GPL-2.0-or-later
"""Native preview pipeline, snapshot ownership and full-render coexistence."""
from pathlib import Path
import sys, os, json, threading
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT/'addon')))
import blender_internal as BI
from blender_internal import full_native as N, full_export as E, viewport as V
from blender_internal.scene_snapshot import Snapshot
BI.register()
scene=bpy.context.scene
scene.render.engine=BI.ENGINE
camera=scene.camera
scene.classic_internal.samples='1'
observer=V.Observer(threading.Event())
checks=[]
with N.LOCK:
    dg=bpy.context.evaluated_depsgraph_get()
    m=camera.calc_matrix_camera(dg,x=160,y=100)
    plane,near,far,ortho=V.projection(m)
    view=E.matrix_values(camera.matrix_world.inverted())
    snap=E.export_scene(dg,observer,host=Snapshot(),preview=True)
    host=E.export_scene(dg,observer)
    reference=host.render(1,160,100,observer)[0]
    # Replay after the mesh used to record commands has been freed and changed.
    bpy.data.objects['Cube'].location.x=10
    bpy.context.view_layer.update()
    host=snap.replay(observer)
    levels=list(host.preview(1,(160,100),view,plane,near,far,ortho,32,observer))
    assert [(w,h) for _,w,h in levels]==[(40,25),(80,50),(160,100)]
    delta=float(np.abs(levels[-1][0]-reference).mean())
    assert delta < 0.005, delta
    checks.append({'snapshot_and_original_preview_parity':delta,'levels':[(w,h) for _,w,h in levels]})
    bpy.data.objects['Cube'].location.x=0
    scene.camera=None
    bpy.context.view_layer.update()
    snap=E.export_scene(bpy.context.evaluated_depsgraph_get(),observer,host=Snapshot(),preview=True)
    host=snap.replay(observer)
    data=list(host.preview(1,(160,100),view,plane,near,far,ortho,32,observer))[-1][0]
    assert np.allclose(data,levels[-1][0],atol=1e-5)
    checks.append('free-view preview requires no scene camera')
    host=snap.replay(observer)
    gen=host.preview(1,(160,100),view,plane,near,far,ortho,32,observer)
    next(gen)
    observer.cancelled.set()
    try:
        next(gen)
        raise AssertionError('Cancelled job continued')
    except (InterruptedError,RuntimeError): pass
    observer.cancelled.clear()
    scene.camera=camera
    bpy.context.view_layer.update()
    host=E.export_scene(bpy.context.evaluated_depsgraph_get(),observer)
    again=host.render(1,160,100,observer)[0]
    assert np.allclose(again,reference,atol=1e-5)
    checks.append('cancellation frees preview database and F12 still renders identically')
# Exercise the snapshot ABI on the existing mirror/glass/texture-node fixture.
scene=BI.legacy_import.import_file(str(ROOT/'artifacts/full-features/reference.blend'))[0]
bpy.context.window.scene=scene
scene.classic_internal.legacy.use_antialiasing=False
with N.LOCK:
    dg=bpy.context.evaluated_depsgraph_get()
    camera=scene.camera
    view=E.matrix_values(camera.matrix_world.inverted())
    plane,near,far,ortho=V.projection(camera.calc_matrix_camera(dg,x=160,y=100))
    host=E.export_scene(dg,observer)
    reference=host.render(1,160,100,observer)[0]
    snap=E.export_scene(dg,observer,host=Snapshot(),preview=True)
    host=snap.replay(observer)
    result=list(host.preview(1,(160,100),view,plane,near,far,ortho,32,observer))[-1][0]
    delta=float(np.abs(result-reference).mean())
    assert delta < 0.005, delta
    checks.append({'mirror_refraction_nodes_preview_parity':delta})
BI.unregister()
(ROOT/'artifacts/viewport-pipeline.json').write_text(json.dumps(checks,indent=2))
print('VIEWPORT_PIPELINE_OK',len(checks))
