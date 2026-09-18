#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the original Internal pipeline with the isolated modern-host ABI."""
from pathlib import Path
import argparse
import json
import platform
import shutil
import subprocess
from build_dependencies import build as build_dependencies
from build_platform import cmake_defaults, full_library, static_library

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def build(skip_dependencies=False):
    prefix = ROOT / 'build-deps/install' if skip_dependencies else build_dependencies()
    source = ROOT / 'blender-legacy'
    work = ROOT / 'blender-legacy-port'
    revision = json.loads((ROOT / 'versions.json').read_text())['legacy']['commit']
    if not source.exists() and (ROOT / 'upstream/blender-2.79b.tar.gz').exists():
        run(['tar', '-xf', ROOT / 'upstream/blender-2.79b.tar.gz', '-C', ROOT])
    if not source.exists():
        raise RuntimeError('Run scripts/clone_sources.py first (or unpack the corresponding source bundle)')
    if (source / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision:
            raise RuntimeError('Legacy checkout does not match versions.json')
    if not work.exists():
        if (source / '.git').exists():
            run(['git', '-C', source, 'worktree', 'add', '--detach', work, revision])
        else:
            shutil.copytree(source, work)
    for patch_name in ('legacy-full-host.patch', 'legacy-ray-stack.patch', 'legacy-portable-host.patch'):
        patch = ROOT / 'patches' / patch_name
        applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=work,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not applied:
            run(['git', 'apply', '--check', patch], cwd=work)
            run(['git', 'apply', patch], cwd=work)
    libraries = {'ZLIB_LIBRARY': 'z', 'PNG_LIBRARY_RELEASE': 'png',
                 'JPEG_LIBRARY': 'jpeg', 'FREETYPE_LIBRARY_RELEASE': 'freetype'}
    options = cmake_defaults() + [
               '-DINTERNAL_DEPS_ROOT=' + str(prefix), '-DWITH_HEADLESS=ON',
               '-DWITH_PYTHON=OFF', '-DWITH_CPU_SSE=OFF', '-DWITH_CXX11=ON',
               '-DWITH_SYSTEM_GLEW=OFF', '-DWITH_BLENDER=ON', '-DWITH_PLAYER=OFF',
               '-DWITH_INPUT_IME=OFF', '-DWITH_BINRELOC=OFF']
    if platform.system() != 'Windows':
        options += ['-DCMAKE_C_FLAGS=-fcommon -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=int-conversion']
    options += ['-D' + key + '=' + str(static_library(prefix, value)) for key, value in libraries.items()]
    options += ['-D' + key + '=' + str(prefix / 'include') for key in ('ZLIB_INCLUDE_DIR', 'PNG_PNG_INCLUDE_DIR', 'JPEG_INCLUDE_DIR')]
    options += ['-D' + key + '=' + str(prefix / 'include/freetype2') for key in ('FREETYPE_INCLUDE_DIR_freetype2', 'FREETYPE_INCLUDE_DIR_ft2build')]
    run(['cmake', '-S', work, '-B', ROOT / 'build-full', '-C', work / 'build_files/cmake/config/blender_lite.cmake'] + options)
    run(['cmake', '--build', ROOT / 'build-full', '--config', 'Release', '--target', 'blender_internal_full', '-j4'])
    library = full_library()
    if platform.system() == 'Windows':
        shutil.copyfile(prefix / 'bin/pthreadVC3.dll', library.parent / 'pthreadVC3.dll')
    if platform.system() == 'Darwin':
        links = subprocess.check_output(['otool', '-L', str(library)], text=True)
        for line in links.splitlines()[2:]:
            dependency = line.strip().split(' (', 1)[0]
            if not dependency.startswith(('/System/Library/', '/usr/lib/')):
                raise RuntimeError('Non-system runtime dependency remains: ' + dependency)
    return library


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-dependencies', action='store_true')
    args = parser.parse_args()
    print(build(args.skip_dependencies))
