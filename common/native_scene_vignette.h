#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

// FIFA 16 0x577de45c: the existing Vignette renderable retains three float4x3
// parameter copies even when Settings.PostFX_Vignette is zero. Lease only their
// opacity, on the scene callback; no shader, camera, light or save is changed.
namespace native_scene_vignette {
struct Value {uintptr_t bits=0;int type=0;};
template<class Read>inline uintptr_t pointer(uintptr_t at,Read read){uintptr_t p=0;read(at,&p,sizeof p);return p;}
template<class Read>Value field(uintptr_t table,const char* key,Read read){
 unsigned char h[64]{};if(!read(table,h,sizeof h)||h[8]!=5||h[11]>14)return {};
 const auto nodes=pointer(table+32,read);const auto length=std::strlen(key);
 if(!nodes||length>=32)return {};
 struct Node{uintptr_t bits;int type,padding;uintptr_t key;int keyType,keyPadding;uintptr_t next;};
 static_assert(sizeof(Node)==40);
 for(unsigned start=0;start<(1u<<h[11]);start+=32){
  Node rows[32]{};const unsigned count=std::min(32u,(1u<<h[11])-start);
  if(!read(nodes+start*sizeof(Node),rows,count*sizeof(Node)))return {};
  for(unsigned i=0;i<count;++i){const auto& row=rows[i];if(row.keyType!=4)continue;
   if(pointer(row.key+16,read)!=length)continue;
   char name[32]{};if(read(row.key+24,name,length)&&!std::memcmp(name,key,length))return {row.bits,row.type};
  }
 }
 return {};
}
template<class Read>uintptr_t resolve(uintptr_t image,Read read){
 const auto vm=pointer(image+0x3613fd0,read);int tag=0;
 if(!vm||!read(vm+0x80,&tag,sizeof tag)||tag!=5)return 0;
 const auto root=field(pointer(vm+0x78,read),"gRenderObj",read);if(root.type!=5)return 0;
 const auto value=field(root.bits,"postfx_vignette",read);return value.type==2?value.bits:0;
}
struct Lease {
 std::array<bool,2> owners{};uintptr_t object=0,parameters=0;std::array<float,3> original{};
 uint64_t nextResolve=0;unsigned writes=0,restores=0;bool captured=false;
 template<class Read>bool owned(uintptr_t image,Read read)const{
  return object&&parameters&&pointer(object,read)==image+0x221c420&&pointer(object+32,read)==parameters;
 }
 template<class Read,class Write>void release(uintptr_t image,Read read,Write write){
  if(captured&&owned(image,read))for(unsigned i=0;i<3;++i){float current=-1;
   const auto at=parameters+i*48+44;
   if(read(at,&current,4)&&current==0.f&&write(at,&original[i],4))++restores;
  }
  object=parameters=0;captured=false;nextResolve=0;
 }
 template<class Read,class Write>void state(uintptr_t image,unsigned owner,bool enabled,uint64_t now,Read read,Write write){
  if(owner<1||owner>owners.size())return;owners[owner-1]=enabled;
  if(!owners[0]&&!owners[1]){release(image,read,write);return;}
  if(now>=nextResolve){
   const auto selected=resolve(image,read);nextResolve=now+500;
   if(selected!=object){release(image,read,write);object=selected;nextResolve=now+500;}
  }
  if(!object||pointer(object,read)!=image+0x221c420)return;
  const auto block=pointer(object+32,read);
  if(captured&&parameters!=block){captured=false;parameters=0;}
  std::array<float,36> values{};if(!block||!read(block,values.data(),sizeof values))return;
  for(unsigned i=0;i<3;++i){const auto* p=values.data()+i*12;
   for(unsigned j=0;j<12;++j)if(!std::isfinite(p[j]))return;
   if(p[0]<0||p[0]>32||p[1]<0||p[2]<p[1]||p[2]>32||p[11]<0||p[11]>1)return;
  }
  if(!captured){parameters=block;for(unsigned i=0;i<3;++i)original[i]=values[i*12+11];captured=true;}
  const float zero=0;
  for(unsigned i=0;i<3;++i){const float alpha=values[i*12+11];if(alpha==0)continue;
   // Follow a newly blended engine profile, so exit restores its latest value.
   original[i]=alpha;if(write(parameters+i*48+44,&zero,4))++writes;
  }
 }
};
}
