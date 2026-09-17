/* SPDX-License-Identifier: GPL-2.0-or-later
 * Minimal replacements for legacy BLI helpers. Kernels themselves are unchanged. */
#pragma once
#include <cmath>
#include <cstring>
#include <algorithm>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#define UNUSED(x) x
#define UNLIKELY(x) (x)
#define MAX2(a,b) ((a) > (b) ? (a) : (b))
#define SWAP(type,a,b) do { type tmp = a; a = b; b = tmp; } while (0)
static float dot_v3v3(const float a[3], const float b[3]) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
static float normalize_v3(float n[3]) {
  float d = dot_v3v3(n,n);
  if (d > 1.0e-35f) { d = sqrtf(d); float inv = 1.0f / d; for (int i=0;i<3;i++) n[i] *= inv; }
  else { n[0]=n[1]=n[2]=0; d=0; }
  return d;
}
static float saacos(float v) { return v <= -1 ? float(M_PI) : v >= 1 ? 0 : acosf(v); }
static float sasqrt(float v) { return v <= 0 ? 0 : sqrtf(v); }
static float max_ff(float a, float b) { return a > b ? a : b; }
struct IsectRayPrecalc { int kx,ky,kz; float sx,sy,sz; };
static int axis_dominant_v3_single(const float v[3]) {
  float x=fabsf(v[0]), y=fabsf(v[1]), z=fabsf(v[2]);
  return x > y ? (x > z ? 0 : 2) : (y > z ? 1 : 2);
}
static int float_as_int(float f) { int i; memcpy(&i,&f,4); return i; }
static float xor_fl(float f, int mask) { int i=float_as_int(f)^mask; memcpy(&f,&i,4); return f; }
