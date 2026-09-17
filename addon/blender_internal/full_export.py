# SPDX-License-Identifier: GPL-2.0-or-later
"""Modern depsgraph → original legacy scene, material and node structures."""
import ctypes as C
import bpy
import numpy as np
from . import full_native as FN
from .legacy_ui import SCHEMA, TREE
from .passes import PASSES


def matrix_values(matrix):
    return [matrix[row][column] for column in range(4) for row in range(4)]


def export_region_passes(host, scene, layer):
    host.set(host.handle, 'render.use_border', scene.render.use_border)
    host.set(host.handle, 'render.use_crop_to_border', True)
    for name in ('border_min_x', 'border_max_x', 'border_min_y', 'border_max_y'):
        host.set(host.handle, 'render.' + name, getattr(scene.render, name))
    for key in PASSES:
        name = 'use_pass_' + key
        host.set(host.handle, 'render.layers[0].' + name, getattr(layer.classic_internal, name))


def export_properties(host, handle, props, schema, prefix=''):
    for prop in schema:
        name = prop['id']
        if name in ('diffuse_toon_size', 'diffuse_toon_smooth') and getattr(props, 'diffuse_shader', '') != 'TOON':
            continue
        if name in ('diffuse_fresnel', 'diffuse_fresnel_factor') and getattr(props, 'diffuse_shader', '') != 'FRESNEL':
            continue
        if hasattr(props, name):
            host.set(handle, prefix + name, getattr(props, name))


def export_material(host, material):
    key = material.as_pointer() if material else 0
    if key in host.materials:
        return host.materials[key]
    handle = host.create('MATERIAL', material.name if material else 'Default')
    host.materials[key] = handle
    if material is None:
        return handle
    p = material.classic_internal
    host.set(handle, 'pass_index', material.pass_index)
    # Full original settings remain available, including mirror, transparency,
    # SSS, volumes, halos and strands. Existing prototype files keep their look.
    if p.use_legacy_settings:
        export_properties(host, handle, p.legacy, SCHEMA['material'])
    else:
        values = {
            'diffuse_color': p.color, 'specular_color': p.specular_color,
            'diffuse_shader': ('LAMBERT', 'OREN_NAYAR', 'TOON', 'MINNAERT', 'FRESNEL')[int(p.diffuse_shader)],
            'specular_shader': ('COOKTORR', 'PHONG', 'BLINN', 'TOON', 'WARDISO')[int(p.specular_shader)],
            'diffuse_intensity': p.diffuse_intensity, 'specular_intensity': p.specular_intensity,
            'specular_hardness': p.hardness, 'roughness': p.roughness, 'darkness': p.darkness,
            'diffuse_toon_size': p.diffuse_size, 'diffuse_toon_smooth': p.diffuse_smooth,
            'specular_toon_size': p.specular_size, 'specular_toon_smooth': p.specular_smooth,
            'specular_ior': p.ior, 'specular_slope': p.slope, 'emit': p.emission,
            'use_shadeless': p.shadeless,
        }
        # Toon and Fresnel share DNA parameters; assign only the active model.
        if p.diffuse_shader == '4':
            del values['diffuse_toon_size'], values['diffuse_toon_smooth']
            values.update(diffuse_fresnel_factor=p.diffuse_size, diffuse_fresnel=p.diffuse_smooth)
        for name, value in values.items():
            host.set(handle, name, value)
    for name, schema in SCHEMA['nested'].items():
        export_properties(host, handle, getattr(p.legacy, name), schema, name + '.')
    for index, slot in enumerate(p.texture_slots):
        if slot.texture and slot.enabled:
            texture = export_texture(host, slot.texture)
            native_slot = host.check(host.lib.bi_full_texture_slot(handle, texture, index))
            export_properties(host, native_slot, slot.settings, SCHEMA['texture_slot'])
    if p.node_tree:
        export_tree(host, handle, p.node_tree)
    return handle


def export_tree(host, material, tree, native_tree=None):
    if tree.bl_idname != TREE:
        raise RuntimeError('Expected a Blender Internal node tree')
    if native_tree is None:
        native_tree = host.check(host.lib.bi_full_material_tree(material))
    nodes = {}
    for node in tree.nodes:
        if node.bl_idname == 'NodeFrame':
            continue
        kind = getattr(node, 'legacy_type', node.bl_idname)
        if kind not in SCHEMA['nodes'] and kind not in ('ShaderNodeGroup', 'NodeGroupInput', 'NodeGroupOutput', 'NodeReroute'):
            raise RuntimeError('Unsupported node in legacy tree: ' + kind)
        handle = host.check(host.lib.bi_full_node(native_tree, kind.encode()))
        if kind == 'ShaderNodeGroup':
            if node.node_tree is None:
                raise RuntimeError('Legacy group node has no tree: ' + node.name)
            key = node.node_tree.as_pointer()
            if key not in host.trees:
                group_handle = host.check(host.lib.bi_full_tree_create(node.node_tree.name.encode()))
                host.trees[key] = group_handle
                for socket in node.node_tree.interface.items_tree:
                    if socket.item_type == 'SOCKET':
                        host.check(host.lib.bi_full_tree_socket(group_handle, socket.in_out == 'OUTPUT', socket.socket_type.encode(), socket.name.encode()))
                export_tree(host, None, node.node_tree, group_handle)
            host.pointer(handle, 'node_tree', host.trees[key])
        nodes[node.as_pointer()] = handle
        host.set(handle, 'name', node.name)
        host.set(handle, 'mute', node.mute)
        for prop in SCHEMA['nodes'].get(kind, {}).get('properties', []):
            host.set(handle, prop['id'], getattr(node, 'legacy_' + prop['id']))
        for direction in ('inputs', 'outputs'):
            for index, socket in enumerate(getattr(node, direction)):
                if hasattr(socket, 'default_value'):
                    host.set(handle, '{}[{}].default_value'.format(direction, index), socket.default_value)
        if hasattr(node, 'material') and node.material:
            host.pointer(handle, 'material', export_material(host, node.material))
        if hasattr(node, 'texture') and node.texture:
            export_texture_node(host, handle, node.texture)
        if hasattr(node, 'lamp_object') and node.lamp_object:
            light_handle = host.objects.get(node.lamp_object.original.as_pointer())
            if light_handle:
                host.pointer(handle, 'lamp_object', light_handle)
            else:
                raise RuntimeError('Lamp node references a light outside the render scene')
        if getattr(node, 'storage', None):
            export_node_storage(host, handle, node)
    for link in tree.links:
        source = nodes.get(link.from_node.as_pointer())
        target = nodes.get(link.to_node.as_pointer())
        if source and target:
            output = list(link.from_node.outputs).index(link.from_socket)
            input_index = list(link.to_node.inputs).index(link.to_socket)
            host.check(host.lib.bi_full_node_link(native_tree, source, output, target, input_index))


def export_image(host, image):
    key = image.as_pointer()
    if key in host.images:
        return host.images[key]
    width, height = image.size
    if not width or not height:
        raise RuntimeError('Image has no loaded pixels: ' + image.name)
    pixels = np.empty(width*height*4, np.float32)
    image.pixels.foreach_get(pixels)
    if image.is_float or image.colorspace_settings.name in ('Linear', 'Linear Rec.709'):
        handle = host.check(host.lib.bi_full_image(image.name.encode(), width, height,
                                                  pixels.ctypes.data_as(C.POINTER(C.c_float))))
    else:
        # Blender's byte Image.pixels are normalized encoded values, not linear
        # samples. Preserve bytes so legacy filtering precedes sRGB conversion.
        if image.colorspace_settings.name not in ('sRGB', 'Non-Color'):
            raise RuntimeError('Byte image color space needs conversion: ' + image.colorspace_settings.name)
        encoded = np.rint(np.clip(pixels, 0, 1)*255).astype(np.uint8)
        handle = host.check(host.lib.bi_full_image_bytes(image.name.encode(), width, height,
            encoded.ctypes.data_as(C.POINTER(C.c_ubyte)), image.colorspace_settings.is_data))
    host.images[key] = handle
    return handle


def export_ramp(host, handle, path, ramp):
    positions = (C.c_float * len(ramp.elements))(*(p.position for p in ramp.elements))
    colors = (C.c_float * (len(ramp.elements)*4))(*(v for p in ramp.elements for v in p.color))
    host.check(host.lib.bi_full_ramp(handle, path.encode(), len(ramp.elements), positions, colors))
    for prop in ('interpolation', 'color_mode', 'hue_interpolation'):
        host.set(handle, path + '.' + prop, getattr(ramp, prop))


def export_texture(host, texture):
    key = texture.as_pointer()
    if key in host.textures:
        return host.textures[key]
    if texture.type not in SCHEMA['textures']:
        raise RuntimeError('Texture type needs a legacy archive: ' + texture.type)
    handle = host.create('TEXTURE', texture.name)
    host.textures[key] = handle
    host.set(handle, 'type', texture.type)
    export_properties(host, handle, texture, SCHEMA['textures'][texture.type])
    if texture.type == 'IMAGE' and texture.image:
        host.pointer(handle, 'image', export_image(host, texture.image))
    if texture.use_color_ramp:
        export_ramp(host, handle, 'color_ramp', texture.color_ramp)
    if texture.use_nodes and texture.node_tree:
        tree = host.check(host.lib.bi_full_texture_tree(handle))
        export_texture_tree(host, tree, texture.node_tree)
    return handle


def export_texture_tree(host, native_tree, tree):
    nodes = {}
    socket_indices = {}
    for node in tree.nodes:
        kind = node.bl_idname
        if kind == 'NodeFrame':
            continue
        # Modern replacement color nodes retain the original RGB behavior only
        # when configured in RGB mode.
        if kind in ('TextureNodeCombineColor', 'TextureNodeSeparateColor'):
            if node.mode != 'RGB':
                raise RuntimeError('Legacy texture color composition supports RGB mode')
            kind = 'TextureNodeCompose' if kind == 'TextureNodeCombineColor' else 'TextureNodeDecompose'
        schema = SCHEMA['texture_nodes'].get(kind)
        if schema is None and kind not in ('TextureNodeGroup', 'NodeGroupInput', 'NodeGroupOutput', 'NodeReroute'):
            raise RuntimeError('Unsupported legacy texture node: ' + kind)
        handle = host.check(host.lib.bi_full_node(native_tree, kind.encode()))
        nodes[node.as_pointer()] = handle
        if kind == 'TextureNodeGroup':
            if not node.node_tree:
                raise RuntimeError('Texture group has no node tree')
            key = node.node_tree.as_pointer()
            if key not in host.trees:
                group = host.check(host.lib.bi_full_texture_group(node.node_tree.name.encode()))
                host.trees[key] = group
                for socket in node.node_tree.interface.items_tree:
                    if socket.item_type == 'SOCKET':
                        host.check(host.lib.bi_full_tree_socket(group, socket.in_out == 'OUTPUT', socket.socket_type.encode(), socket.name.encode()))
                export_texture_tree(host, group, node.node_tree)
            host.pointer(handle, 'node_tree', host.trees[key])
        host.set(handle, 'name', node.name)
        host.set(handle, 'mute', node.mute)
        if schema:
            export_properties(host, handle, node, schema['properties'])
        for direction in ('inputs', 'outputs'):
            sockets = getattr(node, direction)
            # Modern Combine/Separate Color add an alpha socket; 2.79 RGB nodes
            # always supply opaque alpha and have only three scalar sockets.
            if kind == 'TextureNodeCompose' and direction == 'inputs':
                sockets = list(sockets)[:3]
            if kind == 'TextureNodeDecompose' and direction == 'outputs':
                sockets = list(sockets)[:3]
            if schema:
                sockets = list(sockets)[:len(schema[direction])]
            for index, socket in enumerate(sockets):
                socket_indices[socket.as_pointer()] = index
                if hasattr(socket, 'default_value'):
                    host.set(handle, '{}[{}].default_value'.format(direction, index), socket.default_value)
        if getattr(node, 'image', None):
            host.pointer(handle, 'image', export_image(host, node.image))
        if getattr(node, 'texture', None):
            host.pointer(handle, 'texture', export_texture(host, node.texture))
        if hasattr(node, 'color_ramp'):
            export_ramp(host, handle, 'color_ramp', node.color_ramp)
        for path in ('mapping', 'curve'):
            if hasattr(node, path):
                export_mapping(host, handle, path, getattr(node, path))
    for link in tree.links:
        if link.from_node.as_pointer() in nodes and link.to_node.as_pointer() in nodes:
            if link.from_socket.as_pointer() not in socket_indices or link.to_socket.as_pointer() not in socket_indices:
                raise RuntimeError('Texture link uses a socket introduced after Blender 2.79: ' + link.to_node.name)
            host.check(host.lib.bi_full_node_link(native_tree, nodes[link.from_node.as_pointer()],
                socket_indices[link.from_socket.as_pointer()], nodes[link.to_node.as_pointer()],
                socket_indices[link.to_socket.as_pointer()]))


def export_texture_node(host, node, texture):
    host.pointer(node, 'texture', export_texture(host, texture))


def export_node_storage(host, handle, node):
    storage = node.storage.nodes[0]
    if node.legacy_type == 'ShaderNodeValToRGB':
        export_ramp(host, handle, 'color_ramp', storage.color_ramp)
        return
    export_mapping(host, handle, 'mapping', storage.mapping)


def export_mapping(host, handle, path, mapping):
    for prop in ('use_clip', 'clip_min_x', 'clip_min_y', 'clip_max_x', 'clip_max_y', 'black_level', 'white_level'):
        host.set(handle, path + '.' + prop, getattr(mapping, prop))
    for index, curve in enumerate(mapping.curves):
        host.set(handle, path + '.curves[{}].extend'.format(index), mapping.extend)
        xy = (C.c_float * (len(curve.points)*2))(*(v for p in curve.points for v in p.location))
        types = (C.c_int * len(curve.points))(*({'AUTO': 0, 'VECTOR': 1, 'AUTO_CLAMPED': 2}[p.handle_type] for p in curve.points))
        host.check(host.lib.bi_full_curve(handle, path.encode(), index, len(curve.points), xy, types))


def export_scene(depsgraph, engine):
    host = FN.Scene()
    scene = depsgraph.scene_eval
    settings = scene.classic_internal
    host.set(host.handle, 'render.engine', 'BLENDER_RENDER')
    host.set(host.handle, 'render.resolution_percentage', 100)
    host.set(host.handle, 'render.pixel_aspect_x', scene.render.pixel_aspect_x)
    host.set(host.handle, 'render.pixel_aspect_y', scene.render.pixel_aspect_y)
    host.set(host.handle, 'render.use_antialiasing', settings.samples != '1')
    if settings.samples != '1':
        host.set(host.handle, 'render.antialiasing_samples', {'2': '5', '3': '8', '4': '16'}[settings.samples])
    host.set(host.handle, 'render.use_shadows', settings.shadows)
    host.set(host.handle, 'render.use_raytrace', True)
    host.set(host.handle, 'render.alpha_mode', 'TRANSPARENT' if scene.render.film_transparent else 'SKY')
    if settings.use_legacy_settings:
        export_properties(host, host.handle, settings.legacy, SCHEMA['render'], 'render.')
        if settings.legacy.use_motion_blur:
            raise RuntimeError('Legacy motion blur needs temporal geometry export; disable it for this render')
        if settings.legacy.use_freestyle:
            raise RuntimeError('This native build does not include Freestyle')
        # Composition and output belong to the modern host, not the embedded main.
        host.set(host.handle, 'render.use_compositing', False)
        host.set(host.handle, 'render.use_sequencer', False)
    export_region_passes(host, scene, depsgraph.view_layer)
    world = host.create('WORLD', scene.world.name if scene.world else 'World')
    host.set(world, 'horizon_color', scene.world.color if scene.world else (0.05,)*3)
    host.set(world, 'ambient_color', (settings.ambient,)*3)
    if settings.use_legacy_world:
        export_properties(host, world, settings.world, SCHEMA['world'])
        for name, schema in SCHEMA['world_nested'].items():
            export_properties(host, world, getattr(settings.world, name), schema, name + '.')
    camera = scene.camera.evaluated_get(depsgraph) if scene.camera else None
    if camera is None:
        raise RuntimeError('A camera is required')
    ch = host.create('CAMERA', camera.name)
    host.set(ch, 'matrix_world', matrix_values(camera.matrix_world))
    for prop in ('type', 'lens', 'sensor_width', 'sensor_height', 'sensor_fit', 'shift_x', 'shift_y', 'ortho_scale', 'clip_start', 'clip_end'):
        host.set(ch, 'data.' + prop, getattr(camera.data, prop))
    if camera.data.type == 'PANO':
        raise RuntimeError('Panoramic camera mapping needs validation')
    # Export light objects before nodes can refer to them.
    instances = [(i.object, i.matrix_world.copy(), i.show_self) for i in depsgraph.object_instances]
    for obj, matrix, show_self in instances:
        if obj.type != 'LIGHT' or obj.hide_render or not show_self:
            continue
        data = obj.data
        light = host.create('LIGHT', obj.name)
        host.objects[obj.original.as_pointer()] = light
        host.set(light, 'matrix_world', matrix_values(matrix))
        if data.classic_internal.use_legacy_settings:
            legacy = data.classic_internal.legacy
            host.set(light, 'data.type', legacy.type)
            export_properties(host, light, legacy, SCHEMA['lights'][legacy.type], 'data.')
            continue
        host.set(light, 'data.type', data.type)
        host.set(light, 'data.color', data.color)
        host.set(light, 'data.energy', data.classic_internal.energy)
        host.set(light, 'data.distance', data.classic_internal.distance)
        host.set(light, 'data.shadow_method', 'RAY_SHADOW' if data.classic_internal.shadows else 'NOSHADOW')
        if data.type in ('POINT', 'SPOT'):
            host.set(light, 'data.falloff_type', 'INVERSE_SQUARE')
        if data.type == 'SPOT':
            host.set(light, 'data.spot_size', data.spot_size)
            host.set(light, 'data.spot_blend', data.spot_blend)
        if data.type == 'AREA':
            host.set(light, 'data.shape', 'RECTANGLE' if data.shape == 'RECTANGLE' else 'SQUARE')
            host.set(light, 'data.size', data.size)
            if data.shape == 'RECTANGLE':
                host.set(light, 'data.size_y', data.size_y)
    override = depsgraph.view_layer.material_override
    for obj, matrix, show_self in instances:
        if engine.test_break():
            raise InterruptedError('Render cancelled')
        if show_self and not obj.hide_render and obj.type in ('VOLUME', 'POINTCLOUD', 'CURVES', 'GREASEPENCIL'):
            raise RuntimeError('Geometry export is not implemented for ' + obj.type + ': ' + obj.name)
        if obj.hide_render or not show_self or obj.type not in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META'):
            continue
        mesh = obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        if mesh is None:
            continue
        try:
            handle = host.create('MESH', obj.name)
            host.objects[obj.original.as_pointer()] = handle
            host.set(handle, 'matrix_world', matrix_values(matrix))
            host.set(handle, 'pass_index', obj.pass_index)
            nv, npoly, nl = len(mesh.vertices), len(mesh.polygons), len(mesh.loops)
            coords = np.empty(nv*3, np.float32)
            starts = np.empty(npoly, np.int32)
            counts = np.empty(npoly, np.int32)
            indices = np.empty(nl, np.int32)
            material_indices = np.empty(npoly, np.int32)
            smooth = np.empty(npoly, np.uint8)
            normals = np.empty(nl*3, np.float32)
            mesh.vertices.foreach_get('co', coords)
            mesh.polygons.foreach_get('loop_start', starts)
            mesh.polygons.foreach_get('loop_total', counts)
            mesh.polygons.foreach_get('material_index', material_indices)
            mesh.polygons.foreach_get('use_smooth', smooth)
            mesh.loops.foreach_get('vertex_index', indices)
            mesh.corner_normals.foreach_get('vector', normals)
            def ptr(data, kind): return data.ctypes.data_as(C.POINTER(kind))
            host.check(host.lib.bi_full_mesh(handle, nv, ptr(coords,C.c_float), npoly,
                ptr(starts,C.c_int), ptr(counts,C.c_int), nl, ptr(indices,C.c_int),
                ptr(material_indices,C.c_int), ptr(smooth,C.c_ubyte),
                ptr(normals,C.c_float) if mesh.has_custom_normals or any(e.use_edge_sharp for e in mesh.edges) else None))
            for slot, material in enumerate(list(mesh.materials) or [None]):
                mh = export_material(host, override or material)
                host.check(host.lib.bi_full_mesh_material(handle, mh, slot+1))
            for layer in mesh.uv_layers:
                uv = np.empty(nl*2, np.float32)
                layer.data.foreach_get('uv', uv)
                host.check(host.lib.bi_full_mesh_uv(handle, layer.name.encode(), nl, ptr(uv,C.c_float)))
            for layer in mesh.color_attributes:
                if layer.domain not in ('POINT', 'CORNER'):
                    continue
                colors = np.empty(len(layer.data)*4, np.float32)
                # Legacy byte colors store sRGB; RNA color_srgb handles conversion
                # for modern floating-point attributes as well as byte colors.
                layer.data.foreach_get('color_srgb', colors)
                if layer.domain == 'POINT':
                    colors = colors.reshape((-1, 4))[indices].ravel()
                host.check(host.lib.bi_full_mesh_color(handle, layer.name.encode(), nl, ptr(colors, C.c_float)))
            active_uv = next((layer.name for layer in mesh.uv_layers if layer.active_render), '')
            color_index = mesh.color_attributes.render_color_index
            active_color = mesh.color_attributes[color_index].name if 0 <= color_index < len(mesh.color_attributes) else ''
            host.check(host.lib.bi_full_mesh_active_layers(handle, active_uv.encode(), active_color.encode()))
        finally:
            obj.to_mesh_clear()
    return host
