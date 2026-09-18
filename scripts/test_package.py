#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the distributed ZIP, then render in a fresh process outside the checkout."""
import argparse
import ast
import ctypes as C
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def load_module(directory, name):
    spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(directory):
    load_module(directory, 'native').load()  # Verify the prototype ABI too.
    native = load_module(directory, 'full_native')
    scene = native.Scene()
    camera = scene.create('CAMERA', 'Camera')
    scene.set(camera, 'location', (0, 0, 5))
    world = scene.create('WORLD', 'World')
    scene.set(world, 'horizon_color', (0.05, 0.1, 0.2))
    mesh = scene.create('MESH', 'Triangle')
    scene.check(scene.lib.bi_full_mesh(mesh, 3,
        (C.c_float * 9)(-1, -1, 0, 1, -1, 0, 0, 1, 0), 1,
        (C.c_int * 1)(0), (C.c_int * 1)(3), 3,
        (C.c_int * 3)(0, 1, 2), (C.c_int * 1)(0), (C.c_ubyte * 1)(0), None))
    material = scene.create('MATERIAL', 'Red')
    scene.set(material, 'diffuse_color', (0.8, 0.1, 0.05))
    scene.set(material, 'use_shadeless', True)
    scene.check(scene.lib.bi_full_mesh_material(mesh, material, 1))
    scene.set(scene.handle, 'render.threads_mode', 'FIXED')
    scene.set(scene.handle, 'render.threads', 2)
    scene.check(scene.lib.bi_full_render(1, 32, 32))
    pixels = (C.c_float * (32 * 32 * 4))()
    width, height = C.c_int(), C.c_int()
    scene.check(scene.lib.bi_full_result(pixels, len(pixels), C.byref(width), C.byref(height)))
    assert (width.value, height.value) == (32, 32)
    assert all(math.isfinite(x) for x in pixels)
    center = (16 * 32 + 16) * 4
    assert pixels[center] > pixels[center + 2] * 2, 'Triangle did not render red'
    assert pixels[2] > pixels[0], 'Background did not render blue'
    assert pixels[center + 3] > 0.99
    print('PACKAGED_RENDER_OK', flush=True)


def verify():
    from build_platform import ROOT, library_name
    archives = list((ROOT / 'dist').glob('blender-internal-port-*.zip'))
    expected_name = 'blender-internal-port-'
    import platform
    expected_name += platform.system().lower() + '-' + platform.machine() + '.zip'
    package = ROOT / 'dist' / expected_name
    if package not in archives:
        raise RuntimeError('No package for this host: ' + str(package))
    with tempfile.TemporaryDirectory(prefix='bi-package-') as temporary:
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
            names = set(archive.namelist())
            assert all(name.startswith('blender_internal/') and '\\' not in name for name in names)
            required = {'__init__.py', 'full_native.py', 'native.py', 'LICENSE', 'build_manifest.json',
                        'source/upstream/blender-2.79b.tar.gz', 'source/patches/legacy-portable-host.patch'}
            expected_libraries = {library_name('core'), library_name('full', published=True)}
            if sys.platform == 'win32':
                expected_libraries.add('pthreadVC3.dll')
            required |= expected_libraries
            for name in required:
                assert 'blender_internal/' + name in names, 'Missing package member: ' + name
            actual_libraries = {Path(name).name for name in names
                                if len(Path(name).parts) == 2 and Path(name).suffix in ('.dll', '.dylib', '.so')}
            assert actual_libraries == expected_libraries, actual_libraries
            for name in names:
                if name.endswith('.py'):
                    source = archive.read(name)
                    tree = ast.parse(source, filename=name)
                    # Catch omitted sibling modules without importing bpy outside Blender.
                    if len(Path(name).parts) == 2:
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ImportFrom) and node.level == 1:
                                modules = [node.module.split('.')[0]] if node.module else [a.name for a in node.names]
                                for module in modules:
                                    assert 'blender_internal/' + module + '.py' in names, module
            archive.extractall(temporary)
        directory = Path(temporary) / 'blender_internal'
        manifest = json.loads((directory / 'build_manifest.json').read_text())
        digest = hashlib.sha256((directory / library_name('full', published=True)).read_bytes()).hexdigest()
        assert digest == manifest['native_sha256']
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--render', str(directory)],
                       cwd=temporary, check=True, timeout=120)
    print('PACKAGE_OK', package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--render', type=Path)
    args = parser.parse_args()
    render(args.render) if args.render else verify()
