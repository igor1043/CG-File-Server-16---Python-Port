#pragma once
#include <memory>
#include <atomic>
#include <mutex>

// All field modules share one FlatShadow entry. FIFA's native parent queries
// instance bounds with pass 5 and draws with pass 2; forwarding both passes in
// the same order keeps its own atlas and projection machinery intact.
namespace fieldshadow {
struct FlatGroup {
 struct Frame {Native api;uintptr_t object=0;std::array<uintptr_t,4> children{};};
 inline static std::shared_ptr<const Frame> current;
 inline static std::list<std::string> names;
 inline static std::array<uintptr_t,65> table{};
 inline static uintptr_t tableImage=0;
 inline static unsigned serial=0;
 inline static std::mutex updateMutex;
 static int member(const char* key){
  const char* keys[]={"var_cabin","stands","balls","entrance"};
  for(int i=0;i<4;++i)if(key&&!std::strcmp(key,keys[i]))return i;return -1;
 }
 static void __fastcall render(void* self,unsigned pass,void* context){
  const auto frame=std::atomic_load(&current);
  if(!frame||frame->object!=(uintptr_t)self||!context||(pass!=2&&pass!=5))return;
  const auto scope=scene_lua_snapshot(frame->api.image);
  if(scope.vm!=frame->api.scope.vm||scope.globals!=frame->api.scope.globals)return;
  draw(*frame,pass,context);
 }
 static void draw(const Frame& frame,unsigned pass,void* context){
  // No material loading, Lua execution or light changes on the draw thread.
  // The native child method checks readiness and per-instance visibility.
  __try{for(auto child:frame.children)if(frame.api.validObject(child))
   ((void(__fastcall*)(void*,unsigned,void*))(frame.api.image+0x43c8f30))((void*)child,pass,context);
  }__except(EXCEPTION_EXECUTE_HANDLER){}
 }
 static bool owned(const Native& api,uintptr_t object){
  const auto ctx=api.read<uintptr_t>(object+0x30),impl=api.read<uintptr_t>(object+0x20);
  return object&&api.read<uintptr_t>(object)==(uintptr_t)(table.data()+1)&&ctx&&
   api.read<uintptr_t>(ctx+8)==object&&impl&&api.read<unsigned>(impl+0x38)==64;
 }
 static bool __fastcall submit(const Native* request,uintptr_t child){
  if(!request||!request->validObject(child))return false;
  const auto& api=*request;const int index=member(api.key);if(index<0)return false;
  std::lock_guard<std::mutex> lock(updateMutex);
  const auto scope=scene_lua_snapshot(api.image);
  if(scope.vm!=api.scope.vm||scope.globals!=api.scope.globals)return false;
  const auto objects=api.field(api.scope.globals,"gRenderObj",5);
  const auto parent=api.field(objects,"flatShadow",2);
  if(!parent)return false;
  const auto previous=std::atomic_load(&current);
  auto frame=std::make_shared<Frame>();frame->api=api;frame->api.logger=nullptr;frame->api.key="";
  const bool sameScope=previous&&previous->api.scope.vm==api.scope.vm&&previous->api.scope.globals==api.scope.globals;
  const bool previousOwned=previous&&previous->api.image==api.image&&owned(api,previous->object);
  const auto oldLink=previousOwned&&!sameScope?api.registry(parent,previous->object,2):Native::Registry{};
  if(previousOwned&&(sameScope||(oldLink.valid&&oldLink.linked))){
   frame->object=previous->object;if(sameScope)frame->children=previous->children;
  }else{
   if(tableImage&&tableImage!=api.image)return false;
   if(!tableImage){
    if(!api.bytes(api.image+0x2210dc0-8,table.data(),sizeof(table)))return false;
    table[4]=(uintptr_t)&render;tableImage=api.image;
   }
   names.push_back("server16_field_shadow_group_"+std::to_string(++serial));
   frame->object=api.create(names.back().c_str());if(!frame->object)return false;
   InterlockedExchangePointer((void*volatile*)frame->object,table.data()+1);
  }
  frame->children[index]=child;
  // Publish complete immutable membership before exposing the group to FIFA.
  std::atomic_store(&current,std::shared_ptr<const Frame>(frame));
  if(!api.connect(parent,frame->object,2))return false;
  api.note("native_flat_shadow_group_linked one_mod_slot_original_props_preserved");return true;
 }
};

// The first field DLL owns the group for this process. Other DLLs call its POD
// interface; no STL allocation crosses a DLL boundary. Pin the owner so a
// plugin unload cannot leave a native vtable pointing at released code.
struct FlatGroupBroker {
 using Submit=bool(__fastcall*)(const Native*,uintptr_t);
 struct Shared {unsigned size,version;uintptr_t image;unsigned apiSize,reserved;void* volatile submit;};
 HANDLE mapping=nullptr;Shared* shared=nullptr;
 ~FlatGroupBroker(){if(shared)UnmapViewOfFile(shared);if(mapping)CloseHandle(mapping);}
 bool connect(const Native& api,uintptr_t child){
  if(!shared){
   wchar_t name[96];swprintf_s(name,L"Local\\FIFA16_FieldShadowGroup_v2_%lu",GetCurrentProcessId());
   mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Shared),name);if(!mapping)return false;
   shared=(Shared*)MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Shared));if(!shared){CloseHandle(mapping);mapping=nullptr;return false;}
  }
  auto callback=InterlockedCompareExchangePointer(&shared->submit,nullptr,nullptr);
  if(!callback){
   HMODULE owner=nullptr;
   if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,
     reinterpret_cast<LPCWSTR>(&FlatGroup::submit),&owner))return false;
   shared->size=sizeof(Shared);shared->version=2;shared->image=api.image;shared->apiSize=sizeof(Native);
   auto seen=InterlockedCompareExchangePointer(&shared->submit,(void*)&FlatGroup::submit,nullptr);
   callback=seen?seen:(void*)&FlatGroup::submit;
  }
  if(shared->size!=sizeof(Shared)||shared->version!=2||shared->image!=api.image||shared->apiSize!=sizeof(Native))return false;
  return ((Submit)callback)(&api,child);
 }
};
inline bool connectFlatGroup(const Native& api,uintptr_t child){static FlatGroupBroker broker;return broker.connect(api,child);}
}
