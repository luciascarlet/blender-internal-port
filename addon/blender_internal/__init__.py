# SPDX-License-Identifier: GPL-2.0-or-later
bl_info = {
    'name': 'Blender Internal — Experimental Port',
    'author': 'Blender authors; modern adapter contributors',
    'version': (0, 2, 6),
    'blender': (5, 2, 0),
    'location': 'Render engine selector; Render, Material and Light properties',
    'description': 'Original Blender Internal scanlines, legacy nodes and ray tracing in modern Blender',
    'category': 'Render',
}

import ctypes as C
import math
import bpy
from bpy.props import CollectionProperty, BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Vector
from . import native, legacy_ui, full_native, full_export, legacy_import, material_ui, render_settings, render_ui, viewport
from .passes import PASSES

ENGINE = 'BLENDER_INTERNAL_PORT'
DIFFUSE = [('0', 'Lambert', ''), ('1', 'Oren-Nayar', ''), ('2', 'Toon', ''), ('3', 'Minnaert', ''), ('4', 'Fresnel', '')]
SPECULAR = [('0', 'Cook-Torrance', ''), ('1', 'Phong', ''), ('2', 'Blinn', ''), ('3', 'Toon', ''), ('4', 'Ward Isotropic', '')]

class ClassicMaterial(bpy.types.PropertyGroup):
    texture_slots: CollectionProperty(type=legacy_ui.LegacyTextureSlot)
    use_legacy_settings: BoolProperty(name='Use Full Legacy Material Controls', default=False)
    legacy: PointerProperty(type=legacy_ui.LegacyMaterial)
    node_tree: PointerProperty(name='Legacy Nodes', type=bpy.types.NodeTree, poll=lambda self, tree: tree.bl_idname == legacy_ui.TREE)
    use_nodes: BoolProperty(name='Use Nodes', default=True, description='Render this material using its Blender Internal node tree')
    ramp_storage: PointerProperty(type=bpy.types.NodeTree)
    color: FloatVectorProperty(name='Diffuse Color', subtype='COLOR', size=3, min=0, max=1, default=(0.8, 0.8, 0.8))
    specular_color: FloatVectorProperty(name='Specular Color', subtype='COLOR', size=3, min=0, max=1, default=(1, 1, 1))
    diffuse_shader: EnumProperty(name='Diffuse', items=DIFFUSE, default='0')
    specular_shader: EnumProperty(name='Specular', items=SPECULAR, default='0')
    diffuse_intensity: FloatProperty(name='Diffuse Intensity', min=0, max=1, default=0.8)
    specular_intensity: FloatProperty(name='Specular Intensity', min=0, max=1, default=0.5)
    hardness: IntProperty(name='Hardness', min=1, max=511, default=50)
    roughness: FloatProperty(name='Roughness', min=0, max=3.14, default=0.5)
    darkness: FloatProperty(name='Darkness', min=0, max=2, default=1)
    diffuse_size: FloatProperty(name='Diffuse Size / Fresnel Factor', min=0, max=5, default=0.5)
    diffuse_smooth: FloatProperty(name='Diffuse Smooth / Fresnel Power', min=0, max=5, default=0.1)
    specular_size: FloatProperty(name='Specular Size', min=0, max=1.53, default=0.5)
    specular_smooth: FloatProperty(name='Specular Smooth', min=0, max=1.53, default=0.1)
    ior: FloatProperty(name='Specular IOR', min=1.001, max=10, default=4)
    slope: FloatProperty(name='Ward Slope', min=0.001, max=0.4, default=0.1)
    emission: FloatProperty(name='Emission', min=0, max=10, default=0)
    shadeless: BoolProperty(name='Shadeless', default=False)

class ClassicScene(bpy.types.PropertyGroup):
    __annotations__ = dict(render_settings.PROPERTIES)
    source: EnumProperty(name='Scene Source', items=[('MODERN', 'Current Scene', 'Render evaluated modern geometry and editable legacy materials'),
                                                   ('ARCHIVE', 'Original Legacy File', 'Render the original scene, animation, particles and nodes from a 2.79 blend file')], default='MODERN')
    archive_path: StringProperty(name='Legacy File', subtype='FILE_PATH')
    archive_scene: StringProperty(name='Scene Name', description='Empty uses the active scene stored in the original file')
    use_legacy_settings: BoolProperty(name='Full Legacy Render Settings', default=False)
    override_archive_render: BoolProperty(name='Override File Render Settings', default=False,
        description='Apply the settings below to the original scene; load its settings first to preserve its starting appearance')
    legacy: PointerProperty(type=legacy_ui.LegacyRender)
    use_legacy_world: BoolProperty(name='Full Legacy World Settings', default=False)
    world: PointerProperty(type=legacy_ui.LegacyWorld)
    backend: EnumProperty(name='Backend', items=[('FULL', 'Full Legacy Renderer', 'Original scanlines, nodes, reflections and refraction'), ('KERNEL', 'Initial Kernel Prototype', 'Initial comparison renderer')], default='FULL')
    viewport_resolution: IntProperty(name='Resolution', description='Percentage of viewport pixels rendered after refinement', default=100, min=10, max=100, subtype='PERCENTAGE')
    viewport_pause: BoolProperty(name='Pause Preview', default=False)
    samples: EnumProperty(name='Legacy AA Samples', items=[('1', 'Off', ''), ('2', '5', ''), ('3', '8', ''), ('4', '16', '')], default='2')
    ambient: FloatProperty(name='Ambient Fill', min=0, max=1, default=0.05)
    shadows: BoolProperty(name='Ray Shadows', default=True)

class ClassicLight(bpy.types.PropertyGroup):
    use_legacy_settings: BoolProperty(name='Full Legacy Light Settings', default=False)
    legacy: PointerProperty(type=legacy_ui.LegacyLight)
    energy: FloatProperty(name='Classic Energy', min=0, max=100, default=1)
    distance: FloatProperty(name='Falloff Distance', min=0.001, default=25)
    shadows: BoolProperty(name='Cast Shadows', default=True)

class ClassicLayer(bpy.types.PropertyGroup):
    __annotations__ = {'use_pass_' + key: BoolProperty(name=name, default=False)
                       for key, (name, channels) in PASSES.items()}


def export_material(material):
    m = native.default_material()
    if material is not None:
        props = material.classic_internal
        for name, _ in m._fields_:
            value = getattr(props, name)
            if name in ('color', 'specular_color'):
                getattr(m, name)[:] = value
            else:
                setattr(m, name, int(value) if name in ('diffuse_shader', 'specular_shader', 'hardness', 'shadeless') else value)
    return m


def export_scene(depsgraph, engine):
    materials = [native.default_material()]
    material_indices = {}
    triangles, lights = [], []
    skipped = set()
    override = depsgraph.view_layer.material_override
    for instance in depsgraph.object_instances:
        if engine.test_break():
            raise InterruptedError('Render cancelled')
        obj = instance.object
        if obj.hide_render or not instance.show_self:
            continue
        matrix = instance.matrix_world.copy()
        if obj.type == 'LIGHT':
            data = obj.data
            if data.type not in ('SUN', 'POINT', 'SPOT'):
                skipped.add('area lights')
                continue
            light = native.Light()
            light.position[:] = matrix.translation
            light.direction[:] = matrix.to_quaternion() @ Vector((0, 0, -1))
            light.color[:] = data.color
            light.energy = data.classic_internal.energy
            light.distance = data.classic_internal.distance
            light.type = {'SUN': 0, 'POINT': 1, 'SPOT': 2}[data.type]
            light.shadows = data.classic_internal.shadows
            light.spot_cos = math.cos(data.spot_size / 2) if data.type == 'SPOT' else -1
            light.spot_blend = data.spot_blend if data.type == 'SPOT' else 0
            lights.append(light)
            continue
        if obj.type not in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META'):
            if obj.type in ('VOLUME', 'POINTCLOUD', 'CURVES', 'GREASEPENCIL'):
                skipped.add(obj.type.lower())
            continue
        mesh = obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
        if mesh is None:
            continue
        try:
            mesh.calc_loop_triangles()
            normal_matrix = matrix.to_3x3().inverted_safe().transposed()
            positions = [matrix @ vertex.co for vertex in mesh.vertices]
            # Corner normals include flat shading and custom split normals.
            normals = [(normal_matrix @ normal.vector).normalized() for normal in mesh.corner_normals]
            slots = []
            for material in mesh.materials:
                material = override or material
                if material is None:
                    slots.append(0)
                    continue
                key = material.as_pointer()
                if key not in material_indices:
                    material_indices[key] = len(materials)
                    materials.append(export_material(material))
                slots.append(material_indices[key])
            if override and not slots:
                key = override.as_pointer()
                if key not in material_indices:
                    material_indices[key] = len(materials)
                    materials.append(export_material(override))
                slots = [material_indices[key]]
            for tri in mesh.loop_triangles:
                t = native.Triangle()
                t.p[:] = [component for index in tri.vertices for component in positions[index]]
                t.n[:] = [component for loop in tri.loops for component in normals[loop]]
                t.material = slots[tri.material_index] if tri.material_index < len(slots) else 0
                triangles.append(t)
        finally:
            obj.to_mesh_clear()
    if skipped:
        engine.report({'WARNING'}, 'Internal port skipped unsupported: ' + ', '.join(sorted(skipped)))
    return ((native.Triangle * len(triangles))(*triangles),
            (native.Material * len(materials))(*materials),
            (native.Light * len(lights))(*lights))


def export_camera(scene, depsgraph):
    if scene.camera is None:
        raise RuntimeError('A camera is required')
    obj = scene.camera.evaluated_get(depsgraph)
    data = obj.data
    if data.type not in ('PERSP', 'ORTHO'):
        raise RuntimeError('The Internal port supports perspective and orthographic cameras only')
    frame = data.view_frame(scene=scene)
    left, right = min(v.x for v in frame), max(v.x for v in frame)
    bottom, top = min(v.y for v in frame), max(v.y for v in frame)
    rotation = obj.matrix_world.to_quaternion()
    camera = native.Camera()
    camera.origin[:] = obj.matrix_world.translation
    camera.orthographic = data.type == 'ORTHO'
    camera.lower_left[:] = rotation @ Vector((left, bottom, 0 if camera.orthographic else frame[0].z))
    camera.horizontal[:] = rotation @ Vector((right - left, 0, 0))
    camera.vertical[:] = rotation @ Vector((0, top - bottom, 0))
    camera.forward[:] = rotation @ Vector((0, 0, -1))
    camera.clip_start, camera.clip_end = data.clip_start, data.clip_end
    return camera


class InternalEngine(bpy.types.RenderEngine):
    bl_idname = ENGINE
    bl_label = 'Blender Internal (Experimental Port)'
    bl_use_preview = False
    bl_use_shading_nodes = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewport = None

    def __del__(self):
        if getattr(self, 'viewport', None) is not None:
            self.viewport.close()
        destructor = getattr(super(), '__del__', None)
        if destructor is not None:
            destructor()

    def view_update(self, context, depsgraph):
        if self.viewport is None:
            self.viewport = viewport.Viewport(self)
        self.viewport.update(context, depsgraph)

    def view_draw(self, context, depsgraph):
        if self.viewport is None:
            self.viewport = viewport.Viewport(self)
        self.viewport.draw(context, depsgraph)

    def update_render_passes(self, scene, view_layer):
        self.register_pass(scene, view_layer, 'Combined', 4, 'RGBA', 'COLOR')
        if scene.classic_internal.backend == 'FULL':
            for key, (name, channels) in PASSES.items():
                if getattr(view_layer.classic_internal, 'use_pass_' + key):
                    self.register_pass(scene, view_layer, name, len(channels), channels,
                                       'VALUE' if len(channels) == 1 else 'VECTOR' if name in ('Normal', 'UV') else 'COLOR')

    def render(self, depsgraph):
        if depsgraph.scene_eval.classic_internal.backend == 'FULL':
            with viewport.final_render():
                return self.render_full(depsgraph)
        handle = None
        lib = None
        try:
            scene = depsgraph.scene_eval
            if scene.render.use_border:
                raise RuntimeError('Render borders are not supported yet; disable Render Region')
            if scene.render.use_multiview:
                raise RuntimeError('Multiview rendering is not supported yet')
            lib = native.load()
            camera = export_camera(scene, depsgraph)
            self.update_stats('Blender Internal', 'Exporting evaluated scene')
            triangles, materials, lights = export_scene(depsgraph, self)
            handle = lib.bi_scene_create(triangles, len(triangles), materials, len(materials), lights, len(lights))
            if not handle:
                raise RuntimeError(lib.bi_last_error().decode())
            settings = native.Settings()
            settings.width = max(1, int(scene.render.resolution_x * scene.render.resolution_percentage / 100))
            settings.height = max(1, int(scene.render.resolution_y * scene.render.resolution_percentage / 100))
            settings.sample_grid = int(scene.classic_internal.samples)
            settings.ambient = scene.classic_internal.ambient
            settings.shadows = scene.classic_internal.shadows
            settings.transparent = scene.render.film_transparent
            settings.background[:] = scene.world.color if scene.world else (0.05, 0.05, 0.05)
            self.update_stats('Blender Internal', f'{len(triangles):,} triangles; legacy native shaders')
            import numpy as np
            for y in range(0, settings.height, 8):
                if self.test_break():
                    break
                rows = min(8, settings.height - y)
                pixels = np.empty((rows * settings.width, 4), dtype=np.float32)
                if not lib.bi_render_rows(handle, C.byref(camera), C.byref(settings), y, rows,
                                          pixels.ctypes.data_as(C.POINTER(C.c_float))):
                    raise RuntimeError(lib.bi_last_error().decode())
                result = self.begin_result(0, y, settings.width, rows, layer=depsgraph.view_layer.name)
                result.layers[0].passes['Combined'].rect = pixels
                self.end_result(result)
                self.update_progress((y + rows) / settings.height)
        except InterruptedError:
            pass
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            raise
        finally:
            if handle is not None and lib is not None:
                lib.bi_scene_destroy(handle)


    def render_full(self, depsgraph):
        scene = depsgraph.scene_eval
        if scene.render.use_multiview:
            raise RuntimeError('Multiview host export is not configured yet')
        with full_native.LOCK:
            try:
                self.update_stats('Blender Internal', 'Exporting into the complete legacy renderer')
                if scene.classic_internal.source == 'ARCHIVE':
                    host = full_native.Scene()
                    path = bpy.path.abspath(scene.classic_internal.archive_path)
                    if not path:
                        raise RuntimeError('Choose an original Blender Internal .blend file')
                    host.check(host.lib.bi_full_load(path.encode()))
                    host.handle = host.check(host.lib.bi_full_scene_current(scene.classic_internal.archive_scene.encode()))
                    render_settings.export(host, scene, archive=True)
                    full_export.export_region_passes(host, scene, depsgraph.view_layer)
                else:
                    host = full_export.export_scene(depsgraph, self)
                width = max(1, int(scene.render.resolution_x * scene.render.resolution_percentage / 100))
                height = max(1, int(scene.render.resolution_y * scene.render.resolution_percentage / 100))
                self.update_stats('Blender Internal', 'Original scanline and ray-tracing pipeline')
                pixels, width, height = host.render(scene.frame_current, width, height, self)
                result = self.begin_result(0, 0, width, height, layer=depsgraph.view_layer.name)
                result.layers[0].passes['Combined'].rect = pixels
                for key, (name, channels) in PASSES.items():
                    if getattr(depsgraph.view_layer.classic_internal, 'use_pass_' + key):
                        result.layers[0].passes[name].rect = host.render_pass(name)
                self.end_result(result)
            except InterruptedError:
                return
            except Exception as error:
                if self.test_break():
                    return
                self.report({'ERROR'}, str(error))
                raise


class ClassicPanel:
    bl_label = 'Blender Internal Port'
    bl_idname = 'CLASSIC_PT_render'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'

    @classmethod
    def poll(cls, context):
        return context.engine == ENGINE


class CLASSIC_PT_render(ClassicPanel, bpy.types.Panel):
    bl_label = 'Blender Internal Port'
    bl_idname = 'CLASSIC_PT_render'

    bl_order = 0

    def draw(self, context):
        layout = self.layout
        p = context.scene.classic_internal
        row = layout.row(align=True)
        row.operator('render.render', text='Render', icon='RENDER_STILL')
        row.operator('render.render', text='Animation', icon='RENDER_ANIMATION').animation = True
        layout.prop(context.scene.render, 'use_lock_interface')
        layout.prop(p, 'backend')
        if p.backend == 'KERNEL':
            for name in ('samples', 'ambient', 'shadows'):
                layout.prop(p, name)
            layout.prop(context.scene.render, 'film_transparent')
            return
        layout.prop(p, 'source')
        if p.source == 'ARCHIVE':
            layout.prop(p, 'archive_path')
            layout.prop(p, 'archive_scene')
            layout.operator('render.internal_load_settings', icon='FILE_REFRESH')
            layout.prop(p, 'override_archive_render')
            if not p.override_archive_render:
                layout.label(text='Using render settings stored in the file', icon='INFO')
                layout.label(text='Load settings to inspect and edit them.')
        else:
            layout.operator('import_scene.blender_internal')


class CLASSIC_PT_material(ClassicPanel, bpy.types.Panel):
    bl_label = 'Classic Material'
    bl_idname = 'CLASSIC_PT_material'
    bl_order = -50
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        return context.engine == ENGINE and context.material is not None

    def draw(self, context):
        layout = self.layout
        p = context.material.classic_internal
        if context.scene.classic_internal.source == 'ARCHIVE':
            layout.label(text='Original file mode ignores scene edits', icon='INFO')
            layout.prop(context.scene.classic_internal, 'source')
        if context.scene.classic_internal.backend == 'KERNEL':
            layout.label(text='Use Full Legacy Renderer for nodes and effects', icon='INFO')
            layout.prop(context.scene.classic_internal, 'backend')
        layout.template_ID(p, 'node_tree', new='material.internal_new_tree')
        if p.node_tree:
            layout.prop(p, 'use_nodes')
            layout.operator('material.internal_edit_nodes', icon='NODETREE')
        layout.prop(p.legacy, 'type', text='Material Type')


class CLASSIC_PT_light(ClassicPanel, bpy.types.Panel):
    bl_label = 'Classic Light'
    bl_idname = 'CLASSIC_PT_light'
    bl_context = 'data'

    @classmethod
    def poll(cls, context):
        return context.engine == ENGINE and context.light is not None

    def draw(self, context):
        layout = self.layout
        data = context.light
        layout.prop(data.classic_internal, 'use_legacy_settings')
        if data.classic_internal.use_legacy_settings:
            p = data.classic_internal.legacy
            for prop in legacy_ui.SCHEMA['lights'][p.type]:
                layout.prop(p, prop['id'])
            return
        layout.prop(data, 'type')
        layout.prop(data, 'color')
        for name in ('energy', 'distance', 'shadows'):
            layout.prop(data.classic_internal, name)
        if data.type == 'SPOT':
            layout.prop(data, 'spot_size')
            layout.prop(data, 'spot_blend')
        if data.type == 'AREA':
            layout.prop(data, 'shape')
            layout.prop(data, 'size')
            if data.shape == 'RECTANGLE':
                layout.prop(data, 'size_y')

class CLASSIC_PT_world(ClassicPanel, bpy.types.Panel):
    bl_label = 'Legacy World, Ambient Occlusion and Mist'
    bl_idname = 'CLASSIC_PT_world'
    bl_context = 'world'

    def draw(self, context):
        p = context.scene.classic_internal
        self.layout.prop(p, 'use_legacy_world')
        if p.use_legacy_world:
            for prop in legacy_ui.SCHEMA['world']:
                self.layout.prop(p.world, prop['id'])
            for name, schema in legacy_ui.SCHEMA['world_nested'].items():
                box = self.layout.box()
                box.label(text=name.replace('_', ' ').title())
                for prop in schema:
                    box.prop(getattr(p.world, name), prop['id'])
        elif context.scene.world:
            self.layout.prop(context.scene.world, 'color', text='Horizon Color')
            self.layout.prop(p, 'ambient')


class CLASSIC_PT_textures(material_ui.MaterialPanel, bpy.types.Panel):
    bl_label = 'Texture Slots'
    bl_idname = 'CLASSIC_PT_textures'
    bl_order = 6
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.operator('material.internal_texture_slot', icon='ADD').remove = -1
        for index, slot in enumerate(context.material.classic_internal.texture_slots):
            head, body = self.layout.panel('internal_slot_' + str(index), default_closed=False)
            head.prop(slot, 'enabled', text='')
            head.label(text=slot.texture.name if slot.texture else 'Empty Texture Slot')
            op = head.operator('material.internal_texture_slot', text='', icon='X')
            op.remove = index
            if body:
                material_ui.draw_texture(body, slot, str(index))

class CLASSIC_PT_passes(ClassicPanel, bpy.types.Panel):
    bl_label = 'Legacy Render Passes'
    bl_idname = 'CLASSIC_PT_passes'
    bl_context = 'view_layer'

    def draw(self, context):
        for key in PASSES:
            self.layout.prop(context.view_layer.classic_internal, 'use_pass_' + key)


CLASSES = (ClassicMaterial, ClassicScene, ClassicLight, ClassicLayer, InternalEngine,
           CLASSIC_PT_render, CLASSIC_PT_material, CLASSIC_PT_light, CLASSIC_PT_world, CLASSIC_PT_textures, CLASSIC_PT_passes, *material_ui.CLASSES, *render_ui.CLASSES)
_compat_panels = []

def register():
    legacy_ui.register()
    for cls in CLASSES:
        legacy_ui.add_update_callbacks(cls)
        bpy.utils.register_class(cls)
    bpy.types.Material.classic_internal = PointerProperty(type=ClassicMaterial)
    bpy.types.Scene.classic_internal = PointerProperty(type=ClassicScene)
    bpy.types.Light.classic_internal = PointerProperty(type=ClassicLight)
    bpy.types.ViewLayer.classic_internal = PointerProperty(type=ClassicLayer)
    legacy_import.register()
    viewport.register()
    # Reuse Blender's material slots, assignment, datablock and output controls.
    for name in ('RENDER_PT_context', 'RENDER_PT_color_management', 'DATA_PT_lens', 'DATA_PT_camera',
                 'DATA_PT_camera_display', 'RENDER_PT_output', 'RENDER_PT_format', 'RENDER_PT_frame_range',
                 'MATERIAL_PT_custom_props',
                 'MATERIAL_PT_animation', 'RENDER_PT_output_color_management',
                 'RENDER_PT_encoding', 'RENDER_PT_encoding_video', 'RENDER_PT_encoding_audio',
                 'RENDER_PT_time_stretching', 'RENDER_PT_post_processing', 'RENDER_PT_stamp', 'RENDER_PT_stamp_note', 'RENDER_PT_stamp_burn',
                 'RENDER_PT_color_management_working_space', 'RENDER_PT_color_management_advanced',
                 'RENDER_PT_color_management_curves', 'RENDER_PT_color_management_white_balance'):
        panel = getattr(bpy.types, name, None)
        if panel and hasattr(panel, 'COMPAT_ENGINES') and ENGINE not in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.add(ENGINE)
            _compat_panels.append(panel)


def unregister():
    viewport.unregister()
    legacy_import.unregister()
    for panel in _compat_panels:
        panel.COMPAT_ENGINES.discard(ENGINE)
    _compat_panels.clear()
    for cls in (bpy.types.Material, bpy.types.Scene, bpy.types.Light, bpy.types.ViewLayer):
        del cls.classic_internal
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    legacy_ui.unregister()
