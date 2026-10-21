#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include "director.h"
using namespace panorama;
static uintptr_t image=0,previousScene=0;
static LONG beforeCall=0,ourCall=0;
static void* relay=nullptr;
static volatile LONG started=0,stopping=0,installed=0;
static SRWLOCK gate=SRWLOCK_INIT;
static wchar_t configPath[MAX_PATH]{},routePath[MAX_PATH]{},statusPath[MAX_PATH]{},logPath[MAX_PATH]{};
static Settings settings;
static Director director;
static uint64_t lastTick=0;
static uint32_t profile=0;
extern "C" {__declspec(dllexport) struct PublicStatus {
 uint32_t version=3,size=sizeof(PublicStatus),ready=0,enabled=0,active=0;
 int32_t shot=-1;
 uint64_t frames=0,applied=0;
 float progress=0,weight=0,eye[3]{},target[3]{};
 uint32_t profile=0;
 char name[64]{},nativeCamera[96]{};
 float fadeOpacity=0;
 float shotDuration=0;uint32_t shotCount=motionCount,exterior=0;
} PanoramaDroneStatus{};}
static bool read(uintptr_t at,void* out,size_t n){
 if(at<0x10000||at>UINTPTR_MAX-n)return false;
 __try{std::memcpy(out,(void*)at,n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T> static T get(uintptr_t at){T v{};read(at,&v,sizeof v);return v;}
static bool write(uintptr_t at,const void* out,size_t n){
 __try{std::memcpy((void*)at,out,n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
struct Borrowed {
 uintptr_t scene=0;unsigned char original[0x84]{},written[0x84]{};
 uintptr_t fadeScene=0;uint32_t originalFade=0,writtenFade=0;
 void restore(){
  if(fadeScene&&fadeScene==get<uintptr_t>(image+0x3517c10)&&get<uint32_t>(fadeScene+0x225c)==writtenFade)write(fadeScene+0x225c,&originalFade,4);
  fadeScene=0;
  if(scene&&scene==get<uintptr_t>(image+0x3517c10)){
   // These are the only fields edited by this mod. Do not restore flags,
   // lifecycle fields, names or any bytes subsequently changed by FIFA.
   struct Field{unsigned offset,size;};
   const Field fields[]={{0,64},{0x48,8},{0x70,1},{0x7c,8}};
   for(const auto& f:fields){unsigned char current[64]{};
    if(read(scene+0x40+f.offset,current,f.size)&&!std::memcmp(current,written+f.offset,f.size))write(scene+0x40+f.offset,original+f.offset,f.size);
   }
  }
  scene=0;
 }
} borrowed;
static void log(const char* event,int detail=0){FILE* f=nullptr;if(!_wfopen_s(&f,logPath,L"ab")){std::fprintf(f,"%llu pid=%lu %s detail=%d\r\n",GetTickCount64(),GetCurrentProcessId(),event,detail);std::fclose(f);}}
static bool eligible(uintptr_t scene,char* name){
 if(!scene||get<int>(scene+0x3c)!=1||!read(scene+0xc4,name,95))return false;
 // Native FE menu shots only. Exclude FE Step/Kit Select, introductions,
 // live play, replay and every manager/mascot MUSE sequence.
 return eligibleCamera(get<int>(scene+0x3c),name);
}
static bool nativePose(uintptr_t scene,Pose& p,float& aspect){
 float m[16]{};if(!read(scene+0x40,m,sizeof m))return false;
 for(float v:m)if(!std::isfinite(v))return false;
 p.eye={m[12],m[13],m[14]};Vec ray{-m[8],-m[9],-m[10]};
 if(!unit(ray)||std::fabs(p.eye.x)>100000||std::fabs(p.eye.z)>100000||std::fabs(p.eye.y)>100000)return false;
 p.target=p.eye+ray*4000.f;
 const float x=get<float>(scene+0x88),y=get<float>(scene+0x8c);aspect=y>0?x/y:0;
 if(!std::isfinite(aspect)||aspect<.5f||aspect>4.f)return false;
 p.fov=2*std::atan(y)*57.29577951f;return std::isfinite(p.fov)&&p.fov>1&&p.fov<175;
}
static void* __fastcall sceneHook(){
 AcquireSRWLockExclusive(&gate);borrowed.restore();ReleaseSRWLockExclusive(&gate);
 // Preserve the frontend stadium's own scene callback and reload handling.
 void* result=((void*(__fastcall*)())previousScene)();
 AcquireSRWLockExclusive(&gate);
 auto& status=PanoramaDroneStatus;++status.frames;status.enabled=settings.enabled?1u:0u;status.active=0;
 const auto scene=get<uintptr_t>(image+0x3517c10),now=GetTickCount64();
 char name[96]{};Pose native{};float aspect=0;
 const auto nativeFade=get<uint32_t>(scene+0x225c);
 const bool valid=!stopping&&eligible(scene,name)&&nativePose(scene,native,aspect)&&nativeFade<=255;
 const double dt=lastTick&&now>=lastTick?static_cast<double>(now-lastTick)*.001:0;lastTick=now;
 const auto decision=director.tick(dt,valid,settings);
 std::memcpy(status.nativeCamera,name,sizeof name);status.shot=decision.active?static_cast<int>(decision.motion):-1;
 status.progress=decision.progress;status.weight=decision.active?1.f:0.f;status.profile=profile;status.fadeOpacity=decision.opacity;
 status.shotDuration=duration(decision.motion,settings.duration);status.exterior=decision.active&&motions[decision.motion].exterior?1u:0u;
 if(valid&&decision.opacity>0){
  // BC 5D420 emits the native black-fade alpha at frame+740, copied to
  // scene+225C by FIFA's frame consumer. 0=clear, 255=black. Preserve a
  // stronger engine loading fade and restore only our own unchanged value.
  borrowed.fadeScene=scene;borrowed.originalFade=nativeFade;
  borrowed.writtenFade=std::max(nativeFade,static_cast<uint32_t>(std::lround(decision.opacity*255.f)));
  write(scene+0x225c,&borrowed.writtenFade,4);
 }
 if(decision.active){
  // Position changes occur only in CutToDrone/CutToNative at opacity 1.
  // There is no spatial blend to a distant native camera.
  const auto pose=sample(decision.motion,decision.progress,settings.heightLimit,settings.scale);float matrixData[16]{};
  if(matrix(pose,matrixData)&&read(scene+0x40,borrowed.original,sizeof borrowed.original)){
   borrowed.scene=scene;
   const float y=std::tan(pose.fov*.00872664626f),x=y*aspect,zero=0;const unsigned char off=0;
   write(scene+0x40,matrixData,sizeof matrixData);write(scene+0x88,&x,4);write(scene+0x8c,&y,4);
   write(scene+0xb0,&off,1);write(scene+0xbc,&zero,4);write(scene+0xc0,&zero,4);
   read(scene+0x40,borrowed.written,sizeof borrowed.written);
   status.active=1;++status.applied;std::memcpy(status.eye,&pose.eye,sizeof pose.eye);std::memcpy(status.target,&pose.target,sizeof pose.target);
   strncpy_s(status.name,motions[decision.motion].id,_TRUNCATE);
  }
 }else status.name[0]=0;
 ReleaseSRWLockExclusive(&gate);return result;
}
static bool exchangeCall(LONG from,LONG to){
 auto* at=(volatile LONG*)(image+0x3a19f80);DWORD old=0;
 if(!VirtualProtect((void*)at,4,PAGE_EXECUTE_READWRITE,&old))return false;
 const auto previous=InterlockedCompareExchange(at,to,from);DWORD ignored=0;
 VirtualProtect((void*)at,4,old,&ignored);FlushInstructionCache(GetCurrentProcess(),(void*)(image+0x3a19f7f),5);return previous==from;
}
static bool frontendLoaded(){
 HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,GetCurrentProcessId());if(snapshot==INVALID_HANDLE_VALUE)return true;
 MODULEENTRY32W entry{};entry.dwSize=sizeof entry;bool found=false;
 if(Module32FirstW(snapshot,&entry))do{if(!_wcsnicmp(entry.szModule,L"frontend_stadium_",17)){found=true;break;}}while(Module32NextW(snapshot,&entry));
 CloseHandle(snapshot);return found;
}
static bool compatibleTarget(uintptr_t target){
 if(target==image+0x44d8ce0)return !frontendLoaded(); // Wait for its own hook if installed.
 unsigned char jump[14]{};if(!read(target,jump,sizeof jump)||std::memcmp(jump,"\xff\x25\0\0\0\0",6))return false;
 uintptr_t destination=0;std::memcpy(&destination,jump+6,8);HMODULE owner=nullptr;
 if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCWSTR)destination,&owner))return false;
 wchar_t path[MAX_PATH]{};if(!GetModuleFileNameW(owner,path,MAX_PATH))return false;
 const auto leaf=wcsrchr(path,L'\\');return leaf&&!_wcsnicmp(leaf+1,L"frontend_stadium_",17);
}
static bool install(){
 if(get<unsigned char>(image+0x3a19f7f)!=0xe8)return false;
 const auto before=get<LONG>(image+0x3a19f80);const auto target=image+0x3a19f84+before;
 if(!compatibleTarget(target))return false;
 if(!relay){
  for(uintptr_t step=0x10000;step<0x70000000&&!relay;step+=0x10000)relay=VirtualAlloc((void*)(image+step),4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
  if(!relay)return false;
  unsigned char jump[14]={0xff,0x25,0,0,0,0};const auto destination=(uintptr_t)&sceneHook;
  std::memcpy(jump+6,&destination,8);std::memcpy(relay,jump,sizeof jump);DWORD old=0;
  if(!VirtualProtect(relay,4096,PAGE_EXECUTE_READ,&old))return false;FlushInstructionCache(GetCurrentProcess(),relay,4096);
 }
 beforeCall=before;previousScene=target;ourCall=static_cast<LONG>((intptr_t)relay-(intptr_t)(image+0x3a19f84));
 if(!exchangeCall(beforeCall,ourCall))return false;
 PanoramaDroneStatus.ready=1;log("READY additive_menu_panoramas");return true;
}
static unsigned value(const wchar_t* section,const wchar_t* key,int fallback,int lo,int hi){return static_cast<unsigned>(std::clamp(static_cast<int>(GetPrivateProfileIntW(section,key,fallback,configPath)),lo,hi));}
static Settings load(uint32_t& profileId){
 Settings cfg;const wchar_t* section=L"panorama_drone";
 cfg.enabled=value(section,L"enabled",1,0,1)!=0;cfg.duration=static_cast<float>(value(section,L"duration_seconds",52,20,120));
 cfg.gap=static_cast<float>(value(section,L"original_interval_seconds",24,10,180));cfg.initial=static_cast<float>(value(section,L"initial_original_seconds",8,0,120));
 cfg.transition=static_cast<float>(value(section,L"transition_seconds",3,1,8));cfg.heightLimit=static_cast<float>(value(section,L"height_limit_cm",11000,1000,14000));
 cfg.scale=value(section,L"route_scale_percent",100,60,100)*.01f;cfg.mask=0;
 for(unsigned i=0;i<motionCount;++i){wchar_t key[64]{};MultiByteToWideChar(CP_UTF8,0,motions[i].id,-1,key,64);if(value(L"shots",key,1,0,1))cfg.mask|=1u<<i;}
 // The frontend mod can route many stadiums through a shared slot. Hash its
 // actual stadium name, rather than treating slot 176/261 as its identity.
 wchar_t name[256]{};GetPrivateProfileStringW(L"frontend_stadium",L"name",L"",name,256,routePath);
 profileId=0;
 if(name[0]){uint32_t hash=2166136261u;for(const auto* p=name;*p;++p){hash^=static_cast<uint16_t>(*p);hash*=16777619u;}profileId=hash;
  wchar_t specific[32]{};swprintf_s(specific,L"stadium_%08X",hash);
  cfg.heightLimit=static_cast<float>(value(specific,L"height_limit_cm",static_cast<int>(cfg.heightLimit),1000,14000));
  cfg.scale=value(specific,L"route_scale_percent",static_cast<int>(std::round(cfg.scale*100)),60,100)*.01f;
 }
 return cfg;
}
static DWORD WINAPI worker(void*){
 uint64_t nextStatus=0;
 while(!stopping){
  uint32_t identity=0;const auto cfg=load(identity);
  AcquireSRWLockExclusive(&gate);if(profile!=identity){director.reset();lastTick=0;}profile=identity;settings=cfg;ReleaseSRWLockExclusive(&gate);
  AcquireSRWLockExclusive(&gate);
  if(!stopping&&!installed&&install())InterlockedExchange(&installed,1);
  ReleaseSRWLockExclusive(&gate);
  if(GetTickCount64()>=nextStatus){
   nextStatus=GetTickCount64()+1000;AcquireSRWLockShared(&gate);const auto state=PanoramaDroneStatus;ReleaseSRWLockShared(&gate);
   FILE* f=nullptr;if(!_wfopen_s(&f,statusPath,L"wb")){std::fprintf(f,"[panorama_drone]\r\npid=%lu\r\nready=%u\r\nenabled=%u\r\nactive=%u\r\nshot=%d\r\nname=%s\r\nprofile=%08X\r\napplied=%llu\r\nfade_opacity=%.3f\r\ntransition=black_fade\r\nshot_count=%u\r\nduration_seconds=%.1f\r\nexterior=%u\r\n",GetCurrentProcessId(),state.ready,state.enabled,state.active,state.shot,state.name,state.profile,state.applied,state.fadeOpacity,state.shotCount,state.shotDuration,state.exterior);std::fclose(f);}
  }
  Sleep(500);
 }
 return 0;
}
extern "C" __declspec(dllexport) unsigned WINAPI Fifa16ModGetApiVersion(){return 1;}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char*){
 if(InterlockedCompareExchange(&started,1,0))return !stopping;
 image=(uintptr_t)GetModuleHandleW(nullptr);const auto pe=get<int32_t>(image+0x3c);
 if(pe<0||pe>4096||get<uint32_t>(image+pe+8)!=0x577de45c){started=0;return FALSE;}
 wchar_t root[MAX_PATH]{};if(!GetModuleFileNameW(nullptr,root,MAX_PATH))return FALSE;auto* slash=wcsrchr(root,L'\\');if(!slash)return FALSE;*slash=0;
 swprintf_s(configPath,L"%s\\ModCarrerMode\\config\\panorama_drone.ini",root);swprintf_s(routePath,L"%s\\ModCarrerMode\\runtime\\frontend_stadium_route.ini",root);
 swprintf_s(statusPath,L"%s\\runtime\\panorama_drone_status.ini",root);swprintf_s(logPath,L"%s\\ModCarrerMode\\logs\\panorama_drone.log",root);
 HMODULE pin=nullptr;if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCWSTR)&image,&pin))return FALSE;
 uint32_t identity=0;settings=load(identity);profile=identity;
 HANDLE thread=CreateThread(nullptr,0,worker,nullptr,0,nullptr);if(!thread){started=0;return FALSE;}CloseHandle(thread);return TRUE;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStop(){
 InterlockedExchange(&stopping,1);AcquireSRWLockExclusive(&gate);
 const bool restored=!installed||exchangeCall(ourCall,beforeCall);
 borrowed.restore();director.reset();PanoramaDroneStatus.active=0;PanoramaDroneStatus.ready=0;PanoramaDroneStatus.fadeOpacity=0;ReleaseSRWLockExclusive(&gate);
 return restored?TRUE:FALSE;
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(module);return TRUE;}
