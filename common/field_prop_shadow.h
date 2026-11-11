#pragma once
#include <windows.h>
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <list>
#include <string>
#include "scene_lua.h"

// Native, shadow-only GameplayProps. The match's own flat/self-shadow renderers
// select stadium lights and draw the actual mesh. No overlay, painted ellipse,
// cloned ball owner, global lighting change, or per-match file is involved.
namespace fieldshadow {
struct Native;
inline bool connectFlatGroup(const Native& api,uintptr_t child);
using Matrix=std::array<float,16>;
inline unsigned nativeInstance(const char* key,unsigned slot){
 // FIFA identifies projected geometry by instance number within a parent
 // entry. A shared group needs disjoint numbers across its four children.
 if(!key)return 64;
 if(!std::strcmp(key,"var_cabin"))return slot<1?slot:64;
 if(!std::strcmp(key,"stands"))return slot<13?slot+1:64;
 if(!std::strcmp(key,"balls"))return slot<13?slot+14:64;
 if(!std::strcmp(key,"entrance"))return slot<1?slot+27:64;
 return 64;
}
inline Matrix transform(float x,float y,float z,float yaw=0,float scale=1){
 const float c=std::cos(yaw)*scale,s=std::sin(yaw)*scale;
 return {c,0,s,0, 0,scale,0,0, -s,0,c,0, x,y,z,1};
}
inline bool valid(const Matrix& m){
 for(float f:m)if(!std::isfinite(f)||std::abs(f)>50000)return false;
 return m[15]==1&&std::abs(m[12])<15000&&std::abs(m[13])<5000&&std::abs(m[14])<15000;
}
inline std::string literal(const std::string& text){
 std::string out="'";for(char c:text){if(c=='\\'||c=='\'')out+='\\';out+=c;}return out+"'";
}
inline std::string bindScript(const std::string& key,const std::string& type,const std::string& model,const std::string& submesh){
 const auto k=literal(key),t=literal(type),path=literal(model),mesh=literal(submesh);
 const std::string row="S16FieldShadowObjects["+k+"]";
 const std::string expression="${S16FieldShadowObjects."+key+".";
 std::string s="S16FieldShadowBound=false;do local ok,err=pcall(function() local gr=gRenderables;assert(gr and gRenderObj and gRenderObj.flatShadow and gRenderObj.selfshadow);";
 s+="S16FieldShadowObjects=S16FieldShadowObjects or {};local o=gr:Find("+t+",0);assert(o);local s="+row+";if not s or s.object~=o then s={object=o};"+row+"=s end;s.model="+path+";s.submesh="+mesh+";";
 // BallUpdate has already run when the real ball publishes its visible frame.
 // Keep the current competition's football and its original fallback order.
 if(key=="balls")s+="if db and db.ball and db.ball[1] and db.ball[1].model and GetRMBall then s.model=GetRMBall(1,0)..'data/sceneassets/ball/ball_'..db.ball[1].model..'.rx3;data/sceneassets/ball/ball_23.rx3' end;";
 s+="if not s.assets then local part='prop_plastic';gr:AddAsset(o,0,'shader','data/fifarna/shader.big');gr:AddAsset(o,0,part,"+literal(expression+"model}")+" );";
 s+="gr:AddAsset(o,0,'aux','data/sceneassets/prop/prop_102_textures.rx3');local st=gSportsRNA:GetTable('wvState');local env=gSportsRNA:GetInt(st,'wvAttribEnvLighting');gr:AddAsset(o,0,'charcmn','data/sceneassets/charactercmn/charactercmn_'..env..'.rx3');";
 // These assets contain one mesh. Their RX3 object name is not a named
 // submesh (SetSubMesh's argument). Filtering by that object name resolves
 // to -1: the resource reports ready but submits no geometry. Select the
 // default mesh, as FIFA's corner-flag binding does for a single-mesh asset.
 s+="gr:CreateMaterialFromAttribulator(o,0,part,'field_shadow_material','prop_plastic');";
 s+="gr:SetTexture(o,0,part,'textures','diffuseTexture','aux','prop_cm');gr:SetTexture(o,0,part,'textures','normalMap','aux','prop_nm');gr:SetTexture(o,0,part,'textures','coeffMap','aux','prop_coeff');gr:SetTexture(o,0,part,'textures','envDiffuseTexture','charcmn','envd_');gr:SetTexture(o,0,part,'textures','envSpecTexture','charcmn','envs_');s.assets=true end;";
 // Linking is done only after the native fixed-size registry has been checked.
 // Lua pcall cannot contain an out-of-bounds write in FIFA's AddSubObject.
 s+="gr:Reload(o,1);end);S16FieldShadowBound=ok;S16FieldShadowError=ok and nil or tostring(err) end";
 return s;
}

struct Native {
 uintptr_t image=0;SceneLuaSnapshot scope{};
 void(*logger)(const char*)=nullptr;
 template<class T>T read(uintptr_t at)const{T result{};scene_lua_read(at,result);return result;}
 bool bytes(uintptr_t at,void* output,size_t size)const{SIZE_T n=0;return at&&ReadProcessMemory(GetCurrentProcess(),(void*)at,output,size,&n)&&n==size;}
 bool run(const std::string& script)const{return runChecked(script.c_str(),script.size());}
 bool runChecked(const char* script,size_t size)const{
  __try{((void(__fastcall*)(const char*,size_t,const char*))(image+0x4ac35e0))(script,size,"field_prop_shadows");return true;}
  __except(EXCEPTION_EXECUTE_HANDLER){return false;}
 }
 bool validObject(uintptr_t o)const{
  const auto ctx=read<uintptr_t>(o+0x30),impl=read<uintptr_t>(o+0x20);
  return o&&read<uintptr_t>(o)==image+0x2210dc0&&ctx&&read<uintptr_t>(ctx+8)==o&&impl&&read<unsigned>(impl+0x38)==64;
 }
 bool alive(uintptr_t o,const std::string& type)const{
  if(!validObject(o))return false;
  const auto script="S16FieldShadowAlive=false;pcall(function() local s=S16FieldShadowObjects and S16FieldShadowObjects["+literal(key)+"];S16FieldShadowAlive=s and s.object==gRenderables:Find("+literal(type)+",0) or false end)";
  return run(script)&&scene_lua_flag(scope.globals,"S16FieldShadowAlive");
 }
 const char* key="";
 std::array<float,8> localBounds{};
 bool applyBounds(uintptr_t o)const{
  if(localBounds[0]==localBounds[4]&&localBounds[1]==localBounds[5]&&localBounds[2]==localBounds[6])return true;
  for(float value:localBounds)if(!std::isfinite(value)||std::abs(value)>50000)return false;
  for(unsigned i=0;i<3;++i)if(localBounds[i]>=localBounds[i+4])return false;
  if(!validObject(o))return false;const auto context=read<uintptr_t>(o+0x28);
  if(!context||read<uintptr_t>(context+0x28)!=o)return false;
  SIZE_T written=0;return WriteProcessMemory(GetCurrentProcess(),(void*)context,localBounds.data(),sizeof(localBounds),&written)&&written==sizeof(localBounds);
 }
 // Native AddSubObject writes a fixed array without checking its count. In
 // the crash, flatshadow already held 74 entries; the 75th overwrote its own
 // count at +0x548. Never infer spare slots from Lua's db alone.
 struct Registry {uintptr_t parent=0,implementation=0,adder=0;unsigned first=0,countAt=0,count=0,capacity=0;bool linked=false,valid=false;};
 uintptr_t field(uintptr_t table,const char* name,int expectedTag)const{
  unsigned char tag=0,power=0;uintptr_t nodes=0;
  if(!scene_lua_read(table+8,tag)||tag!=5||!scene_lua_read(table+11,power)||power>16||!scene_lua_read(table+32,nodes)||!nodes)return 0;
  struct Value{uint64_t bits;int tag,padding;};struct Node{Value value,key;uintptr_t next;};
  const size_t length=std::strlen(name);if(length>=64)return 0;
  for(unsigned start=0;start<(1u<<power);start+=32){
   Node block[32]{};const unsigned count=(std::min)(32u,(1u<<power)-start);
   if(!bytes(nodes+size_t(start)*sizeof(Node),block,count*sizeof(Node)))return 0;
   for(unsigned i=0;i<count;++i){const auto& n=block[i];size_t textLength=0;char text[64]{};
    if(n.key.tag!=4||!scene_lua_read(uintptr_t(n.key.bits)+16,textLength)||textLength!=length)continue;
    if(bytes(uintptr_t(n.key.bits)+24,text,length)&&!std::memcmp(text,name,length))return n.value.tag==expectedTag?uintptr_t(n.value.bits):0;
   }
  }return 0;
 }
 Registry registry(uintptr_t parent,uintptr_t child,unsigned pass)const{
  Registry result;result.parent=parent;
  const uintptr_t expectedVtable=pass==2?0x22063b0:pass==4?0x2217870:0;
  const uintptr_t expectedAdder=pass==2?0x436f080:pass==4?0x44022e0:0;
  if(!parent||!child||!expectedVtable||read<uintptr_t>(parent)!=image+expectedVtable)return result;
  result.adder=read<uintptr_t>(image+expectedVtable+0x90);
  result.implementation=read<uintptr_t>(parent+0x10);
  if(!result.implementation||result.adder!=image+expectedAdder)return result;
  unsigned char code[63]{};
  const unsigned char signature[58]={0x48,0x83,0xec,0x18,0x4c,0x8b,0x49,0x10,0x44,0x89,0x44,0x24,0x08,0x48,0x8b,0x44,0x24,0x08,0x49,0x63,0x89,0,0,0,0,0x48,0x01,0xc9,0x49,0x89,0x94,0xc9,0,0,0,0,0x49,0x89,0x84,0xc9,0,0,0,0,0x41,0xff,0x81,0,0,0,0,0xb0,0x01,0x48,0x83,0xc4,0x18,0xc3};
  if(!bytes(result.adder,code,sizeof(code)))return result;
  unsigned next=0,increment=0;
  if(pass==2){
   for(unsigned i=0;i<sizeof(signature);++i){if((i>=21&&i<25)||(i>=32&&i<36)||(i>=40&&i<44)||(i>=47&&i<51))continue;if(code[i]!=signature[i])return result;}
   std::memcpy(&result.countAt,code+21,4);std::memcpy(&result.first,code+32,4);std::memcpy(&next,code+40,4);std::memcpy(&increment,code+47,4);
  }else{
   // SelfshadowPO uses (index+7)*16, not FlatShadow's +0xa8 array.
   // Its real capacity is 70. Some protected executables include an eight
   // byte counter between the count load and append; retain it unchanged.
   if(std::memcmp(code,signature,21))return result;
   std::memcpy(&result.countAt,code+21,4);unsigned tail=25;
   if(code[tail]==0x9c){if(code[26]!=0xfe||code[27]!=0x05||code[32]!=0x9d)return result;tail=33;}
   const unsigned char selfTail[]={0x48,0x83,0xc1,0x07,0x48,0x01,0xc9,0x49,0x89,0x14,0xc9,0x49,0x89,0x44,0xc9,0x08,0x41,0xff,0x81,0,0,0,0,0xb0,0x01,0x48,0x83,0xc4,0x18,0xc3};
   for(unsigned i=0;i<sizeof(selfTail);++i)if((i<19||i>=23)&&code[tail+i]!=selfTail[i])return result;
   std::memcpy(&increment,code+tail+19,4);result.first=0x70;next=result.first+8;
   if(result.countAt!=0x4d0)return result;
  }
  if(result.first<0x20||result.countAt>0x4000||next!=result.first+8||increment!=result.countAt||result.countAt<=result.first||(result.countAt-result.first)%16)return result;
  result.capacity=(result.countAt-result.first)/16;
  if(result.capacity>256||!scene_lua_read(result.implementation+result.countAt,result.count)||result.count>result.capacity)return result;
  for(unsigned i=0;i<result.count;++i){uintptr_t object=0;unsigned mode=0;
   if(!scene_lua_read(result.implementation+result.first+i*16,object)||!scene_lua_read(result.implementation+result.first+i*16+8,mode))return result;
   if(object==child&&mode==pass)result.linked=true;
  }
  result.valid=true;return result;
 }
 bool connect(uintptr_t parent,uintptr_t child,unsigned pass)const{
  const auto slots=registry(parent,child,pass);
  if(!slots.valid){note("native_shadow_registry_unverified skipped_no_native_write");return false;}
  if(slots.linked)return true;
  if(slots.count>=slots.capacity){char message[144];_snprintf_s(message,sizeof(message),_TRUNCATE,"native_shadow_registry_full pass=%u count=%u capacity=%u extra_shadow_skipped_prop_preserved",pass,slots.count,slots.capacity);note(message);return false;}
  return append(slots,child,pass);
 }
 bool append(const Registry& slots,uintptr_t child,unsigned pass)const{
  // Recheck immediately before calling the verified native writer; no global
  // engine patch, table expansion or replacement of another prop is involved.
  if(!slots.valid||slots.count>=slots.capacity||read<unsigned>(slots.implementation+slots.countAt)!=slots.count)return false;
  __try{return ((bool(__fastcall*)(void*,void*,unsigned))slots.adder)((void*)slots.parent,(void*)child,pass)&&
   read<unsigned>(slots.implementation+slots.countAt)==slots.count+1&&read<uintptr_t>(slots.implementation+slots.first+slots.count*16)==child;}
  __except(EXCEPTION_EXECUTE_HANDLER){return false;}
 }
 bool available()const{
  const unsigned char expected[]={0x4c,0x8b,0x51,0x20,0x41,0x8b,0x00,0x4c,0x63,0xda};unsigned char actual[sizeof(expected)]{};SIZE_T n=0;
  return image&&ReadProcessMemory(GetCurrentProcess(),(void*)(image+0x4ad80b0),actual,sizeof(actual),&n)&&n==sizeof(actual)&&!std::memcmp(actual,expected,sizeof(actual));
 }
 uintptr_t create(const char* type)const{
  if(!available())return 0;
  __try{
   auto allocator=((void*(__fastcall*)())(image+0x4abfba0))();const auto allocate=read<uintptr_t>(read<uintptr_t>((uintptr_t)allocator)+0x10);if(!allocate)return 0;
   auto storage=((void*(__fastcall*)(void*,size_t,const char*,int))allocate)(allocator,0x38,"FieldPropShadow",1);if(!storage)return 0;
   auto o=(uintptr_t)((void*(__fastcall*)(void*,void*,const char*,int,int,int))(image+0x43c8be0))(storage,allocator,type,0,1,64);if(!validObject(o))return 0;
   alignas(16)const auto hidden=transform(0,-3000,0);
   for(int i=0;i<64;++i)((void(__fastcall*)(void*,int,const float*,bool))(image+0x4ad80b0))((void*)o,i,hidden.data(),false);
   ((void(__fastcall*)(void*,const char*,int))(image+0x4ac5450))((void*)o,type,0);return o;
  }__except(EXCEPTION_EXECUTE_HANDLER){return 0;}
 }
 bool bind(uintptr_t o,const std::string& type,const std::string& model,const std::string& mesh)const{
  if(!validObject(o)||!run(bindScript(key,type,model,mesh))||!scene_lua_flag(scope.globals,"S16FieldShadowBound"))return false;
  const auto renderObjects=field(scope.globals,"gRenderObj",5);
  const bool flat=connectFlatGroup(*this,o);
  const bool self=connect(field(renderObjects,"selfshadow",2),o,4);
  return (flat||self)&&prepare(o);
 }
 bool prepare(uintptr_t o)const{
  // GameplayProp::Prepare is gated by parameter dirtiness (+0x51). A newly
  // registered shadow-only object has no ordinary gameplay parameter update,
  // so that wrapper silently does nothing. Request its own, verified LOD
  // composite exactly as the wrapper does, on the native scene callback.
  if(!validObject(o))return false;
  const auto impl=read<uintptr_t>(o+0x20);
  if(read<unsigned>(impl+0x18)!=1)return false;
  const auto list=read<uintptr_t>(impl+0x20),composite=read<uintptr_t>(list);
  if(!composite)return false;
  __try{((void(__fastcall*)(void*))(image+0x4adca80))((void*)composite);return applyBounds(o);}
  __except(EXCEPTION_EXECUTE_HANDLER){return false;}
 }
 bool ready(uintptr_t o)const{
  if(!validObject(o))return false;
  __try{
   const auto impl=read<uintptr_t>(o+0x20);if(read<unsigned>(impl+0x18)!=1)return false;
   const auto composite=read<uintptr_t>(read<uintptr_t>(impl+0x20));if(!composite)return false;
   if(!read<unsigned char>(composite+0x10))((int(__fastcall*)(void*))(image+0x4add100))((void*)composite);
   // A completed resource can still contain a rejected submesh. Never report
   // that empty caster as usable merely because its GPU request completed.
   const auto resource=read<uintptr_t>(composite),first=read<uintptr_t>(resource),end=read<uintptr_t>(resource+8);
   if(!first||end<first||end-first!=40||!read<uintptr_t>(first)||read<short>(first+16)<0||!read<unsigned char>(first+18))return false;
   return ((bool(__fastcall*)(void*))(image+0x4ad7d80))((void*)o);
  }__except(EXCEPTION_EXECUTE_HANDLER){return false;}
 }
 bool set(uintptr_t o,unsigned slot,const Matrix& m,bool requestedVisible)const{
  const unsigned instance=nativeInstance(key,slot);
  if(!validObject(o)||instance>=64||!valid(m))return false;
  alignas(16)auto matrix=m;
  __try{((void(__fastcall*)(void*,int,const float*,bool))(image+0x4ad80b0))((void*)o,int(instance),matrix.data(),requestedVisible);return true;}
  __except(EXCEPTION_EXECUTE_HANDLER){return false;}
 }
 void note(const char* s)const{if(logger){char text[256];_snprintf_s(text,sizeof(text),_TRUNCATE,"field_shadow[%s] %s",key,s);logger(text);}}
};

}
#include "field_prop_shadow_group.h"
namespace fieldshadow {

// One reusable native resource per module/VM, with lazy loading and exact
// visibility. Changing competition reloads this resource, not another copy.
template<class Api>struct Cache {
 Api api{};const char* key;uintptr_t object=0,owner=0,vm=0,globals=0;
 std::string model,mesh,type;std::list<std::string> typeStorage;
 std::array<Matrix,64> matrices{};std::array<bool,64> shown{},known{};
 unsigned serial=0,bindings=0,updates=0,errors=0;bool failed=false,wasReady=false;
 explicit Cache(const char* name):key(name){}
 void hide(){if(!object)return;for(unsigned i=0;i<64;++i)if(known[i]&&shown[i]){api.set(object,i,matrices[i],false);shown[i]=false;}}
 bool update(uintptr_t scene,SceneLuaSnapshot context,const char* path,const char* submesh,const Matrix* poses,unsigned count,bool requestedVisible){
  // An absent Lua scene may already have freed every old renderable. Forget
  // ownership instead of writing through addresses from the previous stadium.
  if(!scene||!context.vm||!context.globals){object=owner=vm=globals=0;known.fill(false);shown.fill(false);failed=wasReady=false;model.clear();mesh.clear();return false;}
  const bool contextChanged=vm!=context.vm||globals!=context.globals;
  const bool ownerChanged=owner!=scene;
  if(contextChanged){object=0;known.fill(false);shown.fill(false);model.clear();mesh.clear();failed=wasReady=false;vm=context.vm;globals=context.globals;}
  else if(ownerChanged&&object&&!api.alive(object,type)){object=0;known.fill(false);shown.fill(false);model.clear();mesh.clear();failed=wasReady=false;}
  owner=scene;if(ownerChanged)failed=false;
  if(!path||!submesh||!poses||count>64){hide();return false;}
  for(unsigned i=0;i<count;++i)if(!valid(poses[i])){hide();return false;}
  if(!requestedVisible){hide();return false;}if(failed)return false;
  if(!object){
   typeStorage.push_back(std::string("server16_field_shadow_")+key+"_"+std::to_string(++serial));type=typeStorage.back();object=api.create(typeStorage.back().c_str());
   if(!object){failed=true;++errors;api.note("native_shadow_object_failed");return false;}
  }
  if(model!=path||mesh!=submesh||ownerChanged){
   hide();known.fill(false);wasReady=false;
   if(!api.bind(object,type,path,submesh)){failed=true;++errors;api.note("native_shadow_binding_failed");return false;}
   model=path;mesh=submesh;++bindings;api.note("native_shadow_mesh_registered checked_stadium_passes");
  }
  if(!api.ready(object)){
   if(wasReady&&!api.alive(object,type)){object=0;known.fill(false);shown.fill(false);model.clear();wasReady=false;}
   else {hide();if(wasReady){model.clear();wasReady=false;}}return false;
  }wasReady=true;
  for(unsigned i=0;i<64;++i){const bool show=i<count;const Matrix& matrix=show?poses[i]:matrices[i];
   if((!known[i]&&show)||(known[i]&&(shown[i]!=show||(show&&matrix!=matrices[i])))){
    if(!api.set(object,i,matrix,show)){hide();failed=true;++errors;api.note("native_shadow_transform_failed");return false;}
    matrices[i]=matrix;shown[i]=show;known[i]=true;++updates;
   }
  }return true;
 }
};
using NativeLogged=Native;
using Caster=Cache<NativeLogged>;
inline bool update(Caster& caster,uintptr_t image,uintptr_t owner,SceneLuaSnapshot context,const char* model,const char* mesh,const Matrix* poses,unsigned count,bool requestedVisible,void(*logger)(const char*),const float* bounds=nullptr){
 caster.api.image=image;caster.api.scope=context;caster.api.key=caster.key;caster.api.logger=logger;
 caster.api.localBounds.fill(0);if(bounds)std::copy(bounds,bounds+8,caster.api.localBounds.begin());
 return caster.update(owner,context,model,mesh,poses,count,requestedVisible);
}
}
