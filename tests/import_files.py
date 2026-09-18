# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise user-supplied legacy scenes without modifying or bundling the originals.

blender -b --factory-startup --python-exit-code 1 --python tests/import_files.py -- file.blend ...
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
import blender_internal as BI
from blender_internal import full_native as N, full_export as E
BI.register()
OUT = ROOT / 'artifacts/file-imports'
OUT.mkdir(parents=True, exist_ok=True)

class Observer:
    def test_break(self): return False
    def update_progress(self, value): pass

report = {}
original_ids = set(bpy.data.user_map())
for argument in sys.argv[sys.argv.index('--') + 1:]:
    path = Path(argument).resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with N.LOCK:
        reader = BI.legacy_import.Reader(str(path))
        snapshot = reader.snapshot()
        object_counts = {reader.name(s): len(reader.value(s, 'objects'))
                         for s in reader.value(reader.main, 'scenes')}
    before = set(bpy.data.user_map())
    scenes = BI.legacy_import.import_file(str(path))
    created = set(bpy.data.user_map()) - before
    assert len(scenes) == len(snapshot['scenes'])
    assert sorted(len(s.objects) for s in scenes) == sorted(object_counts.values())
    materials = [d for d in created if isinstance(d, bpy.types.Material)]
    assert len(materials) == len(snapshot['materials'])
    slots = [slot for m in materials for slot in m.classic_internal.texture_slots]
    assert len([slot for slot in slots if slot.texture]) == sum(
        bool(s['texture']) for m in snapshot['materials'].values() for s in m['slots'])
    images = [d for d in created if isinstance(d, bpy.types.Image) and d.source == 'FILE']
    for image in images:
        assert image.size[0] > 0, (image.name, image.filepath)
    results = []
    for scene in scenes:
        bpy.context.window.scene = scene
        scene.render.resolution_x = 320
        scene.render.resolution_y = 240
        scene.render.resolution_percentage = 100
        bpy.context.view_layer.update()
        with N.LOCK:
            host = E.export_scene(bpy.context.evaluated_depsgraph_get(), Observer())
            pixels, width, height = host.render(scene.frame_current, 320, 240, Observer())
        assert np.isfinite(pixels).all()
        assert float(pixels[:, :3].max() - pixels[:, :3].min()) > 0.01
        pixels.tofile(OUT / (path.stem + '-import.rgba'))
        image = bpy.data.images.new('Imported render', width, height, alpha=True, float_buffer=True)
        image.pixels.foreach_set(pixels.ravel())
        image.save_render(str(OUT / (path.stem + '-import.png')), scene=scene)
        bpy.data.images.remove(image)
        results.append({'objects': len(scene.objects), 'render_finite': True})
    saved = OUT / (path.stem + '-imported.blend')
    bpy.data.libraries.write(str(saved), set(scenes), path_remap='ABSOLUTE')
    with bpy.data.libraries.load(str(saved), link=False) as (source, dest):
        dest.scenes = list(source.scenes)
    assert sorted(len(s.objects) for s in dest.scenes) == sorted(object_counts.values())
    assert original_ids <= set(bpy.data.user_map()), 'Import removed existing user data'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    report[path.name] = {'scenes': results, 'materials': len(materials),
                         'texture_slots': len([s for s in slots if s.texture]),
                         'file_images': len(images), 'packed_images': sum(bool(i.packed_file) for i in images),
                         'save_reopen': True, 'source_unchanged': True}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    print('FILE_IMPORT_OK', path.name, report[path.name], flush=True)
BI.unregister()
