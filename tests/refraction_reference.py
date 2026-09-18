# SPDX-License-Identifier: GPL-2.0-or-later
"""Official 2.79b: traced secondary rays, node alpha and transmission tint."""
import bpy, os, json, array
from mathutils import Vector
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,'artifacts','refraction-investigation')
os.makedirs(OUT,exist_ok=True)
assert bpy.app.version[:2]==(2,79)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
scene=bpy.context.scene
scene.render.engine='BLENDER_RENDER'
scene.render.resolution_x=300;scene.render.resolution_y=220;scene.render.resolution_percentage=100
scene.render.use_antialiasing=False
scene.render.use_raytrace=True
scene.world.horizon_color=(0.12,0.2,0.4)
scene.view_settings.view_transform='Default'
scene.render.image_settings.file_format='PNG'
base=bpy.data.materials.new('Tinted glass')
base.diffuse_color=(0.7943232,1,0.13059995)
base.diffuse_intensity=1
base.use_transparency=True;base.transparency_method='RAYTRACE';base.alpha=0
base.raytrace_transparency.ior=1.117
base.raytrace_transparency.fresnel=1.26
base.raytrace_transparency.depth=32
base.use_nodes=True
initial=[(l.from_socket.name,l.to_socket.name) for l in base.node_tree.links]
base.node_tree.nodes.clear()
source=base.node_tree.nodes.new('ShaderNodeMaterial');source.material=base
output=base.node_tree.nodes.new('ShaderNodeOutput')
base.node_tree.links.new(source.outputs['Color'],output.inputs['Color'])
bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=1,depth=2.5,location=(0,0,1.4))
bpy.context.object.name='Glass cylinder';bpy.context.object.data.materials.append(base)
for f in bpy.context.object.data.polygons:f.use_smooth=len(f.vertices)==4
# White and colored stripes make ray bending and filtering visible.
for i,color in enumerate(((1,1,1),(0.85,0.05,0.05),(1,1,1),(0.05,0.05,0.85),(1,1,1))):
 mat=bpy.data.materials.new('Stripe '+str(i));mat.diffuse_color=color;mat.use_shadeless=True
 bpy.ops.mesh.primitive_cube_add(location=(-2+i,2,1.5));ob=bpy.context.object;ob.scale=(0.5,0.12,1.5);ob.data.materials.append(mat)
bpy.ops.object.lamp_add(type='SUN');bpy.context.object.rotation_euler=(0.6,-0.5,-0.4);bpy.context.object.data.energy=0.9
bpy.ops.object.camera_add(location=(4,-9,3.6));cam=bpy.context.object
cam.rotation_euler=(Vector((0,0.6,1.5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=6.5;scene.camera=cam
cases=[('unlinked-trace-on',True,False,0,True),('unlinked-trace-off',False,False,0,True),
       ('linked-trace-on',True,True,0,True),('linked-tinted',True,True,0.8,True),
       ('no-nodes-tinted',True,False,0.8,False)]
report={'original_default_links':initial,'cases':[]}
for name,trace,alpha,filter_value,nodes in cases:
 base.use_raytrace=trace;base.use_nodes=nodes;base.raytrace_transparency.filter=filter_value
 for link in list(base.node_tree.links):
  if link.to_socket==output.inputs['Alpha']:base.node_tree.links.remove(link)
 if alpha:base.node_tree.links.new(source.outputs['Alpha'],output.inputs['Alpha'])
 scene.render.filepath=os.path.join(OUT,name+'.png')
 bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT,name+'.blend'))
 bpy.ops.render.render(write_still=True)
 scene.render.image_settings.file_format='OPEN_EXR'
 scene.render.image_settings.color_depth='32'
 exr=os.path.join(OUT,name+'.exr')
 bpy.data.images['Render Result'].save_render(exr,scene=scene)
 image=bpy.data.images.load(exr,check_existing=False)
 array.array('f',image.pixels[:]).tofile(open(os.path.join(OUT,name+'.rgba'),'wb'))
 bpy.data.images.remove(image)
 scene.render.image_settings.file_format='PNG'
 report['cases'].append(name)
open(os.path.join(OUT,'reference.json'),'w').write(json.dumps(report,indent=2))
print('REFRACTION_REFERENCE_OK',len(cases))
