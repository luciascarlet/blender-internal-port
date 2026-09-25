/* SPDX-License-Identifier: GPL-2.0-or-later
 * In-process host boundary for the COMPLETE Blender 2.79b Internal pipeline.
 * All renderer, legacy shader/texture nodes, ray code and scanline sources are
 * linked from the pinned legacy source tree, compiled for the host architecture.
 * Calls are serialized by the Python host: legacy Blender has global state.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "DNA_genfile.h"
#include "DNA_scene_types.h"
#include "BLI_threads.h"
#include "BLI_callbacks.h"
#include "BLI_string.h"
#include "BLI_rect.h"
#include "BKE_appdir.h"
#include "BKE_blender.h"
#include "BKE_blendfile.h"
#include "BKE_brush.h"
#include "BKE_cachefile.h"
#include "BKE_context.h"
#include "BKE_depsgraph.h"
#include "BKE_font.h"
#include "BKE_global.h"
#include "BKE_icons.h"
#include "BKE_image.h"
#include "BKE_material.h"
#include "BKE_modifier.h"
#include "BKE_node.h"
#include "BKE_particle.h"
#include "BKE_report.h"
#include "BKE_scene.h"
#include "BKE_sound.h"
#include "IMB_imbuf.h"
#include "RE_engine.h"
#include "RE_pipeline.h"
#include "RE_render_ext.h"
#include "RNA_define.h"
#include "RNA_access.h"
#include "ED_datafiles.h"
#include "BLO_readfile.h"

#ifdef _WIN32
#define FULL_API __declspec(dllexport)
#else
#define FULL_API __attribute__((visibility("default")))
#endif
static bContext *context;
static struct Render *render;
static char last_error[2048];
static ReportList reports;
static int (*cancel_callback)(void *);
static void (*progress_callback)(void *, float);
static void *callback_data;
static void reset_handles(void);

FULL_API const char *bi_full_error(void) { return last_error; }
FULL_API int bi_full_abi_version(void) { return 1; }
FULL_API int bi_full_initialize(const char *resource_path) {
  if(context) return 1;
  BKE_appdir_program_path_init(resource_path);
  BLI_threadapi_init();
  DNA_sdna_current_init();
  BKE_blender_globals_init();
  G.background = true;
  G.factory_startup = true;
  G.f &= ~G_SCRIPT_AUTOEXEC;
  G.fileflags |= G_FILE_NO_UI;
  IMB_init();
  BKE_cachefiles_init();
  BKE_images_init();
  BKE_modifier_init();
  DAG_init();
  BKE_brush_system_init();
  RE_texture_rng_init();
  BLI_callback_global_init();
  RNA_init();
  RE_engines_init();
  init_nodesystem();
  psys_init_rng();
  BKE_vfont_builtin_register(datatoc_bfont_pfb, datatoc_bfont_pfb_size);
  BKE_sound_init_once();
  init_def_material();
  BKE_icons_init(1);
  BKE_tempdir_init(NULL);
  context = CTX_create();
  CTX_data_main_set(context, G.main);
  BKE_reports_init(&reports, RPT_STORE);
  return 1;
}
FULL_API void bi_full_callbacks(int (*cancel)(void *), void (*progress)(void *,float), void *data) {
  cancel_callback=cancel;progress_callback=progress;callback_data=data;
}
static int should_break(void *data) {
  (void)data;
  return cancel_callback ? cancel_callback(callback_data):0;
}
static void progress(void *data,float value) {
  (void)data;
  if(progress_callback) progress_callback(callback_data,value);
}
FULL_API int bi_full_load(const char *path) {
  if(!context) { strcpy(last_error,"Full engine is not initialized");return 0; }
  if(render) { RE_FreeRender(render);render=NULL; }
  reset_handles();
  RNA_property_update_cache_free();
  BKE_reports_clear(&reports);
  last_error[0]=0;
  if(!BKE_blendfile_read(context,path,&reports,BLO_READ_SKIP_USERDEF)) {
    BLI_snprintf(last_error,sizeof(last_error),"Could not read legacy scene: %s",path);return 0;
  }
  G.f &= ~G_SCRIPT_AUTOEXEC;
  Scene *scene=CTX_data_scene(context);
  if(!scene) { strcpy(last_error,"Legacy file has no scene");return 0; }
  return 1;
}
FULL_API int bi_full_render(int frame,int width,int height) {
  Scene *scene=context?CTX_data_scene(context):NULL;
  if(!scene) { strcpy(last_error,"No scene loaded");return 0; }
  if(!scene->camera) { strcpy(last_error,"Legacy scene has no camera");return 0; }
  if(strcmp(scene->r.engine,"BLENDER_RENDER")) { strcpy(last_error,"Scene does not use Blender Internal");return 0; }
  if(width>0 && height>0) { scene->r.xsch=width;scene->r.ysch=height;scene->r.size=100; }
  G.is_break=false;
  if(render) RE_FreeRender(render);
  render=RE_NewRender("Legacy Full Engine");
  RE_SetReports(render,&reports);
  RE_test_break_cb(render,NULL,should_break);
  RE_progress_cb(render,NULL,progress);
  RE_BlenderFrame(render,G.main,scene,NULL,NULL,0,frame,false);
  if(should_break(NULL)) { strcpy(last_error,"Render cancelled");return 0; }
  return 1;
}
/* Adapted from 2.79 render_internal.c: Rendered viewport's progressive scanline
 * job. No window/context pointers cross this boundary. The host owns scheduling,
 * cancellation and display; the original render database is retained between
 * resolution steps. All entry points require the same serialized library lock. */
static void preview_stats(void *data, RenderStats *stats) { (void)data; (void)stats; }
static float preview_view[4][4];
static int preview_step_count;
FULL_API int bi_full_preview_begin(int frame, int width, int height,
                                   const float *view, const float *plane,
                                   float near_clip, float far_clip, int ortho) {
  Scene *scene=context?CTX_data_scene(context):NULL;
  if(!scene || width<1 || height<1 || !view || !plane) {
    strcpy(last_error,"Invalid viewport scene or dimensions");return 0;
  }
  if(render) RE_FreeRender(render);
  render=RE_NewRender("Legacy Viewport Preview");
  RE_stats_draw_cb(render,NULL,preview_stats);
  RE_SetReports(render,&reports);
  RE_test_break_cb(render,NULL,should_break);
  RE_progress_cb(render,NULL,progress);
  G.is_break=false;
  scene->r.cfra=frame;
  EvaluationContext eval_ctx={0};
  eval_ctx.mode=DAG_EVAL_PREVIEW;
  BKE_scene_update_for_newframe(&eval_ctx,G.main,scene,scene->lay);
  RenderData rd=scene->r;
  rd.mode &= ~(R_OSA|R_MBLUR|R_BORDER|R_PANORAMA|R_FIELDS|R_EDGE_FRS);
  rd.scemode &= ~(R_DOSEQ|R_DOCOMP|R_FREE_IMAGE|R_EXR_TILE_FILE|R_FULL_SAMPLE);
  rd.scemode |= R_VIEWPORT_PREVIEW|R_SINGLE_LAYER;
  RE_InitState(render,NULL,&rd,NULL,width,height,NULL);
  rctf viewplane={plane[0],plane[1],plane[2],plane[3]};
  if(ortho) RE_SetOrtho(render,&viewplane,near_clip,far_clip);
  else RE_SetWindow(render,&viewplane,near_clip,far_clip);
  RE_SetPixelSize(render,(plane[1]-plane[0])/width);
  memcpy(preview_view,view,sizeof(preview_view));
  RE_SetView(render,preview_view);
  RE_Database_FromScene(render,G.main,scene,scene->lay,0);
  RE_Database_Preprocess(render);
  RE_DataBase_ApplyWindow(render);
  RE_updateRenderInstances(render,RE_OBJECT_INSTANCES_UPDATE_VIEW);
  preview_step_count=0;
  if(should_break(NULL)) { strcpy(last_error,"Viewport render cancelled");return 0; }
  return 1;
}
FULL_API int bi_full_preview_step(int width,int height) {
  if(!render || width<1 || height<1) { strcpy(last_error,"No viewport render");return 0; }
  if(preview_step_count>1) RE_DataBase_IncrementalView(render,preview_view,1);
  RE_ChangeResolution(render,width,height,NULL);
  if(preview_step_count) {
    RE_DataBase_IncrementalView(render,preview_view,0);
    RE_DataBase_ApplyWindow(render);
  }
  RE_TileProcessor(render);
  preview_step_count++;
  if(should_break(NULL)) { strcpy(last_error,"Viewport render cancelled");return 0; }
  return 1;
}
FULL_API void bi_full_preview_end(void) {
  if(render) { RE_FreeRender(render);render=NULL; }
}
FULL_API int bi_full_result(float *rgba,uint64_t capacity,int *width,int *height) {
  if(!render) { strcpy(last_error,"No render result");return 0; }
  RenderResult result={0};
  RE_AcquireResultImage(render,&result,0);
  *width=result.rectx;*height=result.recty;
  uint64_t length=(uint64_t)result.rectx*result.recty*4;
  int ok=result.rectf && length>0;
  if(rgba && ok) {
    if(capacity<length) { ok=0;strcpy(last_error,"Result buffer too small"); }
    else memcpy(rgba,result.rectf,length*sizeof(float));
  }
  RE_ReleaseResultImage(render);
  return ok;
}

/* Owned scene construction and legacy RNA bridge. Handles expire on reset/load. */
#include "MEM_guardedalloc.h"
#include "DNA_camera_types.h"
#include "DNA_lamp_types.h"
#include "DNA_material_types.h"
#include "DNA_texture_types.h"
#include "DNA_mesh_types.h"
#include "DNA_meshdata_types.h"
#include "DNA_object_types.h"
#include "DNA_node_types.h"
#include "DNA_world_types.h"
#include "BKE_main.h"
#include "BKE_library.h"
#include "BKE_mesh.h"
#include "BKE_object.h"
#include "BKE_customdata.h"
#include "BKE_world.h"
#include "BKE_texture.h"
#include "BLI_math.h"
#include "BLI_listbase.h"
#include "RNA_access.h"

static PointerRNA *handles;
static int handle_count, handle_capacity, handle_base;
static void reset_handles(void) {
  handle_base += handle_count;
  handle_count = 0;
}
static int add_pointer(PointerRNA p) {
  if(!p.data) return 0;
  for(int i=0;i<handle_count;i++)
    if(handles[i].data==p.data && handles[i].type==p.type) return handle_base+i+1;
  if(handle_count==handle_capacity) {
    handle_capacity=handle_capacity?handle_capacity*2:256;
    handles=MEM_reallocN(handles,sizeof(*handles)*handle_capacity);
  }
  handles[handle_count]=p;
  return handle_base + ++handle_count;
}
static int add_id(ID *id) {
  PointerRNA p;RNA_id_pointer_create(id,&p);return add_pointer(p);
}
static PointerRNA *get_pointer(int h) {
  h -= handle_base;
  if(h<1||h>handle_count) { strcpy(last_error,"Invalid or expired handle");return NULL; }
  PointerRNA *ptr=&handles[h-1];
  if(ptr->id.data==ptr->data) RNA_id_pointer_create(ptr->data,ptr);
  return ptr;
}
FULL_API int bi_full_scene_new(void) {
  if(!context) return 0;
  last_error[0]=0;
  if(render) { RE_FreeRender(render);render=NULL; }
  RNA_property_update_cache_free();
  BKE_blender_globals_clear();
  G.main=BKE_main_new();
  reset_handles();
  Scene *scene=BKE_scene_add(G.main,"Modern scene");
  CTX_data_main_set(context,G.main);
  CTX_data_scene_set(context,scene);
  CTX_wm_manager_set(context,NULL);
  CTX_wm_screen_set(context,NULL);
  G.f &= ~G_SCRIPT_AUTOEXEC;
  return add_id((ID *)scene);
}
FULL_API int bi_full_create(const char *kind,const char *name) {
  Scene *scene=CTX_data_scene(context);
  ID *id=NULL;
  if(!strcmp(kind,"MATERIAL")) id=(ID *)BKE_material_add(G.main,name);
  else if(!strcmp(kind,"TEXTURE")) id=(ID *)BKE_texture_add(G.main,name);
  else if(!strcmp(kind,"WORLD")) { id=(ID *)add_world(G.main,name);scene->world=(World *)id; }
  else {
    int type=!strcmp(kind,"MESH")?OB_MESH:!strcmp(kind,"CAMERA")?OB_CAMERA:!strcmp(kind,"LIGHT")?OB_LAMP:0;
    if(type) {
      Object *ob=BKE_object_add(G.main,scene,type,name);
      if(type==OB_CAMERA) scene->camera=ob;
      id=(ID *)ob;
    }
  }
  if(!id) { strcpy(last_error,"Unsupported datablock kind");return 0; }
  return add_id(id);
}
static int resolve(int h,const char *path,PointerRNA *ptr,PropertyRNA **prop) {
  PointerRNA *source=get_pointer(h);
  if(!source) return 0;
  if(!RNA_path_resolve_property(source,path,ptr,prop)) {
    BLI_snprintf(last_error,sizeof(last_error),"Unknown legacy property: %s",path);return 0;
  }
  if(!RNA_property_editable(ptr,*prop)) {
    BLI_snprintf(last_error,sizeof(last_error),"Read-only legacy property: %s",path);return 0;
  }
  return 1;
}
FULL_API int bi_full_set_numbers(int h,const char *path,const double *values,int count) {
  PointerRNA ptr;PropertyRNA *prop;
  if(!resolve(h,path,&ptr,&prop)) return 0;
  int length=RNA_property_array_length(&ptr,prop);
  if(count!=(length?length:1)) { strcpy(last_error,"Wrong property array length");return 0; }
  switch(RNA_property_type(prop)) {
    case PROP_FLOAT:
      if(length) { float *data=MEM_mallocN(sizeof(float)*length,"property values");for(int i=0;i<length;i++) data[i]=(float)values[i];RNA_property_float_set_array(&ptr,prop,data);MEM_freeN(data); }
      else RNA_property_float_set(&ptr,prop,(float)values[0]);
      break;
    case PROP_INT:
    case PROP_BOOLEAN: {
      int *data=MEM_mallocN(sizeof(int)*count,"property values");for(int i=0;i<count;i++) data[i]=(int)values[i];
      if(RNA_property_type(prop)==PROP_BOOLEAN) {
        if(length) RNA_property_boolean_set_array(&ptr,prop,data);else RNA_property_boolean_set(&ptr,prop,data[0]);
      } else { if(length) RNA_property_int_set_array(&ptr,prop,data);else RNA_property_int_set(&ptr,prop,data[0]); }
      MEM_freeN(data);break;
    }
    default:strcpy(last_error,"Property is not numeric");return 0;
  }
  RNA_property_update(context,&ptr,prop);
  return 1;
}
FULL_API int bi_full_set_string(int h,const char *path,const char *value) {
  PointerRNA ptr;PropertyRNA *prop;
  if(!resolve(h,path,&ptr,&prop)) return 0;
  if(RNA_property_type(prop)==PROP_STRING) RNA_property_string_set(&ptr,prop,value);
  else if(RNA_property_type(prop)==PROP_ENUM) {
    EnumPropertyItem *items=NULL;bool free_items=false;int enum_value;
    RNA_property_enum_items(context,&ptr,prop,&items,NULL,&free_items);
    bool found=RNA_enum_value_from_id(items,value,&enum_value);
    if(free_items) MEM_freeN(items);
    if(!found) { BLI_snprintf(last_error,sizeof(last_error),"Invalid enum %s for %s",value,path);return 0; }
    RNA_property_enum_set(&ptr,prop,enum_value);
  } else { strcpy(last_error,"Property is not a string or enum");return 0; }
  RNA_property_update(context,&ptr,prop);
  return 1;
}
FULL_API int bi_full_set_pointer(int h,const char *path,int target) {
  PointerRNA ptr;PropertyRNA *prop;PointerRNA *value=get_pointer(target);
  if(!value||!resolve(h,path,&ptr,&prop)) return 0;
  if(RNA_property_type(prop)!=PROP_POINTER || !RNA_struct_is_a(value->type,RNA_property_pointer_type(&ptr,prop))) {
    strcpy(last_error,"Incompatible pointer property");return 0;
  }
  RNA_property_pointer_set(&ptr,prop,*value);RNA_property_update(context,&ptr,prop);return 1;
}
FULL_API int bi_full_mesh(int h,int vertices,const float *coords,int polygons,const int *starts,const int *counts,int loops,const int *indices,const int *materials,const unsigned char *smooth,const float *normals) {
  PointerRNA *ptr=get_pointer(h);if(!ptr||!RNA_struct_is_a(ptr->type,&RNA_Object)) return 0;
  Object *ob=ptr->data;if(ob->type!=OB_MESH) return 0;
  Mesh *mesh=ob->data;
  if(vertices<0||polygons<0||loops<0||mesh->totvert) return 0;
  for(int i=0;i<loops;i++) if(indices[i]<0||indices[i]>=vertices) return 0;
  for(int i=0;i<polygons;i++) if(starts[i]<0||counts[i]<3||starts[i]>loops-counts[i]) return 0;
  mesh->totvert=vertices;mesh->totpoly=polygons;mesh->totloop=loops;
  mesh->mvert=CustomData_add_layer(&mesh->vdata,CD_MVERT,CD_CALLOC,NULL,vertices);
  mesh->mpoly=CustomData_add_layer(&mesh->pdata,CD_MPOLY,CD_CALLOC,NULL,polygons);
  mesh->mloop=CustomData_add_layer(&mesh->ldata,CD_MLOOP,CD_CALLOC,NULL,loops);
  for(int i=0;i<vertices;i++) copy_v3_v3(mesh->mvert[i].co,coords+i*3);
  for(int i=0;i<loops;i++) mesh->mloop[i].v=indices[i];
  for(int i=0;i<polygons;i++) {
    mesh->mpoly[i].loopstart=starts[i];mesh->mpoly[i].totloop=counts[i];
    mesh->mpoly[i].mat_nr=materials[i];mesh->mpoly[i].flag=smooth[i]?ME_SMOOTH:0;
  }
  BKE_mesh_calc_edges(mesh,false,false);
  BKE_mesh_calc_normals(mesh);
  if(normals) {
    mesh->flag|=ME_AUTOSMOOTH;
    float (*copy)[3]=MEM_mallocN(sizeof(float)*loops*3,"split normals");
    memcpy(copy,normals,sizeof(float)*loops*3);
    float (*polynors)[3]=MEM_mallocN(sizeof(float[3])*polygons,"polygon normals");
    short (*clnors)[2]=CustomData_add_layer(&mesh->ldata,CD_CUSTOMLOOPNORMAL,CD_DEFAULT,NULL,loops);
    BKE_mesh_calc_normals_poly(mesh->mvert,NULL,vertices,mesh->mloop,mesh->mpoly,loops,polygons,polynors,false);
    BKE_mesh_normals_loop_custom_set(mesh->mvert,vertices,mesh->medge,mesh->totedge,mesh->mloop,copy,loops,mesh->mpoly,(const float (*)[3])polynors,polygons,clnors);
    MEM_freeN(polynors);
    MEM_freeN(copy);
  }
  BKE_mesh_texspace_calc(mesh);
  return 1;
}
FULL_API int bi_full_mesh_material(int h,int material,int slot) {
  PointerRNA *ob=get_pointer(h),*ma=get_pointer(material);
  if(!ob||!ma||!RNA_struct_is_a(ob->type,&RNA_Object)||!RNA_struct_is_a(ma->type,&RNA_Material)||slot<1) return 0;
  assign_material(ob->data,ma->data,slot,BKE_MAT_ASSIGN_OBDATA);return 1;
}
FULL_API int bi_full_mesh_uv(int h,const char *name,int count,const float *uv) {
  PointerRNA *p=get_pointer(h);if(!p||!RNA_struct_is_a(p->type,&RNA_Object)) return 0;
  Object *ob=p->data;if(ob->type!=OB_MESH) return 0;Mesh *me=ob->data;
  if(count!=me->totloop) return 0;
  MLoopUV *layer=CustomData_add_layer_named(&me->ldata,CD_MLOOPUV,CD_CALLOC,NULL,count,name);
  CustomData_add_layer_named(&me->pdata,CD_MTEXPOLY,CD_CALLOC,NULL,me->totpoly,name);
  for(int i=0;i<count;i++) copy_v2_v2(layer[i].uv,uv+i*2);
  BKE_mesh_update_customdata_pointers(me,true);return 1;
}
FULL_API int bi_full_material_tree(int h) {
  PointerRNA *p=get_pointer(h);if(!p||!RNA_struct_is_a(p->type,&RNA_Material)) return 0;
  Material *ma=p->data;
  if(!ma->nodetree) ma->nodetree=ntreeAddTree(NULL,"Legacy shader","ShaderNodeTree");
  ma->use_nodes=1;
  return add_id((ID *)ma->nodetree);
}
FULL_API int bi_full_texture_tree(int h) {
  PointerRNA *p=get_pointer(h);if(!p||!RNA_struct_is_a(p->type,&RNA_Texture)) return 0;
  Tex *tex=p->data;
  if(!tex->nodetree) tex->nodetree=ntreeAddTree(NULL,"Legacy texture","TextureNodeTree");
  tex->use_nodes=1;
  return add_id((ID *)tex->nodetree);
}
FULL_API int bi_full_node(int tree,const char *type) {
  PointerRNA *p=get_pointer(tree);if(!p||!RNA_struct_is_a(p->type,&RNA_NodeTree)) return 0;
  bNodeTree *nt=p->data;bNode *node=nodeAddNode(NULL,nt,type);
  if(!node) { BLI_snprintf(last_error,sizeof(last_error),"Unknown legacy node %s",type);return 0; }
  PointerRNA pointer;RNA_pointer_create(&nt->id,&RNA_Node,node,&pointer);
  return add_pointer(pointer);
}
FULL_API int bi_full_node_link(int tree,int from,int output,int to,int input) {
  PointerRNA *nt=get_pointer(tree),*a=get_pointer(from),*b=get_pointer(to);
  if(!nt||!a||!b||!RNA_struct_is_a(nt->type,&RNA_NodeTree)||!RNA_struct_is_a(a->type,&RNA_Node)||!RNA_struct_is_a(b->type,&RNA_Node)) return 0;
  bNode *na=a->data,*nb=b->data;
  bNodeSocket *out=BLI_findlink(&na->outputs,output),*in=BLI_findlink(&nb->inputs,input);
  if(!out||!in||a->id.data!=nt->data||b->id.data!=nt->data) return 0;
  nodeAddLink(nt->data,na,out,nb,in);
  ntreeUpdateTree(G.main,nt->data);
  return 1;
}

#include "DNA_texture_types.h"
#include "DNA_color_types.h"
#include "IMB_imbuf_types.h"
#include "IMB_colormanagement.h"
#include "BKE_colortools.h"
static int sub_pointer(int handle,const char *path,PointerRNA *value) {
  PointerRNA *source=get_pointer(handle),ptr;PropertyRNA *prop;
  if(!source||!RNA_path_resolve_property(source,path,&ptr,&prop)||RNA_property_type(prop)!=PROP_POINTER) {
    BLI_snprintf(last_error,sizeof(last_error),"Invalid storage path: %s",path);return 0;
  }
  *value=RNA_property_pointer_get(&ptr,prop);
  if(!value->data) { strcpy(last_error,"Unallocated node storage");return 0; }
  return 1;
}
FULL_API int bi_full_ramp(int handle,const char *path,int count,const float *positions,const float *colors) {
  PointerRNA ptr;if(!sub_pointer(handle,path,&ptr)||!RNA_struct_is_a(ptr.type,&RNA_ColorRamp)) return 0;
  if(count<1||count>32) { strcpy(last_error,"Legacy color ramps support 1-32 stops");return 0; }
  ColorBand *band=ptr.data;band->tot=count;
  for(int i=0;i<count;i++) { band->data[i].pos=positions[i];copy_v4_v4(&band->data[i].r,colors+i*4); }
  return 1;
}
FULL_API int bi_full_curve(int handle,const char *path,int index,int count,const float *xy,const int *types) {
  PointerRNA ptr;if(!sub_pointer(handle,path,&ptr)||!RNA_struct_is_a(ptr.type,&RNA_CurveMapping)) return 0;
  if(index<0||index>=4||count<2||count>32767) return 0;
  CurveMapping *mapping=ptr.data;CurveMap *curve=&mapping->cm[index];
  if(curve->curve) MEM_freeN(curve->curve);
  curve->curve=MEM_callocN(sizeof(CurveMapPoint)*count,"host curve");curve->totpoint=count;
  for(int i=0;i<count;i++) {
    curve->curve[i].x=xy[i*2];curve->curve[i].y=xy[i*2+1];
    curve->curve[i].flag=types[i]==1?CUMA_HANDLE_VECTOR:types[i]==2?CUMA_HANDLE_AUTO_ANIM:0;
  }
  curvemapping_changed_all(mapping);curvemapping_initialize(mapping);return 1;
}
FULL_API int bi_full_image(const char *name,int width,int height,const float *pixels) {
  if(width<1||height<1||!pixels) return 0;
  ImBuf *buffer=IMB_allocImBuf(width,height,32,IB_rectfloat);
  if(!buffer) return 0;
  /* Host pixels have no backing file to reload after cache eviction. Keep
   * them for this scene's lifetime, like normal loaded still-image textures. */
  buffer->userflags |= IB_PERSISTENT;
  memcpy(buffer->rect_float,pixels,(size_t)width*height*4*sizeof(float));
  struct Image *image=BKE_image_add_from_imbuf(buffer,name);
  IMB_freeImBuf(buffer);
  if(!image) return 0;
  return add_id((ID *)image);
}
FULL_API int bi_full_image_bytes(const char *name,int width,int height,const unsigned char *pixels,int is_data) {
  if(width<1||height<1||!pixels) return 0;
  ImBuf *buffer=IMB_allocImBuf(width,height,32,IB_rect);
  if(!buffer) return 0;
  buffer->userflags |= IB_PERSISTENT;
  memcpy(buffer->rect,pixels,(size_t)width*height*4);
  IMB_colormanagement_assign_rect_colorspace(buffer,is_data?"Non-Color":"sRGB");
  struct Image *image=BKE_image_add_from_imbuf(buffer,name);
  IMB_freeImBuf(buffer);
  return image?add_id((ID *)image):0;
}
FULL_API int bi_full_texture_slot(int material,int texture,int index) {
  PointerRNA *ma=get_pointer(material),*tex=get_pointer(texture);
  if(!ma||!tex||!RNA_struct_is_a(ma->type,&RNA_Material)||!RNA_struct_is_a(tex->type,&RNA_Texture)) return 0;
  MTex *slot=BKE_texture_mtex_add_id(ma->data,index);
  if(!slot) return 0;
  slot->tex=tex->data;id_us_plus((ID *)slot->tex);
  PointerRNA ptr;RNA_pointer_create(ma->id.data,&RNA_MaterialTextureSlot,slot,&ptr);return add_pointer(ptr);
}
FULL_API int bi_full_tree_create(const char *name) {
  bNodeTree *tree=ntreeAddTree(G.main,name,"ShaderNodeTree");return add_id((ID *)tree);
}
FULL_API int bi_full_texture_group(const char *name) {
  bNodeTree *tree=ntreeAddTree(G.main,name,"TextureNodeTree");return add_id((ID *)tree);
}
FULL_API int bi_full_tree_socket(int handle,int output,const char *type,const char *name) {
  PointerRNA *p=get_pointer(handle);if(!p||!RNA_struct_is_a(p->type,&RNA_NodeTree)) return 0;
  bNodeSocket *socket=ntreeAddSocketInterface(p->data,output?SOCK_OUT:SOCK_IN,type,name);
  if(!socket) return 0;
  ntreeUpdateTree(G.main,p->data);return 1;
}

/* Read original DNA through its own RNA before a modern file loader versions it.
 * No raw legacy pointers cross the ABI. Collection handles share the reset epoch. */
FULL_API int bi_full_main(void) {
  PointerRNA pointer;RNA_main_pointer_create(G.main,&pointer);return add_pointer(pointer);
}
FULL_API int bi_full_scene_current(const char *name) {
  Scene *scene=CTX_data_scene(context);
  if(name && name[0]) {
    for(scene=G.main->scene.first;scene;scene=(Scene *)scene->id.next)
      if(!strcmp(scene->id.name+2,name)) break;
  }
  if(!scene) { strcpy(last_error,"Legacy scene name was not found");return 0; }
  CTX_data_scene_set(context,scene);return add_id((ID *)scene);
}
static int read_property(int handle,const char *path,PointerRNA *ptr,PropertyRNA **prop) {
  PointerRNA *source=get_pointer(handle);
  if(!source || !RNA_path_resolve_property(source,path,ptr,prop)) {
    BLI_snprintf(last_error,sizeof(last_error),"Cannot read legacy property: %s",path);return 0;
  }
  return 1;
}
FULL_API int bi_full_property_info(int handle,const char *path,int *length) {
  PointerRNA ptr;PropertyRNA *prop;
  if(!read_property(handle,path,&ptr,&prop)) return 0;
  *length=RNA_property_array_length(&ptr,prop);
  switch(RNA_property_type(prop)) {
    case PROP_BOOLEAN:return 1;case PROP_INT:return 2;case PROP_FLOAT:return 3;
    case PROP_STRING:return 4;case PROP_ENUM:return 5;case PROP_POINTER:return 6;
    case PROP_COLLECTION:*length=RNA_property_collection_length(&ptr,prop);return 7;
    default:return 0;
  }
}
FULL_API int bi_full_get_numbers(int handle,const char *path,double *values,int capacity) {
  PointerRNA ptr;PropertyRNA *prop;if(!read_property(handle,path,&ptr,&prop)) return 0;
  int length=RNA_property_array_length(&ptr,prop),count=length?length:1;
  if(capacity<count) return 0;
  switch(RNA_property_type(prop)) {
    case PROP_FLOAT:
      for(int i=0;i<count;i++) values[i]=length?RNA_property_float_get_index(&ptr,prop,i):RNA_property_float_get(&ptr,prop);
      break;
    case PROP_INT:
      for(int i=0;i<count;i++) values[i]=length?RNA_property_int_get_index(&ptr,prop,i):RNA_property_int_get(&ptr,prop);
      break;
    case PROP_BOOLEAN:
      for(int i=0;i<count;i++) values[i]=length?RNA_property_boolean_get_index(&ptr,prop,i):RNA_property_boolean_get(&ptr,prop);
      break;
    default:return 0;
  }
  return 1;
}
FULL_API int bi_full_get_string(int handle,const char *path,char *buffer,int capacity) {
  PointerRNA ptr;PropertyRNA *prop;if(!read_property(handle,path,&ptr,&prop)||capacity<1) return 0;
  const char *value=NULL;char *allocated=NULL;
  if(RNA_property_type(prop)==PROP_STRING) value=allocated=RNA_property_string_get_alloc(&ptr,prop,NULL,0,NULL);
  else if(RNA_property_type(prop)==PROP_ENUM)
    RNA_property_enum_identifier(context,&ptr,prop,RNA_property_enum_get(&ptr,prop),&value);
  if(!value) return 0;
  int size=strlen(value)+1;
  if(size<=capacity) memcpy(buffer,value,size);
  if(allocated) MEM_freeN(allocated);
  return size;
}
FULL_API int bi_full_get_pointer(int handle,const char *path) {
  PointerRNA ptr;PropertyRNA *prop;
  if(!read_property(handle,path,&ptr,&prop)||RNA_property_type(prop)!=PROP_POINTER) return 0;
  return add_pointer(RNA_property_pointer_get(&ptr,prop));
}
FULL_API int bi_full_collection_item(int handle,const char *path,int index) {
  PointerRNA ptr,item;PropertyRNA *prop;
  if(!read_property(handle,path,&ptr,&prop)||RNA_property_type(prop)!=PROP_COLLECTION) return 0;
  if(!RNA_property_collection_lookup_int(&ptr,prop,index,&item)) return 0;
  return add_pointer(item);
}
FULL_API int bi_full_pass(const char *name,float *data,uint64_t capacity,int *width,int *height,int *channels) {
  if(!render) return 0;
  RenderResult *rr=RE_AcquireResultRead(render);
  RenderLayer *layer=rr?rr->layers.first:NULL;
  RenderPass *pass=layer?RE_pass_find_by_name(layer,name,""):NULL;
  int ok=pass&&pass->rect;
  if(ok) {
    *width=pass->rectx;*height=pass->recty;*channels=pass->channels;
    uint64_t length=(uint64_t)*width * *height * *channels;
    if(data) {
      if(capacity<length) ok=0;
      else memcpy(data,pass->rect,sizeof(float)*length);
    }
  }
  RE_ReleaseResult(render);
  if(!ok) BLI_snprintf(last_error,sizeof(last_error),"Missing or undersized render pass: %s",name);
  return ok;
}
FULL_API int bi_full_mesh_color(int handle,const char *name,int count,const float *rgba) {
  PointerRNA *p=get_pointer(handle);if(!p||!RNA_struct_is_a(p->type,&RNA_Object)) return 0;
  Object *ob=p->data;if(ob->type!=OB_MESH) return 0;Mesh *me=ob->data;
  if(count!=me->totloop) return 0;
  MLoopCol *layer=CustomData_add_layer_named(&me->ldata,CD_MLOOPCOL,CD_CALLOC,NULL,count,name);
  for(int i=0;i<count;i++) {
    layer[i].r=FTOCHAR(rgba[i*4]);
    layer[i].g=FTOCHAR(rgba[i*4+1]);
    layer[i].b=FTOCHAR(rgba[i*4+2]);
    layer[i].a=FTOCHAR(rgba[i*4+3]);
  }
  BKE_mesh_update_customdata_pointers(me,true);return 1;
}
FULL_API int bi_full_mesh_active_layers(int handle,const char *uv,const char *color) {
  PointerRNA *p=get_pointer(handle);if(!p||!RNA_struct_is_a(p->type,&RNA_Object)) return 0;
  Object *ob=p->data;if(ob->type!=OB_MESH) return 0;Mesh *me=ob->data;
  int index=uv?CustomData_get_named_layer(&me->ldata,CD_MLOOPUV,uv):-1;
  if(index>=0) {
    CustomData_set_layer_active(&me->ldata,CD_MLOOPUV,index);
    CustomData_set_layer_render(&me->ldata,CD_MLOOPUV,index);
    CustomData_set_layer_active(&me->pdata,CD_MTEXPOLY,index);
    CustomData_set_layer_render(&me->pdata,CD_MTEXPOLY,index);
  }
  index=color?CustomData_get_named_layer(&me->ldata,CD_MLOOPCOL,color):-1;
  if(index>=0) {
    CustomData_set_layer_active(&me->ldata,CD_MLOOPCOL,index);
    CustomData_set_layer_render(&me->ldata,CD_MLOOPCOL,index);
  }
  BKE_mesh_update_customdata_pointers(me,true);return 1;
}
