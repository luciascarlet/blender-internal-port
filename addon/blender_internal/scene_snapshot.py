# SPDX-License-Identifier: GPL-2.0-or-later
"""Copy an export into owned commands on Blender's main thread.

The render thread replays only these bytes/numbers/ctypes arrays. It never reads
bpy, a depsgraph, an RNA pointer, or borrowed NumPy/mesh memory.
"""
import ctypes as C
from . import full_native as N

class Handle(int):
    pass

# Pointer argument -> (element type, element count), for the exporter ABI.
def buffers(name, a):
    F, I, B = C.c_float, C.c_int, C.c_ubyte
    if name == 'bi_full_mesh':
        return {2: (F,a[1]*3), 4: (I,a[3]), 5: (I,a[3]), 7: (I,a[6]),
                8: (I,a[3]), 9: (B,a[3]), 10: (F,a[6]*3)}
    if name in ('bi_full_mesh_uv', 'bi_full_mesh_color'):
        return {3: (F,a[2]*(2 if name.endswith('_uv') else 4))}
    if name in ('bi_full_image', 'bi_full_image_bytes'):
        return {3: (B if name.endswith('_bytes') else F,a[1]*a[2]*4)}
    if name == 'bi_full_ramp': return {3: (F,a[2]), 4: (F,a[2]*4)}
    if name == 'bi_full_curve': return {4: (F,a[3]*2), 5: (I,a[3])}
    return {}

CREATES = {'bi_full_material_tree', 'bi_full_texture_tree', 'bi_full_node',
           'bi_full_tree_create', 'bi_full_tree_socket', 'bi_full_texture_group',
           'bi_full_image', 'bi_full_image_bytes', 'bi_full_texture_slot'}

class RecordingLibrary:
    def __init__(self, scene): self.scene = scene

    def __getattr__(self, name):
        def record(*args):
            args = list(args)
            for index, (kind, count) in buffers(name, args).items():
                if args[index] is not None:
                    owned = (kind * count)()
                    C.memmove(owned, args[index], C.sizeof(owned))
                    args[index] = owned
            result = self.scene.new_handle() if name in CREATES else 1
            self.scene.commands.append(('native', name, tuple(args), result))
            return result
        return record

class Snapshot:
    def __init__(self):
        self.commands = []
        self._counter = 0
        self.handle = self.new_handle()
        self.lib = RecordingLibrary(self)
        self.materials, self.trees, self.objects, self.textures, self.images = {}, {}, {}, {}, {}

    def new_handle(self):
        self._counter += 1
        return Handle(self._counter)

    def check(self, value): return value

    def create(self, kind, name):
        handle = self.new_handle()
        self.commands.append(('create', kind, name, handle))
        return handle

    def set(self, handle, path, value):
        if not isinstance(value, (str, bool, int, float)):
            value = tuple(value)
        self.commands.append(('set', handle, path, value))

    def pointer(self, handle, path, target):
        self.commands.append(('pointer', handle, path, target))

    def replay(self, observer):
        host = N.Scene()
        handles = {self.handle: host.handle}
        for kind, a, b, c in self.commands:
            if observer.test_break(): raise InterruptedError('Viewport export superseded')
            if kind == 'create': handles[c] = host.create(a,b)
            elif kind == 'set': host.set(handles[a],b,c)
            elif kind == 'pointer': host.pointer(handles[a],b,handles[c])
            else:
                args = [handles[v] if isinstance(v,Handle) else v for v in b]
                result = host.check(getattr(host.lib,a)(*args))
                if isinstance(c,Handle): handles[c] = result
        return host
