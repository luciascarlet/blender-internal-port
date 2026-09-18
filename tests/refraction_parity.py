# SPDX-License-Identifier: GPL-2.0-or-later
"""Compare original node transparency/filter behavior in final and viewport paths."""
import os,sys,json,threading
from pathlib import Path
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,os.environ.get('BI_TEST_ADDON_PATH',str(ROOT/'addon')))
import blender_internal as BI
from blender_internal import full_export as E, full_native as N, viewport as V
from blender_internal.scene_snapshot import Snapshot
BI.register()
folder=ROOT/'artifacts/refraction-investigation'
cases=json.loads((folder/'reference.json').read_text())
observer=V.Observer(threading.Event())
report={}
images={}
for name in cases['cases']:
    scene=BI.legacy_import.import_file(str(folder/(name+'.blend')))[0]
    bpy.context.window.scene=scene
    reference=np.fromfile(folder/(name+'.rgba'),np.float32).reshape((-1,4))
    images[name]=reference
    with N.LOCK:
        dg=bpy.context.evaluated_depsgraph_get()
        host=E.export_scene(dg,observer)
        result=host.render(1,300,220,observer)[0]
        final_error=float(np.abs(result-reference).mean())
        final_max_error=float(np.abs(result-reference).max())
        camera=scene.camera
        plane,near,far,ortho=V.projection(camera.calc_matrix_camera(dg,x=300,y=220))
        snapshot=E.export_scene(dg,observer,host=Snapshot(),preview=True)
        host=snapshot.replay(observer)
        preview=list(host.preview(1,(300,220),E.matrix_values(camera.matrix_world.inverted()),
                                  plane,near,far,ortho,64,observer))[-1][0]
        preview_error=float(np.abs(preview-reference).mean())
        preview_max_error=float(np.abs(preview-reference).max())
    assert final_error<0.0001,(name,final_error)
    assert preview_error<0.0001,(name,preview_error)
    report[name]={'final_mean_error':final_error,'final_max_error':final_max_error,
                  'preview_mean_error':preview_error,'preview_max_error':preview_max_error}
assert float(np.abs(images['unlinked-trace-on']-images['linked-trace-on']).mean())>0.01
assert float(np.abs(images['linked-tinted']-images['linked-trace-on']).mean())>0.005
# High recursion depths need more than macOS ARM64's default 512 KiB pthread
# stack. Exercise both entry points repeatedly with closed, traceable glass;
# keep the full depth instead of masking the issue with a host-side clamp.
scene=BI.legacy_import.import_file(str(folder/'linked-tinted.blend'))[0]
bpy.context.window.scene=scene
glass=next(o for o in scene.objects if o.name.startswith('Glass cylinder')).active_material
glass.classic_internal.legacy.raytrace_transparency.depth=256
glass.classic_internal.legacy.raytrace_transparency.ior=2.0
glass.update_tag()
bpy.context.view_layer.update()
with N.LOCK:
    dg=bpy.context.evaluated_depsgraph_get()
    camera=scene.camera
    plane,near,far,ortho=V.projection(camera.calc_matrix_camera(dg,x=300,y=220))
    for repeat in range(3):
        host=E.export_scene(dg,observer,host=Snapshot(),preview=True).replay(observer)
        preview=list(host.preview(1,(300,220),E.matrix_values(camera.matrix_world.inverted()),
                                  plane,near,far,ortho,64,observer))[-1][0]
        assert np.isfinite(preview).all()
    final=E.export_scene(dg,observer).render(1,300,220,observer)[0]
    assert np.isfinite(final).all()
report['high_depth']={'depth':256,'preview_repeats':3,'final_render':True,'finite':True}
(folder/'parity.json').write_text(json.dumps(report,indent=2))
BI.unregister()
print('REFRACTION_PARITY_OK',len(report))
