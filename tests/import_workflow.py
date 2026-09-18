# SPDX-License-Identifier: GPL-2.0-or-later
"""Legacy compositor, orphan slots, packed images and repeated import isolation."""
import os
import sys
import json
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
BI.register()
path = ROOT / 'artifacts/import-regression/reference.blend'
original = set(bpy.data.user_map())
original_scene = bpy.context.scene
imports = []
for repeat in range(2):
    if repeat == 0:
        scene = BI.legacy_import.import_file(str(path))[0]
        assert bpy.context.scene == original_scene
    else:
        assert bpy.ops.import_scene.blender_internal(filepath=str(path)) == {'FINISHED'}
        scene = bpy.context.scene
        assert scene != original_scene and scene != imports[0][0]
    assert len(scene.objects) == 3
    cube = next(o for o in scene.objects if o.type == 'MESH')
    material = cube.active_material
    slot = material.classic_internal.texture_slots[0]
    assert slot.texture and slot.texture.image
    assert slot.texture.image.packed_file
    assert tuple(slot.texture.image.size) == (8, 8)
    external = material.classic_internal.texture_slots[1].texture.image
    assert Path(bpy.path.abspath(external.filepath)).resolve() == path.with_name('external.png')
    assert external.size[0] == 8
    assert material.classic_internal.use_legacy_settings
    assert scene.use_nodes
    tree = scene.compositing_node_group if hasattr(scene, 'compositing_node_group') else scene.node_tree
    assert any(n.bl_idname == 'CompositorNodeViewer' for n in tree.nodes)
    assert original <= set(bpy.data.user_map())
    imports.append((scene, material, slot.texture, slot.texture.image))
for left, right in zip(*imports):
    assert left != right, 'Repeated import reused editable IDs'
assert len([t for t in bpy.data.textures if t.name.startswith('Unused texture')]) == 2
# The original low-level error must become actionable without appending IDs.
real_run = BI.legacy_import.subprocess.run
before = set(bpy.data.user_map())
def fail(*args, **kwargs):
    return BI.legacy_import.subprocess.CompletedProcess(args[0], 17)
BI.legacy_import.subprocess.run = fail
try:
    BI.legacy_import.import_file(str(path))
    raise AssertionError('Expected conversion failure')
except RuntimeError as error:
    assert 'conversion failed (exit 17)' in str(error), str(error)
finally:
    BI.legacy_import.subprocess.run = real_run
assert set(bpy.data.user_map()) == before
(ROOT / 'artifacts/import-workflow.json').write_text(json.dumps({
    'repeated_import': True, 'packed_slot_images': True, 'orphan_textures': True,
    'compositor_preserved': True, 'existing_scene_unchanged': True,
    'external_image_path': True, 'operator_switches_scene': True,
    'conversion_failure_atomic': True}, indent=2))
BI.unregister()
print('IMPORT_WORKFLOW_OK')
