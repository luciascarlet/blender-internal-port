# SPDX-License-Identifier: GPL-2.0-or-later
"""Render matched mirror, glass and legacy-node fixtures in 2.79b and modern Blender."""
import array
import json
import math
import os
import sys
import bpy
from mathutils import Vector
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
old=bpy.app.version<(2,80,0)
if not old:
    sys.path.insert(0,os.path.join(ROOT,'addon'))
    import blender_internal as BI
    BI.register()
label='reference' if old else 'modern-full'
out=os.path.join(ROOT,'artifacts','full-features')
os.makedirs(out,exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
scene=bpy.context.scene
scene.render.engine='BLENDER_RENDER' if old else BI.ENGINE
scene.render.resolution_x=480
scene.render.resolution_y=300
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_depth='8'
scene.view_settings.view_transform='Default' if old else 'Standard'
scene.view_settings.look='None'
if old:
    scene.render.use_antialiasing=False
    scene.world.horizon_color=(0.06,0.1,0.16)
    scene.world.ambient_color=(0.025,)*3
else:
    scene.classic_internal.samples='1'
    scene.classic_internal.ambient=0.025
    scene.world.color=(0.06,0.1,0.16)

def mat(name,color):
    m=bpy.data.materials.new(name)
    if old:p=m
    else:
        m.classic_internal.use_legacy_settings=True
        p=m.classic_internal.legacy
    p.diffuse_color=color
    p.diffuse_intensity=0.8
    p.specular_intensity=0.4
    p.specular_hardness=60
    return m,p

def mesh(name,verts,faces,material,location=(0,0,0),smooth=False):
    data=bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    ob=bpy.data.objects.new(name,data)
    if old:scene.objects.link(ob)
    else:scene.collection.objects.link(ob)
    ob.location=location
    data.materials.append(material)
    for poly in data.polygons:poly.use_smooth=smooth
    return ob

def sphere(name,material,location):
    seg,rings=64,32
    vertices=[(0,0,1)]
    for j in range(1,rings):
        t=math.pi*j/rings
        for i in range(seg):
            p=2*math.pi*i/seg
            vertices.append((math.sin(t)*math.cos(p),math.sin(t)*math.sin(p),math.cos(t)))
    vertices.append((0,0,-1))
    faces=[(0,1+i,1+(i+1)%seg) for i in range(seg)]
    for j in range(rings-2):
        a,b=1+j*seg,1+(j+1)*seg
        for i in range(seg):faces.append((a+i,b+i,b+(i+1)%seg,a+(i+1)%seg))
    for i in range(seg):faces.append((1+(rings-2)*seg+i,len(vertices)-1,1+(rings-2)*seg+(i+1)%seg))
    return mesh(name,vertices,faces,material,location,True)

floor,_=mat('Floor',(0.24,0.28,0.36))
mesh('Floor',[(-200,-200,0),(200,-200,0),(200,200,0),(-200,200,0)],[(0,1,2,3)],floor)
mirror,p=mat('Mirror',(0.5,0.06,0.025))
p.raytrace_mirror.use=True
p.raytrace_mirror.reflect_factor=0.8
p.raytrace_mirror.depth=6
sphere('Mirror',mirror,(-2.4,0,1.05))
glass,p=mat('Glass',(0.75,0.95,1))
p.use_transparency=True
p.transparency_method='RAYTRACE'
p.alpha=0.08
p.raytrace_transparency.ior=1.45
p.raytrace_transparency.depth=6
sphere('Glass',glass,(0,0,1.05))
node_material,p=mat('Legacy nodes',(0.05,0.5,0.15))
if old:
    node_material.use_nodes=True
    tree=node_material.node_tree
    tree.nodes.clear()
    def new(kind):return tree.nodes.new(kind)
else:
    tree=bpy.data.node_groups.new('Legacy nodes',BI.legacy_ui.TREE)
    node_material.classic_internal.node_tree=tree
    def new(kind):return tree.nodes.new('BI_'+kind)
texture=bpy.data.textures.new('Wood','WOOD')
texture.wood_type='RINGNOISE'
texture.noise_scale=0.35
geometry=new('ShaderNodeGeometry')
tex=new('ShaderNodeTexture')
tex.texture=texture
ramp=new('ShaderNodeValToRGB')
color_ramp=ramp.color_ramp if old else ramp.storage.nodes[0].color_ramp
color_ramp.elements[0].color=(0.02,0.06,0.015,1)
color_ramp.elements[1].color=(0.15,0.75,0.3,1)
material_node=new('ShaderNodeMaterial')
leaf,_=mat('Node shading base',(0.05,0.5,0.15))
material_node.material=leaf
output=new('ShaderNodeOutput')
tree.links.new(geometry.outputs['Global'],tex.inputs['Vector'])
tree.links.new(tex.outputs['Value'],ramp.inputs[0])
tree.links.new(ramp.outputs[0],material_node.inputs['Color'])
tree.links.new(material_node.outputs['Color'],output.inputs['Color'])
for i,node in enumerate(tree.nodes):node.location=(i*200,0)
sphere('Node textured',node_material,(2.4,0,1.05))
# A colorful card visible through glass and in mirror reflection.
card,_=mat('Card',(0.9,0.2,0.035))
mesh('Card',[(-1,0,0),(1,0,0),(1,0,2),(-1,0,2)],[(0,1,2,3)],card,(0,2,0))
if old:bpy.ops.object.lamp_add(type='SUN')
else:bpy.ops.object.light_add(type='SUN')
sun=bpy.context.object
sun.rotation_euler=(0.45,-0.5,-0.4)
if old:
    sun.data.energy=1.3
    sun.data.shadow_method='RAY_SHADOW'
else:sun.data.classic_internal.energy=1.3
bpy.ops.object.camera_add(location=(5,-12,7))
camera=bpy.context.object
camera.rotation_euler=(Vector((0,0,0.8))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO'
camera.data.ortho_scale=9
scene.camera=camera
scene.render.filepath=os.path.join(out,label+'.png')
bpy.ops.render.render(write_still=True)
result=bpy.data.images['Render Result']
pixels=array.array('f',result.pixels[:])
if not pixels:
    scene.render.image_settings.file_format='OPEN_EXR'
    scene.render.image_settings.color_depth='32'
    path=os.path.join(out,label+'.exr')
    result.save_render(path,scene=scene)
    image=bpy.data.images.load(path)
    pixels=array.array('f',image.pixels[:])
    bpy.data.images.remove(image)
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_depth='8'
assert len(pixels)==480*300*4
with open(os.path.join(out,label+'.rgba'),'wb') as f:pixels.tofile(f)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out,label+'.blend'))
print('FULL_FEATURES_OK',label)
