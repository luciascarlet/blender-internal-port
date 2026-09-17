/* SPDX-License-Identifier: GPL-2.0-or-later
 * New host adapter and BVH. Shading and triangle kernels are from Blender 2.79b.
 * This is deliberately not represented as the complete legacy render pipeline. */
#include "classic.h"
#include "legacy_compat.h"
#include "legacy_kernels.inc"
#include <array>
#include <vector>
#include <numeric>
#include <memory>
#include <limits>
#include <string>
#include <stdexcept>

namespace {
thread_local std::string error;
struct V {
  float x,y,z;
  explicit V(const float *p):x(p[0]),y(p[1]),z(p[2]){}
  V(float x=0,float y=0,float z=0):x(x),y(y),z(z){}
  float operator[](int i) const { return i==0?x:i==1?y:z; }
  V operator+(V b) const { return {x+b.x,y+b.y,z+b.z}; }
  V operator-(V b) const { return {x-b.x,y-b.y,z-b.z}; }
  V operator*(float f) const { return {x*f,y*f,z*f}; }
  V operator*(V b) const { return {x*b.x,y*b.y,z*b.z}; }
  float dot(V b) const { return x*b.x+y*b.y+z*b.z; }
  V normalized() const { float d=sqrtf(dot(*this)); return d>1e-18f ? *this*(1/d):V(); }
  void store(float *p) const { p[0]=x;p[1]=y;p[2]=z; }
};
struct Bounds {
  V lo{1e30f,1e30f,1e30f}, hi{-1e30f,-1e30f,-1e30f};
  void add(V p) { lo={std::min(lo.x,p.x),std::min(lo.y,p.y),std::min(lo.z,p.z)};
                 hi={std::max(hi.x,p.x),std::max(hi.y,p.y),std::max(hi.z,p.z)}; }
  bool hit(V o,V d,float near,float far) const {
    for(int i=0;i<3;i++) {
      if(fabsf(d[i])<1e-30f) { if(o[i]<lo[i]||o[i]>hi[i]) return false; continue; }
      float a=(lo[i]-o[i])/d[i],b=(hi[i]-o[i])/d[i];
      if(a>b) std::swap(a,b);
      near=std::max(near,a);far=std::min(far,b);
      if(near>far) return false;
    }
    return true;
  }
};
struct Node { Bounds box; int begin=0,end=0,left=-1,right=-1; };
struct Hit { int triangle=-1; float distance,u=0,v=0; };
struct Scene {
  std::vector<BI_Triangle> triangles;
  std::vector<BI_Material> materials;
  std::vector<BI_Light> lights;
  std::vector<int> order;
  std::vector<Node> nodes;
  int build(int begin,int end) {
    int index=int(nodes.size()); nodes.emplace_back();
    Bounds box, centers;
    for(int i=begin;i<end;i++) {
      const auto &t=triangles[order[i]];
      V a(t.p),b(t.p+3),c(t.p+6);box.add(a);box.add(b);box.add(c);centers.add((a+b+c)*(1.f/3));
    }
    nodes[index].box=box;nodes[index].begin=begin;nodes[index].end=end;
    if(end-begin>4) {
      V delta=centers.hi-centers.lo;
      int axis=delta.x>delta.y ? (delta.x>delta.z?0:2) : (delta.y>delta.z?1:2);
      int mid=(begin+end)/2;
      std::nth_element(order.begin()+begin,order.begin()+mid,order.begin()+end,[&](int a,int b){
        const auto &p=triangles[a].p;const auto &q=triangles[b].p;
        return p[axis]+p[axis+3]+p[axis+6]<q[axis]+q[axis+3]+q[axis+6];
      });
      int left=build(begin,mid), right=build(mid,end);
      nodes[index].left=left;nodes[index].right=right;
    }
    return index;
  }
  Hit intersect(V origin,V direction,float near,float far,int skip=-1,bool any=false) const {
    Hit hit;hit.distance=far;
    if(nodes.empty()) return hit;
    float o[3],d[3];origin.store(o);direction.store(d);
    IsectRayPrecalc pre;isect_ray_tri_watertight_v3_precalc(&pre,d);
    // Median splitting bounds depth to < 32 for the signed-int triangle count.
    std::array<int,64> stack{};int top=0;stack[top++]=0;
    while(top) {
      const Node &node=nodes[stack[--top]];
      if(!node.box.hit(origin,direction,near,hit.distance)) continue;
      if(node.left>=0) { stack[top++]=node.left;stack[top++]=node.right;continue; }
      for(int j=node.begin;j<node.end;j++) {
        int index=order[j];if(index==skip) continue;
        const auto &t=triangles[index];float distance,uv[2];
        if(isect_ray_tri_watertight_v3(o,&pre,t.p,t.p+3,t.p+6,&distance,uv) && distance>=near && distance<hit.distance) {
          hit={index,distance,uv[0],uv[1]};if(any) return hit;
        }
      }
    }
    return hit;
  }
};
V shade(const Scene &s,const Hit &hit,V o,V direction,const BI_Settings &settings) {
  const auto &t=s.triangles[hit.triangle];const auto &m=s.materials[t.material];
  V base(m.color);if(m.shadeless) return base;
  V p=o+direction*hit.distance;
  V n=(V(t.n)*hit.u+V(t.n+3)*hit.v+V(t.n+6)*(1-hit.u-hit.v)).normalized();
  V view=direction*(-1);if(n.dot(view)<0) n=n*(-1);
  float normal[3],v[3];n.store(normal);view.store(v);
  V color=base*(settings.ambient+m.emission);
  for(const auto &light:s.lights) {
    V l;float distance=1e30f,energy=light.energy;
    if(light.type==0) l=V(light.direction)*(-1);
    else {
      l=V(light.position)-p;distance=sqrtf(l.dot(l));if(distance<=1e-8f) continue;l=l*(1/distance);
      // Classic inverse-square falloff with a legacy distance control.
      energy*=light.distance/(light.distance+distance*distance);
      if(light.type==2) {
        float cone=(l*(-1)).dot(V(light.direction));
        if(cone<=light.spot_cos) continue;
        energy*=cone;
        float width=(1-light.spot_cos)*light.spot_blend;
        if(width>0) { float f=std::clamp((cone-light.spot_cos)/width,0.f,1.f);energy*=f*f*(3-2*f); }
      }
    }
    if(n.dot(l)<=0 || energy<=0) continue;
    if(settings.shadows && light.shadows) {
      float eps=std::max(1e-5f,1e-6f*std::max({fabsf(p.x),fabsf(p.y),fabsf(p.z)}));
      if(s.intersect(p+n*eps,l,eps,distance-eps,hit.triangle,true).triangle>=0) continue;
    }
    float lv[3];l.store(lv);
    float diffuse=bi_diffuse(&m,normal,lv,v)*m.diffuse_intensity;
    float specular=bi_specular(&m,normal,lv,v)*m.specular_intensity;
    color=color+(base*diffuse+V(m.specular_color)*specular)*V(light.color)*energy;
  }
  return color;
}
}
extern "C" {
int bi_abi_version(void) { return 1; }
int bi_struct_size(int kind) {
  const int sizes[]={sizeof(BI_Triangle),sizeof(BI_Material),sizeof(BI_Light),sizeof(BI_Camera),sizeof(BI_Settings)};
  return kind>=0&&kind<5?sizes[kind]:0;
}
const char *bi_last_error(void) { return error.c_str(); }
float bi_diffuse(const BI_Material *m,const float n[3],const float l[3],const float v[3]) {
  float nl=dot_v3v3(n,l),result;
  switch(m->diffuse_shader) {
    case 1:result=OrenNayar_Diff(nl,n,l,v,m->roughness);break;
    case 2:result=Toon_Diff(n,l,v,m->diffuse_size,m->diffuse_smooth);break;
    case 3:result=Minnaert_Diff(nl,n,v,m->darkness);break;
    case 4: { float nn[3],ll[3],vv[3];memcpy(nn,n,12);memcpy(ll,l,12);memcpy(vv,v,12);
      result=Fresnel_Diff(nn,ll,vv,m->diffuse_size,m->diffuse_smooth);break; }
    default:result=nl;
  }
  return std::isfinite(result)?std::max(0.f,result):0.f;
}
float bi_specular(const BI_Material *m,const float n[3],const float l[3],const float v[3]) {
  float result;
  switch(m->specular_shader) {
    case 1:result=Phong_Spec(n,l,v,m->hardness,0);break;
    case 2:result=Blinn_Spec(n,l,v,m->ior,float(m->hardness),0);break;
    case 3:result=Toon_Spec(n,l,v,m->specular_size,m->specular_smooth,0);break;
    case 4:result=WardIso_Spec(n,l,v,m->slope,0);break;
    default:result=CookTorr_Spec(n,l,v,m->hardness,0);
  }
  return std::isfinite(result)?std::max(0.f,result):0.f;
}
void *bi_scene_create(const BI_Triangle *tri,int count,const BI_Material *mat,int materials,const BI_Light *lights,int num_lights) {
  error.clear();
  try {
    if(count<0||materials<1||num_lights<0||(!tri&&count)||!mat||(!lights&&num_lights)) throw std::runtime_error("Invalid scene buffers");
    for(int i=0;i<count;i++) {
      if(tri[i].material<0||tri[i].material>=materials) throw std::runtime_error("Invalid triangle material index");
      for(float f:tri[i].p) if(!std::isfinite(f)) throw std::runtime_error("Non-finite geometry");
      for(float f:tri[i].n) if(!std::isfinite(f)) throw std::runtime_error("Non-finite normal");
    }
    auto scene=std::make_unique<Scene>();
    if(count) scene->triangles.assign(tri,tri+count);
    scene->materials.assign(mat,mat+materials);
    if(num_lights) scene->lights.assign(lights,lights+num_lights);
    scene->order.resize(count);std::iota(scene->order.begin(),scene->order.end(),0);
    if(count) scene->build(0,count);
    return scene.release();
  } catch(const std::exception &e) { error=e.what();return nullptr; }
}
void bi_scene_destroy(void *scene) { delete static_cast<Scene *>(scene); }
int bi_render_rows(void *ptr,const BI_Camera *camera,const BI_Settings *settings,int first,int rows,float *rgba) {
  error.clear();
  if(!ptr||!camera||!settings||!rgba||settings->width<1||settings->height<1||first<0||rows<1||first>settings->height-rows||settings->sample_grid<1||settings->sample_grid>4||camera->clip_start<=0||camera->clip_end<=camera->clip_start) {
    error="Invalid camera or render dimensions";return 0;
  }
  const Scene &s=*static_cast<Scene *>(ptr);const auto &c=*camera;const auto &r=*settings;
  V origin(c.origin),ll(c.lower_left),dx(c.horizontal),dy(c.vertical),forward(c.forward);
  int grid=r.sample_grid;
  for(int y=first;y<first+rows;y++) for(int x=0;x<r.width;x++) {
    V color;float alpha=0;
    for(int sy=0;sy<grid;sy++) for(int sx=0;sx<grid;sx++) {
      float u=(x+(sx+0.5f)/grid)/r.width, v=(y+(sy+0.5f)/grid)/r.height;
      V frame=ll+dx*u+dy*v;
      V o=c.orthographic?origin+frame:origin;
      V d=c.orthographic?forward:frame.normalized();
      float cosine=d.dot(forward);if(cosine<=1e-8f) continue;
      Hit hit=s.intersect(o,d,c.clip_start/cosine,c.clip_end/cosine);
      if(hit.triangle>=0) { color=color+shade(s,hit,o,d,r);alpha+=1; }
      else if(!r.transparent) { color=color+V(r.background);alpha+=1; }
    }
    size_t offset=(size_t(y-first)*r.width+x)*4;
    (color*(1.f/(grid*grid))).store(rgba+offset);rgba[offset+3]=alpha/(grid*grid);
  }
  return 1;
}
}
