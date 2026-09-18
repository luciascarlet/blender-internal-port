# SPDX-License-Identifier: GPL-2.0-or-later
"""Windowed regression: run in a disposable --factory-startup Blender process.
Exercises actual redraw/context resolution, not a fake bpy context. Quits that
process after recording the result; never run this in a user's working session.
"""
from pathlib import Path
import os
import sys
import json
import traceback
import bpy
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
for cls in BI.render_ui.CLASSES:
    if issubclass(cls, bpy.types.Panel):
        cls.bl_options = set()
BI.register()
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
window = bpy.context.window
editor = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
properties = next(a for a in window.screen.areas if a.type == 'PROPERTIES')
properties.spaces.active.context = 'MATERIAL'
editor.type = 'NODE_EDITOR'
editor.ui_type = BI.legacy_ui.TREE
obj = bpy.data.objects['Cube']
obj.data.materials.clear()
bpy.context.view_layer.objects.active = obj
space = editor.spaces.active
checks = []
phase = 0
state = {}
report = ROOT / 'artifacts/ui-workflow.json'


def operator_context(area):
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(window=window, area=area, region=region)


def check_graph(tree, label):
    assert space.node_tree == tree and space.edit_tree == tree, (label, space.node_tree, space.edit_tree)
    assert len(space.path) == 1
    assert all(n.dimensions.x > 0 and n.dimensions.y > 0 for n in tree.nodes), 'Nodes never drew'
    checks.append(label)


def tick():
    global phase
    try:
        if phase == 0:
            with operator_context(editor):
                assert bpy.ops.material.internal_new_tree() == {'FINISHED'}
            state['material'] = obj.active_material
            state['tree'] = obj.active_material.classic_internal.node_tree
        elif phase == 1:
            check_graph(state['tree'], 'New Material Nodes draws an owned graph after redraw')
            assert space.id == obj.active_material and space.id_from == obj
            other = bpy.data.objects.new('Empty material object', bpy.data.meshes.new('Empty'))
            scene.collection.objects.link(other)
            state['other'] = other
            bpy.context.view_layer.objects.active = other
        elif phase == 2:
            assert space.node_tree is None, 'Unpinned editor did not follow active object'
            with operator_context(editor):
                bpy.ops.material.internal_new_tree()
            orphan = bpy.data.node_groups.new('Previously unattached graph', BI.legacy_ui.TREE)
            orphan.nodes.new('BI_ShaderNodeRGB')
            orphan.nodes.new('BI_ShaderNodeOutput').location = (300, 0)
            state['other'].active_material.classic_internal.node_tree = orphan
            state['orphan'] = orphan
        elif phase == 3:
            check_graph(state['orphan'], 'Existing unattached graph becomes editable when assigned')
            space.pin = True
            bpy.context.view_layer.objects.active = obj
        elif phase == 4:
            check_graph(state['orphan'], 'Pinned graph survives object selection changes')
            space.pin = False
        elif phase == 5:
            check_graph(state['tree'], 'Unpin follows the active material again')
            slot = obj.active_material.classic_internal.texture_slots.add()
            slot.texture = bpy.data.textures.new('Texture editor test', 'CLOUDS')
            slot.texture.use_nodes = True
            state['texture'] = slot.texture
            with operator_context(properties):
                assert bpy.ops.material.internal_edit_texture_nodes(index=0) == {'FINISHED'}
        elif phase == 6:
            check_graph(state['texture'].node_tree, 'Texture slot opens its real embedded graph')
            assert space.pin and space.tree_type == 'TextureNodeTree'
            with operator_context(properties):
                assert bpy.ops.material.internal_edit_nodes() == {'FINISHED'}
        elif phase == 7:
            check_graph(state['tree'], 'Return from texture editor to material graph')
            assert not space.pin
            with operator_context(properties):
                assert bpy.ops.material.internal_new_material() == {'FINISHED'}
        elif phase == 8:
            copied = obj.active_material
            assert copied != state['material']
            check_graph(copied.classic_internal.node_tree, 'Copied material resolves an independent graph')
            node = next(n for n in copied.classic_internal.node_tree.nodes if hasattr(n, 'material'))
            assert node.material == copied
            group = copied.classic_internal.node_tree.nodes.new('BI_ShaderNodeGroup')
            copied.classic_internal.node_tree.nodes.active = group
            state['group'] = group
            with operator_context(editor):
                assert bpy.ops.node.internal_new_group() == {'FINISHED'}
                assert bpy.ops.node.internal_group_edit() == {'FINISHED'}
        elif phase == 9:
            group = state['group']
            assert space.edit_tree == group.node_tree and len(space.path) == 2
            group.node_tree.interface.new_socket(name='Strength', in_out='INPUT', socket_type='NodeSocketFloat')
            assert len(group.inputs) == 2
            with operator_context(editor):
                assert bpy.ops.node.internal_group_edit() == {'FINISHED'}
            checks.append('Create group, edit interface, enter group and return to parent')
        elif phase == 10:
            check_graph(obj.active_material.classic_internal.node_tree, 'Group editing preserves the material root')
            properties.spaces.active.context = 'RENDER'
        elif phase == 11:
            assert properties.spaces.active.context == 'RENDER'
            scene.classic_internal.source = 'ARCHIVE'
            scene.classic_internal.override_archive_render = True
            scene.classic_internal.legacy.raytrace_method = 'OCTREE'
            checks.append('Expanded current-scene render panels redraw without RNA errors')
        elif phase == 12:
            checks.append('Expanded archive override panels redraw without RNA errors')
            properties.spaces.active.context = 'OUTPUT'
        elif phase == 13:
            assert properties.spaces.active.context == 'OUTPUT'
            checks.append('Native output properties remain available')
            report.write_text(json.dumps({'passed': True, 'version': bpy.app.version_string, 'checks': checks}, indent=2))
            print('UI_WORKFLOW_OK', len(checks), flush=True)
            bpy.ops.wm.quit_blender()
            return None
        phase += 1
        editor.tag_redraw()
        properties.tag_redraw()
        return 0.5
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        report.write_text(json.dumps({'passed': False, 'phase': phase, 'checks': checks, 'error': error}, indent=2))
        bpy.ops.wm.quit_blender()
        return None

bpy.app.timers.register(tick, first_interval=1.0)
