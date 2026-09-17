# SPDX-License-Identifier: GPL-2.0-or-later
"""Versioned ctypes interface, usable both inside Blender and in standalone tests."""
import ctypes as C
from pathlib import Path
import sys

F3 = C.c_float * 3
F9 = C.c_float * 9

class Triangle(C.Structure):
    _fields_ = [('p', F9), ('n', F9), ('material', C.c_int32)]

class Material(C.Structure):
    _fields_ = [('color', F3), ('specular_color', F3)] + [
        (name, C.c_float) for name in (
            'diffuse_intensity', 'specular_intensity', 'roughness', 'darkness',
            'diffuse_size', 'diffuse_smooth', 'specular_size', 'specular_smooth',
            'ior', 'slope', 'emission')] + [
        (name, C.c_int32) for name in ('diffuse_shader', 'specular_shader', 'hardness', 'shadeless')]

class Light(C.Structure):
    _fields_ = [(name, F3) for name in ('position', 'direction', 'color')] + [
        (name, C.c_float) for name in ('energy', 'distance', 'spot_cos', 'spot_blend')] + [
        ('type', C.c_int32), ('shadows', C.c_int32)]

class Camera(C.Structure):
    _fields_ = [(name, F3) for name in ('origin', 'lower_left', 'horizontal', 'vertical', 'forward')] + [
        ('clip_start', C.c_float), ('clip_end', C.c_float), ('orthographic', C.c_int32)]

class Settings(C.Structure):
    _fields_ = [('background', F3), ('ambient', C.c_float)] + [
        (name, C.c_int32) for name in ('width', 'height', 'sample_grid', 'transparent', 'shadows')]

_library = None

def load():
    global _library
    if _library is not None:
        return _library
    name = ('blender_internal_core.dll' if sys.platform == 'win32' else
            'libblender_internal_core.dylib' if sys.platform == 'darwin' else
            'libblender_internal_core.so')
    path = Path(__file__).parent / name
    if not path.exists():
        raise RuntimeError('Native Blender Internal library is missing. Run scripts/build.py first.')
    lib = C.CDLL(str(path))
    lib.bi_abi_version.restype = C.c_int
    lib.bi_struct_size.argtypes = [C.c_int]
    lib.bi_struct_size.restype = C.c_int
    if lib.bi_abi_version() != 1:
        raise RuntimeError('Incompatible Blender Internal native ABI')
    for index, structure in enumerate((Triangle, Material, Light, Camera, Settings)):
        if C.sizeof(structure) != lib.bi_struct_size(index):
            raise RuntimeError('Native structure layout mismatch: ' + structure.__name__)
    lib.bi_last_error.restype = C.c_char_p
    lib.bi_scene_create.argtypes = [C.POINTER(Triangle), C.c_int, C.POINTER(Material), C.c_int, C.POINTER(Light), C.c_int]
    lib.bi_scene_create.restype = C.c_void_p
    lib.bi_scene_destroy.argtypes = [C.c_void_p]
    lib.bi_scene_destroy.restype = None
    lib.bi_render_rows.argtypes = [C.c_void_p, C.POINTER(Camera), C.POINTER(Settings), C.c_int, C.c_int, C.POINTER(C.c_float)]
    lib.bi_render_rows.restype = C.c_int
    for name in ('bi_diffuse', 'bi_specular'):
        fn = getattr(lib, name)
        fn.argtypes = [C.POINTER(Material), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float)]
        fn.restype = C.c_float
    _library = lib
    return lib

def default_material():
    m = Material()
    m.color[:] = (0.8, 0.8, 0.8)
    m.specular_color[:] = (1, 1, 1)
    m.diffuse_intensity = 0.8
    m.specular_intensity = 0.5
    m.roughness = 0.5
    m.darkness = 1
    m.diffuse_size, m.diffuse_smooth = 0.5, 0.1
    m.specular_size, m.specular_smooth = 0.5, 0.1
    m.ior, m.slope, m.hardness = 4, 0.1, 50
    return m
