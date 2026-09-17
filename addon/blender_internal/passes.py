# SPDX-License-Identifier: GPL-2.0-or-later
# Original Internal pass names and channel identifiers (not Cycles pass aliases).
PASSES = {
    'z': ('Depth', 'Z'), 'normal': ('Normal', 'XYZ'), 'uv': ('UV', 'UVA'),
    'color': ('Color', 'RGBA'), 'emit': ('Emit', 'RGB'), 'diffuse': ('Diffuse', 'RGB'),
    'specular': ('Spec', 'RGB'), 'shadow': ('Shadow', 'RGB'),
    'ambient_occlusion': ('AO', 'RGB'), 'environment': ('Env', 'RGB'),
    'indirect': ('Indirect', 'RGB'), 'reflection': ('Reflect', 'RGB'),
    'refraction': ('Refract', 'RGB'), 'object_index': ('IndexOB', 'X'),
    'material_index': ('IndexMA', 'X'), 'mist': ('Mist', 'Z'),
}
