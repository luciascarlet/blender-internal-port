# SPDX-License-Identifier: GPL-2.0-or-later
"""Run: Blender --background --factory-startup --python-exit-code 1 --python scripts/render_demo.py"""
import json
import math
from pathlib import Path
import sys
import time
import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addon'))
import blender_internal
blender_internal.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.render.engine = blender_internal.ENGINE
scene.render.resolution_x = 800
scene.render.resolution_y = 500
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.world.color = (0.035, 0.045, 0.07)
scene.classic_internal.samples = '2'
scene.classic_internal.ambient = 0.08

colors = [(0.65, 0.16, 0.045), (0.10, 0.37, 0.58), (0.12, 0.50, 0.26), (0.42, 0.15, 0.58), (0.64, 0.41, 0.07)]
for i, (name, color) in enumerate(zip(('Lambert', 'Oren-Nayar', 'Toon', 'Minnaert', 'Fresnel'), colors)):
    x = (i - 2) * 2.5
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24, location=(x, 0, 1.1), radius=1)
    obj = bpy.context.object
    obj.name = name
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    material = bpy.data.materials.new(name)
    p = material.classic_internal
    p.color = color
    p.diffuse_shader = str(i)
    p.specular_shader = str(i)
    p.roughness = 1
    p.darkness = 1.4
    p.diffuse_size = 3.14 if i == 4 else 0.7
    p.diffuse_smooth = 0.12 if i != 4 else 1.5
    p.specular_size = 0.25
    p.specular_smooth = 0.05
    p.hardness = 75
    p.specular_intensity = 0.5
    obj.data.materials.append(material)
    # Text converted through the same evaluated mesh adapter.
    bpy.ops.object.text_add(location=(x, -1.65, 0.02), rotation=(0, 0, 0))
    text = bpy.context.object
    text.data.body = name
    text.data.align_x = 'CENTER'
    text.data.size = 0.28
    text.data.extrude = 0.006
    label = bpy.data.materials.get('Labels') or bpy.data.materials.new('Labels')
    label.classic_internal.color = (0.8, 0.85, 0.95)
    label.classic_internal.shadeless = True
    text.data.materials.append(label)

bpy.ops.mesh.primitive_plane_add(size=200)
plane = bpy.context.object
plane.name = 'Shadow receiver'
material = bpy.data.materials.new('Floor')
material.classic_internal.color = (0.085, 0.105, 0.145)
material.classic_internal.specular_intensity = 0.05
plane.data.materials.append(material)

bpy.ops.object.light_add(type='SUN', location=(0, -4, 8))
sun = bpy.context.object
sun.rotation_euler = (math.radians(30), math.radians(-25), math.radians(-25))
sun.data.classic_internal.energy = 1.2
bpy.ops.object.light_add(type='POINT', location=(2, 4, 6))
fill = bpy.context.object
fill.data.color = (0.5, 0.65, 1)
fill.data.classic_internal.energy = 0.5

bpy.ops.object.camera_add(location=(5, -15, 11))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 0.7)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 15
scene.camera = camera
(ROOT / 'artifacts').mkdir(exist_ok=True)
scene.render.filepath = str(ROOT / 'artifacts/classic-demo.png')
start = time.perf_counter()
bpy.ops.render.render(write_still=True)
elapsed = time.perf_counter() - start
# Read the saved image because background Render Result pixel access is version-dependent.
image = bpy.data.images.load(scene.render.filepath, check_existing=False)
import numpy as np
pixels = np.array(image.pixels[:]).reshape(-1, 4)
assert pixels.shape[0] == 800 * 500
assert np.isfinite(pixels).all()
assert pixels[:, :3].std() > 0.05, 'Render appears blank'
assert pixels[:, 3].min() > 0.99
bpy.data.images.remove(image)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'artifacts/classic-demo.blend'))
report = {'blender_version': bpy.app.version_string, 'blender_hash': bpy.app.build_hash.decode(),
          'resolution': [800, 500], 'backend': 'FULL', 'samples': 5, 'seconds': elapsed,
          'finite_pixels': True, 'nonblank': True}
(ROOT / 'artifacts/demo-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print('CLASSIC_DEMO_OK', report)
