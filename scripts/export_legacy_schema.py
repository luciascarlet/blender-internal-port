# SPDX-License-Identifier: GPL-2.0-or-later
"""Run only in the official 2.79b reference binary to record its editable RNA schema."""
import bpy
import json
import os
import re
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
scene=bpy.context.scene
scene.render.engine='BLENDER_RENDER'
material=bpy.data.materials.new('Schema')
material.use_nodes=True
ignored={'rna_type','name','name_full','is_updated','is_updated_data','is_library_indirect','is_evaluated','tag','use_fake_user','use_extra_user','users','pass_index','use_nodes','active_texture_index','is_embedded_data'}
node_ignored={'location','width','width_hidden','height','dimensions','show_options','show_preview','show_texture','hide','select','mute','use_custom_color','color','label','type','bl_idname','bl_label','bl_description','bl_icon','bl_static_type','bl_width_default','bl_width_min','bl_width_max','bl_height_default','bl_height_min','bl_height_max'}

def properties(obj,skip=()):
    result=[]
    for p in obj.bl_rna.properties:
        if p.identifier in ignored or p.identifier in skip or p.is_readonly: continue
        if p.type not in ('BOOLEAN','INT','FLOAT','ENUM','STRING'): continue
        try: value=getattr(obj,p.identifier)
        except Exception: continue
        d={'id':p.identifier,'name':p.name,'description':p.description,'type':p.type}
        if p.type in ('FLOAT','INT','BOOLEAN'):
            if p.array_length:
                d['size']=p.array_length;d['default']=list(value)
            else:d['default']=value
            if p.type!='BOOLEAN':
                d['min']=p.hard_min;d['max']=p.hard_max
            d['subtype']=p.subtype
        elif p.type=='ENUM':
            if p.is_enum_flag: continue
            d['items']=[(i.identifier,i.name,i.description) for i in p.enum_items if i.identifier]
            if not d['items']: continue
            d['default']=value
        else:d['default']=value
        result.append(d)
    return result

schema={'version':bpy.app.version_string,'material':properties(material),'nested':{},'nodes':{}}
for name in ('raytrace_mirror','raytrace_transparency','subsurface_scattering','halo','volume','strand'):
    schema['nested'][name]=properties(getattr(material,name))
# Match source-declared legacy shader compatibility, including shared math nodes.
source=os.path.join(ROOT,'blender-legacy/source/blender/nodes')
legacy_ids=set()
for filename in os.listdir(os.path.join(source,'shader/nodes')):
    if not filename.endswith('.c'):continue
    text=open(os.path.join(source,'shader/nodes',filename)).read()
    for function in re.split(r'\nvoid register_node_type_',text)[1:]:
        if 'NODE_OLD_SHADING' in function:
            match=re.search(r'sh_node_type_base\(&ntype,\s*(\w+)',function)
            if match:legacy_ids.add(match.group(1))
for line in open(os.path.join(source,'NOD_static_types.h')):
    match=re.search(r'DefNode\(\s*ShaderNode,\s*(\w+),[^,]+,[^,]+,\s*(\w+),',line)
    if not match or match.group(1) not in legacy_ids:continue
    typename='ShaderNode'+match.group(2)
    node=material.node_tree.nodes.new(typename)
    item={'name':node.bl_label,'properties':properties(node,node_ignored)}
    for direction in ('inputs','outputs'):
        item[direction]=[]
        for socket in getattr(node,direction):
            if socket.type not in ('VALUE','RGBA','VECTOR'):continue
            value=getattr(socket,'default_value',None)
            try:value=list(value)
            except TypeError:pass
            item[direction].append({'name':socket.name,'identifier':socket.identifier,'type':socket.type,'default':value})
    # Pointer-backed controls need explicit host support rather than losing them.
    item['pointers']=[p.identifier for p in node.bl_rna.properties if p.type=='POINTER' and p.identifier not in ('rna_type','id_data','parent','internal_links')]
    schema['nodes'][typename]=item
    material.node_tree.nodes.remove(node)
schema['textures']={}
for typename in ('NONE','BLEND','CLOUDS','DISTORTED_NOISE','IMAGE','MAGIC','MARBLE','MUSGRAVE','NOISE','STUCCI','VORONOI','WOOD'):
    texture=bpy.data.textures.new('schema '+typename,typename)
    schema['textures'][typename]=properties(texture)
slot=material.texture_slots.add()
schema['texture_slot']=properties(slot, {'output_node'})
schema['world'] = properties(scene.world)
schema['world_nested'] = {name: properties(getattr(scene.world, name))
                          for name in ('light_settings', 'mist_settings')}
schema['lights'] = {kind: properties(bpy.data.lamps.new('Schema ' + kind, kind))
                    for kind in ('POINT', 'SUN', 'SPOT', 'HEMI', 'AREA')}
schema['light'] = list({p['id']: p for items in schema['lights'].values() for p in items}.values())
schema['render'] = properties(scene.render, {'engine', 'filepath', 'file_extension', 'resolution_x', 'resolution_y', 'resolution_percentage', 'use_border', 'use_crop_to_border', 'border_min_x', 'border_max_x', 'border_min_y', 'border_max_y'})
schema['texture_nodes'] = {}
texture = bpy.data.textures.new('Schema node texture', 'NONE')
texture.use_nodes = True
for line in open(os.path.join(source, 'NOD_static_types.h')):
    match = re.search(r'DefNode\(\s*TextureNode,[^,]+,[^,]+,[^,]+,\s*(\w+),', line)
    if not match: continue
    typename = 'TextureNode' + match.group(1)
    node = texture.node_tree.nodes.new(typename)
    schema['texture_nodes'][typename] = {
        'properties': properties(node, node_ignored),
        'pointers': [p.identifier for p in node.bl_rna.properties if p.type == 'POINTER' and p.identifier not in ('rna_type', 'id_data', 'parent', 'internal_links')],
    }
    for direction in ('inputs', 'outputs'):
        schema['texture_nodes'][typename][direction] = [s.name for s in getattr(node, direction)]
    texture.node_tree.nodes.remove(node)
with open(os.path.join(ROOT,'addon/blender_internal/legacy_schema.json'),'w') as f:json.dump(schema,f,indent=2)
print('SCHEMA_OK',len(schema['material']),len(schema['nodes']))
