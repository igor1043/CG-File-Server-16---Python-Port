#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <intrin.h>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <cstring>
#include "scene_actor_api.h"
#include "scene_math.h"
#include "scene_tracking.h"
#include "reaction_policy.h"
#include "scene_readiness.h"
using namespace extra;
static uintptr_t image=0,bc=0;
extern "C" { __declspec(dllexport) uintptr_t ExtraScenesEngine=0; }
static wchar_t gamePath[MAX_PATH]{},configPath[MAX_PATH]{},logPath[MAX_PATH]{},statusPath[MAX_PATH]{};
static volatile LONG started=0,stopping=0;
using GetFrame=void*(__fastcall*)(void*,double);
using CameraConvert=void(__fastcall*)(void*,void*);
static CameraConvert convertOriginal=nullptr;
using ReadActors=BOOL(WINAPI*)(SceneActorSnapshot*);
static GetFrame original=nullptr;
static ReadActors readActors=nullptr;
static SRWLOCK gate=SRWLOCK_INIT;
struct Config {bool enabled=true,test=false;int views[2]{3,3};unsigned weights[2]{1,1};unsigned cooldown=45000,chance=35,duration=5000;uint32_t preview=0;int previewActor=0;Lens lens[4]{{600,26,120,0},{600,12,170,0},{850,24,120,0},{850,12,170,0}};};
static Config options;
static uint32_t lastPreview=0;
static bool pendingPreview=false;
static int currentShot=0,nextView[2]{0,0},nextTestActor=0;
static Tripod tripod;
static ActorReadiness readiness[2];
static int coachTeam=-1;
static uint64_t patched=0;
static unsigned char saved[0x94]{},written[0x94]{};
extern "C" {__declspec(dllexport) uint64_t ExtraScenesNativeCameraWrites=0;}
static int coachPalette[2]{-1,-1};
extern "C" {__declspec(dllexport) struct PublicStatus {
 uint32_t version=1,size=sizeof(PublicStatus);
 int32_t running=0,enabled=0,active=0,shot=-1,phase=-1,reason=0;
 uint64_t frames=0,inserted=0,applied=0;
 float eye[3]{},target[3]{};char camera[64]{};
} ExtraScenesStatus{};}
static bool read(uintptr_t at,void* out,size_t n){
 if(at<0x10000||at>UINTPTR_MAX-n)return false;
 __try{std::memcpy(out,reinterpret_cast<void*>(at),n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t at){T v{};read(at,&v,sizeof v);return v;}
static bool write(uintptr_t at,const void* p,size_t n){
 __try{std::memcpy(reinterpret_cast<void*>(at),p,n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
static bool swapAt(uintptr_t offset,uintptr_t expected,uintptr_t value){
 auto* at=reinterpret_cast<void* volatile*>(bc+offset);DWORD old=0;
 if(!VirtualProtect(const_cast<void**>(at),8,PAGE_READWRITE,&old))return false;
 auto* before=InterlockedCompareExchangePointer(at,reinterpret_cast<void*>(value),reinterpret_cast<void*>(expected));
 DWORD ignored=0;VirtualProtect(const_cast<void**>(at),8,old,&ignored);return before==reinterpret_cast<void*>(expected);
}
static bool swap(uintptr_t expected,uintptr_t value){return swapAt(0x113318,expected,value);}
static void restore(){if(patched){
 unsigned char current[sizeof saved]{};
 // A producer can recycle a pool slot between consumers. Restore only our
 // unchanged bytes; never overwrite a newer frame produced by the engine.
 if(read(patched,current,sizeof current)&&!std::memcmp(current,written,sizeof current))write(patched,saved,sizeof saved);
 patched=0;
}}
static void log(const char* event,int detail=0){
 FILE* f=nullptr;if(_wfopen_s(&f,logPath,L"ab")||!f)return;
 std::fprintf(f,"%llu pid=%lu %s detail=%d\r\n",GetTickCount64(),GetCurrentProcessId(),event,detail);std::fclose(f);
}
static unsigned setting(const wchar_t* section,const wchar_t* key,int fallback,int lo,int hi){
 const int n=static_cast<int>(GetPrivateProfileIntW(section,key,fallback,configPath));return static_cast<unsigned>(std::clamp(n,lo,hi));
}
static Config loadConfig(){
 Config c;c.enabled=setting(L"scenes",L"enabled",1,0,1)!=0;
 c.test=setting(L"scenes",L"test_mode",0,0,1)!=0;
 c.views[0]=static_cast<int>(setting(L"scenes",L"coach_view",3,0,3));c.views[1]=static_cast<int>(setting(L"scenes",L"mascot_view",3,0,3));
 c.weights[0]=setting(L"scenes",L"coach_weight",1,0,100);c.weights[1]=setting(L"scenes",L"mascot_weight",1,0,100);
 c.cooldown=1000*setting(L"scenes",L"cooldown_seconds",45,5,300);c.chance=setting(L"scenes",L"chance_percent",35,0,100);c.duration=setting(L"scenes",L"duration_ms",5000,1000,10000);
 c.preview=setting(L"scenes",L"preview_serial",0,0,0x7fffffff);c.previewActor=static_cast<int>(setting(L"scenes",L"preview_actor",0,0,1));
 const wchar_t* sections[]={L"coach_full",L"coach_face",L"mascot_full",L"mascot_face"};
 for(int i=0;i<4;++i){
  c.lens[i].distance=static_cast<int>(setting(sections[i],L"distance",c.lens[i].distance,250,1600));
  c.lens[i].fov=static_cast<int>(setting(sections[i],L"fov",c.lens[i].fov,8,65));
  c.lens[i].height=static_cast<int>(setting(sections[i],L"height",c.lens[i].height,80,220));
  c.lens[i].angle=static_cast<int>(setting(sections[i],L"angle",c.lens[i].angle,-45,45));
 }
 return c;
}
static bool onMatchPage(){
 uintptr_t p=get<uintptr_t>(image+58757168);
 for(unsigned off:{232u,192u,136u,472u}){p=get<uintptr_t>(p+off);if(!p)return false;}
 char name[128]{};if(!read(p,name,sizeof name)||!std::memchr(name,0,sizeof name))return false;
 if(!name[0])return true;
 return !_stricmp(name,"game/screens/match/match")||!_stricmp(name,"game/screens/tv/bumper")||!_stricmp(name,"tv/bumper")||!_stricmp(name,"game/screens/misc/StadiumPan");
}
static bool snapshot(SceneActorSnapshot& s){return readActors&&readActors(&s)&&s.version==1&&s.size==sizeof s&&s.renderer&&GetTickCount64()-s.tick<400;}
static bool coach(const SceneActorSnapshot& s,Actor& result){
 const auto game=get<uintptr_t>(get<uintptr_t>(image+0x3517420)+16);const int seq=get<int>(game+0xda840);
 if(!game||seq<0)return false;const auto frame=game+static_cast<uintptr_t>(seq%10)*0x15da0;
 const auto control=get<uintptr_t>(get<uintptr_t>(frame+0xb90));const int selected=get<int>(control+0x10);
 if(!control||selected<0||selected>=46)return false;
 const auto player=get<uintptr_t>(get<uintptr_t>(frame+0xca0)+static_cast<uintptr_t>(selected)*8);const int team=get<int>(player+4);
 if(team<0||team>1)return false;
 const auto native=get<uintptr_t>(get<uintptr_t>(frame+0xe30)+static_cast<uintptr_t>(team)*8);Vec feet{};
 if(!native||get<int>(native)!=team||!read(native+0x10,&feet,sizeof feet))return false;feet=feet*30.48f;
 if(!finite(feet)||std::fabs(feet.z)<2800||std::fabs(feet.z)>6000)return false;
 int found=-1;float best=150.f;Vec renderedRoot{};
 for(int pass=0;pass<74;++pass){
  const int slot=pass==0?coachPalette[team]:pass-1;if(slot<0||slot>=73)continue;
  if(!get<unsigned char>(s.renderer+static_cast<uintptr_t>(slot)*0xe00+0xf5d0))continue;
  Vec root{};if(!read(s.renderer+static_cast<uintptr_t>(slot)*0xe00+0xe7e0+64+48,&root,sizeof root)||!finite(root))continue;
  const float error=length(root-feet);if(error<best){found=slot;best=error;renderedRoot=root;if(pass==0)break;}
 }
 if(found<0)return false;float head[16]{};
 if(!read(s.renderer+static_cast<uintptr_t>(found)*0xe00+0xe7e0+14*64,head,sizeof head))return false;
 const Vec position{head[12],head[13],head[14]};Vec front{head[4],0,head[6]};
 if(!finite(position)||position.y<110||position.y>250||length(position-feet)>270||!unit(front))return false;
 // The simulation chooses the correct coach; the visible mesh positions the
 // shot. Animation/root motion can offset it from the simulation's anchor.
 coachPalette[team]=found;coachTeam=team;result={renderedRoot,position,front,std::max(185.f,position.y-renderedRoot.y+28.f)};return true;
}
static bool mascot(const SceneActorSnapshot& s,Actor& out){
 if(s.mascotValid!=1)return false;
 const Vec root{s.mascotPosition[0],s.mascotPosition[1],s.mascotPosition[2]};
 const auto* m=s.mascotHead;const Vec head=root+Vec{m[12],m[13],m[14]};Vec front{m[4],0,m[6]};
 if(!finite(root)||!finite(head)||std::fabs(root.x)<5600||std::fabs(root.x)>6200||std::fabs(root.z)>3500||m[13]<100||m[13]>260||!unit(front))return false;
 out={root,head,front,std::max(200.f,m[13]+50.f)};return true;
}
static bool choose(const Config& cfg,const SceneActorSnapshot& s,Camera& camera,Actor& outActor){
 const int first=pendingPreview?cfg.previewActor:cfg.test?nextTestActor:weightedActor(static_cast<uint32_t>(GetTickCount64()),cfg.views[0]?cfg.weights[0]:0,cfg.views[1]?cfg.weights[1]:0);
 if(first<0)return false;
 for(int attempt=0;attempt<2;++attempt){
  const int actor=pendingPreview?cfg.previewActor:(first+attempt)%2;const int view=cfg.views[actor];
  if(!readiness[actor].ready(GetTickCount64()))continue;
  if(!pendingPreview&&!cfg.weights[actor])continue;
  if(!view)continue;const int index=actor*2+(view==3?nextView[actor]:view-1);
  Actor candidate;
  if((index<2?coach(s,candidate):mascot(s,candidate))&&build(candidate,cfg.lens[index],index%2==1,camera)){
   currentShot=index;outActor=candidate;nextView[actor]=1-index%2;if(cfg.test)nextTestActor=1-actor;return true;
  }
  if(pendingPreview)break;
 }
 return false;
}
#include "native_muse.h"
// BroadcastingBehavior's native conversion runs before the camera frame is
// published. Feed its consumers the actual shot, not only a final view patch.
static void __fastcall convertHook(void* self,void* output){
 convertOriginal(self,output);
 AcquireSRWLockExclusive(&gate);
 const auto scene=get<uintptr_t>(image+0x3517c10),now=GetTickCount64();
 SceneActorSnapshot actors{};Camera view{};
 if(!stopping&&options.enabled&&native_muse::ownedGraph&&
    stoppedScenePhase(get<int>(scene+0x3c))&&!get<unsigned char>(scene+0x39)&&
    onMatchPage()&&snapshot(actors)&&native_muse::lease(now,view,actors)){
  const auto out=(uintptr_t)output;const float zero=0;
  if(write(out,&view.eye,sizeof view.eye)&&write(out+0x10,&view.target,sizeof view.target)){
   write(out+0x30,&view.fov,4);write(out+0x34,&zero,4);
   ++ExtraScenesNativeCameraWrites;
   static uint64_t tracedInsertion=0;
   if(tracedInsertion!=ExtraScenesStatus.inserted){tracedInsertion=ExtraScenesStatus.inserted;log("NATIVE_CAMERA_SOURCE_APPLIED",currentShot);}
  }
 }
 ReleaseSRWLockExclusive(&gate);
}
static void* __fastcall hook(void* self,double time){
 const auto caller=reinterpret_cast<uintptr_t>(_ReturnAddress());
 AcquireSRWLockExclusive(&gate);
 static unsigned traced=0;static uint64_t tracedInsertion=0;
 if(tracedInsertion!=ExtraScenesStatus.inserted){tracedInsertion=ExtraScenesStatus.inserted;traced=0;}
 if(patched&&ExtraScenesStatus.active&&traced<3){
  const auto scene=get<uintptr_t>(image+0x3517c10);Vec actual{};
  if(read(scene+0x70,&actual,sizeof actual)){
   FILE* trace=nullptr;if(!_wfopen_s(&trace,logPath,L"ab")){
    std::fprintf(trace,"%llu NATIVE_VIEW_CHECK desired=%.2f,%.2f,%.2f actual=%.2f,%.2f,%.2f target=%.2f,%.2f,%.2f\r\n",GetTickCount64(),ExtraScenesStatus.eye[0],ExtraScenesStatus.eye[1],ExtraScenesStatus.eye[2],actual.x,actual.y,actual.z,ExtraScenesStatus.target[0],ExtraScenesStatus.target[1],ExtraScenesStatus.target[2]);std::fclose(trace);
   }++traced;
  }
 }
 restore();ReleaseSRWLockExclusive(&gate);
 void* frame=original(self,time);
 if(!frame)return frame;
 AcquireSRWLockExclusive(&gate);ExtraScenesStatus.frames++;
 const auto now=GetTickCount64();const auto scene=get<uintptr_t>(image+0x3517c10);
 const int phase=get<int>(scene+0x3c);const bool replay=get<unsigned char>(scene+0x39)!=0;
 char name[64]{};read(reinterpret_cast<uintptr_t>(frame)+0xe9,name,63);
 if(char* timer=std::strrchr(name,' ')){if(timer[1]>='0'&&timer[1]<='9')*timer=0;}
 ExtraScenesStatus.phase=phase;strncpy_s(ExtraScenesStatus.camera,name,_TRUNCATE);
 SceneActorSnapshot actors{};const bool valid=snapshot(actors);const Config cfg=options;
 if(valid&&onMatchPage()){
  Actor observed{};const bool managerValid=coach(actors,observed);
  const uint64_t managerIdentity=(actors.renderer<<1)^static_cast<uint64_t>(coachTeam+1);
  readiness[0].observe(managerIdentity,actors.tick,now,managerValid?&observed:nullptr);
  const bool mascotValid=mascot(actors,observed);
  readiness[1].observe(actors.renderer,actors.tick,now,mascotValid?&observed:nullptr);
 }else{readiness[0].reset();readiness[1].reset();}
 if(cfg.preview!=lastPreview){lastPreview=cfg.preview;pendingPreview=cfg.preview!=0;}
 const bool active=!stopping&&valid&&!replay&&onMatchPage()&&stoppedScenePhase(phase)&&native_muse::ownedGraph;
 ExtraScenesStatus.enabled=cfg.enabled?1:0;ExtraScenesStatus.active=0;
 if(!active){ReleaseSRWLockExclusive(&gate);return frame;}
 Camera simulationCamera{},camera{};
 static uintptr_t readers[16]{};static unsigned readerCount=0;static uint64_t readerInsertion=0;
 if(readerInsertion!=ExtraScenesStatus.inserted){readerInsertion=ExtraScenesStatus.inserted;readerCount=0;}
 bool known=false;for(unsigned i=0;i<readerCount;++i)if(readers[i]==caller)known=true;
 if(!known&&readerCount<16){readers[readerCount++]=caller;
  const auto out=(uintptr_t)frame;const Vec before=get<Vec>(out+0x60);
  FILE* f=nullptr;if(!_wfopen_s(&f,logPath,L"ab")){std::fprintf(f,"%llu NATIVE_CAMERA_READER caller=%llx native_eye=%.2f,%.2f,%.2f camera=%s\r\n",now,(unsigned long long)caller,before.x,before.y,before.z,name);std::fclose(f);}
 }
 if(!native_muse::lease(now,simulationCamera,actors)||!exportedCamera(simulationCamera,camera)){ExtraScenesStatus.reason=4;ReleaseSRWLockExclusive(&gate);return frame;}
 ExtraScenesStatus.active=1;ExtraScenesStatus.reason=1;
 const auto data=reinterpret_cast<uintptr_t>(frame)+0x30;
 if(read(data,saved,sizeof saved)){
  const float oldY=get<float>(reinterpret_cast<uintptr_t>(frame)+0x8c),oldX=get<float>(reinterpret_cast<uintptr_t>(frame)+0x88);
  const float aspect=oldY>0?oldX/oldY:0;
  if(std::isfinite(aspect)&&aspect>.5f&&aspect<4.f){
   const float scaleY=std::tan(camera.fov*.5f),scaleX=scaleY*aspect,zero=0;const unsigned char off=0;
   // Only the leased native output frame is edited, after all original cuts.
   // Preserve lens/DOF fields and restore before the pool frame is reused.
   write(data,camera.matrix,sizeof camera.matrix);write(reinterpret_cast<uintptr_t>(frame)+0x88,&scaleX,4);write(reinterpret_cast<uintptr_t>(frame)+0x8c,&scaleY,4);
   write(reinterpret_cast<uintptr_t>(frame)+0xa0,&camera.focus,4);write(reinterpret_cast<uintptr_t>(frame)+0xb0,&off,1);
   write(reinterpret_cast<uintptr_t>(frame)+0xbc,&zero,4);write(reinterpret_cast<uintptr_t>(frame)+0xc0,&zero,4);read(data,written,sizeof written);patched=data;
   ExtraScenesStatus.shot=currentShot;ExtraScenesStatus.applied++;
   std::memcpy(ExtraScenesStatus.eye,&camera.eye,sizeof camera.eye);std::memcpy(ExtraScenesStatus.target,&camera.target,sizeof camera.target);
  }else{ExtraScenesStatus.active=0;ExtraScenesStatus.reason=5;}
 }
 ReleaseSRWLockExclusive(&gate);return frame;
}
static bool install(){
 bc=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"BCEnginezf.dll"));if(!bc)return false;
 original=reinterpret_cast<GetFrame>(bc+0x3fd90);
 if(get<uintptr_t>(bc+0x113318)!=reinterpret_cast<uintptr_t>(original))return false;
 if(get<uintptr_t>(bc+0x113300)!=bc+0x67220||get<uintptr_t>(bc+0x12c890)!=bc+0xb09f0||get<uintptr_t>(bc+0x1245b0)!=bc+0x853a0)return false;
 convertOriginal=(CameraConvert)(bc+0x853a0);
 const unsigned char sig[]={0x48,0x8b,0x89,0x28,0x01,0x00,0x00};unsigned char actual[7]{};
 if(!read(bc+0x3fd90,actual,7)||std::memcmp(actual,sig,7))return false;
 native_muse::updateOriginal=(native_muse::Update)(bc+0x67220);native_muse::playOriginal=(native_muse::Play)(bc+0xb09f0);
 if(!swapAt(0x113300,bc+0x67220,(uintptr_t)&native_muse::updateHook))return false;
 if(!swapAt(0x12c890,bc+0xb09f0,(uintptr_t)&native_muse::playHook)){
  swapAt(0x113300,(uintptr_t)&native_muse::updateHook,bc+0x67220);return false;
 }
 if(!swap((uintptr_t)original,(uintptr_t)&hook)){
  swapAt(0x12c890,(uintptr_t)&native_muse::playHook,bc+0xb09f0);
  swapAt(0x113300,(uintptr_t)&native_muse::updateHook,bc+0x67220);return false;
 }
 if(!swapAt(0x1245b0,bc+0x853a0,(uintptr_t)&convertHook)){
  swap((uintptr_t)&hook,(uintptr_t)original);
  swapAt(0x12c890,(uintptr_t)&native_muse::playHook,bc+0xb09f0);
  swapAt(0x113300,(uintptr_t)&native_muse::updateHook,bc+0x67220);return false;
 }
 return true;
}
static DWORD WINAPI worker(void*){
 bool installed=false;uint64_t nextStatus=0;uint64_t lastInserted=0;
 while(!stopping){
  auto mascotModule=GetModuleHandleW(L"mascot_goal_line.dll");
  const auto actorReader=mascotModule?reinterpret_cast<ReadActors>(GetProcAddress(mascotModule,"Fifa16ReadSceneActors")):nullptr;
  const Config cfg=loadConfig();AcquireSRWLockExclusive(&gate);options=cfg;readActors=actorReader;ReleaseSRWLockExclusive(&gate);
  if(!installed&&actorReader){installed=install();if(installed){AcquireSRWLockExclusive(&gate);ExtraScenesStatus.running=1;ReleaseSRWLockExclusive(&gate);log("READY native_muse_reactions");}}
  const auto now=GetTickCount64();
  if(now>=nextStatus){
   nextStatus=now+1000;AcquireSRWLockShared(&gate);const PublicStatus status=ExtraScenesStatus;ReleaseSRWLockShared(&gate);
   if(status.inserted!=lastInserted){lastInserted=status.inserted;log("EXTRA_INSERTED",status.shot);}
   wchar_t temp[MAX_PATH]{};_snwprintf_s(temp,MAX_PATH,_TRUNCATE,L"%ls.tmp",statusPath);FILE* f=nullptr;
   if(!_wfopen_s(&f,temp,L"wb")){
    std::fprintf(f,"[runtime]\r\nmode=native_muse\r\npid=%lu\r\nready=%d\r\nenabled=%d\r\nactive=%d\r\nshot=%d\r\ninserted=%llu\r\nreason=%d\r\n",GetCurrentProcessId(),status.running,status.enabled,status.active,status.shot,status.inserted,status.reason);
    std::fclose(f);MoveFileExW(temp,statusPath,MOVEFILE_REPLACE_EXISTING);
   }
  }
  Sleep(250);
 }
 return 0;
}
extern "C" __declspec(dllexport) unsigned WINAPI Fifa16ModGetApiVersion(){return 1;}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char*){
 if(InterlockedCompareExchange(&started,1,0))return TRUE;
 image=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
 if(get<uint16_t>(image)!=0x5a4d||get<uint32_t>(image+get<int32_t>(image+0x3c)+8)!=0x577de45c){started=0;return FALSE;}
 if(!GetModuleFileNameW(nullptr,gamePath,MAX_PATH))return FALSE;auto* slash=wcsrchr(gamePath,L'\\');if(!slash)return FALSE;*slash=0;
 _snwprintf_s(configPath,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\config\\extra_scenes.ini",gamePath);
 _snwprintf_s(logPath,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\logs\\extra_scenes.log",gamePath);
 _snwprintf_s(statusPath,MAX_PATH,_TRUNCATE,L"%ls\\runtime\\extra_scenes_status.ini",gamePath);
 wchar_t runtime[MAX_PATH]{};_snwprintf_s(runtime,MAX_PATH,_TRUNCATE,L"%ls\\runtime",gamePath);CreateDirectoryW(runtime,nullptr);
 HMODULE pin=nullptr;if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&image),&pin))return FALSE;
 options=loadConfig();lastPreview=options.preview;
 HANDLE thread=CreateThread(nullptr,0,&worker,nullptr,0,nullptr);if(!thread){started=0;return FALSE;}CloseHandle(thread);log("START waiting_actor_api");return TRUE;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStop(){
 InterlockedExchange(&stopping,1);AcquireSRWLockExclusive(&gate);restore();ReleaseSRWLockExclusive(&gate);
 if(bc)swapAt(0x1245b0,(uintptr_t)&convertHook,bc+0x853a0);
 if(bc)swapAt(0x12c890,(uintptr_t)&native_muse::playHook,bc+0xb09f0);
 if(original)swap(reinterpret_cast<uintptr_t>(&hook),reinterpret_cast<uintptr_t>(original));return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);return TRUE;}
