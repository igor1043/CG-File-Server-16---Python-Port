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
#include "frame_camera.h"
#include "shot_variants.h"
#include "../../common/scene_camera_lease.h"
using namespace extra;
static uintptr_t image=0,bc=0;
extern "C" { __declspec(dllexport) uintptr_t ExtraScenesEngine=0; }
static wchar_t gamePath[MAX_PATH]{},configPath[MAX_PATH]{},logPath[MAX_PATH]{},statusPath[MAX_PATH]{};
static volatile LONG started=0,stopping=0;
using Publish=void(__fastcall*)(void*,double,void*);
using ReadActors=BOOL(WINAPI*)(SceneActorSnapshot*);
static Publish original=nullptr;
static ReadActors readActors=nullptr;
static SRWLOCK gate=SRWLOCK_INIT;
struct Config {bool enabled=true,test=false;int views[2]{3,3};unsigned weights[2]{1,1};unsigned cooldown=10000,chance=40;uint32_t preview=0;int previewActor=0;Lens lens[4]{{600,26,120,0},{600,12,170,0},{850,24,120,0},{850,12,170,0}};};
static Config options;
static SceneRandom randomizer(1);
static SceneCameraClaim cameraClaim(0x45585452);
static int currentVariant=0,lastVariant[2]{-1,-1};
static uint32_t lastPreview=0;
static bool pendingPreview=false;
static int currentShot=0,nextView[2]{0,0},nextTestActor=0;
static Tripod tripod;
static ActorReadiness readiness[2];
static int coachTeam=-1;
extern "C" {__declspec(dllexport) uint64_t ExtraScenesNativeCameraWrites=0;}
static int coachPalette[2]{-1,-1};
extern "C" {__declspec(dllexport) struct PublicStatus {
 uint32_t version=1,size=sizeof(PublicStatus);
 int32_t running=0,enabled=0,active=0,shot=-1,phase=-1,reason=0;
 uint64_t frames=0,inserted=0,applied=0;
 float eye[3]{},target[3]{};char camera[64]{};
 int32_t cue=0,coachReady=0,mascotReady=0,waiting=0;
} ExtraScenesStatus{};}
static bool read(uintptr_t at,void* out,size_t n){
 if(at<0x10000||at>UINTPTR_MAX-n)return false;
 __try{std::memcpy(out,reinterpret_cast<void*>(at),n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t at){T v{};read(at,&v,sizeof v);return v;}
static bool swapAt(uintptr_t offset,uintptr_t expected,uintptr_t value){
 auto* at=reinterpret_cast<void* volatile*>(bc+offset);DWORD old=0;
 if(!VirtualProtect(const_cast<void**>(at),8,PAGE_READWRITE,&old))return false;
 auto* before=InterlockedCompareExchangePointer(at,reinterpret_cast<void*>(value),reinterpret_cast<void*>(expected));
 DWORD ignored=0;VirtualProtect(const_cast<void**>(at),8,old,&ignored);return before==reinterpret_cast<void*>(expected);
}
static bool swap(uintptr_t expected,uintptr_t value){return swapAt(0x113358,expected,value);}
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
 c.cooldown=1000*setting(L"scenes",L"cooldown_seconds",10,5,300);c.chance=setting(L"scenes",L"chance_percent",40,0,100);
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
 return !_stricmp(name,"game/screens/match/match");
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
 const int first=pendingPreview?cfg.previewActor:cfg.test?nextTestActor:weightedActor(randomizer.next(),cfg.views[0]?cfg.weights[0]:0,cfg.views[1]?cfg.weights[1]:0);
 if(first<0)return false;
 for(int attempt=0;attempt<2;++attempt){
  const int actor=pendingPreview?cfg.previewActor:(first+attempt)%2;const int view=cfg.views[actor];
  if(!readiness[actor].ready(GetTickCount64()))continue;
  if(!pendingPreview&&!cfg.weights[actor])continue;
  if(!view)continue;const int index=actor*2+(view==3?nextView[actor]:view-1);
  Actor candidate;
  if(index<2?coach(s,candidate):mascot(s,candidate)){
   const unsigned start=randomizer.below(shotVariants);
   for(unsigned pass=0;pass<shotVariants;++pass){
    const auto variant=(start+pass)%shotVariants;
    if(static_cast<int>(variant)==lastVariant[actor])continue;
    if(!build(candidate,shotLens(cfg.lens[index],variant,index%2==1),index%2==1,camera)||!frontal(candidate,camera))continue;
    currentShot=index;currentVariant=static_cast<int>(variant);lastVariant[actor]=currentVariant;
    outActor=candidate;nextView[actor]=1-index%2;if(cfg.test)nextTestActor=1-actor;return true;
   }
  }
  if(pendingPreview)break;
 }
 return false;
}
#include "native_muse.h"
static StoppageLatch stoppage;
static uint64_t identity=0,graphLease=0,shotStart=0,lastEnd=0;
static bool sceneActive=false;
static void endScene(int reason){
 if(sceneActive){
  log("NATIVE_CUT_FINISHED",reason);lastEnd=GetTickCount64();
  log("CUT_VISIBLE_MS",static_cast<int>(lastEnd>=shotStart?std::min<uint64_t>(lastEnd-shotStart,600000):0));
 }
 sceneActive=false;graphLease=0;shotStart=0;tripod.reset();
 cameraClaim.release();
 ExtraScenesStatus.active=0;ExtraScenesStatus.shot=-1;
}
// Called by the original update after it builds the reserved frame and BEFORE
// the atomic publication. Only this producer edits it; every reader sees one
// immutable camera. Original MUSE graphs own the cut's lifetime and input.
static void __fastcall producerHook(void* self,double dt,void* output){
 original(self,dt,output);
 AcquireSRWLockExclusive(&gate);
 ExtraScenesEngine=(uintptr_t)self;ExtraScenesStatus.frames++;
 const auto now=GetTickCount64(),scene=get<uintptr_t>(image+0x3517c10);
 const int phase=get<int>(scene+0x3c);const bool replay=get<unsigned char>(scene+0x39)!=0;
 const auto pool=get<uintptr_t>(get<uintptr_t>((uintptr_t)self+0x128));
 const bool reserved=producerFrame(pool,get<int>(pool+0x50b0),get<int>(pool+0x50b4),(uintptr_t)output);
 char name[64]{};read((uintptr_t)output+0xe9,name,63);
 if(char* timer=std::strrchr(name,' ')){if(timer[1]>='0'&&timer[1]<='9')*timer=0;}
 ExtraScenesStatus.phase=phase;strncpy_s(ExtraScenesStatus.camera,name,_TRUNCATE);
 ExtraScenesStatus.enabled=options.enabled?1:0;ExtraScenesStatus.reason=reserved?0:6;
 const bool match=onMatchPage();SceneActorSnapshot actors{};const bool valid=snapshot(actors);
 if(valid&&match){
  const auto fresh=actorSceneIdentity(actors.renderer,actors.generation,actors.home);
  if(identity!=fresh){endScene(6);identity=fresh;stoppage.reset();readiness[0].reset();readiness[1].reset();coachPalette[0]=coachPalette[1]=-1;}
  Actor observed{};const bool managerValid=coach(actors,observed);
  readiness[0].observe((identity<<1)^static_cast<uint64_t>(coachTeam+1),actors.tick,now,managerValid?&observed:nullptr);
  const bool mascotValid=mascot(actors,observed);
  readiness[1].observe(identity,actors.tick,now,mascotValid?&observed:nullptr);
 }else{readiness[0].reset();readiness[1].reset();}
 ExtraScenesStatus.coachReady=readiness[0].ready(now)?1:0;
 ExtraScenesStatus.mascotReady=readiness[1].ready(now)?1:0;
 stoppage.observe(identity,phase==15&&!replay&&match,false,now);
 if(options.preview!=lastPreview){lastPreview=options.preview;pendingPreview=options.preview!=0;}
 const auto presentation=native_muse::current((uintptr_t)self);
 const bool safe=!stopping&&options.enabled&&valid&&
  nativeCutAllowed(phase,name,presentation.cue,reserved,match,replay);
 ExtraScenesStatus.cue=static_cast<int>(presentation.cue);
 const bool continuation=!stopping&&options.enabled&&valid&&
  nativeCutContinuation(phase,name,presentation.name,reserved,match,replay);
 // A graph pointer change or the old five-second cap used to reveal the
 // remaining player reaction. One selected actor now owns the compatible
 // native sequence, and the native gameplay/replay/menu transition ends it.
 if(sceneActive&&!continuation)endScene(2);
 if(safe&&!sceneActive&&!stoppage.claimed()){
  // One roll for the whole stoppage. A missing actor/frontal angle never
  // retries the probability every frame until it becomes a guaranteed cut.
  stoppage.claim();
  const bool chance=options.test||pendingPreview||
   ((!lastEnd||(now>=lastEnd&&now-lastEnd>=options.cooldown))&&randomizer.chance(options.chance));
  if(chance){
   Camera view{};Actor subject{};
   if(choose(options,actors,view,subject)&&tripod.begin(subject,view,now,currentShot%2==1)&&cameraClaim.take((uintptr_t)self^presentation.graph,now)){
    sceneActive=true;graphLease=presentation.graph;shotStart=now;pendingPreview=false;
    ExtraScenesStatus.inserted++;log("NATIVE_CUT_REFRAMED",currentShot);
    log("FRONTAL_VARIANT",currentVariant);
   }
  }
 }
 if(sceneActive){
  Camera view{};Actor subject{};
  if(!(currentShot<2?coach(actors,subject):mascot(actors,subject))||!tripod.update(subject,now,view)||
     !frontal(subject,view,.35f)||!cameraClaim.take((uintptr_t)self^graphLease,now))endScene(1);
  else{
   unsigned char frame[0xc4]{};
   if(read((uintptr_t)output,frame,sizeof frame)&&cameraFrame(frame,sizeof frame,view)){
    // The reserved producer frame remains private until this callback returns.
    __try{std::memcpy((void*)((uintptr_t)output+0x30),frame+0x30,sizeof frame-0x30);}
    __except(EXCEPTION_EXECUTE_HANDLER){endScene(7);}
    if(sceneActive){
     ExtraScenesStatus.active=1;ExtraScenesStatus.shot=currentShot;ExtraScenesStatus.applied++;
     std::memcpy(ExtraScenesStatus.eye,&view.eye,sizeof view.eye);std::memcpy(ExtraScenesStatus.target,&view.target,sizeof view.target);
     ++ExtraScenesNativeCameraWrites;
    }
   }else endScene(7);
  }
 }
 ReleaseSRWLockExclusive(&gate);
}
static bool install(){
 bc=(uintptr_t)GetModuleHandleW(L"BCEnginezf.dll");if(!bc)return false;
 original=(Publish)get<uintptr_t>(bc+0x113358);
 if(!scene_camera_chain((uintptr_t)original,bc+0x5d420)||get<uintptr_t>(bc+0x113318)!=bc+0x3fd90||
    get<uintptr_t>(bc+0x113300)!=bc+0x67220||get<uintptr_t>(bc+0x12c890)!=bc+0xb09f0||
    get<uintptr_t>(bc+0x1245b0)!=bc+0x853a0)return false;
 // Signature and exact caller verify this is the pre-publication callback.
 const unsigned char signature[]={0x40,0x56,0x41,0x56,0x48,0x83,0xec,0x48};unsigned char actual[sizeof signature]{};
 if(!read(bc+0x5d420,actual,sizeof actual)||memcmp(actual,signature,sizeof actual))return false;
 return cameraClaim.open()&&swap((uintptr_t)original,(uintptr_t)&producerHook);
}
static DWORD WINAPI worker(void*){
 bool installed=false;uint64_t nextStatus=0;uint64_t lastInserted=0;
 while(!stopping){
  auto mascotModule=GetModuleHandleW(L"mascot_goal_line.dll");
  const auto actorReader=mascotModule?reinterpret_cast<ReadActors>(GetProcAddress(mascotModule,"Fifa16ReadSceneActors")):nullptr;
  const Config cfg=loadConfig();AcquireSRWLockExclusive(&gate);options=cfg;readActors=actorReader;ReleaseSRWLockExclusive(&gate);
  if(!installed&&actorReader){installed=install();if(installed){AcquireSRWLockExclusive(&gate);ExtraScenesStatus.running=1;ReleaseSRWLockExclusive(&gate);log("READY native_cut_producer");}}
  const auto now=GetTickCount64();
  if(now>=nextStatus){
   nextStatus=now+1000;AcquireSRWLockShared(&gate);const PublicStatus status=ExtraScenesStatus;ReleaseSRWLockShared(&gate);
   if(status.inserted!=lastInserted){lastInserted=status.inserted;log("EXTRA_INSERTED",status.shot);}
   wchar_t temp[MAX_PATH]{};_snwprintf_s(temp,MAX_PATH,_TRUNCATE,L"%ls.tmp",statusPath);FILE* f=nullptr;
   if(!_wfopen_s(&f,temp,L"wb")){
   std::fprintf(f,"[runtime]\r\nmode=native_cut_producer\r\nrevision=12\r\npid=%lu\r\nready=%d\r\nenabled=%d\r\nactive=%d\r\nshot=%d\r\ninserted=%llu\r\nreason=%d\r\nphase=%d\r\ncue=%d\r\ncoach_ready=%d\r\nmascot_ready=%d\r\nwaiting=%d\r\n",GetCurrentProcessId(),status.running,status.enabled,status.active,status.shot,status.inserted,status.reason,status.phase,status.cue,status.coachReady,status.mascotReady,status.waiting);
    std::fclose(f);MoveFileExW(temp,statusPath,MOVEFILE_REPLACE_EXISTING);
   }
  }
  Sleep(250);
 }
 return 0;
}
extern "C" __declspec(dllexport) unsigned WINAPI Fifa16ModGetApiVersion(){return 1;}
extern "C" __declspec(dllexport) unsigned WINAPI Fifa16SceneCameraChainApi(){return 1;}
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
 randomizer=SceneRandom(GetTickCount64()^image^(static_cast<uint64_t>(GetCurrentProcessId())<<32));
 HANDLE thread=CreateThread(nullptr,0,&worker,nullptr,0,nullptr);if(!thread){started=0;return FALSE;}CloseHandle(thread);log("START waiting_actor_api");return TRUE;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStop(){
 InterlockedExchange(&stopping,1);
 if(original)swap((uintptr_t)&producerHook,(uintptr_t)original);
 return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);return TRUE;}
