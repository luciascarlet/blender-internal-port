# SPDX-License-Identifier: GPL-2.0-or-later
"""Produce broader, deterministic official-2.79b regression fixtures."""
import bpy
import os
import array
import json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'artifacts', 'legacy-cases')
os.makedirs(OUT, exist_ok=True)
assert bpy.app.version == (2, 79, 0)

def groups():
    material = bpy.data.materials['Legacy nodes']
    tree = material.node_tree
    ramp = next(n for n in tree.nodes if n.bl_idname == 'ShaderNodeValToRGB')
    shading = next(n for n in tree.nodes if n.bl_idname == 'ShaderNodeMaterial')
    group = bpy.data.node_groups.new('Curved color group', 'ShaderNodeTree')
    group.inputs.new('NodeSocketColor', 'Color')
    group.outputs.new('NodeSocketColor', 'Color')
    inp, out = group.nodes.new('NodeGroupInput'), group.nodes.new('NodeGroupOutput')
    curve = group.nodes.new('ShaderNodeRGBCurve')
    curve.mapping.curves[3].points.new(0.3, 0.65)
    curve.mapping.update()
    group.links.new(inp.outputs[0], curve.inputs['Color'])
    group.links.new(curve.outputs['Color'], out.inputs[0])
    call = tree.nodes.new('ShaderNodeGroup')
    call.node_tree = group
    tree.links.new(ramp.outputs[0], call.inputs[0])
    tree.links.new(call.outputs[0], shading.inputs['Color'])

def image_slots():
    image = bpy.data.images.new('Packed checker', 8, 8, alpha=True, float_buffer=True)
    pixels = []
    for y in range(8):
        for x in range(8):
            pixels.extend((0.8, 0.08, 0.03, 1) if (x+y)%2 else (0.03, 0.4, 0.8, 1))
    image.pixels = pixels
    image.pack(as_png=True)
    # PNG packing applies sRGB encoding; tag the persisted byte buffer correctly.
    image.colorspace_settings.name = 'sRGB'
    texture = bpy.data.textures.new('Checker image', 'IMAGE')
    texture.image = image
    texture.use_interpolation = False
    material = bpy.data.materials['Floor']
    slot = material.texture_slots.add()
    slot.texture = texture
    slot.texture_coords = 'UV'
    slot.diffuse_color_factor = 0.9
    mesh = bpy.data.objects['Floor'].data
    mesh.uv_textures.new(name='Unused UV')
    mesh.uv_textures.new(name='Checker UV')
    mesh.uv_textures.active_index = 1
    mesh.uv_textures['Checker UV'].active_render = True
    layer = mesh.uv_layers.active
    for item, uv in zip(layer.data, ((0,0),(30,0),(30,30),(0,30))):
        item.uv = uv
    bump = material.texture_slots.add()
    bump.texture = bpy.data.textures.new('Bump Clouds', 'CLOUDS')
    bump.texture.noise_scale = 0.3
    bump.use_map_color_diffuse = False
    bump.use_map_normal = True
    bump.normal_factor = 0.15

def vertex_color():
    material = bpy.data.materials['Mirror']
    material.raytrace_mirror.use = False
    material.use_vertex_color_paint = True
    material.use_shadeless = True
    mesh = bpy.data.objects['Mirror'].data
    mesh.vertex_colors.new(name='Unused color')
    layer = mesh.vertex_colors.new(name='Paint')
    layer.active_render = True
    for loop, color in zip(mesh.loops, layer.data):
        v = mesh.vertices[loop.vertex_index].co
        color.color = ((v.x+1)/2, (v.y+1)/2, (v.z+1)/2)

def area_sss_ao():
    world = bpy.context.scene.world
    world.light_settings.use_ambient_occlusion = True
    world.light_settings.ao_factor = 0.4
    world.light_settings.samples = 4
    sun = bpy.data.objects['Sun']
    sun.data.type = 'AREA'
    sun.location = (0,-3,6)
    sun.data.energy = 0.5
    sun.data.size = 3
    sun.data.shadow_ray_samples_x = 2
    sun.data.shadow_ray_samples_y = 2
    material = bpy.data.materials['Mirror']
    material.raytrace_mirror.use = False
    material.subsurface_scattering.use = True
    material.subsurface_scattering.scale = 0.1
    material.subsurface_scattering.front = 0.8
    material.subsurface_scattering.back = 0.5

def antialiasing():
    scene = bpy.context.scene
    scene.render.use_antialiasing = True
    scene.render.antialiasing_samples = '8'
    scene.render.pixel_filter_type = 'MITCHELL'
    scene.render.filter_size = 1.2

def texture_nodes():
    texture = bpy.data.textures.new('Legacy checker graph', 'NONE')
    texture.use_nodes = True
    tree = texture.node_tree
    checker = next(n for n in tree.nodes if n.bl_idname == 'TextureNodeChecker')
    output = next(n for n in tree.nodes if n.bl_idname == 'TextureNodeOutput')
    checker.inputs[0].default_value = (0.04, 0.2, 0.8, 1)
    checker.inputs[1].default_value = (0.9, 0.15, 0.03, 1)
    checker.inputs[2].default_value = 0.8
    curve = tree.nodes.new('TextureNodeCurveRGB')
    curve.mapping.curves[3].points.new(0.3, 0.6)
    curve.mapping.update()
    tree.links.new(checker.outputs[0], curve.inputs['Color'])
    tree.links.new(curve.outputs[0], output.inputs[0])
    slot = bpy.data.materials['Floor'].texture_slots.add()
    slot.texture = texture
    slot.texture_coords = 'GLOBAL'

def motion_blur():
    scene = bpy.context.scene
    obj = bpy.data.objects['Mirror']
    obj.location.x = -3.0
    obj.keyframe_insert(data_path='location', frame=0)
    obj.location.x = -1.6
    obj.keyframe_insert(data_path='location', frame=2)
    scene.frame_set(1)
    scene.render.use_motion_blur = True
    scene.render.motion_blur_samples = 8
    scene.render.motion_blur_shutter = 0.7

def strands():
    scene = bpy.context.scene
    obj = bpy.data.objects['Mirror']
    scene.objects.active = obj
    obj.select = True
    bpy.ops.object.particle_system_add()
    settings = obj.particle_systems[-1].settings
    settings.type = 'HAIR'
    settings.count = 500
    settings.hair_length = 0.35
    settings.hair_step = 3
    material = bpy.data.materials['Mirror']
    material.raytrace_mirror.use = False
    material.strand.root_size = 2.0
    material.strand.tip_size = 0.3

cases = {'groups_curves': groups, 'image_uv_bump_slots': image_slots,
         'vertex_colors': vertex_color, 'area_sss_ao': area_sss_ao, 'antialiasing': antialiasing,
         'texture_nodes': texture_nodes}
archive_only = {'motion_blur': motion_blur, 'strands': strands}
cases.update(archive_only)
completed = []
for name, setup in sorted(cases.items()):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, 'artifacts/full-features/reference.blend'))
    setup()
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 240, 150
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = os.path.join(OUT, name + '.png')
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, name + '.blend'))
    # Compare saved-file behavior, including re-decoding packed image buffers.
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, name + '.blend'))
    scene = bpy.context.scene
    bpy.ops.render.render(write_still=True)
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    path = os.path.join(OUT, name + '.exr')
    bpy.data.images['Render Result'].save_render(path, scene=scene)
    image = bpy.data.images.load(path)
    with open(os.path.join(OUT, name + '.rgba'), 'wb') as f:
        array.array('f', image.pixels[:]).tofile(f)
    completed.append(name)
    print('LEGACY_CASE_OK', name)
with open(os.path.join(OUT, 'cases.json'), 'w') as f:
    json.dump([name for name in completed if name not in archive_only], f)
with open(os.path.join(OUT, 'archive_cases.json'), 'w') as f:
    json.dump(completed, f)
