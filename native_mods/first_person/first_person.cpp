#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "head_camera_stabilizer.h"
#include "camera_protocol.h"
#include "game_framing.h"
#include "career_camera.h"
#include "camera_channel.h"
#include "camera_bootstrap.h"
#include "camera_subject.h"
#include "camera_final_pose.h"
extern "C" {__declspec(dllexport) CameraPublicState CameraStatus{};}
extern "C" {__declspec(dllexport) CameraTrackingPublicState CameraTrackingStatus{};}
static volatile LONG profile=0;
static volatile LONG framing=1;
static volatile LONG fieldOfView=85,lookBias=0;
static volatile LONG cameraMode=0;
static volatile LONG cameraDistance=0;

static uintptr_t image,bc;
static volatile LONG started=0,stopping=0,enabled=0;
static volatile LONG64 frames=0,applied=0,collections=0;
static volatile LONG64 lastCameraTick=0;
static int headIndex=-1,rootIndex=-1;
static LARGE_INTEGER timerFrequency{};
static fp::Stabilizer stabilizer;
static fp::PossessionFraming gameView;
static fp::CareerCamera careerView;
static fp::CameraSubject subject;
static uintptr_t previousBehavior=0,previousTable=0;
static int previousPlayer=-1;
static int previousPhase=-1;
static int previousMode=-1;
static LARGE_INTEGER previousTime{};
using Generator=void(__fastcall*)(void*,void*);
// The transform source is argument SIX. Keep both intervening arguments intact.
using Collect=void(__fastcall*)(void*,int,int,uintptr_t,uintptr_t,const void*);
static Generator generator;
static Generator moduleUpdate,fixup;
static Collect collect;
static bool read(uintptr_t a,void* out,size_t n){
    if(a<0x10000||a>UINTPTR_MAX-n)return false;
    __try{std::memcpy(out,reinterpret_cast<void*>(a),n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t a){T x{};read(a,&x,sizeof x);return x;}
struct Head {float m[16]{};ULONGLONG tick=0;uintptr_t table=0;fp::Vec root{};bool anchored=false,bodyValid=false;float bodyHeading=0.f;};
struct State{uintptr_t behavior=0,output=0;LONG64 serial=0;int selected=-1,gameState=0,mode=0;Head head{};fp::Pose pose{};float original[28]{},result[28]{};bool valid=false,modded=false;fp::Pose raw{};};
static SRWLOCK headLock=SRWLOCK_INIT,stateLock=SRWLOCK_INIT;
static Head heads[46]{};
static State state{};
static void __fastcall collectHook(void* self,int type,int id,uintptr_t a,uintptr_t b,const void* source){
    collect(self,type,id,a,b,source);
    InterlockedIncrement64(&collections);
    if(type!=0||id<0||id>=46||headIndex<0||headIndex>255)return;
    Head h{};h.tick=GetTickCount64();h.table=reinterpret_cast<uintptr_t>(self);
    if(!read(reinterpret_cast<uintptr_t>(source)+0x20+static_cast<uintptr_t>(headIndex)*64,h.m,sizeof h.m))return;
    float body[16]{};
    if(rootIndex>=0&&rootIndex<=255&&read(reinterpret_cast<uintptr_t>(source)+0x20+static_cast<uintptr_t>(rootIndex)*64,body,sizeof body)){
        h.root={body[12],body[13],body[14]};
        const fp::Vec delta=fp::Vec{h.m[12],h.m[13],h.m[14]}-h.root;
        h.anchored=std::isfinite(h.root.x)&&std::isfinite(h.root.y)&&std::isfinite(h.root.z)&&fp::dot(delta,delta)<300.f*300.f;
        const float horizontal=std::hypot(body[4],body[6]);
        h.bodyValid=std::isfinite(horizontal)&&horizontal>.7f&&horizontal<1.1f&&std::fabs(body[5])<.4f;
        if(h.bodyValid)h.bodyHeading=std::atan2(-body[6],body[4]);
    }
    AcquireSRWLockExclusive(&headLock);heads[id]=h;ReleaseSRWLockExclusive(&headLock);
}
static void __fastcall generatorHook(void* self,void* output){
    generator(self,output);const LONG64 serial=InterlockedIncrement64(&frames);
    InterlockedExchange64(&lastCameraTick,static_cast<LONG64>(GetTickCount64()));
    State s{};s.serial=serial;s.behavior=reinterpret_cast<uintptr_t>(self);s.output=reinterpret_cast<uintptr_t>(output);
    s.selected=get<int>(s.behavior+0x9cc);s.gameState=get<int>(s.behavior+0xaa4);
    const auto iface=get<uintptr_t>(s.behavior+8),data=get<uintptr_t>(iface+0x38);
    // +9C1 is populated by the native areUsersLockedToPlayers property.
    // Retain that match's subject instead of the professional camera's
    // temporary ball/restart focus. Team-control modes still switch normally.
    if(fp::playerCameraPhase(s.gameState)&&data)
        s.selected=subject.resolve(data,s.selected,get<unsigned char>(s.behavior+0x9c1)==1);
    if(!read(s.output,s.original,sizeof s.original))return;
    std::memcpy(s.result,s.original,sizeof s.result);
    if(s.selected>=0&&s.selected<46&&fp::playerCameraPhase(s.gameState)){
        AcquireSRWLockShared(&headLock);s.head=heads[s.selected];ReleaseSRWLockShared(&headLock);
        s.valid=s.head.anchored&&s.head.table==data+0x3470&&GetTickCount64()-s.head.tick<200&&fp::solve(s.head.m,s.raw);
        if(s.valid&&InterlockedCompareExchange(&enabled,0,0)&&!stopping){
            LARGE_INTEGER now{};QueryPerformanceCounter(&now);
            const int mode=InterlockedCompareExchange(&cameraMode,0,0);s.mode=mode;
            const bool contextChanged=previousBehavior!=s.behavior||previousTable!=s.head.table||previousPhase!=s.gameState||previousMode!=mode;
            const bool playerChanged=previousPlayer!=s.selected;
            if(contextChanged||playerChanged){stabilizer.reset();gameView.reset();}
            if(contextChanged)careerView.reset();
            const float dt=previousTime.QuadPart?static_cast<float>(static_cast<double>(now.QuadPart-previousTime.QuadPart)/static_cast<double>(timerFrequency.QuadPart)):0.f;
            auto target=s.raw;
            const float baseFov=static_cast<float>(InterlockedCompareExchange(&fieldOfView,0,0));
            const bool possessing=get<int>(s.behavior+0xa30)==s.selected;
            float fov=baseFov*.01745329252f;
            if(mode==1){
                const auto view=careerView.update(s.raw,s.head.root,get<fp::Vec>(s.behavior+0xa20),dt,baseFov,InterlockedCompareExchange(&cameraDistance,0,0),playerChanged,s.head.bodyValid,s.head.bodyHeading,possessing);
                s.pose=view.pose;fov=view.fov;
            }else{
              if(InterlockedCompareExchange(&framing,0,0)){
                const bool closeControl=get<int>(s.behavior+0xa10)==1; // Native isInPaceControl, not a generic animation id.
                const auto view=gameView.update(target,s.head.root,get<fp::Vec>(s.behavior+0xa20),possessing,dt,closeControl,baseFov);
                target=view.pose;fov=view.fov;
              }else gameView.reset();
              target=fp::personalizeLook(target,InterlockedCompareExchange(&lookBias,0,0));
              s.pose=stabilizer.update(target,s.head.root,dt,InterlockedCompareExchange(&profile,0,0),s.gameState!=15);
              fp::headClearance(s.pose,s.raw);
            }
            previousTime=now;previousBehavior=s.behavior;previousTable=s.head.table;previousPlayer=s.selected;
            previousPhase=s.gameState;
            previousMode=mode;
            auto* p=s.result;const auto& v=s.pose;
            p[0]=v.eye.x;p[1]=v.eye.y;p[2]=v.eye.z;
            p[4]=v.eye.x+v.forward.x*1000.f;p[5]=v.eye.y+v.forward.y*1000.f;p[6]=v.eye.z+v.forward.z*1000.f;
            p[12]=fov;p[13]=v.roll;p[14]=2.f;
            p[16]=v.heading;p[17]=v.pitch;
            if(mode==0){
                // The native post-generator caches output[0..0x64) at +BE0
                // (BCEngine RVAs 8AB29..8ABC8), and reads that cache back into
                // its transition interpolation at 8AAE7. Keep it at the same
                // head anchor as the rendered pose, including restart handoffs.
                std::memcpy(reinterpret_cast<void*>(s.behavior+0xbe0),p,0x64);
            }
            std::memcpy(output,p,0x70);InterlockedIncrement64(&applied);
            s.modded=true;
        }
    }
    if(!s.valid||!InterlockedCompareExchange(&enabled,0,0)||stopping){stabilizer.reset();gameView.reset();careerView.reset();previousTime.QuadPart=0;}
    AcquireSRWLockExclusive(&stateLock);state=s;ReleaseSRWLockExclusive(&stateLock);
}
static void __fastcall moduleUpdateHook(void* self,void* timing){
    const LONG64 before=InterlockedCompareExchange64(&frames,0,0);
    moduleUpdate(self,timing);
    AcquireSRWLockShared(&stateLock);const State s=state;ReleaseSRWLockShared(&stateLock);
    const auto module=get<uintptr_t>(reinterpret_cast<uintptr_t>(self)+8);
    if(stopping||!InterlockedCompareExchange(&enabled,0,0)||!s.modded||s.serial<=before||
       !module||get<uintptr_t>(module+8)!=get<uintptr_t>(s.behavior+8)||
       GetTickCount64()-s.head.tick>=200||!fp::finiteCameraData(s.result))return;
    float finalData[28]{};
    if(!read(module+0xad0,finalData,sizeof finalData))return;
    // Native CameraModule::Update blends restart/intro poses AFTER the
    // third-person generator. Rebuild this exact frame from the authored pose,
    // keeping native projection/viewport conversion and all unrelated fields.
    fp::applyFinalPose(finalData,s.result);
    fixup(reinterpret_cast<void*>(module),finalData);
    std::memcpy(reinterpret_cast<void*>(module+0xad0),finalData,0x64);
    fp::clearNativeCameraEffects(reinterpret_cast<unsigned char*>(module),s.mode==0);
}
static bool exchange(uintptr_t slot,uintptr_t oldValue,uintptr_t newValue){
    DWORD old=0;if(!VirtualProtect(reinterpret_cast<void*>(slot),8,PAGE_READWRITE,&old))return false;
    const auto result=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),reinterpret_cast<void*>(newValue),reinterpret_cast<void*>(oldValue));
    DWORD ignored=0;VirtualProtect(reinterpret_cast<void*>(slot),8,old,&ignored);return result==reinterpret_cast<void*>(oldValue);
}
static DWORD WINAPI worker(void*){
    while(!stopping){
        // Emergency return to the native camera, only while the game is foreground.
        DWORD foreground=0;GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
        if(foreground==GetCurrentProcessId()&&(GetAsyncKeyState(VK_F10)&0x8000))InterlockedExchange(&enabled,0);
        AcquireSRWLockShared(&stateLock);const State s=state;ReleaseSRWLockShared(&stateLock);
        CameraPublicState pub{};pub.started=started;pub.stopping=stopping;pub.enabled=InterlockedCompareExchange(&enabled,0,0);
        pub.profile=InterlockedCompareExchange(&profile,0,0);pub.valid=s.valid&&GetTickCount64()-static_cast<ULONGLONG>(lastCameraTick)<250;pub.selected=s.selected;pub.gameState=s.gameState;pub.frames=frames;pub.applied=applied;
        pub.reserved=static_cast<uint32_t>(InterlockedCompareExchange(&cameraMode,0,0));
        std::memcpy(&CameraStatus,&pub,sizeof pub);
        CameraTrackingPublicState tracking{};
        tracking.selected=s.selected;tracking.gameState=s.gameState;tracking.mode=static_cast<int32_t>(pub.reserved);tracking.valid=pub.valid;
        std::memcpy(tracking.root,&s.head.root,sizeof tracking.root);
        std::memcpy(tracking.headEye,&s.raw.eye,sizeof tracking.headEye);
        std::memcpy(tracking.cameraEye,&s.pose.eye,sizeof tracking.cameraEye);
        tracking.headAgeMs=s.head.tick?static_cast<uint32_t>(GetTickCount64()-s.head.tick):UINT32_MAX;
        tracking.frames=frames;tracking.applied=applied;
        std::memcpy(&CameraTrackingStatus,&tracking,sizeof tracking);
        Sleep(100);
    }return 0;
}
extern "C" __declspec(dllexport) DWORD WINAPI Start(void* directory){
    (void)directory;if(started)return stopping?0:1;
    image=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));bc=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"BCEnginezf.dll"));
    const auto pe=get<int>(image+0x3c);
    if(!bc||pe<0||pe>4096||get<unsigned>(image+static_cast<uintptr_t>(pe)+8)!=0x577de45c)return 0;
    generator=reinterpret_cast<Generator>(bc+0x8a6b0);collect=reinterpret_cast<Collect>(bc+0x5cd20);
    moduleUpdate=reinterpret_cast<Generator>(bc+0x943d0);fixup=reinterpret_cast<Generator>(bc+0x88310);
    if(get<uintptr_t>(bc+0x1254f0)!=reinterpret_cast<uintptr_t>(generator)||get<uintptr_t>(bc+0x1130e0)!=reinterpret_cast<uintptr_t>(collect)||get<uintptr_t>(bc+0x123e40)!=reinterpret_cast<uintptr_t>(moduleUpdate))return 0;
    // Loaded BCEngine is not sufficient: saved activation can reach here
    // before FIFA builds its bone registry. Defer without invoking the API.
    const auto boneCacheReady=get<unsigned char>(image+fp::boneCacheReadyRva);
    if(boneCacheReady!=1)return 2; // Pending native initialization, retry later.
    if(!fp::initializedBones(boneCacheReady,reinterpret_cast<int(__fastcall*)(int)>(bc+0x24a0),headIndex,rootIndex))return 0;
    if(!QueryPerformanceFrequency(&timerFrequency)||timerFrequency.QuadPart<=0)return 0;
    HMODULE pinned=nullptr;if(!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCSTR>(&image),&pinned))return 0;
    if(!exchange(bc+0x1130e0,reinterpret_cast<uintptr_t>(collect),reinterpret_cast<uintptr_t>(&collectHook)))return 0;
    if(!exchange(bc+0x1254f0,reinterpret_cast<uintptr_t>(generator),reinterpret_cast<uintptr_t>(&generatorHook))){exchange(bc+0x1130e0,reinterpret_cast<uintptr_t>(&collectHook),reinterpret_cast<uintptr_t>(collect));return 0;}
    if(!exchange(bc+0x123e40,reinterpret_cast<uintptr_t>(moduleUpdate),reinterpret_cast<uintptr_t>(&moduleUpdateHook))){exchange(bc+0x1254f0,reinterpret_cast<uintptr_t>(&generatorHook),reinterpret_cast<uintptr_t>(generator));exchange(bc+0x1130e0,reinterpret_cast<uintptr_t>(&collectHook),reinterpret_cast<uintptr_t>(collect));return 0;}
    HANDLE t=CreateThread(nullptr,0,worker,nullptr,0,nullptr);
    if(!t){exchange(bc+0x123e40,reinterpret_cast<uintptr_t>(&moduleUpdateHook),reinterpret_cast<uintptr_t>(moduleUpdate));exchange(bc+0x1254f0,reinterpret_cast<uintptr_t>(&generatorHook),reinterpret_cast<uintptr_t>(generator));exchange(bc+0x1130e0,reinterpret_cast<uintptr_t>(&collectHook),reinterpret_cast<uintptr_t>(collect));return 0;}
    CloseHandle(t);InterlockedExchange(&started,1);return 1;
}
extern "C" __declspec(dllexport) DWORD WINAPI Enable(void*){if(stopping)return 0;InterlockedExchange(&enabled,1);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI Disable(void*){InterlockedExchange(&enabled,0);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI SetProfile(void* value){
    if(!value||stopping)return 0;const int selected=get<int>(reinterpret_cast<uintptr_t>(value));
    if(selected<0||selected>3)return 0;InterlockedExchange(&profile,selected);return 1;
}
extern "C" __declspec(dllexport) DWORD WINAPI Stop(void*){
    InterlockedExchange(&enabled,0);InterlockedExchange(&stopping,1);
    const bool a=exchange(bc+0x1254f0,reinterpret_cast<uintptr_t>(&generatorHook),reinterpret_cast<uintptr_t>(generator));
    const bool b=exchange(bc+0x1130e0,reinterpret_cast<uintptr_t>(&collectHook),reinterpret_cast<uintptr_t>(collect));
    const bool c=exchange(bc+0x123e40,reinterpret_cast<uintptr_t>(&moduleUpdateHook),reinterpret_cast<uintptr_t>(moduleUpdate));return a&&b&&c?1:0;
}
static DWORD WINAPI controlLoop(void*){
    HANDLE mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(CameraChannel),CAMERA_MAPPING_NAME);
    if(!mapping)return 0;
    auto* channel=static_cast<CameraChannel*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(CameraChannel)));
    if(!channel){CloseHandle(mapping);return 0;}
    uint32_t lastOwner=0,lastCommand=0;
    while(!stopping){
        const uint32_t owner=channel->owner,command=channel->command;
        const bool alive=channel->version==4&&owner&&static_cast<uint32_t>(GetTickCount()-channel->heartbeat)<3000;
        if(!alive||owner!=lastOwner)InterlockedExchange(&enabled,0);
        if(alive&&(owner!=lastOwner||command!=lastCommand||channel->error==3)){
            int error=0;
            const int wanted=channel->requested,smoothing=channel->profile,view=channel->framing;
            const int lens=channel->fov,bias=channel->look_bias;
            const int mode=channel->mode;
            const int distance=channel->distance;
            const int minLens=mode==1?60:75,maxLens=mode==1?90:150;
            if((wanted!=0&&wanted!=1)||smoothing<0||smoothing>3||view<0||view>1||lens<minLens||lens>maxLens||bias<-10||bias>20||mode<0||mode>1||distance<0||distance>2)error=2;
            else if(wanted){const DWORD result=Start(nullptr);if(!result)error=1;else if(result==2)error=3;}
            if(!error){InterlockedExchange(&profile,smoothing);InterlockedExchange(&framing,view);InterlockedExchange(&fieldOfView,lens);InterlockedExchange(&lookBias,bias);InterlockedExchange(&cameraMode,mode);InterlockedExchange(&cameraDistance,distance);InterlockedExchange(&enabled,wanted);}
            else InterlockedExchange(&enabled,0);
            channel->error=error;MemoryBarrier();channel->ack=command;lastCommand=command;
        }
        lastOwner=owner;
        channel->ready=1;channel->enabled=InterlockedCompareExchange(&enabled,0,0);
        AcquireSRWLockShared(&stateLock);const State s=state;ReleaseSRWLockShared(&stateLock);
        channel->valid=s.valid&&GetTickCount64()-static_cast<ULONGLONG>(lastCameraTick)<250;channel->selected=s.selected;channel->gameState=s.gameState;
        channel->frames=static_cast<uint32_t>(frames);channel->applied=static_cast<uint32_t>(applied);
        Sleep(50);
    }
    channel->ready=channel->enabled=0;UnmapViewOfFile(channel);CloseHandle(mapping);return 0;
}
BOOL WINAPI DllMain(HINSTANCE dll,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(dll);HANDLE t=CreateThread(nullptr,0,controlLoop,nullptr,0,nullptr);if(t)CloseHandle(t);else return FALSE;}
    return TRUE;
}
