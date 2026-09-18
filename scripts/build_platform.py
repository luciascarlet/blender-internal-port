# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared native build conventions (also used by package verification)."""
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def library_name(component, published=False):
    component += '_v2' if published and component == 'full' else ''
    if platform.system() == 'Windows':
        return 'blender_internal_' + component + '.dll'
    return 'libblender_internal_' + component + ('.dylib' if platform.system() == 'Darwin' else '.so')


def full_library():
    return ROOT / 'build-full/lib' / library_name('full')


def static_library(prefix, component):
    names = {'z': ('zlibstatic.lib', 'libz.a'),
             'png': ('libpng16_static.lib', 'libpng16.a'),
             'jpeg': ('jpeg-static.lib', 'libjpeg.a'),
             'freetype': ('freetype.lib', 'libfreetype.a')}
    return prefix / 'lib' / names[component][platform.system() != 'Windows']


def cmake_defaults():
    options = ['-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_LIBDIR=lib',
               '-DCMAKE_POSITION_INDEPENDENT_CODE=ON']
    if platform.system() == 'Darwin':
        options += ['-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0',
                    '-DCMAKE_OSX_ARCHITECTURES=' + platform.machine()]
    return options
