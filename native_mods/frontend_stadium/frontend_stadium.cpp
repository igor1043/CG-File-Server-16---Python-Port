#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <array>
#include "background_provider.h"
#include "frontend_visibility.h"
#include "career_profile.h"
#include "scene_context.h"
#include "menu_page.h"
#include "profile_reload.h"

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
static volatile LONG stageRequest=0,stageComplete=0;
static int stageTeam=0,stageCareer=0,stageSlot=0,stageMode=0;
static DWORD stageError=0;
static uint64_t lastProbe=0,waitSince=0;
static LONG requestNumber=0;
static int observedTeam=0,observedCareer=0;
static int observedRevision=0,stageRevision=0;
static wchar_t observedSelection[512]{};
static bool awaitingReload=false;
static bool sceneReady=false,photoDirty=false,careerWasActive=false;
static int careerSession=0,careerSessionTeam=0,observedEnabled=-1;
static uintptr_t backgroundViewModel=0,backgroundVtable=0;
static uint32_t drawnRequest=0;
static frontend_stadium::ProfileReloadProgress reloadProgress;
static bool bootComplete=false;
static uint32_t requestsAtPost=0;
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
    const int careerTeam=activeCareerClub(image,read);
    if(careerTeam){*career=true;return careerTeam;}
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
static bool customActive(){return !stopping&&activeMode==1&&setting(L"enabled",0)&&activeSlot()==static_cast<int>(FrontendStadiumStatus.slot);}
static bool menuScene(){
    // The same predicate used by StadiumPanDP::IsScreenTriggeredInMenus.
    const auto owner=reinterpret_cast<void*(__fastcall*)()>(image+0x4036820)();
    if(!owner)return false;
    const int mode=reinterpret_cast<int(__fastcall*)(void*)>(image+0x470ce20)(owner);
    return mode<4||mode>7;
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
    if(!output||!customActive()||!menuScene())return;
    wchar_t name[256]{};char utf8[256]{};
    wcsncpy_s(name,activeName,_TRUNCATE);
    if(!name[0]||!WideCharToMultiByte(CP_UTF8,0,name,-1,utf8,sizeof utf8,nullptr,nullptr))return;
    std::memset(output,0,256);std::memcpy(output,utf8,std::strlen(utf8));
    // Custom packages do not supply trustworthy capacity/construction data.
    const int values[]={0,0,static_cast<int>(FrontendStadiumStatus.team),-1,-1};
    std::memcpy(static_cast<unsigned char*>(output)+0x100,values,sizeof values);
    log("PAN_CUSTOM_INFO",static_cast<int>(FrontendStadiumStatus.team),stadium);
}
static void* __fastcall backgroundHook(void* self){
    auto* provider=reinterpret_cast<void*(__fastcall*)(void*)>(image+0x40893e0)(self);
    backgroundViewModel=reinterpret_cast<uintptr_t>(self);backgroundVtable=get<uintptr_t>(backgroundViewModel);
    const auto slot=FrontendStadiumStatus.slot;
    const auto page=frontend_stadium::pageKind(image,read);
    const bool menuPage=page==frontend_stadium::PageKind::Menu;
    const bool validRoute=sceneReady&&activeMode&&setting(L"enabled",0)&&activeSlot()==static_cast<int>(slot);
    const bool transition=page==frontend_stadium::PageKind::Transition;
    const auto photograph=frontend_stadium::photographPolicy(menuPage,bootComplete,awaitingReload||stageRequest!=0,sceneReady,validRoute,transition);
    if(provider&&!stopping&&photograph!=frontend_stadium::Photograph::Original){
        const auto text=get<uintptr_t>(reinterpret_cast<uintptr_t>(self)+0x168);
        char previous[64]{};
        if(read(text,previous,sizeof previous-1))std::memcpy(FrontendStadiumStatus.previousImage,previous,sizeof previous);
        if(photograph==frontend_stadium::Photograph::Stadium&&menuScene()&&frontend_stadium::routePhotograph(provider,
            reinterpret_cast<frontend_stadium::SetProviderString>(image+0x4c174d0),
            reinterpret_cast<const char*>(image+0x21c3fe8))){
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
    if(!photoDirty||!frontend_stadium::reloadPage(image,read))return;
    const auto self=backgroundViewModel;
    // Publish through the current native view model, without retaining a DP.
    // Its factory and owning service must still match the live registration.
    if(!self||get<uintptr_t>(self)!=backgroundVtable||get<uintptr_t>(backgroundVtable+0x38)!=image+0x408d1d0||!get<uintptr_t>(self+8))return;
    photoDirty=false;
    reinterpret_cast<void(__fastcall*)(void*,int,void*)>(image+0x4c15b20)(reinterpret_cast<void*>(self),0x9c40,nullptr);
    log(sceneReady?"PHOTO_REFRESH_STADIUM":"PHOTO_REFRESH_FALLBACK",static_cast<int>(FrontendStadiumStatus.team));
}
static DWORD prepare(int team,int slot,int career){
    wchar_t command[2048]{};
    _snwprintf_s(command,_countof(command),_TRUNCATE,L"\"%ls\" --game-root \"%ls\" --team %d --slot %d %ls --session %d",
        helper,game,team,slot,career?L"--career":L"",careerSession);
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
    if(stopping||!activeMode||!setting(L"enabled",0)||!read(reinterpret_cast<uintptr_t>(context),copy.data(),copy.size())){
        original(self,context);return;
    }
    const int slot=static_cast<int>(FrontendStadiumStatus.slot);
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
static bool startNativeReload(){
    // ReloadFEStadiumViewModel::evt_start_stadium_change (action 0x2787)
    // delegates to this native service command (40fac8a..40faca9).
    // Run it once on FIFA's frame thread. Do not additionally post a profile
    // change event: that can start the same request before this call runs.
    const auto commands=nativeCommands();
    if(!commands)return false;
    const unsigned char signature[]={0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10};
    unsigned char actual[sizeof signature]{};
    if(!read(image+0x3d8b8a0,actual,sizeof actual)||std::memcmp(actual,signature,sizeof actual))return false;
    const bool accepted=frontend_stadium::requestProfileReload([&](int command,void* request){
        reinterpret_cast<void(__fastcall*)(void*,int,void*)>(image+0x3d8b8a0)(reinterpret_cast<void*>(commands),command,request);
    });
    log(accepted?"NATIVE_STADIUM_CHANGE_STARTED":"NATIVE_STADIUM_CHANGE_BUSY",static_cast<int>(FrontendStadiumStatus.team),accepted?1:0);
    return accepted;
}
static bool acknowledgeBackground(){
    int state=-1;const auto commands=nativeCommands(&state);
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
    if(!installed||stopping||now-lastProbe<250||!menuScene())return;
    lastProbe=now;
    if(!TryAcquireSRWLockExclusive(&gate))return;
    const bool allowedPage=frontend_stadium::reloadPage(image,read);
    if(allowedPage)bootComplete=true;
    if(!allowedPage&&!awaitingReload){ReleaseSRWLockExclusive(&gate);return;}
    bool career=stageCareer!=0;
    const int team=allowedPage?club(&career):(stageTeam?stageTeam:static_cast<int>(FrontendStadiumStatus.team));
    const bool contextChanged=allowedPage&&(career!=careerWasActive||(career&&team!=careerSessionTeam));
    if(allowedPage)updateCareerContext(career,team);
    if(contextChanged){
        awaitingReload=false;observedTeam=0;
        InterlockedExchange(&stageRequest,0);InterlockedExchange(&stageComplete,0);
        sceneReady=false;photoDirty=true;
    }
    const int enabled=setting(L"enabled",0);
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
            awaitingReload=false;publishState(activeMode?3:4,static_cast<int>(FrontendStadiumStatus.team),static_cast<int>(FrontendStadiumStatus.career),activeSlot(),0);
            log("RELOAD_COMPLETE",static_cast<int>(FrontendStadiumStatus.team),activeSlot());
        }else if(now-waitSince>60000){
            failReload(20);
        }else if(FrontendStadiumStatus.requests==requestsAtPost){
            int nativeState=-1;nativeCommands(&nativeState);
            const auto step=reloadProgress.next(nativeState,stageRequest&&stageComplete==stageRequest,now);
            if(step==frontend_stadium::ReloadStep::Failed){failReload(22);}
            else if(step==frontend_stadium::ReloadStep::Start){
                ReleaseSRWLockExclusive(&gate);reloadProgress.started=startNativeReload();return;
            }else if(step==frontend_stadium::ReloadStep::BackgroundReady){
                // The FIFA Friends cover was already requested before staging.
                // A cached/hidden image need not fire another UI callback.
                // Resume the standard native loader, outside our staging lock.
                ReleaseSRWLockExclusive(&gate);
                if(!acknowledgeBackground())log("NATIVE_BACKGROUND_READY_SKIPPED",team);
                return;
            }
        }
        ReleaseSRWLockExclusive(&gate);return;
    }
    if(!allowedPage){ReleaseSRWLockExclusive(&gate);return;}
    const int revision=setting(L"reload_revision",0);
    wchar_t chosen[512]{};selection(team,chosen,_countof(chosen));
    if(team>0&&setting(career?L"career":L"favorite_team",1)&&
       (team!=observedTeam||static_cast<int>(career)!=observedCareer||revision!=observedRevision||std::wcscmp(chosen,observedSelection))){
        observedTeam=stageTeam=team;observedCareer=stageCareer=career?1:0;
        observedRevision=stageRevision=revision;
        wcsncpy_s(observedSelection,chosen,_TRUNCATE);wcsncpy_s(stageSelection,chosen,_TRUNCATE);
        stageSlot=activeSlot()==176?261:176;
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
static void __fastcall frameHook(void* self,void* a,void* b,void* c){
    reinterpret_cast<void(__fastcall*)(void*,void*,void*,void*)>(image+0x4361d70)(self,a,b,c);
    pollReload();
    refreshPhotograph();
}
static void* __fastcall sceneFrameHook(){
    // GameFlow::Render selects one of two branches. The boot FE branch
    // stops running once a 3D scene exists; this call covers the scene branch.
    // Keep probing and posting events on the same game render thread.
    static bool reported=false;
    if(!reported){reported=true;log("SCENE_MONITOR_ACTIVE");}
    pollReload();
    refreshPhotograph();
    return reinterpret_cast<void*(__fastcall*)()>(image+0x44d8ce0)();
}
static void __fastcall hook(void* self,const void* context){
    const auto original=reinterpret_cast<Prepare>(image+kPrepare);
    if(stopping||!setting(L"enabled",0)){activeMode=0;sceneReady=false;photoDirty=true;original(self,context);return;}
    bool career=false;const int team=club(&career);
    updateCareerContext(career,team);
    if(team<=0||team>2000000||!setting(career?L"career":L"favorite_team",1)){activeMode=0;original(self,context);return;}
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
    const bool staged=stageRequest&&stageComplete==stageRequest&&stageTeam==team&&stageCareer==static_cast<int>(career)&&stageRevision==revision&&!std::wcscmp(chosen,stageSelection);
    const DWORD result=staged?stageError:prepare(team,slot,career?1:0);
    observedTeam=team;observedCareer=career?1:0;wcsncpy_s(observedSelection,chosen,_TRUNCATE);
    observedRevision=revision;
    observedEnabled=1;
    FrontendStadiumStatus.error=result;
    activeMode=0;
    const int mode=staged?stageMode:(!result?static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",L"mode",0,routeIni)):0);
    activeCrowd[0]=0;activeName[0]=0;
    if(!result&&mode){
        // Only the FE stadium fields change in this private context copy.
        // Home/away match teams, fixture stadium and save data retain their values.
        const int selected=static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",L"slot",slot,routeIni));
        frontend_stadium::routeContext(copy,selected);
        FrontendStadiumStatus.slot=static_cast<uint32_t>(selected);activeMode=mode;
        GetPrivateProfileStringW(L"frontend_stadium",L"name",L"",activeName,_countof(activeName),routeIni);
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
                log("PREPARE_ASYNC",stageTeam,stageSlot);
                stageError=prepare(stageTeam,stageSlot,stageCareer);
                stageMode=stageError?0:static_cast<int>(GetPrivateProfileIntW(L"frontend_stadium",L"mode",0,routeIni));
                InterlockedExchange(&stageComplete,request);
                log("PREPARE_ASYNC_COMPLETE",stageTeam,static_cast<int>(stageError));
            }
            ReleaseSRWLockExclusive(&gate);
        }
        Sleep(100);
    }
    return 0;
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
