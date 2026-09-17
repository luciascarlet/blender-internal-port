# SPDX-License-Identifier: GPL-2.0-or-later
"""Run with Python or modern Blender to check symbol isolation and actual full rendering."""
import array
import ctypes as C
import json
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
library = (Path(os.environ['BI_TEST_ADDON_PATH']) / 'blender_internal/libblender_internal_full.dylib'
           if os.environ.get('BI_TEST_ADDON_PATH') else ROOT/'build-full/lib/libblender_internal_full.dylib')
lib=C.CDLL(str(library))
lib.bi_full_initialize.argtypes=[C.c_char_p]
lib.bi_full_load.argtypes=[C.c_char_p]
lib.bi_full_render.argtypes=[C.c_int,C.c_int,C.c_int]
lib.bi_full_result.argtypes=[C.POINTER(C.c_float),C.c_uint64,C.POINTER(C.c_int),C.POINTER(C.c_int)]
lib.bi_full_error.restype=C.c_char_p
assert lib.bi_full_initialize(str(ROOT/'blender-legacy-port/blender').encode())
results=[]
for factor in (0.7,3.14):
 for shadows in (0,1):
  name='legacy-factor{}-shadows{}'.format(factor,shadows)
  path=ROOT/'artifacts/fresnel'/(name+'.blend')
  assert lib.bi_full_load(str(path).encode()),lib.bi_full_error()
  assert lib.bi_full_render(1,256,256),lib.bi_full_error()
  w,h=C.c_int(),C.c_int()
  pixels=(C.c_float*(256*256*4))()
  assert lib.bi_full_result(pixels,len(pixels),C.byref(w),C.byref(h)),lib.bi_full_error()
  assert (w.value,h.value)==(256,256)
  reference=array.array('f');reference.frombytes(path.with_suffix('.rgba').read_bytes())
  differences=[abs(a-b) for a,b in zip(pixels,reference)]
  report={'case':name,'mae':sum(differences)/len(differences),'maximum_error':max(differences)}
  results.append(report)
  (ROOT/'artifacts/fresnel'/('full-'+name+'.rgba')).write_bytes(bytes(pixels))
  print('FULL_RENDER',report,flush=True)
(ROOT/'artifacts/full-parity.json').write_text(json.dumps(results,indent=2)+'\n')
