# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate a distributable 2.79 append/versioning regression fixture."""
import bpy
import os
assert bpy.app.version[:2] == (2, 79)
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
folder = os.path.join(root, 'artifacts', 'import-regression')
os.makedirs(folder, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=False)
scene = bpy.context.scene
scene.use_nodes = True
tree = scene.node_tree
viewer = tree.nodes.new('CompositorNodeViewer')
tree.links.new(tree.nodes.get('Render Layers').outputs['Image'], viewer.inputs['Image'])
mat = bpy.data.materials.new('Legacy only slots')
bpy.data.objects['Cube'].data.materials.clear()
bpy.data.objects['Cube'].data.materials.append(mat)
texture = bpy.data.textures.new('Legacy only texture', type='IMAGE')
image = bpy.data.images.new('Packed slot image', width=8, height=8)
image.pixels[:] = [0.3, 0.6, 0.1, 1.0] * 64
image.pack(as_png=True)
texture.image = image
slot = mat.texture_slots.add()
slot.texture = texture
slot.texture_coords = 'ORCO'
external_path = os.path.join(folder, 'external.png')
image.save_render(external_path, scene=scene)
external = bpy.data.images.load(external_path)
external.filepath = '//external.png'
external_texture = bpy.data.textures.new('External slot texture', type='IMAGE')
external_texture.image = external
mat.texture_slots.add().texture = external_texture
# Remain available for explicit import even after modern versioning discards
# Internal slot users or material conversion no longer references this texture.
orphan = bpy.data.textures.new('Unused texture', type='CLOUDS')
orphan.use_fake_user = True
scene.render.resolution_x = 160
scene.render.resolution_y = 120
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, 'reference.blend'))
print('IMPORT_REFERENCE_OK')
