# SPDX-License-Identifier: GPL-2.0-or-later
"""Progressive legacy viewport with main-thread snapshots and cancellable jobs."""
import atexit
import threading
import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager
import bpy
from . import full_export as E, full_native as N
from .scene_snapshot import Snapshot

STATES = weakref.WeakSet()
_condition = threading.Condition()
_pending = OrderedDict()
_worker = None
_active = None
_stopping = False
_suspended = 0


def tag_update():
    for state in list(STATES):
        state.invalidate()
        state.snapshot = None


def projection(matrix):
    """Recover the old engine's view plane from Blender's actual window matrix.
    This includes camera zoom/shift, non-square pixels, pan and orthographic views.
    """
    m = matrix
    ortho = abs(m[3][3] - 1) < 1e-5
    if ortho:
        near, far = (m[2][3]+1)/m[2][2], (m[2][3]-1)/m[2][2]
        plane = ((-1-m[0][3])/m[0][0], (1-m[0][3])/m[0][0],
                 (-1-m[1][3])/m[1][1], (1-m[1][3])/m[1][1])
    else:
        near, far = m[2][3]/(m[2][2]-1), m[2][3]/(m[2][2]+1)
        plane = (near*(m[0][2]-1)/m[0][0], near*(m[0][2]+1)/m[0][0],
                 near*(m[1][2]-1)/m[1][1], near*(m[1][2]+1)/m[1][1])
    return plane, near, far, ortho


class Observer:
    def __init__(self, cancelled): self.cancelled = cancelled
    def test_break(self): return self.cancelled.is_set()
    def update_progress(self, value): pass


def _run():
    global _active
    while True:
        with _condition:
            _condition.wait_for(lambda: _stopping or (_pending and not _suspended))
            if _stopping: return
            state, job = _pending.popitem(last=False)
            _active = state
        serial, snapshot, request, cancel = job
        observer = Observer(cancel)
        try:
            with N.LOCK:
                if observer.test_break(): continue
                host = snapshot.replay(observer)
                for pixels, width, height in host.preview(*request, observer):
                    if observer.test_break() or state.serial != serial: break
                    state.result = (serial, pixels, width, height)
                    state.message = f'{width} × {height}'
                    state.publications += 1
                if not observer.test_break() and state.serial == serial:
                    state.message = 'Preview complete'
                    state.completed = serial
        except Exception as error:
            if not observer.test_break() and state.serial == serial:
                state.message = str(error)
                state.error = str(error)
        finally:
            with _condition:
                _active = None
            state.busy = False
            state = job = snapshot = None


def _submit(state, snapshot, request):
    global _worker
    with _condition:
        if _active is state:
            _active.cancel.set()
        state.cancel = threading.Event()
        state.busy = True
        _pending[state] = (state.serial, snapshot, request, state.cancel)
        if _worker is None:
            _worker = threading.Thread(target=_run, name='Blender Internal viewport', daemon=True)
            _worker.start()
        _condition.notify()


@contextmanager
def final_render():
    """Give F12 priority over viewport jobs using the same legacy global state."""
    global _suspended
    with _condition:
        _suspended += 1
        for state in list(STATES): state.invalidate()
        _pending.clear()
    try:
        yield
    finally:
        with _condition:
            _suspended -= 1
            for state in list(STATES):
                state.dirty = True
                state.snapshot = None
            _condition.notify_all()


class Viewport:
    def __init__(self, engine):
        self.engine = weakref.ref(engine)
        self.serial = 0
        self.dirty = True
        self.closed = False
        self.busy = False
        self.cancel = threading.Event()
        self.result = None
        self.texture = None
        self.drawn = None
        self.signature = None
        self.snapshot = None
        self.last_submit = 0
        self.message = 'Preparing viewport'
        self.error = None
        self.completed = -1
        self.publications = 0
        self.last_message = None
        self.paused = False
        STATES.add(self)

    def invalidate(self):
        self.serial += 1
        self.dirty = True
        self.last_message = None
        self.cancel.set()

    def close(self):
        self.closed = True
        self.cancel.set()
        with _condition: _pending.pop(self, None)
        STATES.discard(self)
        self.texture = None

    def update(self, context, depsgraph):
        self.invalidate()
        self.snapshot = None

    def draw(self, context, depsgraph):
        engine = self.engine()
        if engine is None or self.closed: return
        scene = depsgraph.scene_eval
        p = scene.classic_internal
        rv = context.region_data
        if rv is None: return
        dimensions = (max(1, context.region.width*p.viewport_resolution//100),
                      max(1, context.region.height*p.viewport_resolution//100))
        view = E.matrix_values(rv.view_matrix)
        signature = (tuple(view), tuple(E.matrix_values(rv.window_matrix)), dimensions,
                     p.legacy.preview_start_resolution, p.viewport_pause)
        if signature != self.signature:
            self.signature = signature
            self.invalidate()
        self.paused = p.viewport_pause
        if p.viewport_pause or _suspended:
            self.cancel.set()
        elif self.dirty and time.monotonic()-self.last_submit >= 0.1:
            self.dirty = False
            self.error = None
            self.last_submit = time.monotonic()
            try:
                if p.backend != 'FULL': raise RuntimeError('Select Full Legacy Renderer for viewport preview')
                if p.source != 'MODERN': raise RuntimeError('Viewport edits require Current Scene; import the legacy file to preview it')
                if self.snapshot is None:
                    self.snapshot = E.export_scene(depsgraph, Observer(threading.Event()),
                                                   host=Snapshot(), preview=True, space=context.space_data)
                plane, near, far, ortho = projection(rv.window_matrix)
                request = (scene.frame_current, dimensions, view, plane, near, far, ortho,
                           max(16, p.legacy.preview_start_resolution))
                self.message = 'Rendering preview'
                _submit(self, self.snapshot, request)
            except Exception as error:
                self.message = self.error = str(error)
        self.draw_image(engine, context)
        import blf
        blf.position(0, 12, 12, 0)
        blf.size(0, 13)
        blf.color(0, 1, 0.3, 0.2, 1) if self.error else blf.color(0, 0.9, 0.9, 0.9, 1)
        blf.draw(0, 'Blender Internal: ' + ('Paused' if p.viewport_pause else self.message))

    def draw_image(self, engine, context):
        if self.result is None: return
        import gpu
        from gpu_extras.presets import draw_texture_2d
        result = self.result
        if self.drawn is not result:
            serial, pixels, width, height = result
            buffer = gpu.types.Buffer('FLOAT', pixels.size, pixels.ravel())
            self.texture = gpu.types.GPUTexture((width,height), format='RGBA16F', data=buffer)
            self.drawn = result
        gpu.state.blend_set('ALPHA_PREMULT')
        try:
            engine.bind_display_space_shader(context.scene)
            try:
                draw_texture_2d(self.texture, (0,0), context.region.width, context.region.height)
            finally:
                engine.unbind_display_space_shader()
        finally:
            gpu.state.blend_set('NONE')


def _tick():
    if _stopping: return None
    for state in list(STATES):
        engine = state.engine()
        if engine is not None and not state.closed:
            try:
                if (state.dirty and not state.paused) or state.result is not state.drawn or state.last_message != state.message:
                    engine.tag_redraw()
                    state.last_message = state.message
            except ReferenceError:
                state.close()
    return 0.1


def register():
    atexit.unregister(stop_worker)
    atexit.register(stop_worker)
    global _stopping
    _stopping = False
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, persistent=True)


def stop_worker():
    # Also used by atexit: no bpy or GPU calls after Blender tears down its UI.
    global _stopping, _worker
    with _condition:
        _stopping = True
        for state in list(STATES): state.cancel.set()
        _pending.clear()
        _condition.notify_all()
    if _worker is not None:
        _worker.join()
        _worker = None


def unregister():
    stop_worker()
    atexit.unregister(stop_worker)
    for state in list(STATES): state.close()
    if bpy.app.timers.is_registered(_tick): bpy.app.timers.unregister(_tick)
