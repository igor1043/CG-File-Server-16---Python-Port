#pragma once
// Cooperation between independent native cut mods. All camera writes still
// happen in the existing pre-publication callback, never in GetFrame readers.
#include <windows.h>
#include <cstdint>
#include <cstdio>
struct SceneCameraLease {
 uint32_t version,size;volatile LONG gate,owner;
 uint64_t scope,heartbeat;
};
class SceneCameraClaim {
 HANDLE mapping_=nullptr;SceneCameraLease* data_=nullptr;LONG owner_;
 bool enter(){for(unsigned i=0;i<32;++i){if(!InterlockedCompareExchange(&data_->gate,1,0))return true;YieldProcessor();}return false;}
 void leave(){InterlockedExchange(&data_->gate,0);}
public:
 explicit SceneCameraClaim(LONG owner):owner_(owner){}
 bool open(){
  if(data_)return true;wchar_t name[96]{};
  swprintf_s(name,L"Local\\FIFA16SceneCameraLeaseV1_%lu",GetCurrentProcessId());
  mapping_=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(SceneCameraLease),name);
  if(!mapping_)return false;
  data_=static_cast<SceneCameraLease*>(MapViewOfFile(mapping_,FILE_MAP_ALL_ACCESS,0,0,sizeof(SceneCameraLease)));
  if(!data_)return false;
  if(!data_->version){data_->size=sizeof(SceneCameraLease);InterlockedExchange(reinterpret_cast<volatile LONG*>(&data_->version),1);}
  return data_->version==1&&data_->size==sizeof(SceneCameraLease);
 }
 bool take(uint64_t scope,uint64_t now){
  if(!data_||!scope||!enter())return false;
  if(data_->owner&&(now<data_->heartbeat||now-data_->heartbeat>500))data_->owner=0;
  const bool ok=!data_->owner||(data_->owner==owner_&&data_->scope==scope);
  if(ok){data_->scope=scope;data_->heartbeat=now;data_->owner=owner_;}
  leave();return ok;
 }
 void release(){if(data_&&enter()){if(data_->owner==owner_)data_->owner=0;leave();}}
};
inline bool scene_camera_chain(uintptr_t callback,uintptr_t native){
 if(callback==native)return true;
 HMODULE module=nullptr;
 if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(callback),&module))return false;
 const auto api=reinterpret_cast<unsigned(WINAPI*)()>(GetProcAddress(module,"Fifa16SceneCameraChainApi"));
 return api&&api()==1;
}
