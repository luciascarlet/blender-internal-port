# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-supplied textures must survive the legacy image cache's memory limit."""
import ctypes as C
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('BI_TEST_ADDON_PATH', str(ROOT / 'addon')))
from blender_internal import full_native as N
from blender_internal.legacy_import import Reader

with N.LOCK:
    reader = Reader.__new__(Reader)
    reader.lib = N.load()
    # Exceed the legacy cache budget before asking for any image's pixels.
    # Ordinary images have disk/packed backing; these buffers exist only in RAM.
    byte_pixels = np.full((1024, 1024, 4), 127, dtype=np.uint8)
    float_pixels = np.full((1024, 1024, 4), 0.25, dtype=np.float32)
    for repeat in range(2):
        host = N.Scene()  # Also exercise freeing the previous scene's buffers.
        images = []
        for index in range(12):
            images.append(host.check(host.lib.bi_full_image_bytes(
                ('Byte %d' % index).encode(), 1024, 1024,
                byte_pixels.ctypes.data_as(C.POINTER(C.c_ubyte)), False)))
            images.append(host.check(host.lib.bi_full_image(
                ('Float %d' % index).encode(), 1024, 1024,
                float_pixels.ctypes.data_as(C.POINTER(C.c_float)))))
        for image in images:
            assert reader.value(image, 'size') == [1024, 1024], reader.name(image)

(ROOT / 'artifacts/image-cache.json').write_text(json.dumps({
    'passed': True, 'images_per_scene': 24, 'scenes': 2,
    'byte_and_float_images_survive_cache_pressure': True,
}, indent=2))
print('IMAGE_CACHE_OK', flush=True)
