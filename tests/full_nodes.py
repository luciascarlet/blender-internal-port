# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise every registered legacy node, groups, storage ownership and reload."""
from pathlib import Path
import sys
import os
import json
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_export as E, full_native as N
BI.register()
checks = []
with N.LOCK:
    for kind in sorted(BI.legacy_ui.SCHEMA['nodes']):
        tree = bpy.data.node_groups.new(kind, BI.legacy_ui.TREE)
        node = tree.nodes.new('BI_' + kind)
        host = N.Scene()
        material = host.create('MATERIAL', 'Test')
        E.export_tree(host, material, tree)
        checks.append(kind)

    group = bpy.data.node_groups.new('Group arithmetic', BI.legacy_ui.TREE)
    group.interface.new_socket(name='Value', in_out='INPUT', socket_type='NodeSocketFloat')
    group.interface.new_socket(name='Value', in_out='OUTPUT', socket_type='NodeSocketFloat')
    inp = group.nodes.new('NodeGroupInput')
    out = group.nodes.new('NodeGroupOutput')
    math = group.nodes.new('BI_ShaderNodeMath')
    math.legacy_operation = 'MULTIPLY'
    math.inputs[1].default_value = 0.5
    group.links.new(inp.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], out.inputs[0])
    tree = bpy.data.node_groups.new('Group caller', BI.legacy_ui.TREE)
    tree.use_fake_user = True
    call = tree.nodes.new('BI_ShaderNodeGroup')
    call.node_tree = group
    assert len(call.inputs) == 1 and len(call.outputs) == 1
    call.inputs[0].default_value = 0.8
    out = tree.nodes.new('BI_ShaderNodeOutput')
    tree.links.new(call.outputs[0], out.inputs[0])
    host = N.Scene()
    E.export_tree(host, host.create('MATERIAL', 'Group'), tree)
    checks.append('group interface and links')

    for kind in sorted(BI.legacy_ui.SCHEMA['texture_nodes']):
        texture = bpy.data.textures.new(kind, 'NONE')
        texture.use_nodes = True
        texture.node_tree.nodes.clear()
        replacement = {'TextureNodeCompose': 'TextureNodeCombineColor', 'TextureNodeDecompose': 'TextureNodeSeparateColor'}
        texture.node_tree.nodes.new(replacement.get(kind, kind))
        host = N.Scene()
        E.export_texture(host, texture)
        checks.append(kind)

    # A copied ramp must not keep an editable backing tree shared with its source.
    tree = bpy.data.node_groups.new('Storage copy', BI.legacy_ui.TREE)
    ramp = tree.nodes.new('BI_ShaderNodeValToRGB')
    duplicate = tree.copy()
    copied = duplicate.nodes[0]
    assert copied.storage != ramp.storage, 'Copied nodes alias their curve/ramp storage'
    copied.storage.nodes[0].color_ramp.elements[0].color = (0.7, 0.2, 0.1, 1)
    assert ramp.storage.nodes[0].color_ramp.elements[0].color[0] == 0
    checks.append('independent copied node storage')

    # Exercise the actual Create Legacy Nodes button, including its self-material
    # reference. It must preserve the material's initial appearance.
    import numpy as np
    obj = bpy.data.objects['Cube']
    bpy.context.view_layer.objects.active = obj
    material = bpy.data.materials.new('New node material')
    material.classic_internal.shadeless = True
    material.classic_internal.color = (0.2, 0.5, 0.1)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    class Observer:
        def test_break(self): return False
        def update_progress(self, value): pass
    observer = Observer()
    host = E.export_scene(bpy.context.evaluated_depsgraph_get(), observer)
    before, _, _ = host.render(1, 64, 64, observer)
    assert bpy.ops.material.internal_new_tree() == {'FINISHED'}
    host = E.export_scene(bpy.context.evaluated_depsgraph_get(), observer)
    after, _, _ = host.render(1, 64, 64, observer)
    assert np.max(np.abs(before-after)) < 1e-5
    checks.append('create nodes operator preserves appearance')

path = ROOT / 'artifacts/full-nodes.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
with N.LOCK:
    host = N.Scene()
    E.export_tree(host, host.create('MATERIAL', 'Reload'), bpy.data.node_groups['Group caller'])
checks.append('saved node graph reload')
(ROOT / 'artifacts/full-nodes.json').write_text(json.dumps(checks, indent=2))
print('FULL_NODES_OK', len(checks))
