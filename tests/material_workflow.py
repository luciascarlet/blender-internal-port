# SPDX-License-Identifier: GPL-2.0-or-later
"""Material ownership, real slot operators, UI/export agreement and lifecycle."""
from pathlib import Path
import os
import sys
import json
from types import SimpleNamespace
import bpy
import bmesh
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import legacy_ui as U, full_export as E, full_native as N
from blender_internal.legacy_import import Reader
header = bpy.types.NODE_HT_header._dyn_ui_initialize()[0]
BI.register()
checks = []
scene = bpy.context.scene
scene.render.engine = BI.ENGINE
obj = bpy.data.objects['Cube']
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
obj.data.materials.clear()
assert BI.material_ui.BI_PT_material_slots.poll(bpy.context)
assert bpy.ops.material.internal_new_tree.poll()
assert bpy.ops.material.internal_new_tree() == {'FINISHED'}
mat = obj.active_material
assert mat is not None, 'New Nodes did not assign a material to the object'
tree = mat.classic_internal.node_tree
assert tree and len(tree.nodes) == 2
assert U.LegacyTree.get_from_context(bpy.context) == (tree, mat, obj)
checks.append('empty object: create, assign, and resolve material nodes')
assert all(s.hide_value for n in tree.nodes if hasattr(n, 'material') for s in n.inputs)
checks.append('material-node sockets do not offer ignored defaults')
second = bpy.data.materials.new('Second slot')
assert bpy.ops.object.material_slot_add() == {'FINISHED'}
obj.active_material = second
assert obj.active_material_index == 1
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(obj.data)
for face in bm.faces:
    face.select_set(False)
bm.faces.ensure_lookup_table()
bm.faces[0].select_set(True)
bmesh.update_edit_mesh(obj.data)
assert bpy.ops.object.material_slot_assign() == {'FINISHED'}
bpy.ops.object.material_slot_deselect()
assert not any(f.select for f in bm.faces)
bpy.ops.object.material_slot_select()
assert [f.index for f in bm.faces if f.select] == [0]
bpy.ops.object.mode_set(mode='OBJECT')
assert [p.material_index for p in obj.data.polygons] == [1, 0, 0, 0, 0, 0]
checks.append('native edit-mode Assign, Select and Deselect')
assert U.LegacyTree.get_from_context(bpy.context) == (None, second, obj)
second.classic_internal.node_tree = tree
assert U.LegacyTree.get_from_context(bpy.context)[0] == tree
obj.active_material_index = 0
checks.append('switch slots and assign an existing node tree')
assert bpy.ops.material.internal_new_tree() == {'FINISHED'}
assert mat.classic_internal.node_tree != tree
assert second.classic_internal.node_tree == tree
checks.append('tree duplicate leaves other material intact')

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass
observer = Observer()
reader = Reader.__new__(Reader)
reader.lib = N.load()
with N.LOCK:
    # UI edits must hit the same RNA field that the native renderer sees in both
    # an early adapter material and an imported material.
    for full in (False, True):
        mat.classic_internal.use_legacy_settings = full
        for field, value in [('diffuse_color', (0.8, 0.05, 0.1)), ('emit', 0.7), ('alpha', 0.3),
                             ('use_transparency', True), ('transparency_method', 'RAYTRACE')]:
            owner, name = U.material_property(mat, field)
            setattr(owner, name, value)
            host = N.Scene()
            handle = E.export_material(host, mat)
            actual = reader.value(handle, field)
            if isinstance(value, (tuple, float)):
                assert np.allclose(actual, value), (full, field, actual, value)
            else:
                assert actual == value, (full, field, actual, value)
        checks.append('visible properties reach native material: ' + ('imported' if full else 'new'))
    mat.classic_internal.use_legacy_settings = False
    mat.classic_internal.legacy.use_transparency = False
    owner, name = U.material_property(mat, 'use_shadeless')
    setattr(owner, name, True)
    obj.active_material_index = 0
    for face in obj.data.polygons:
        face.material_index = 0
    def render(color):
        owner, name = U.material_property(mat, 'diffuse_color')
        setattr(owner, name, color)
        mat.update_tag()
        host = E.export_scene(bpy.context.evaluated_depsgraph_get(), observer)
        return host.render(1, 48, 48, observer)[0]
    red, green = render((0.8, 0.02, 0.02)), render((0.02, 0.8, 0.02))
    assert np.max(np.abs(red-green)) > 0.5
    checks.append('editing node material color changes rendered pixels')

# Copy through the UI action: editing its color must not keep shading the source.
assert bpy.ops.material.internal_new_material() == {'FINISHED'}
copied = obj.active_material
assert copied != mat and copied.classic_internal.node_tree != mat.classic_internal.node_tree
assert next(n.material for n in copied.classic_internal.node_tree.nodes if hasattr(n, 'material')) == copied
copied.classic_internal.color = (0.8, 0.05, 0.05)
assert not np.allclose(mat.classic_internal.color, copied.classic_internal.color)
obj.active_material = mat
checks.append('New Material copies graph and retargets self-material shading')

assert bpy.ops.material.internal_ramps() == {'FINISHED'}
mat.classic_internal.legacy.use_diffuse_ramp = True
ramp = mat.classic_internal.ramp_storage.nodes['diffuse_ramp'].color_ramp
ramp.elements[0].color = (0.2, 0.4, 0.8, 1)
with N.LOCK:
    host = N.Scene()
    handle = E.export_material(host, mat)
    assert np.allclose(reader.value(handle, 'diffuse_ramp.elements[0].color'), (0.2, 0.4, 0.8, 1))
    mat.classic_internal.use_nodes = False
    host = N.Scene()
    handle = E.export_material(host, mat)
    assert not reader.value(handle, 'use_nodes')
mat.classic_internal.use_nodes = True
checks.append('material ramp editing and Use Nodes toggle reach native renderer')

assert bpy.ops.material.internal_texture_slot() == {'FINISHED'}
slot = mat.classic_internal.texture_slots[0]
slot.texture = bpy.data.textures.new('Clouds', 'CLOUDS')
slot.settings.diffuse_color_factor = 0.7
with N.LOCK:
    host = N.Scene()
    handle = E.export_material(host, mat)
    assert reader.value(handle, 'texture_slots[0].texture.type') == 'CLOUDS'
    assert abs(reader.value(handle, 'texture_slots[0].diffuse_color_factor') - 0.7) < 1e-5
checks.append('texture slot controls reach native texture')

# Exercise all panel and node draw functions with RNA validation, including
# conditional branches. A separate interactive harness checks actual layout.
class Layout:
    def __init__(self): self.properties = []
    def prop(self, data, name, **kwargs):
        assert hasattr(data, name), (type(data).__name__, name)
        self.properties.append((data, name))
    def template_ID(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
    def panel(self, *args, **kwargs): return self, self
    def operator(self, *args, **kwargs): return SimpleNamespace()
    def __getattr__(self, name): return lambda *args, **kwargs: self
layout = Layout()
context = SimpleNamespace(material=mat, object=obj, scene=scene, engine=BI.ENGINE)
panel = SimpleNamespace(layout=layout)
for cls in BI.material_ui.CLASSES:
    cls.draw(panel, context)
BI.CLASSIC_PT_material.draw(panel, context)
BI.CLASSIC_PT_textures.draw(panel, context)
for kind in U.SCHEMA['textures']:
    slot.texture.type = kind
    BI.material_ui.draw_texture(layout, slot, '0')
for kind in U.SCHEMA['nodes']:
    node = tree.nodes.new('BI_' + kind)
    node.draw_buttons(bpy.context, layout)
    tree.nodes.remove(node)
checks.append('all material panels, texture types and shader node draw callbacks')
path = ROOT / 'artifacts/material-workflow.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
assert bpy.data.objects['Cube'].active_material.classic_internal.node_tree
checks.append('material and tree ownership survive save/reload')
BI.unregister()
assert bpy.types.NODE_HT_header._dyn_ui_initialize()[0] is header
assert BI.ENGINE not in bpy.types.EEVEE_MATERIAL_PT_context_material.COMPAT_ENGINES
BI.register()
assert bpy.types.NODE_HT_header._dyn_ui_initialize().count(U.draw_header) == 1
checks.append('unregister restores stock header and registration is repeatable')
(ROOT / 'artifacts/material-workflow.json').write_text(json.dumps(checks, indent=2))
print('MATERIAL_WORKFLOW_OK', len(checks))
