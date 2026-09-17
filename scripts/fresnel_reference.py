# SPDX-License-Identifier: GPL-2.0-or-later
"""Identical explicit geometry/lighting in official 2.79b and the modern adapter.
Compatible with Blender 2.79's Python 3.5. Save linear pixels, PNGs and legacy scenes.
"""
import array
import json
import math
import os
import sys
import bpy
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
old = bpy.app.version < (2, 80, 0)
if not old:
    sys.path.insert(0, os.path.join(ROOT, 'addon'))
    import blender_internal as BI
    BI.register()
label = 'legacy' if old else 'port'
out = os.path.join(ROOT, 'artifacts', 'fresnel')
os.makedirs(out, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
scene = bpy.context.scene
scene.render.engine = 'BLENDER_RENDER' if old else BI.ENGINE
scene.render.resolution_x = scene.render.resolution_y = 256
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '8'
scene.view_settings.view_transform = 'Default' if old else 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
if not old: scene.world.color = (0, 0, 0)
if old:
    scene.world.horizon_color = (0, 0, 0)
    scene.world.ambient_color = (0, 0, 0)
    scene.world.light_settings.use_ambient_occlusion = False
    scene.world.light_settings.use_environment_light = False
    scene.render.use_antialiasing = False
    scene.render.alpha_mode = 'SKY'
else:
    scene.classic_internal.samples = '1'
    scene.classic_internal.ambient = 0

# Build the same UV sphere mesh in both versions, without version-specific operators.
vertices = [(0, 0, 1)]
segments, rings = 64, 32
for j in range(1, rings):
    theta = math.pi*j/rings
    for i in range(segments):
        phi = 2*math.pi*i/segments
        vertices.append((math.sin(theta)*math.cos(phi), math.sin(theta)*math.sin(phi), math.cos(theta)))
vertices.append((0, 0, -1))
faces = []
for i in range(segments):
    faces.append((0, 1+i, 1+(i+1)%segments))
for j in range(rings-2):
    a, b = 1+j*segments, 1+(j+1)*segments
    for i in range(segments):
        k = (i+1)%segments
        faces.append((a+i, b+i, b+k, a+k))
last = len(vertices)-1
base = 1+(rings-2)*segments
for i in range(segments):
    faces.append((base+i, last, base+(i+1)%segments))
mesh = bpy.data.meshes.new('identical sphere')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Sphere', mesh)
if old: scene.objects.link(obj)
else: scene.collection.objects.link(obj)
for p in mesh.polygons: p.use_smooth = True
material = bpy.data.materials.new('Fresnel reference')
mesh.materials.append(material)
if old:
    material.diffuse_color = (0.64, 0.41, 0.07)
    material.diffuse_shader = 'FRESNEL'
    material.diffuse_intensity = 0.8
    material.specular_intensity = 0
    material.use_ray_shadow_bias = False
else:
    material.classic_internal.color = (0.64, 0.41, 0.07)
    material.classic_internal.diffuse_shader = '4'
    material.classic_internal.diffuse_intensity = 0.8
    material.classic_internal.specular_intensity = 0

if old: bpy.ops.object.lamp_add(type='SUN')
else: bpy.ops.object.light_add(type='SUN')
sun = bpy.context.object
sun.rotation_euler = (math.radians(40), math.radians(-30), 0)
if old: sun.data.energy = 1
else: sun.data.classic_internal.energy = 1
bpy.ops.object.camera_add(location=(0, -6, 3))
camera = bpy.context.object
camera.rotation_euler = (-camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 2.5
scene.camera = camera
report = {'version': bpy.app.version_string, 'label': label, 'cases': []}
for factor in (0.7, 3.14):
    for shadows in (False, True):
        if old:
            material.diffuse_fresnel_factor = factor
            material.diffuse_fresnel = 1.5
            sun.data.shadow_method = 'RAY_SHADOW' if shadows else 'NOSHADOW'
        else:
            material.classic_internal.diffuse_size = factor
            material.classic_internal.diffuse_smooth = 1.5
            scene.classic_internal.shadows = shadows
        name = '{}-factor{}-shadows{}'.format(label, factor, int(shadows))
        scene.render.filepath = os.path.join(out, name+'.png')
        bpy.ops.render.render(write_still=True)
        # Read lossless linear Combined data directly from Render Result.
        pixels = array.array('f', bpy.data.images['Render Result'].pixels[:])
        if not pixels:
            # Modern versions expose Result passes differently; use 32-bit EXR.
            scene.render.image_settings.file_format = 'OPEN_EXR'
            scene.render.image_settings.color_depth = '32'
            exr_path = os.path.join(out, name+'.exr')
            bpy.data.images['Render Result'].save_render(exr_path, scene=scene)
            image = bpy.data.images.load(exr_path)
            pixels = array.array('f', image.pixels[:])
            bpy.data.images.remove(image)
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_depth = '8'
        assert len(pixels) == 256*256*4
        with open(os.path.join(out, name+'.rgba'), 'wb') as f: pixels.tofile(f)
        if old:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, name+'.blend'))
        report['cases'].append({'name': name, 'pixels': len(pixels)//4})
with open(os.path.join(out,label+'-report.json'),'w') as f: json.dump(report, f, indent=2)
print('FRESNEL_REFERENCE_OK', report)
