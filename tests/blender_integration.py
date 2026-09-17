# SPDX-License-Identifier: GPL-2.0-or-later
"""Integration tests using real Blender, independent of its unit-test harness."""
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon'))
import blender_internal as BI
BI.register()

class Reporter:
    def test_break(self): return False
    def report(self, level, text): print(level, text)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
scene.render.resolution_x = scene.render.resolution_y = 96
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.classic_internal.samples = '1'
scene.classic_internal.ambient = 0.03
scene.world.color = (0.06, 0.09, 0.15)

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 1))
cube = bpy.context.object
bevel = cube.modifiers.new('Evaluated bevel', 'BEVEL')
bevel.width = 0.15
bevel.segments = 2
material = bpy.data.materials.new('Classic red')
material.classic_internal.color = (0.7, 0.06, 0.03)
cube.data.materials.append(material)
bpy.ops.mesh.primitive_plane_add(size=200)
plane = bpy.context.object
plane_material = bpy.data.materials.new('Receiver')
plane_material.classic_internal.color = (0.5, 0.5, 0.5)
plane.data.materials.append(plane_material)
bpy.ops.object.light_add(type='SUN')
light = bpy.context.object
light.rotation_euler = (0.6, -0.7, -0.3)
bpy.ops.object.camera_add(location=(5, -8, 6))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 0.5)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera

def render(name):
    path = ROOT / 'artifacts' / (name + '.png')
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = np.array(image.pixels[:]).reshape(96, 96, 4)
    bpy.data.images.remove(image)
    assert np.isfinite(pixels).all()
    return pixels

shadowed = render('test-shadowed')
scene.classic_internal.shadows = False
unshadowed = render('test-unshadowed')
delta = unshadowed[:, :, :3] - shadowed[:, :, :3]
assert delta.max() > 0.2, 'Shadow toggle did not affect the image'
assert (delta.mean(axis=2) > 0.03).sum() > 50, 'No meaningful cast shadow'
scene.classic_internal.shadows = True
# Verify output camera modes produce genuinely different views.
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 5
orthographic = render('test-orthographic')
assert np.abs(orthographic - shadowed).mean() > 0.01
# Use render visibility, not viewport visibility.
plane.hide_render = True
scene.render.film_transparent = True
transparent = render('test-transparent')
assert (transparent[:, :, 3] == 0).sum() > 3000
assert (transparent[:, :, 3] == 1).sum() > 100

# Export correctness: evaluated modifiers, collection instances, normal transform,
# material override, and cancellation before allocation.
plane.hide_render = False
collection = bpy.data.collections.new('Instance source')
source = bpy.data.objects.new('Instanced cube', cube.data.copy())
collection.objects.link(source)
instance = bpy.data.objects.new('Collection instance', None)
instance.instance_type = 'COLLECTION'
instance.instance_collection = collection
instance.location = (5, 0, 0)
instance.scale = (-1, 2, 0.5)
scene.collection.objects.link(instance)
bpy.context.view_layer.update()
graph = bpy.context.evaluated_depsgraph_get()
triangles, materials, lights = BI.export_scene(graph, Reporter())
assert len(triangles) > 26, 'Evaluated bevel not exported'
points = np.array([list(t.p) for t in triangles]).reshape(-1, 3)
assert ((points[:, 0] > 3) & (points[:, 0] < 7)).any(), 'Collection instance transform was lost'
assert len(lights) == 1
for tri in triangles:
    for n in np.array(tri.n).reshape(3, 3):
        assert abs(np.linalg.norm(n) - 1) < 1e-5
bpy.context.view_layer.material_override = plane_material
bpy.context.view_layer.update()
triangles, materials, _ = BI.export_scene(bpy.context.evaluated_depsgraph_get(), Reporter())
assert len(materials) == 2 and all(t.material == 1 for t in triangles)
class Cancelled(Reporter):
    def test_break(self): return True
try:
    BI.export_scene(graph, Cancelled())
except InterruptedError:
    pass
else:
    raise AssertionError('Scene export ignored cancellation')

# Repeated registration must leave the API clean.
scene.render.engine = 'BLENDER_EEVEE'
BI.unregister()
assert not hasattr(bpy.types.Scene, 'classic_internal')
BI.register()
BI.unregister()
report = {'blender_version': bpy.app.version_string,
          'checks': ['perspective render', 'orthographic render', 'cast shadows',
                     'transparent film', 'evaluated modifiers', 'collection instances',
                     'transformed normals', 'material override', 'export cancellation', 'register/unregister'],
          'shadow_pixel_count': int((delta.mean(axis=2) > 0.03).sum())}
(ROOT / 'artifacts/integration-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print('CLASSIC_INTEGRATION_OK', report)
