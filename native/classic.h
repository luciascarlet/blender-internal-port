/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <stdint.h>
#if defined(_WIN32)
#  define BI_API __declspec(dllexport)
#else
#  define BI_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* Flat, versioned ABI; no Blender DNA or Python ABI dependency. */
typedef struct { float p[9], n[9]; int32_t material; } BI_Triangle;
typedef struct {
  float color[3], specular_color[3];
  float diffuse_intensity, specular_intensity, roughness, darkness;
  float diffuse_size, diffuse_smooth, specular_size, specular_smooth;
  float ior, slope, emission;
  int32_t diffuse_shader, specular_shader, hardness, shadeless;
} BI_Material;
/* type: 0 SUN, 1 POINT, 2 SPOT. Energy is classic, not watts. */
typedef struct {
  float position[3], direction[3], color[3];
  float energy, distance, spot_cos, spot_blend;
  int32_t type, shadows;
} BI_Light;
typedef struct {
  float origin[3], lower_left[3], horizontal[3], vertical[3], forward[3];
  float clip_start, clip_end;
  int32_t orthographic;
} BI_Camera;
typedef struct {
  float background[3], ambient;
  int32_t width, height, sample_grid, transparent, shadows;
} BI_Settings;
BI_API int bi_abi_version(void);
BI_API int bi_struct_size(int kind);
BI_API const char *bi_last_error(void);
BI_API float bi_diffuse(const BI_Material *, const float n[3], const float l[3], const float v[3]);
BI_API float bi_specular(const BI_Material *, const float n[3], const float l[3], const float v[3]);
BI_API void *bi_scene_create(const BI_Triangle *, int count, const BI_Material *, int materials, const BI_Light *, int lights);
BI_API void bi_scene_destroy(void *scene);
/* Output contains row_count * width * 4 linear, premultiplied RGBA floats, bottom up. */
BI_API int bi_render_rows(void *, const BI_Camera *, const BI_Settings *, int first_row, int row_count, float *rgba);
#ifdef __cplusplus
}
#endif
