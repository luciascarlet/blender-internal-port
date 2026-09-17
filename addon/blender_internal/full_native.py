# SPDX-License-Identifier: GPL-2.0-or-later
"""Serialized, versioned boundary to the complete legacy renderer."""
import ctypes as C
from pathlib import Path
import sys
import threading

LOCK = threading.RLock()
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)
PROGRESS = C.CFUNCTYPE(None, C.c_void_p, C.c_float)
_library = None

def load():
    global _library
    if _library is not None:
        return _library
    name = 'libblender_internal_full.dylib' if sys.platform == 'darwin' else 'libblender_internal_full.so'
    path = Path(__file__).parent / name
    # Development builds use the same library that the package will ship.
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / 'build-full/lib' / name
    lib = C.CDLL(str(path))
    prototypes = {
        'bi_full_abi_version': (C.c_int, []),
        'bi_full_error': (C.c_char_p, []),
        'bi_full_initialize': (C.c_int, [C.c_char_p]),
        'bi_full_load': (C.c_int, [C.c_char_p]),
        'bi_full_main': (C.c_int, []),
        'bi_full_scene_current': (C.c_int, [C.c_char_p]),
        'bi_full_property_info': (C.c_int, [C.c_int, C.c_char_p, C.POINTER(C.c_int)]),
        'bi_full_get_numbers': (C.c_int, [C.c_int, C.c_char_p, C.POINTER(C.c_double), C.c_int]),
        'bi_full_get_string': (C.c_int, [C.c_int, C.c_char_p, C.c_char_p, C.c_int]),
        'bi_full_get_pointer': (C.c_int, [C.c_int, C.c_char_p]),
        'bi_full_collection_item': (C.c_int, [C.c_int, C.c_char_p, C.c_int]),
        'bi_full_scene_new': (C.c_int, []),
        'bi_full_create': (C.c_int, [C.c_char_p, C.c_char_p]),
        'bi_full_set_numbers': (C.c_int, [C.c_int, C.c_char_p, C.POINTER(C.c_double), C.c_int]),
        'bi_full_set_string': (C.c_int, [C.c_int, C.c_char_p, C.c_char_p]),
        'bi_full_set_pointer': (C.c_int, [C.c_int, C.c_char_p, C.c_int]),
        'bi_full_mesh': (C.c_int, [C.c_int, C.c_int, C.POINTER(C.c_float), C.c_int,
            C.POINTER(C.c_int), C.POINTER(C.c_int), C.c_int, C.POINTER(C.c_int),
            C.POINTER(C.c_int), C.POINTER(C.c_ubyte), C.POINTER(C.c_float)]),
        'bi_full_mesh_material': (C.c_int, [C.c_int, C.c_int, C.c_int]),
        'bi_full_mesh_uv': (C.c_int, [C.c_int, C.c_char_p, C.c_int, C.POINTER(C.c_float)]),
        'bi_full_material_tree': (C.c_int, [C.c_int]),
        'bi_full_texture_tree': (C.c_int, [C.c_int]),
        'bi_full_texture_group': (C.c_int, [C.c_char_p]),
        'bi_full_tree_create': (C.c_int, [C.c_char_p]),
        'bi_full_tree_socket': (C.c_int, [C.c_int, C.c_int, C.c_char_p, C.c_char_p]),
        'bi_full_node': (C.c_int, [C.c_int, C.c_char_p]),
        'bi_full_node_link': (C.c_int, [C.c_int, C.c_int, C.c_int, C.c_int, C.c_int]),
        'bi_full_ramp': (C.c_int, [C.c_int, C.c_char_p, C.c_int, C.POINTER(C.c_float), C.POINTER(C.c_float)]),
        'bi_full_curve': (C.c_int, [C.c_int, C.c_char_p, C.c_int, C.c_int, C.POINTER(C.c_float), C.POINTER(C.c_int)]),
        'bi_full_image': (C.c_int, [C.c_char_p, C.c_int, C.c_int, C.POINTER(C.c_float)]),
        'bi_full_image_bytes': (C.c_int, [C.c_char_p, C.c_int, C.c_int, C.POINTER(C.c_ubyte), C.c_int]),
        'bi_full_texture_slot': (C.c_int, [C.c_int, C.c_int, C.c_int]),
        'bi_full_render': (C.c_int, [C.c_int, C.c_int, C.c_int]),
        'bi_full_result': (C.c_int, [C.POINTER(C.c_float), C.c_uint64, C.POINTER(C.c_int), C.POINTER(C.c_int)]),
        'bi_full_pass': (C.c_int, [C.c_char_p, C.POINTER(C.c_float), C.c_uint64, C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int)]),
        'bi_full_mesh_color': (C.c_int, [C.c_int, C.c_char_p, C.c_int, C.POINTER(C.c_float)]),
        'bi_full_mesh_active_layers': (C.c_int, [C.c_int, C.c_char_p, C.c_char_p]),
        'bi_full_callbacks': (None, [CANCEL, PROGRESS, C.c_void_p]),
    }
    for name, (restype, args) in prototypes.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = restype, args
    if lib.bi_full_abi_version() != 1:
        raise RuntimeError('Full Internal engine ABI mismatch')
    if not lib.bi_full_initialize(str(path).encode()):
        raise RuntimeError(lib.bi_full_error().decode())
    _library = lib
    return lib

class Scene:
    """Caller must hold LOCK for this object's whole lifetime, including rendering."""
    def __init__(self):
        self.lib = load()
        self.handle = self.check(self.lib.bi_full_scene_new())
        self.materials = {}
        self.trees = {}
        self.objects = {}
        self.textures = {}
        self.images = {}

    def check(self, result):
        if not result:
            raise RuntimeError(self.lib.bi_full_error().decode() or 'Legacy renderer rejected scene data')
        return result

    def create(self, kind, name):
        return self.check(self.lib.bi_full_create(kind.encode(), name.encode()))

    def set(self, handle, path, value):
        if isinstance(value, str):
            return self.check(self.lib.bi_full_set_string(handle, path.encode(), value.encode()))
        if isinstance(value, (int, float, bool)):
            value = (value,)
        values = (C.c_double * len(value))(*value)
        return self.check(self.lib.bi_full_set_numbers(handle, path.encode(), values, len(value)))

    def pointer(self, handle, path, target):
        return self.check(self.lib.bi_full_set_pointer(handle, path.encode(), target))

    def render(self, frame, width, height, engine):
        import numpy as np
        cancel = CANCEL(lambda _: int(engine.test_break()))
        progress = PROGRESS(lambda _, f: engine.update_progress(f))
        self.lib.bi_full_callbacks(cancel, progress, None)
        try:
            self.check(self.lib.bi_full_render(frame, width, height))
            w, h = C.c_int(), C.c_int()
            self.check(self.lib.bi_full_result(None, 0, C.byref(w), C.byref(h)))
            pixels = np.empty((h.value*w.value, 4), dtype=np.float32)
            self.check(self.lib.bi_full_result(pixels.ctypes.data_as(C.POINTER(C.c_float)),
                                              pixels.size, C.byref(w), C.byref(h)))
            return pixels, w.value, h.value
        finally:
            # Native renderer must not retain dead Python callbacks.
            self.lib.bi_full_callbacks(CANCEL(), PROGRESS(), None)

    def render_pass(self, name):
        import numpy as np
        w, h, c = C.c_int(), C.c_int(), C.c_int()
        self.check(self.lib.bi_full_pass(name.encode(), None, 0, C.byref(w), C.byref(h), C.byref(c)))
        data = np.empty((w.value*h.value, c.value), np.float32)
        self.check(self.lib.bi_full_pass(name.encode(), data.ctypes.data_as(C.POINTER(C.c_float)), data.size,
                                        C.byref(w), C.byref(h), C.byref(c)))
        return data
