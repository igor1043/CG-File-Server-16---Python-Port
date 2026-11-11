#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <array>
#include <atomic>
#include "background_provider.h"
#include "room_cover.h"
#include "frontend_visibility.h"
#include "career_profile.h"
#include "scene_context.h"
#include "player_scene.h"
#include "menu_page.h"
#include "profile_reload.h"
#include "reload_scope.h"
#include "stadium_metadata.h"
#include "../../common/club_stadium_scope.h"
#include "../../common/career_background.h"
#include "../../common/scene_loading.h"

// Verified call sites on the installed 577DE45C FIFA build. Scene requests
// pass through FIFA's existing FE event queue and preparation/loading pair.
static constexpr uintptr_t kPrepare=0x435e8c0,kCall=0x43630eb;
static uintptr_t image=0;
static wchar_t game[MAX_PATH]{},config[MAX_PATH]{},logPath[MAX_PATH]{},helper[MAX_PATH]{};
static volatile LONG started=0,stopping=0,installed=0;
static LONG originalDisplacement=0,ourDisplacement=0;
static LONG64 originalPhotoWord=0,ourPhotoWord=0;
static void* relay=nullptr;
static bool relayReady=false;
static SRWLOCK gate=SRWLOCK_INIT;
static int activeMode=0;
static wchar_t routeIni[MAX_PATH]{};
static LONG originalPan=0,ourPan=0,originalDraw=0,ourDraw=0;
static LONG64 originalFrame=0,ourFrame=0;
static wchar_t liveIni[MAX_PATH]{},activeName[256]{},stageSelection[512]{};
static char activeCrowd[MAX_PATH]{};
static int activeCapacity=0,activeAttendance=-1;
static volatile LONG stageRequest=0,stageComplete=0;
static int stageTeam=0,stageCareer=0,stageSlot=0,stageMode=0;
static DWORD stageError=0;
static uint64_t lastProbe=0,waitSince=0;
static LONG requestNumber=0;
static int observedTeam=0,observedCareer=0;
static int observedRevision=0,stageRevision=0;
static wchar_t observedSelection[512]{};
static bool awaitingReload=false;
static bool sceneReady=false,careerWasActive=false;
static std::atomic_bool photoDirty{false};
static int careerSession=0,careerSessionTeam=0,observedEnabled=-1;
static std::atomic<uintptr_t> backgroundViewModel{0};
static uint32_t observedEpoch=0,stageEpoch=0;
static uint64_t lastRouteComplete=0;
static bool uiRegistered=false;
static std::atomic<DWORD> backgroundOwnerThread{0};
static std::atomic<uint64_t> routedRoomCover{0};
static uint64_t lastRoomCoverRefresh=0;
static void frontendUiTick();
static uint32_t drawnRequest=0;
static frontend_stadium::ProfileReloadProgress reloadProgress;
static frontend_stadium::ReloadScopeGuard reloadScopeGuard;
static thread_local bool frontendDispatch=false;
static frontend_stadium::PlayerScene playerScene;
static bool bootComplete=false;
static frontend_stadium::PageKind previousPage=frontend_stadium::PageKind::Transition;
static uint32_t requestsAtPost=0;
static DWORD publishedTeam=0;static int publishedPhase=0;
static thread_local bool frontendCrowdLoad=false;
struct ExtraCall {uintptr_t source,target,offset;LONG before=0,after=0;};
static ExtraCall extraCalls[]={{0x436311b,0x4361970,0x140},{0x5cbd1b7,0x5cbb330,0x180},{0x5cbb3cb,0x5cbe930,0x1c0},
    {0x3a19f7f,0x44d8ce0,0x240}};
using Prepare=void(__fastcall*)(void*,const void*);
using CareerState=BOOL(WINAPI*)(LONG*,LONG*);
extern "C" {__declspec(dllexport) struct FrontendStatus {
    uint32_t version=11,size=sizeof(FrontendStatus),ready=0;
    uint32_t team=0,slot=0,career=0,requests=0,applied=0,error=0,photoHidden=0;
    char previousImage[64]{};
} FrontendStadiumStatus;}

static bool read(uintptr_t address,void* output,size_t size){
    if(address<0x10000)return false;
    __try {std::memcpy(output,reinterpret_cast<void*>(address),size);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t address){T value{};read(address,&value,sizeof value);return value;}
static void log(const char* event,int team=0,int detail=0){
    FILE* file=nullptr;if(_wfopen_s(&file,logPath,L"ab")||!file)return;
    std::fprintf(file,"tick=%llu pid=%lu %s team=%d detail=%d\r\n",GetTickCount64(),GetCurrentProcessId(),event,team,detail);
    std::fclose(file);
}
static int setting(const wchar_t* key,int fallback){return static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",key,fallback,config));}
static uintptr_t nativeCommands(int* state);
static frontend_stadium::PageKind currentPage(){
 const auto page=frontend_stadium::pageKind(image,read);
 if(page==frontend_stadium::PageKind::ManagerPreferences){
  typedef BOOL (WINAPI* Active)(void);auto module=GetModuleHandleW(L"club_browser.dll");auto active=module?reinterpret_cast<Active>(GetProcAddress(module,"Fifa16ManagerFaceVisible")):nullptr;
  if(active&&active())return frontend_stadium::PageKind::ManagerFace;
 }
 return page;
}
static bool stadiumEnabled(frontend_stadium::PageKind page){
    if(page==frontend_stadium::PageKind::IdlePanorama&&activeCareerClub(image,read)>0)return true;
    return frontend_stadium::enabledForPage(setting(L"enabled",0)!=0,page);
}
static bool stadiumEnabled(){return stadiumEnabled(currentPage());}
static void selection(int team,wchar_t* output,DWORD size){
    if(careerWasActive){
        if(static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium_career",L"session",0,config))==careerSession&&
           static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium_career",L"team",0,config))==team){
            GetPrivateProfileStringW(L"frontend_stadium_career",L"selection",L"auto",output,size,config);
        }else wcsncpy_s(output,size,L"auto",_TRUNCATE);
        return;
    }
    wchar_t key[32]{};_snwprintf_s(key,_countof(key),_TRUNCATE,L"%d",team);
    GetPrivateProfileStringW(L"frontend_stadium_clubs",key,L"auto",output,size,config);
}
static void publishState(int phase,int team,int career,int slot,int error){
    publishedTeam=static_cast<DWORD>(team);publishedPhase=phase;
    sceneReady=phase==3&&activeMode!=0;photoDirty=true;
    wchar_t body[512]{};
    const int length=_snwprintf_s(body,_countof(body),_TRUNCATE,
        L"[frontend_stadium]\r\npid=%lu\r\nphase=%d\r\nteam=%d\r\ncareer=%d\r\nsession=%d\r\nslot=%d\r\nerror=%d\r\nrequest=%ld\r\n",
        GetCurrentProcessId(),phase,team,career,careerSession,slot,error,requestNumber);
    wchar_t temporary[MAX_PATH]{};_snwprintf_s(temporary,_countof(temporary),_TRUNCATE,L"%ls.tmp",liveIni);
    FILE* file=nullptr;if(length<=0||_wfopen_s(&file,temporary,L"wb")||!file)return;
    const wchar_t bom=0xfeff;std::fwrite(&bom,2,1,file);std::fwrite(body,2,static_cast<size_t>(length),file);std::fclose(file);
    MoveFileExW(temporary,liveIni,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
}
static int club(bool* career){
    *career=false;
    bool resolved=false;
    const int careerTeam=activeCareerClub(image,read,&resolved);
    if(careerTeam){*career=true;return careerTeam;}
    // A transient failed read is not a request to load the favourite club.
    // A verified career exit still resolves to the normal profile selection.
    if(!resolved&&careerWasActive&&careerSessionTeam>0){*career=true;return careerSessionTeam;}
    const unsigned char signature[]={0x48,0x89,0x5c,0x24,0x08,0x57,0x48,0x83,0xec,0x20};
    unsigned char actual[sizeof signature]{};
    if(!read(image+0x400b470,actual,sizeof actual)||std::memcmp(signature,actual,sizeof actual))return 0;
    __try{return reinterpret_cast<int(__fastcall*)()>(image+0x400b470)();}
    __except(EXCEPTION_EXECUTE_HANDLER){return 0;}
}
static int activeSlot(){
    const auto stadium=get<uintptr_t>(image+0x3504648);
    const auto table=get<uintptr_t>(stadium+0x20);
    return get<int>(table+0xa90+0x18);
}
static void updateCareerContext(bool career,int team){
    if(career&&(!careerWasActive||team!=careerSessionTeam)){
        careerSession=static_cast<int>(GetTickCount64()&0x7fffffff);
        if(!careerSession)careerSession=1;
        careerSessionTeam=team;
    }
    careerWasActive=career;
}
struct PublishedUiContext {DWORD schema,size,sequence,pid;uintptr_t service,vtable,registry;DWORD epoch,thread;};
static PublishedUiContext uiContext(){
    PublishedUiContext a{},b{};const auto host=GetModuleHandleW(L"dinput8.dll");
    const auto address=reinterpret_cast<uintptr_t>(host?GetProcAddress(host,"Fifa16CareerContextRead"):nullptr);
    if(!read(address,&a,sizeof a)||a.schema!=1||a.size!=sizeof a||a.sequence&1||a.pid!=GetCurrentProcessId()||
       !read(address,&b,sizeof b)||std::memcmp(&a,&b,sizeof a))return {};
    return a;
}
static int activeCareerRole(){
    const auto scope=uiContext();if(!scope.service||get<uintptr_t>(scope.service)!=scope.vtable)return -1;
    int selected=get<int>(scope.service+0x14);if(selected<0||selected>=8)return -1;
    const auto context=get<uintptr_t>(scope.service+0x18)+uintptr_t(selected)*0x318;
    int role=-1;return read(context+0x18c,&role,sizeof role)?role:-1;
}
static bool backgroundCommandOwner(){
    return frontendDispatch&&backgroundOwnerThread.load()==GetCurrentThreadId();
}
static bool customActive(){return !stopping&&activeMode==1&&stadiumEnabled()&&activeSlot()==static_cast<int>(FrontendStadiumStatus.slot);}
static bool menuScene(){
    // The same predicate used by StadiumPanDP::IsScreenTriggeredInMenus.
    const auto owner=reinterpret_cast<void*(__fastcall*)()>(image+0x4036820)();
    if(!owner)return false;
    const int mode=reinterpret_cast<int(__fastcall*)(void*)>(image+0x470ce20)(owner);
    return mode<4||mode>7;
}
static DWORD selectedRoomClub(frontend_stadium::PageKind page){
    if(stopping||!installed)return 0;
    wchar_t value[32]{};
    GetPrivateProfileStringW(L"frontend_stadium",page==frontend_stadium::PageKind::IdlePanorama?L"idle_background":L"background_mode",
        L"stadium",value,_countof(value),config);
    if(std::wcscmp(value,L"dressing_room"))return 0;
    bool resolved=false;const int team=activeCareerClub(image,read,&resolved);
    return career_background::wantsRoom(career_background::Mode::DressingRoom,true,resolved,
        team>0?static_cast<unsigned>(team):0,activeCareerRole(),menuScene())?static_cast<DWORD>(team):0;
}
static DWORD roomBackgroundClub(frontend_stadium::PageKind page){
    using Page=frontend_stadium::PageKind;
    return page==Page::Hub||page==Page::IdlePanorama?selectedRoomClub(page):0;
}
static bool roomCoverSelected(frontend_stadium::PageKind page){
    if(stopping||!installed||!frontend_stadium::roomCoverPage(page))return false;
    wchar_t value[32]{};
    GetPrivateProfileStringW(L"frontend_stadium",page==frontend_stadium::PageKind::IdlePanorama?L"idle_background":L"background_mode",
        L"stadium",value,_countof(value),config);
    return frontend_stadium::roomCoverSelected(page,!std::wcscmp(value,L"dressing_room"),activeCareerRole(),menuScene());
}
static DWORD roomCoverClub(frontend_stadium::PageKind page){
    return frontend_stadium::roomCoverPage(page)?selectedRoomClub(page):0;
}
static bool roomPanoramaReady(DWORD team){
    int nativeState=-1;nativeCommands(&nativeState);
    const bool settled=!awaitingReload&&!stageRequest&&(nativeState==0||nativeState==12)&&GetTickCount64()-lastRouteComplete>=750;
    const bool validRoute=activeMode&&stadiumEnabled(currentPage())&&activeSlot()==static_cast<int>(FrontendStadiumStatus.slot);
    return frontend_stadium::roomPanoramaReady(team,settled,FrontendStadiumStatus.team,sceneReady,validRoute);
}
static int __fastcall drawHook(void* state,void* draw,int bucket,int pass,bool force,bool animated,bool generic){
    using Dispatch=int(__fastcall*)(void*,void*,int,int,bool,bool,bool);
    const auto original=reinterpret_cast<Dispatch>(image+0x4393a00);
    const int count=original(state,draw,bucket,pass,force,animated,generic);
    if(bucket==1&&count>0&&activeMode&&activeSlot()==static_cast<int>(FrontendStadiumStatus.slot))
        drawnRequest=FrontendStadiumStatus.requests;
    static uint32_t reported=0;
    if(bucket==1&&customActive()&&reported!=FrontendStadiumStatus.applied){
        reported=FrontendStadiumStatus.applied;log("MODELS_DISPATCHED",static_cast<int>(FrontendStadiumStatus.team),count);
    }
    return count;
}
static void __fastcall panHook(void* self,int stadium,void* output){
    reinterpret_cast<void(__fastcall*)(void*,int,void*)>(image+0x40d2c60)(self,stadium,output);
    if(!output||!menuScene())return;
    const auto page=currentPage();
    const auto roomClub=page==frontend_stadium::PageKind::IdlePanorama?roomBackgroundClub(page):0;
    if(roomClub){
        // Native provider strings are localized by FIFA. Use an ASCII marker;
        // the panorama APT supplies the accented label in its UTF-8 text path.
        const char label[]="SERVER16_DRESSING_ROOM";
        std::memset(output,0,256);std::memcpy(output,label,sizeof label);
        const int values[]={-1,0,static_cast<int>(roomClub),-1,-1};
        std::memcpy(static_cast<unsigned char*>(output)+0x100,values,sizeof values);
        return;
    }
    if(!customActive())return;
    wchar_t name[256]{};char utf8[256]{};
    wcsncpy_s(name,activeName,_TRUNCATE);
    if(!name[0]||!WideCharToMultiByte(CP_UTF8,0,name,-1,utf8,sizeof utf8,nullptr,nullptr))return;
    std::memset(output,0,256);std::memcpy(output,utf8,std::strlen(utf8));
    // The existing year slot carries a tagged attendance for our APT wrapper.
    // Ordinary stadiums retain FIFA's original provider and construction year.
    const int values[]={activeCapacity,10000000+(activeAttendance+1),static_cast<int>(FrontendStadiumStatus.team),-1,-1};
    std::memcpy(static_cast<unsigned char*>(output)+0x100,values,sizeof values);
    log("PAN_CUSTOM_INFO",static_cast<int>(FrontendStadiumStatus.team),stadium);
}
static void* __fastcall backgroundHook(void* self){
    const auto thread=GetCurrentThreadId();
    using RegisterFrontend=BOOL(WINAPI*)(void(*)());
    const auto host=GetModuleHandleW(L"dinput8.dll");
    const auto registerFrontend=reinterpret_cast<RegisterFrontend>(host?GetProcAddress(host,"Fifa16FrontendRegisterUiCallback"):nullptr);
    if(registerFrontend&&registerFrontend(frontendUiTick)){
        if(backgroundOwnerThread.exchange(thread)!=thread)log("FRONTEND_UI_OWNER",0,static_cast<int>(thread));
    }
    auto* provider=reinterpret_cast<void*(__fastcall*)(void*)>(image+0x40893e0)(self);
    backgroundViewModel=reinterpret_cast<uintptr_t>(self);
    const auto coverPage=currentPage();
    const auto roomClub=roomCoverClub(coverPage);
    if(provider&&roomCoverSelected(coverPage)){
        const bool ready=roomPanoramaReady(roomClub);
        frontend_stadium::routeRoomPhotograph(provider,reinterpret_cast<frontend_stadium::SetProviderString>(image+0x4c174d0),ready);
        const auto stamp=frontend_stadium::roomCoverStamp(roomClub,ready);
        if(routedRoomCover.exchange(stamp)!=stamp)log(ready?"ROOM_PANORAMA_VISIBLE":"ROOM_STADIUM_COVER_HELD",static_cast<int>(roomClub),0);
        photoDirty=false;
        return provider;
    }
    if(provider)routedRoomCover=0;
    const auto slot=FrontendStadiumStatus.slot;
    const auto page=currentPage();
    const bool menuPage=frontend_stadium::isBackgroundPage(page);
    int nativeState=-1;const auto nativeService=nativeCommands(&nativeState);
    const bool nativeBusy=nativeService&&nativeState!=0&&nativeState!=12;
    const bool pending=awaitingReload||stageRequest!=0||nativeBusy;
    const bool stadiumSettled=frontend_stadium::photographRefreshReady(pending,sceneReady,nativeState,GetTickCount64()-lastRouteComplete);
    const bool validRoute=stadiumSettled&&activeMode&&stadiumEnabled(page)&&activeSlot()==static_cast<int>(slot);
    const bool transition=page==frontend_stadium::PageKind::Transition;
    const auto photograph=frontend_stadium::preservesPhotograph(page)?frontend_stadium::Photograph::Friends:frontend_stadium::photographPolicy(menuPage,bootComplete,pending,sceneReady,validRoute,transition);
    if(provider&&!stopping&&photograph!=frontend_stadium::Photograph::Original){
        const auto text=get<uintptr_t>(reinterpret_cast<uintptr_t>(self)+0x168);
        char previous[64]{};
        if(read(text,previous,sizeof previous-1))std::memcpy(FrontendStadiumStatus.previousImage,previous,sizeof previous);
        // This native background component is also used while Career is
        // replacing the initial FIFA scene. Its 3D scene predicate can be
        // false for a frame during that handoff; gating the image route on it
        // restored BOOTFLOW after the custom stadium had already settled.
        if(photograph==frontend_stadium::Photograph::Stadium&&frontend_stadium::routePhotograph(provider,
            reinterpret_cast<frontend_stadium::SetProviderString>(image+0x4c174d0),
            reinterpret_cast<const char*>(image+0x21c3fe8))){
            photoDirty=false;
            FrontendStadiumStatus.photoHidden++;
            log("PHOTO_PARAM_REQUEST",static_cast<int>(FrontendStadiumStatus.team),static_cast<int>(slot));
        }else{
            reinterpret_cast<frontend_stadium::SetProviderString>(image+0x4c174d0)(provider,"Param","BOOTFLOW");
            if(transition){int previousStadium=0;sscanf_s(previous,"%d",&previousStadium);log("PHOTO_TRANSITION_FALLBACK",static_cast<int>(FrontendStadiumStatus.team),previousStadium);}
        }
    }
    return provider;
}
static void refreshPhotograph(){
    const auto page=currentPage();
    if(GetCurrentThreadId()!=backgroundOwnerThread.load())return;
    const auto roomClub=roomCoverClub(page);
    const bool roomSelected=roomCoverSelected(page);
    const bool roomChanged=roomSelected&&routedRoomCover.load()!=frontend_stadium::roomCoverStamp(roomClub,roomPanoramaReady(roomClub));
    if(!photoDirty&&!roomChanged)return;
    if(!frontend_stadium::isBackgroundPage(page))return;
    // Never manufacture another provider while native stadium loading is active.
    int state=-1;nativeCommands(&state);
    if(roomSelected){
        // Keep the normal panorama visible while the room worker prepares.
        // Only a native stadium reload needs the BOOTFLOW photograph.
        if(!roomChanged){photoDirty=false;return;}
        if(awaitingReload||stageRequest||(state!=0&&state!=12)||GetTickCount64()-lastRouteComplete<750)return;
        if(lastRoomCoverRefresh&&GetTickCount64()-lastRoomCoverRefresh<500)return;
    }else if(!frontend_stadium::photographRefreshReady(awaitingReload||stageRequest,sceneReady,state,GetTickCount64()-lastRouteComplete))return;
    const auto self=backgroundViewModel.load();
    const auto vtable=get<uintptr_t>(self);
    // Publish through the current native view model, without retaining a DP.
    // Its factory and owning service must still match the live registration.
    if(!self||get<uintptr_t>(vtable+0x38)!=image+0x408d1d0||!get<uintptr_t>(self+8))return;
    // GameFlow::Render is not the UI provider owner thread. A synchronous
    // 4c15b20 call here raced StatisticsData in the native string pool
    // (captured 3a69c96 -> 4c15c40 -> refreshPhotograph crash). Only enqueue;
    // native background requests still apply backgroundHook during boot.
    using Queue=BOOL(WINAPI*)(void*,void*);
    const auto host=GetModuleHandleW(L"dinput8.dll");
    const auto queue=reinterpret_cast<Queue>(host?GetProcAddress(host,"Fifa16CareerQueueBackgroundRefresh"):nullptr);
    if(!queue||!queue(reinterpret_cast<void*>(self),reinterpret_cast<void*>(vtable)))return;
    if(roomSelected)lastRoomCoverRefresh=GetTickCount64();
    photoDirty=false;
    log("PHOTO_REFRESH_QUEUED",static_cast<int>(FrontendStadiumStatus.team),static_cast<int>(GetCurrentThreadId()));
}
static DWORD prepare(int team,int slot,int career,int session){
    wchar_t command[2048]{};
    _snwprintf_s(command,_countof(command),_TRUNCATE,L"\"%ls\" --game-root \"%ls\" --team %d --slot %d %ls --session %d",
        helper,game,team,slot,career?L"--career":L"",session);
    STARTUPINFOW startup{};startup.cb=sizeof startup;startup.dwFlags=STARTF_USESHOWWINDOW;startup.wShowWindow=SW_HIDE;
    PROCESS_INFORMATION process{};
    HANDLE job=CreateJobObjectW(nullptr,nullptr);
    if(!job)return 5;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if(!SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof limits)){CloseHandle(job);return 6;}
    if(!CreateProcessW(helper,command,nullptr,nullptr,FALSE,CREATE_NO_WINDOW|CREATE_SUSPENDED,nullptr,game,&startup,&process)){
        const DWORD result=1000+GetLastError();CloseHandle(job);return result;
    }
    if(!AssignProcessToJobObject(job,process.hProcess)){
        TerminateProcess(process.hProcess,7);CloseHandle(process.hThread);CloseHandle(process.hProcess);CloseHandle(job);return 7;
    }
    if(ResumeThread(process.hThread)==static_cast<DWORD>(-1)){
        CloseHandle(process.hThread);CloseHandle(process.hProcess);CloseHandle(job);return 8;
    }
    CloseHandle(process.hThread);
    const DWORD wait=WaitForSingleObject(process.hProcess,45000);
    DWORD result=0;
    if(wait!=WAIT_OBJECT_0){TerminateProcess(process.hProcess,3);result=3;}
    else if(!GetExitCodeProcess(process.hProcess,&result))result=4;
    CloseHandle(process.hProcess);
    CloseHandle(job);
    return result;
}
static void __fastcall loadHook(void* self,const void* context){
    const auto original=reinterpret_cast<Prepare>(image+0x4361970);
    alignas(16) std::array<unsigned char,0x110> copy{};
    if(stopping||!activeMode||!stadiumEnabled()||!read(reinterpret_cast<uintptr_t>(context),copy.data(),copy.size())){
        original(self,context);return;
    }
    const int slot=static_cast<int>(FrontendStadiumStatus.slot);
    {
        AcquireSRWLockShared(&gate);
        const bool restored=awaitingReload&&playerScene.restore(copy,static_cast<int>(FrontendStadiumStatus.team),uiContext().epoch,activeCareerRole());
        ReleaseSRWLockShared(&gate);
        if(restored)log("PLAYER_CAREER_LOAD_CONTEXT_PRESERVED",static_cast<int>(FrontendStadiumStatus.team),frontend_stadium::PlayerScene::integer(copy,0xdc));
    }
    frontend_stadium::routeContext(copy,slot);
    log("LOAD_SAME_ROUTE",static_cast<int>(FrontendStadiumStatus.team),slot);
    original(self,copy.data());
}
static void __fastcall crowdLoadHook(void* self){
    const auto crowd=get<uintptr_t>(image+0x3504748);
    const auto state=get<uintptr_t>(crowd+0x10);
    const bool previous=frontendCrowdLoad;
    const auto wrapper=get<uintptr_t>(state+0x90);
    frontendCrowdLoad=!stopping&&activeMode==1&&reinterpret_cast<uintptr_t>(self)==get<uintptr_t>(wrapper);
    reinterpret_cast<void(__fastcall*)(void*)>(image+0x5cbb330)(self);
    frontendCrowdLoad=previous;
}
static void* __fastcall placementOpenHook(const char* path,void* options){
    const auto original=reinterpret_cast<void*(__fastcall*)(const char*,void*)>(image+0x5cbe930);
    if(frontendCrowdLoad&&activeCrowd[0]){
        log("CROWD_ROUTE",static_cast<int>(FrontendStadiumStatus.team),static_cast<int>(FrontendStadiumStatus.slot));
        return original(activeCrowd,options);
    }
    return original(path,options);
}
static uintptr_t nativeCommands(int* state=nullptr){
    const auto service=get<uintptr_t>(image+0x34ea0e8);
    const auto commands=get<uintptr_t>(service+0x68),items=get<uintptr_t>(commands);
    if(!service||!commands||!items)return 0;
    for(unsigned i=0;i<3;++i){
        const auto object=get<uintptr_t>(items+8*i),vtable=get<uintptr_t>(object);
        if(!object||get<uintptr_t>(vtable+8)!=image+0x3d8e370)continue;
        if(state)*state=get<int>(object+0x30);
        return commands;
    }
    return 0;
}
static frontend_stadium::ReloadScope reloadScope(int* nativeState=nullptr){
    frontend_stadium::ReloadScope scope;
    if(!backgroundCommandOwner())return scope;
    scope.frontendCallback=true;scope.ownerThread=GetCurrentThreadId();
    scope.page=currentPage();scope.view=frontend_stadium::pageView(image,read);
    if(!frontend_stadium::isBackgroundPage(scope.page)||!scope.view)return {};
    scope.background=backgroundViewModel.load();
    const auto vtable=get<uintptr_t>(scope.background);
    if(!scope.background||get<uintptr_t>(vtable+0x38)!=image+0x408d1d0)return {};
    scope.backgroundRegistry=get<uintptr_t>(scope.background+8);
    scope.commands=nativeCommands(nativeState);
    const auto before=uiContext();
    bool resolved=false;const auto team=activeCareerClub(image,read,&resolved);
    if(!resolved)return {}; // A loading/retiring career is not the favourite club.
    scope.resolved=true;scope.career=team>0;
    if(scope.career){
        const auto after=uiContext();
        if(std::memcmp(&before,&after,sizeof before))return {};
        scope.epoch=after.epoch;scope.careerService=after.service;
        scope.careerRegistry=after.registry;scope.careerThread=after.thread;
        scope.team=static_cast<uint32_t>(team);
    }else{
        bool career=false;const auto favourite=club(&career);
        if(career||favourite<=0)return {};
        scope.team=static_cast<uint32_t>(favourite);
    }
    if(scope.background!=backgroundViewModel.load()||get<uintptr_t>(scope.background)!=vtable
        ||get<uintptr_t>(scope.background+8)!=scope.backgroundRegistry
        ||!backgroundCommandOwner())return {};
    return scope;
}
static void logReloadScope(const char* event,const frontend_stadium::ReloadScope& scope,int state){
    FILE* file=nullptr;if(_wfopen_s(&file,logPath,L"ab")||!file)return;
    std::fprintf(file,"tick=%llu pid=%lu %s team=%u epoch=%u thread=%lu frontend_owner=%u career_owner=%u view=%llx registry=%llx state=%d\r\n",
        GetTickCount64(),GetCurrentProcessId(),event,scope.team,scope.epoch,GetCurrentThreadId(),
        scope.ownerThread,scope.careerThread,static_cast<unsigned long long>(scope.view),
        static_cast<unsigned long long>(scope.backgroundRegistry),state);
    std::fclose(file);
}
static bool startNativeReload(const frontend_stadium::ReloadScope& expected){
    int state=-1;const auto current=reloadScope(&state);
    if(!frontend_stadium::canDispatchReload(expected,current,state))return false;
    // ReloadFEStadiumViewModel::evt_start_stadium_change (action 0x2787)
    // delegates to this native service command (40fac8a..40faca9).
    // Revalidate after releasing the staging lock. BackgroundDP's genuine
    // frontend callback may differ from the StatisticsData owner thread.
    const auto commands=current.commands;
    const unsigned char signature[]={0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10};
    unsigned char actual[sizeof signature]{};
    if(!read(image+0x3d8b8a0,actual,sizeof actual)||std::memcmp(actual,signature,sizeof actual))return false;
    logReloadScope("NATIVE_RELOAD_DISPATCH",current,state);
    const bool accepted=frontend_stadium::requestProfileReload([&](int command,void* request){
        reinterpret_cast<void(__fastcall*)(void*,int,void*)>(image+0x3d8b8a0)(reinterpret_cast<void*>(commands),command,request);
    });
    log(accepted?"NATIVE_STADIUM_CHANGE_STARTED":"NATIVE_STADIUM_CHANGE_BUSY",static_cast<int>(FrontendStadiumStatus.team),accepted?1:0);
    return accepted;
}
static bool acknowledgeBackground(const frontend_stadium::ReloadScope& expected){
    int state=-1;const auto current=reloadScope(&state);
    if(!frontend_stadium::canDispatchReload(expected,current,state,true))return false;
    const auto commands=current.commands;
    // Command 0x1a -> FreeRoam::3d92c70 -> 3ddf8f0, the normal native
    // background-loaded callback. State 11 is BOOT and must never be bypassed.
    if(!commands||state!=14)return false;
    const unsigned char signature[]={0x56,0x48,0x83,0xec,0x40,0x8b,0x41,0x30};
    unsigned char actual[sizeof signature]{};
    if(!read(image+0x3d92c70,actual,sizeof actual)||std::memcmp(actual,signature,sizeof actual))return false;
    frontend_stadium::profileBackgroundReady([&](int command,void* request){
        reinterpret_cast<void(__fastcall*)(void*,int,void*)>(image+0x3d8b8a0)(reinterpret_cast<void*>(commands),command,request);
    });
    log("NATIVE_BACKGROUND_READY",stageTeam,state);
    return true;
}
static void failReload(int error){
    // A prepared job is terminal on failure. Retaining stageRequest here was
    // re-queuing the same job every frame after its retry limit expired.
    awaitingReload=false;
    reloadProgress.fail();
    InterlockedExchange(&stageRequest,0);InterlockedExchange(&stageComplete,0);
    FrontendStadiumStatus.error=static_cast<uint32_t>(error);
    publishState(-1,stageTeam,stageCareer,stageSlot,error);
    log("RELOAD_FAILED",stageTeam,error);
}
static void pollReload(){
    const auto now=GetTickCount64();
    if(!installed||stopping||!backgroundCommandOwner()||now-lastProbe<250)return;
    lastProbe=now;
    if(!TryAcquireSRWLockExclusive(&gate))return;
    if(!menuScene()){reloadScopeGuard.reset();ReleaseSRWLockExclusive(&gate);return;}
    const auto page=currentPage();
    const auto commandScope=reloadScope();
    const bool commandReady=reloadScopeGuard.observe(commandScope,now);
    const bool allowedPage=frontend_stadium::isBackgroundPage(page);
    const bool enabled=stadiumEnabled(page);
    if(frontend_stadium::refreshOnMenuReturn(previousPage,page,sceneReady,enabled))photoDirty=true;
    previousPage=page;
    if(allowedPage)bootComplete=true;
    if(!allowedPage&&!awaitingReload){ReleaseSRWLockExclusive(&gate);return;}
    bool career=stageCareer!=0;
    const int actualTeam=allowedPage?club(&career):careerSessionTeam;
    const int selected=page==frontend_stadium::PageKind::ClubBrowser?club_stadium_scope::selected():0;
    const int team=allowedPage?club_stadium_scope::target(actualTeam,selected):(stageTeam?stageTeam:static_cast<int>(FrontendStadiumStatus.team));
    const auto epoch=uiContext().epoch;
    const bool newCareer=career&&epoch&&epoch!=observedEpoch;
    const bool contextChanged=allowedPage&&(career!=careerWasActive||(career&&actualTeam!=careerSessionTeam)||newCareer);
    if(allowedPage)updateCareerContext(career,actualTeam);
    if(contextChanged){
        awaitingReload=false;observedTeam=0;
        InterlockedExchange(&stageRequest,0);InterlockedExchange(&stageComplete,0);
        sceneReady=false;photoDirty=true;
        // Background ViewModels can survive a save reload. Keep a weak address;
        // reloadScope validates its live factory/registry before every command.
        observedEpoch=career?epoch:0;
        if(!playerScene.matches(actualTeam,epoch,activeCareerRole()))playerScene.clear();
        if(newCareer){careerSession=static_cast<int>(now&0x7fffffff);log("CAREER_EPOCH_RESET",team,static_cast<int>(epoch));}
    }
    if(!enabled){
        if(observedEnabled!=0||contextChanged||observedTeam!=team){
            activeMode=0;awaitingReload=false;observedTeam=team;
            InterlockedExchange(&stageRequest,0);InterlockedExchange(&stageComplete,0);
            publishState(0,team,career?1:0,activeSlot(),0);
        }
        observedEnabled=0;ReleaseSRWLockExclusive(&gate);return;
    }
    if(observedEnabled!=1){observedTeam=0;observedEnabled=1;}
    if(awaitingReload){
        const auto object=get<uintptr_t>(image+0x3504648),state=get<uintptr_t>(object+0x20);
        if(FrontendStadiumStatus.requests>requestsAtPost&&activeSlot()==static_cast<int>(FrontendStadiumStatus.slot)&&get<unsigned char>(state+1)&&
           (!activeMode||drawnRequest==FrontendStadiumStatus.requests)){
            awaitingReload=false;lastRouteComplete=now;publishState(activeMode?3:4,static_cast<int>(FrontendStadiumStatus.team),static_cast<int>(FrontendStadiumStatus.career),activeSlot(),0);
            log("RELOAD_COMPLETE",static_cast<int>(FrontendStadiumStatus.team),activeSlot());
        }else if(now-waitSince>60000){
            failReload(20);
        }else if(FrontendStadiumStatus.requests==requestsAtPost){
            if(!commandReady){
                static LONG reported=0;
                if(reported!=stageRequest){reported=stageRequest;logReloadScope("NATIVE_RELOAD_WAIT_CONTEXT",commandScope,-1);}
                ReleaseSRWLockExclusive(&gate);return;
            }
            int nativeState=-1;nativeCommands(&nativeState);
            const auto step=reloadProgress.next(nativeState,stageRequest&&stageComplete==stageRequest,now);
            if(step==frontend_stadium::ReloadStep::Failed){failReload(22);}
            else if(step==frontend_stadium::ReloadStep::Start){
                ReleaseSRWLockExclusive(&gate);reloadProgress.started=startNativeReload(commandScope);return;
            }else if(step==frontend_stadium::ReloadStep::BackgroundReady){
                // The FIFA Friends cover was already requested before staging.
                // A cached/hidden image need not fire another UI callback.
                // Resume the standard native loader, outside our staging lock.
                ReleaseSRWLockExclusive(&gate);
                if(!acknowledgeBackground(commandScope)){
                    reloadProgress.backgroundSent=false;
                    log("NATIVE_BACKGROUND_READY_SKIPPED",team);
                }
                return;
            }
        }
        ReleaseSRWLockExclusive(&gate);return;
    }
    if(!allowedPage){ReleaseSRWLockExclusive(&gate);return;}
    const int revision=setting(L"reload_revision",0);
    wchar_t chosen[512]{};selection(team,chosen,_countof(chosen));
    if(team>0&&(frontend_stadium::forcesStadium(page)||setting(career?L"career":L"favorite_team",1))&&
       (team!=observedTeam||static_cast<int>(career)!=observedCareer||revision!=observedRevision||std::wcscmp(chosen,observedSelection))){
        observedTeam=stageTeam=team;observedCareer=stageCareer=career?1:0;
        observedRevision=stageRevision=revision;
        wcsncpy_s(observedSelection,chosen,_TRUNCATE);wcsncpy_s(stageSelection,chosen,_TRUNCATE);
        stageSlot=activeSlot()==176?261:176;
        stageEpoch=career?epoch:0;
        reloadProgress.reset(now);
        InterlockedExchange(&stageRequest,++requestNumber);
        publishState(1,team,stageCareer,stageSlot,0);log("RELOAD_REQUEST",team,stageSlot);
    }
    if(stageRequest&&stageComplete==stageRequest&&!reloadProgress.terminal){
        if(stageError){
            failReload(static_cast<int>(stageError));
        }else{
            requestsAtPost=FrontendStadiumStatus.requests;
            awaitingReload=true;waitSince=now;
            publishState(2,stageTeam,stageCareer,stageSlot,0);log("NATIVE_RELOAD_READY",stageTeam,stageSlot);
        }
    }
    ReleaseSRWLockExclusive(&gate);
}
static void frontendUiTick(){
    if(stopping||frontendDispatch||GetCurrentThreadId()!=backgroundOwnerThread.load())return;
    struct DispatchScope {DispatchScope(){frontendDispatch=true;}~DispatchScope(){frontendDispatch=false;}} dispatch;
    // Observe gaps as well: the same FluxHub address may belong to a new save.
    pollReload();
    refreshPhotograph();
}
static void stadiumUiTick(){
    // Compatible with the host registration, but StatisticsData callbacks do
    // not allocate background UI values. frontendUiTick owns those commands.
    if(stopping)return;
}
static void renderPoll(){
    bool career=false;club(&career);
    if(uiRegistered||career||careerWasActive){
        using Register=BOOL(WINAPI*)(void(*)());
        const auto host=GetModuleHandleW(L"dinput8.dll");
        const auto fn=reinterpret_cast<Register>(host?GetProcAddress(host,"Fifa16CareerRegisterStadiumUiCallback"):nullptr);
        // Registration only. backgroundHook separately registers the actual
        // frontend owner, for menus and career alike.
        if(fn)uiRegistered=fn(stadiumUiTick)!=FALSE;
        return;
    }
    // Never enter the native UI allocator from the render branch, even boot.
}
static void __fastcall frameHook(void* self,void* a,void* b,void* c){
    reinterpret_cast<void(__fastcall*)(void*,void*,void*,void*)>(image+0x4361d70)(self,a,b,c);
    renderPoll();
}
static void* __fastcall sceneFrameHook(){
    // GameFlow::Render selects one of two branches. The boot FE branch
    // stops running once a 3D scene exists; this call covers the scene branch.
    // Career rendering only registers work for the verified UI owner.
    static bool reported=false;
    if(!reported){reported=true;log("SCENE_MONITOR_ACTIVE");}
    renderPoll();
    return reinterpret_cast<void*(__fastcall*)()>(image+0x44d8ce0)();
}
static void __fastcall hook(void* self,const void* context){
    const auto original=reinterpret_cast<Prepare>(image+kPrepare);
    const auto page=currentPage();
    const bool forced=frontend_stadium::forcesStadium(page);
    if(stopping||!stadiumEnabled(page)){activeMode=0;sceneReady=false;photoDirty=true;original(self,context);return;}
    bool career=false;const int actualTeam=club(&career);
    updateCareerContext(career,actualTeam);
    const int team=club_stadium_scope::target(actualTeam,page==frontend_stadium::PageKind::ClubBrowser?club_stadium_scope::selected():0);
    if(team<=0||team>2000000||(!forced&&!setting(career?L"career":L"favorite_team",1))){activeMode=0;original(self,context);return;}
    alignas(16) std::array<unsigned char,0x110> copy{};
    if(!read(reinterpret_cast<uintptr_t>(context),copy.data(),copy.size())){activeMode=0;original(self,context);return;}
    AcquireSRWLockExclusive(&gate);
    const int current=activeSlot();
    const int slot=current==176?261:176;
    FrontendStadiumStatus.requests++;
    FrontendStadiumStatus.team=static_cast<uint32_t>(team);FrontendStadiumStatus.career=career?1u:0u;
    log("PREPARE",team,slot);
    wchar_t chosen[512]{};selection(team,chosen,_countof(chosen));
    const int revision=setting(L"reload_revision",0);
    const auto epoch=uiContext().epoch;
    const int role=career?activeCareerRole():-1;
    if(awaitingReload){
        if(playerScene.restore(copy,team,epoch,role))log("PLAYER_CAREER_PREPARE_CONTEXT_PRESERVED",team,frontend_stadium::PlayerScene::integer(copy,0xdc));
    }else playerScene.capture(copy,team,epoch,role);
    const bool staged=stageRequest&&stageComplete==stageRequest&&stageTeam==team&&stageCareer==static_cast<int>(career)&&stageRevision==revision&&!std::wcscmp(chosen,stageSelection)&&frontend_stadium::sameCareerRoute(career,stageEpoch,epoch);
    // Opening the panorama can request the FE scene again. Reuse the route
    // that is already loaded for this club/choice; do not briefly replace it
    // with the native favourite/profile ground while restaging identical data.
    const int previousMode=activeMode;
    const bool retained=sceneReady&&previousMode&&observedTeam==team&&observedCareer==static_cast<int>(career)
        &&observedRevision==revision&&!std::wcscmp(chosen,observedSelection)&&frontend_stadium::sameCareerRoute(career,observedEpoch,epoch);
    // Never run an extractor or wait on its process on FIFA's render thread.
    // Keep the original scene until pollReload has prepared an async route.
    if(!staged&&!retained){
        activeMode=0;sceneReady=false;photoDirty=true;observedTeam=0;
        ReleaseSRWLockExclusive(&gate);
        log("PREPARE_DEFERRED_NATIVE_SCENE",team,slot);original(self,context);return;
    }
    const DWORD result=retained?0:stageError;
    observedTeam=team;observedCareer=career?1:0;wcsncpy_s(observedSelection,chosen,_TRUNCATE);
    observedRevision=revision;
    observedEnabled=1;
    FrontendStadiumStatus.error=result;
    activeMode=0;
    const int mode=retained?previousMode:stageMode;
    activeCrowd[0]=0;activeName[0]=0;activeCapacity=0;activeAttendance=-1;
    if(!result&&mode){
        // Only the FE stadium fields change in this private context copy.
        // Home/away match teams, fixture stadium and save data retain their values.
        const int selected=static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",L"slot",slot,routeIni));
        frontend_stadium::routeContext(copy,selected);
        FrontendStadiumStatus.slot=static_cast<uint32_t>(selected);activeMode=mode;
        GetPrivateProfileStringW(L"frontend_stadium",L"name",L"",activeName,_countof(activeName),routeIni);
        wchar_t capacity[32]{},attendance[32]{};
        GetPrivateProfileStringW(L"frontend_stadium",L"capacity",L"",capacity,_countof(capacity),routeIni);
        GetPrivateProfileStringW(L"frontend_stadium",L"attendance",L"",attendance,_countof(attendance),routeIni);
        activeCapacity=frontend_stadium::metadataCount(capacity,0);
        activeAttendance=frontend_stadium::metadataCount(attendance,-1);
        if(activeCapacity<0||activeCapacity>2000000)activeCapacity=0;
        if(activeAttendance<0||activeAttendance>2000000||(activeCapacity>0&&activeAttendance>activeCapacity))activeAttendance=-1;
        wchar_t crowd[MAX_PATH]{};GetPrivateProfileStringW(L"frontend_stadium",L"crowd",L"",crowd,_countof(crowd),routeIni);
        WideCharToMultiByte(CP_UTF8,0,crowd,-1,activeCrowd,sizeof activeCrowd,nullptr,nullptr);
        FrontendStadiumStatus.applied++;log("ROUTE",team,slot);
    }else log("FALLBACK",team,static_cast<int>(result));
    if(!mode)FrontendStadiumStatus.slot=get<uint32_t>(reinterpret_cast<uintptr_t>(context)+0xe8);
    InterlockedExchange(&stageRequest,0);InterlockedExchange(&stageComplete,0);
    if(!awaitingReload&&!result){requestsAtPost=FrontendStadiumStatus.requests-1;awaitingReload=true;reloadProgress.started=true;waitSince=GetTickCount64();}
    publishState(result?-1:2,team,career?1:0,static_cast<int>(FrontendStadiumStatus.slot),static_cast<int>(result));
    ReleaseSRWLockExclusive(&gate);
    original(self,result||!mode?context:copy.data());
}
static bool exchangeCall(uintptr_t rva,LONG expected,LONG desired){
    auto* target=reinterpret_cast<volatile LONG*>(image+rva+1);
    if(reinterpret_cast<uintptr_t>(target)%4)return false;
    DWORD old=0;if(!VirtualProtect(const_cast<LONG*>(target),4,PAGE_EXECUTE_READWRITE,&old))return false;
    const LONG before=InterlockedCompareExchange(target,desired,expected);
    DWORD ignored=0;VirtualProtect(const_cast<LONG*>(target),4,old,&ignored);
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(image+rva),5);
    return before==expected;
}
static bool exchange(LONG expected,LONG desired){
    auto* target=reinterpret_cast<volatile LONG*>(image+kCall+1);
    DWORD old=0;if(!VirtualProtect(const_cast<LONG*>(target),4,PAGE_EXECUTE_READWRITE,&old))return false;
    const LONG before=InterlockedCompareExchange(target,desired,expected);
    DWORD ignored=0;VirtualProtect(const_cast<LONG*>(target),4,old,&ignored);
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(image+kCall),5);
    return before==expected;
}
static bool exchangePhoto(LONG64 expected,LONG64 desired){
    // The first displacement byte stays identical. The other three lie in
    // this aligned qword, together with five unchanged instruction bytes.
    auto* target=reinterpret_cast<volatile LONG64*>(image+0x408d208);
    DWORD old=0;if(!VirtualProtect(const_cast<LONG64*>(target),8,PAGE_EXECUTE_READWRITE,&old))return false;
    const auto before=InterlockedCompareExchange64(target,desired,expected);
    DWORD ignored=0;VirtualProtect(const_cast<LONG64*>(target),8,old,&ignored);
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(image+0x408d206),10);
    return before==expected;
}
static bool exchangeFrame(LONG64 expected,LONG64 desired){
    auto* target=reinterpret_cast<volatile LONG64*>(image+0x3a1a168);
    DWORD old=0;if(!VirtualProtect(const_cast<LONG64*>(target),8,PAGE_EXECUTE_READWRITE,&old))return false;
    const auto before=InterlockedCompareExchange64(target,desired,expected);
    DWORD ignored=0;VirtualProtect(const_cast<LONG64*>(target),8,old,&ignored);
    FlushInstructionCache(GetCurrentProcess(),reinterpret_cast<void*>(image+0x3a1a168),8);
    return before==expected;
}
static bool install(){
    const unsigned char call[]={0xe8,0xd0,0xb7,0xff,0xff};
    const unsigned char prologue[]={0x55,0x53,0x56,0x48,0x8d,0xac,0x24,0xd0,0xec,0xfe,0xff,0xb8,0x30,0x14,0x01,0x00};
    unsigned char actual[sizeof prologue]{};
    if(!read(image+kCall,actual,sizeof call)||std::memcmp(actual,call,sizeof call))return false;
    if(!read(image+kPrepare,actual,sizeof prologue)||std::memcmp(actual,prologue,sizeof prologue))return false;
    const unsigned char photoCall[]={0xe8,0xd5,0xc1,0xff,0xff};
    if(!read(image+0x408d206,actual,sizeof photoCall)||std::memcmp(actual,photoCall,sizeof photoCall))return false;
    const char parameter[]="Param";char field[sizeof parameter]{};
    if(!read(image+0x21c3fe8,field,sizeof field)||std::memcmp(field,parameter,sizeof field))return false;
    for(const auto& pair:std::array<std::array<uintptr_t,2>,2>{{{{0x40b5593,0x40d2c60}},{{0x43921af,0x4393a00}}}}){
        unsigned char bytes[5]{};
        if(!read(image+pair[0],bytes,5)||bytes[0]!=0xe8)return false;
        int32_t delta=0;std::memcpy(&delta,bytes+1,4);
        if(static_cast<intptr_t>(pair[0])+5+delta!=static_cast<intptr_t>(pair[1]))return false;
    }
    for(const auto& patch:extraCalls){
        unsigned char bytes[5]{};int32_t delta=0;
        if(!read(image+patch.source,bytes,5)||bytes[0]!=0xe8)return false;
        std::memcpy(&delta,bytes+1,4);
        if(static_cast<intptr_t>(patch.source)+5+delta!=static_cast<intptr_t>(patch.target))return false;
    }
    const unsigned char frame[]={0xe8,0x03,0x7c,0x94,0,0xe8,0x2e,0x80};
    if(!read(image+0x3a1a168,actual,sizeof frame)||std::memcmp(actual,frame,sizeof frame))return false;
    if(!relayReady){
        // Allocation granularity keeps the relay in reach of the original CALL.
        for(uintptr_t step=0x10000;step<0x70000000&&!relay;step+=0x10000){
            relay=VirtualAlloc(reinterpret_cast<void*>(image+step),4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
        }
        if(!relay)return false;
        unsigned char jump[14]={0xff,0x25,0,0,0,0};const auto destination=reinterpret_cast<uintptr_t>(&hook);
        std::memcpy(jump+6,&destination,8);std::memcpy(relay,jump,sizeof jump);
        const auto photoDestination=reinterpret_cast<uintptr_t>(&backgroundHook);
        std::memcpy(jump+6,&photoDestination,8);std::memcpy(static_cast<unsigned char*>(relay)+0xe0,jump,sizeof jump);
        const auto panDestination=reinterpret_cast<uintptr_t>(&panHook);
        std::memcpy(jump+6,&panDestination,8);std::memcpy(static_cast<unsigned char*>(relay)+0x100,jump,sizeof jump);
        const auto drawDestination=reinterpret_cast<uintptr_t>(&drawHook);
        std::memcpy(jump+6,&drawDestination,8);std::memcpy(static_cast<unsigned char*>(relay)+0x120,jump,sizeof jump);
        const uintptr_t destinations[]={reinterpret_cast<uintptr_t>(&loadHook),reinterpret_cast<uintptr_t>(&crowdLoadHook),reinterpret_cast<uintptr_t>(&placementOpenHook),reinterpret_cast<uintptr_t>(&frameHook),reinterpret_cast<uintptr_t>(&sceneFrameHook)};
        const uintptr_t offsets[]={0x140,0x180,0x1c0,0x200,0x240};
        for(size_t i=0;i<_countof(destinations);++i){
            std::memcpy(jump+6,destinations+i,8);std::memcpy(static_cast<unsigned char*>(relay)+offsets[i],jump,sizeof jump);
        }
        DWORD old=0;if(!VirtualProtect(relay,4096,PAGE_EXECUTE_READ,&old))return false;
        FlushInstructionCache(GetCurrentProcess(),relay,4096);relayReady=true;
    }
    originalDisplacement=get<LONG>(image+kCall+1);
    const auto delta=reinterpret_cast<intptr_t>(relay)-static_cast<intptr_t>(image+kCall+5);
    if(delta<INT32_MIN||delta>INT32_MAX)return false;
    ourDisplacement=static_cast<LONG>(delta);
    const auto photoDelta=reinterpret_cast<intptr_t>(relay)+0xe0-static_cast<intptr_t>(image+0x408d20b);
    if(photoDelta<INT32_MIN||photoDelta>INT32_MAX||(photoDelta&255)!=0xd5)return false;
    originalPhotoWord=get<LONG64>(image+0x408d208);
    const auto bytes=static_cast<uint32_t>(photoDelta)>>8;
    ourPhotoWord=(originalPhotoWord&~0xffffffLL)|bytes;
    originalPan=get<LONG>(image+0x40b5594);originalDraw=get<LONG>(image+0x43921b0);
    ourPan=static_cast<LONG>(reinterpret_cast<intptr_t>(relay)+0x100-static_cast<intptr_t>(image+0x40b5598));
    ourDraw=static_cast<LONG>(reinterpret_cast<intptr_t>(relay)+0x120-static_cast<intptr_t>(image+0x43921b4));
    for(auto& patch:extraCalls){
        patch.before=get<LONG>(image+patch.source+1);
        patch.after=static_cast<LONG>(reinterpret_cast<intptr_t>(relay)+patch.offset-static_cast<intptr_t>(image+patch.source+5));
    }
    originalFrame=get<LONG64>(image+0x3a1a168);ourFrame=originalFrame;
    const auto frameDelta=static_cast<LONG>(reinterpret_cast<intptr_t>(relay)+0x200-static_cast<intptr_t>(image+0x3a1a16d));
    std::memcpy(reinterpret_cast<unsigned char*>(&ourFrame)+1,&frameDelta,4);
    size_t patched=0;
    for(const auto& patch:extraCalls){if(!exchangeCall(patch.source,patch.before,patch.after))break;++patched;}
    if(patched!=_countof(extraCalls)||!exchangeFrame(originalFrame,ourFrame)){
        for(size_t i=0;i<patched;++i)exchangeCall(extraCalls[i].source,extraCalls[i].after,extraCalls[i].before);
        return false;
    }
    if(!exchangeCall(0x40b5593,originalPan,ourPan)){
        exchangeFrame(ourFrame,originalFrame);for(const auto& patch:extraCalls)exchangeCall(patch.source,patch.after,patch.before);return false;
    }
    if(!exchangeCall(0x43921af,originalDraw,ourDraw)){
        exchangeCall(0x40b5593,ourPan,originalPan);exchangeFrame(ourFrame,originalFrame);
        for(const auto& patch:extraCalls)exchangeCall(patch.source,patch.after,patch.before);return false;
    }
    if(!exchangePhoto(originalPhotoWord,ourPhotoWord)){
        exchangeCall(0x40b5593,ourPan,originalPan);exchangeCall(0x43921af,ourDraw,originalDraw);exchangeFrame(ourFrame,originalFrame);
        for(const auto& patch:extraCalls)exchangeCall(patch.source,patch.after,patch.before);return false;
    }
    if(exchange(originalDisplacement,ourDisplacement))return true;
    exchangePhoto(ourPhotoWord,originalPhotoWord);
    exchangeCall(0x40b5593,ourPan,originalPan);exchangeCall(0x43921af,ourDraw,originalDraw);exchangeFrame(ourFrame,originalFrame);
    for(const auto& patch:extraCalls)exchangeCall(patch.source,patch.after,patch.before);return false;
}
static DWORD WINAPI worker(void*){
    while(!stopping){
        if(!installed){
            if(install()){InterlockedExchange(&installed,1);FrontendStadiumStatus.ready=1;log("READY");}
            Sleep(500);continue;
        }
        if(TryAcquireSRWLockExclusive(&gate)){
            const LONG request=stageRequest;
            if(request&&stageComplete!=request){
                const int team=stageTeam,slot=stageSlot,career=stageCareer,session=careerSession;
                ReleaseSRWLockExclusive(&gate);
                log("PREPARE_ASYNC",team,slot);
                const DWORD error=prepare(team,slot,career,session);
                const int mode=error?0:static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",L"mode",0,routeIni));
                AcquireSRWLockExclusive(&gate);
                if(stageRequest==request&&stageTeam==team&&stageSlot==slot&&stageCareer==career&&careerSession==session){
                    stageError=error;stageMode=mode;InterlockedExchange(&stageComplete,request);
                    log("PREPARE_ASYNC_COMPLETE",team,static_cast<int>(error));
                }else log("PREPARE_STALE_DISCARDED",team,static_cast<int>(error));
            }
            ReleaseSRWLockExclusive(&gate);
        }
        Sleep(100);
    }
    return 0;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16FrontendStadiumView(DWORD* team,int* phase){
    if(!team||!phase||stopping||!installed||!TryAcquireSRWLockShared(&gate))return FALSE;
    *team=publishedTeam;*phase=publishedPhase;ReleaseSRWLockShared(&gate);return TRUE;
}
extern "C" __declspec(dllexport) DWORD WINAPI Fifa16FrontendRoomBackgroundClub(){
    return roomBackgroundClub(currentPage());
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16FrontendStadiumName(DWORD team,wchar_t* text,DWORD capacity){
    if(!text||capacity<2||capacity>1024||stopping||!installed||!TryAcquireSRWLockShared(&gate))return FALSE;
    const bool matches=team==FrontendStadiumStatus.team&&publishedPhase==3&&activeName[0];
    if(matches)wcsncpy_s(text,capacity,activeName,_TRUNCATE);
    ReleaseSRWLockShared(&gate);return matches?TRUE:FALSE;
}
extern "C" __declspec(dllexport) unsigned WINAPI Fifa16ModGetApiVersion(){return 1;}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char*){
    if(InterlockedCompareExchange(&started,1,0))return TRUE;
    image=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    if(get<uint16_t>(image)!=0x5a4d||get<uint32_t>(image+get<int32_t>(image+0x3c)+8)!=0x577de45c){started=0;return FALSE;}
    if(!GetModuleFileNameW(nullptr,game,MAX_PATH))return FALSE;
    auto* slash=wcsrchr(game,L'\\');if(!slash)return FALSE;*slash=0;
    _snwprintf_s(config,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\config\\frontend_stadium.ini",game);
    _snwprintf_s(logPath,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\logs\\frontend_stadium.log",game);
    _snwprintf_s(helper,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\tools\\frontend_stadium_prepare.exe",game);
    _snwprintf_s(routeIni,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\runtime\\frontend_stadium_route.ini",game);
    _snwprintf_s(liveIni,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\runtime\\frontend_stadium_live.ini",game);
    if(GetFileAttributesW(helper)==INVALID_FILE_ATTRIBUTES){log("MISSING_HELPER");started=0;return FALSE;}
    HMODULE pin=nullptr;
    if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&image),&pin))return FALSE;
    HANDLE thread=CreateThread(nullptr,0,&worker,nullptr,0,nullptr);
    if(!thread){started=0;return FALSE;}CloseHandle(thread);log("START");return TRUE;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStop(){
    InterlockedExchange(&stopping,1);if(installed){exchange(ourDisplacement,originalDisplacement);exchangePhoto(ourPhotoWord,originalPhotoWord);exchangeCall(0x40b5593,ourPan,originalPan);exchangeCall(0x43921af,ourDraw,originalDraw);exchangeFrame(ourFrame,originalFrame);for(const auto& patch:extraCalls)exchangeCall(patch.source,patch.after,patch.before);}
    FrontendStadiumStatus.ready=0;return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID){
    if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);
    return TRUE;
}
