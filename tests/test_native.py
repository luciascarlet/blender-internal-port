# SPDX-License-Identifier: GPL-2.0-or-later
import ctypes as C
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('classic_native', ROOT / 'addon/blender_internal/native.py')
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)

class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = N.load()

    def test_legacy_shaders_reference_values(self):
        m = N.default_material()
        n = N.F3(0, 0, 1)
        l = N.F3(math.sqrt(0.75), 0, 0.5)
        diffuse = lambda: self.lib.bi_diffuse(C.byref(m), n, l, n)
        self.assertAlmostEqual(diffuse(), 0.5, places=6)
        m.diffuse_shader, m.roughness = 1, 0
        self.assertAlmostEqual(diffuse(), 0.5, places=6)  # Oren-Nayar reduces to Lambert.
        m.diffuse_shader, m.darkness = 3, 1
        self.assertAlmostEqual(diffuse(), 0.5, places=6)
        m.diffuse_shader, m.diffuse_size, m.diffuse_smooth = 2, 0.2, 0.1
        self.assertEqual(diffuse(), 0)
        m.diffuse_size = 1.2
        self.assertEqual(diffuse(), 1)
        m.specular_shader = 0
        self.assertAlmostEqual(self.lib.bi_specular(C.byref(m), n, n, n), 1/1.1, places=6)
        m.specular_shader = 1
        self.assertEqual(self.lib.bi_specular(C.byref(m), n, n, n), 1)

    def test_all_shaders_finite_at_grazing_angles(self):
        m = N.default_material()
        n = N.F3(0, 0, 1)
        for shader in range(5):
            m.diffuse_shader = m.specular_shader = shader
            for angle in (0, 0.5, 1, 1.5707963, math.pi):
                l = N.F3(math.sin(angle), 0, math.cos(angle))
                for name in ('bi_diffuse', 'bi_specular'):
                    result = getattr(self.lib, name)(C.byref(m), n, l, n)
                    self.assertTrue(math.isfinite(result))
                    self.assertGreaterEqual(result, 0)

    def scene(self, reverse=False):
        tri = N.Triangle()
        tri.p[:] = (-2, -2, -3, 2, -2, -3, 0, 2, -3)
        if reverse:
            tri.p[:] = (0, 2, -3, 2, -2, -3, -2, -2, -3)
        tri.n[:] = (0, 0, 1) * 3
        m = N.default_material()
        m.color[:] = (0.8, 0.2, 0.1)
        m.shadeless = 1
        return self.lib.bi_scene_create(C.byref(tri), 1, C.byref(m), 1, None, 0)

    def render(self, scene, near=0.1, far=100, ortho=False):
        camera = N.Camera()
        camera.lower_left[:] = (-1, -1, 0 if ortho else -1)
        camera.horizontal[:] = (2, 0, 0)
        camera.vertical[:] = (0, 2, 0)
        camera.forward[:] = (0, 0, -1)
        camera.clip_start, camera.clip_end = near, far
        camera.orthographic = ortho
        settings = N.Settings()
        settings.width = settings.height = 3
        settings.sample_grid = 1
        settings.transparent = 1
        output = (C.c_float * 36)()
        self.assertEqual(self.lib.bi_render_rows(scene, C.byref(camera), C.byref(settings), 0, 3, output), 1)
        return list(output)

    def test_intersections_winding_clipping_alpha_and_orthographic(self):
        for reverse in (False, True):
            handle = self.scene(reverse)
            self.assertTrue(handle)
            try:
                image = self.render(handle)
                self.assertAlmostEqual(image[16], 0.8, places=6)
                self.assertEqual(image[19], 1)
                self.assertEqual(image[27], 0)
                self.assertEqual(self.render(handle, far=2)[19], 0)
                self.assertEqual(self.render(handle, near=4)[19], 0)
                self.assertEqual(self.render(handle, ortho=True)[19], 1)
            finally:
                self.lib.bi_scene_destroy(handle)

    def test_empty_scene_and_invalid_material(self):
        m = N.default_material()
        handle = self.lib.bi_scene_create(None, 0, C.byref(m), 1, None, 0)
        self.assertTrue(handle)
        try:
            self.assertEqual(sum(self.render(handle)), 0)
        finally:
            self.lib.bi_scene_destroy(handle)
        tri = N.Triangle()
        tri.material = 10
        self.assertFalse(self.lib.bi_scene_create(C.byref(tri), 1, C.byref(m), 1, None, 0))
        self.assertIn(b'material', self.lib.bi_last_error())

if __name__ == '__main__':
    unittest.main()
