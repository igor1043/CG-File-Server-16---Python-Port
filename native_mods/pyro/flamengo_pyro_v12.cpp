#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "timing_v6.h"
#include "goal_v11.h"

// FIFA 16 PC x64 577de45c only. All particle mutations occur before the
// native BatchParticles phase 0, after its previous-frame jobs have completed.
using Draw = void (__fastcall*)(void*,int);
using One = void (__fastcall*)(void*);
using Slot = void (__fastcall*)(void*,int);
static uintptr_t image;
static Draw original;
static LONG started, stopping, busy, faulted, replayRequested, phasesSeen;
static constexpr int emitterCount=10;
static constexpr ULONGLONG durationMs=30000;
static constexpr char effectName[]="flamengo_v12";
static char logPath[MAX_PATH], configPath[MAX_PATH];
static bool enabled=true, automatic=true;
static int clubSide=-1;
static PyroGoals goals;
static bool goalShow=false;
static uintptr_t batchImpl=0;
static ULONGLONG lastMatchSample=0;
static bool cachedMatch=false,cachedZero=false;
static void wait_jobs() { if(batchImpl) ((One)(image+0x43f31d0))((void*)batchImpl); }
static uintptr_t activeEffect=0, activeInstances[emitterCount]={};
static ULONGLONG kickoffSince=0, assetSince=0;
static bool showing=false;
static ULONGLONG showStarted=0;
static bool emitterStarted[emitterCount]={};
static uintptr_t activeObject, activeState, activeManager, sessionKey;
static ULONGLONG lastSample, candidateSince, deadline, lastValid;
static bool consumed, configured;
static int handles[emitterCount];
static unsigned char savedDefinition[68];

static void log_event(const char* text) {
    FILE* f=nullptr;
    if (!fopen_s(&f,logPath,"ab") && f) {
        fprintf(f,"%llu %s\n",GetTickCount64(),text); fclose(f);
    }
}
template<class T> static bool get(uintptr_t address,T& value) {
    SIZE_T n=0;
    return address && ReadProcessMemory(GetCurrentProcess(),(void*)address,&value,sizeof(value),&n) && n==sizeof(value);
}
static bool same(uintptr_t address,uintptr_t expected) {
    uintptr_t p=0; return get(address,p) && p==expected;
}
struct LuaValue { uint64_t bits; int tag; int padding; };
static bool lua_field(uintptr_t table,const char* name,LuaValue& out) {
    unsigned char tag=0,power=0; uintptr_t nodes=0;
    if (!get(table+8,tag) || tag!=5 || !get(table+11,power) || power>12 ||
        !get(table+32,nodes) || !nodes) return false;
    const size_t length=strlen(name);
    for (unsigned int i=0;i<(1u<<power);++i) {
        struct Node { LuaValue value; LuaValue key; uintptr_t next; } node={};
        if (!get(nodes+i*40,node)) return false;
        if (node.key.tag!=4) continue;
        size_t keyLength=0; char chars[32]={};
        if (!get((uintptr_t)node.key.bits+16,keyLength) || keyLength!=length || length>=sizeof(chars)) continue;
        SIZE_T got=0;
        if (!ReadProcessMemory(GetCurrentProcess(),(void*)((uintptr_t)node.key.bits+24),chars,length,&got) || got!=length) continue;
        if (!memcmp(chars,name,length)) { out=node.value; return true; }
    }
    return false;
}
static bool lua_index(uintptr_t table,int index,LuaValue& out) {
    unsigned char tag=0,power=0; uintptr_t array=0,nodes=0; int count=0;
    if (!get(table+8,tag) || tag!=5 || !get(table+56,count) || count<0 || count>4096) return false;
    if (index>0 && index<=count && get(table+24,array) && array) return get(array+(index-1)*16,out);
    if (!get(table+11,power) || power>12 || !get(table+32,nodes) || !nodes) return false;
    for (unsigned int i=0;i<(1u<<power);++i) {
        struct Node { LuaValue value; LuaValue key; uintptr_t next; } node={};
        if (!get(nodes+i*40,node)) return false;
        double value=0; memcpy(&value,&node.key.bits,8);
        if (node.key.tag==3 && value==(double)index) { out=node.value; return true; }
    }
    return false;
}
static bool scene_match(uintptr_t& key) {
    uintptr_t lua=0; LuaValue globals={},db={},players={},rows[2]={};
    if (!get(image+0x3613fd0,lua) || !get(lua+0x78,globals) || globals.tag!=5 ||
        !lua_field((uintptr_t)globals.bits,"db",db) || db.tag!=5 ||
        !lua_field((uintptr_t)db.bits,"player",players) || players.tag!=5 ||
        !lua_index((uintptr_t)players.bits,0,rows[0]) || rows[0].tag!=5) return false;
    // Player indices include starters and substitutes; away is not index 11.
    for (int index=1;index<64;++index) {
        LuaValue candidate={},side={}; double teamSide=0;
        if (!lua_index((uintptr_t)players.bits,index,candidate) || candidate.tag!=5 ||
            !lua_field((uintptr_t)candidate.bits,"teamside",side) || side.tag!=3) continue;
        memcpy(&teamSide,&side.bits,8);
        if (teamSide==1) { rows[1]=candidate; break; }
    }
    if (rows[1].tag!=5) return false;
    bool supported=false;
    for (int i=0;i<2;++i) {
        LuaValue club={},side={},again={}; double clubId=0,teamSide=0;
        if (!lua_field((uintptr_t)rows[i].bits,"teamid",club) || club.tag!=3 ||
            !lua_field((uintptr_t)rows[i].bits,"teamside",side) || side.tag!=3 ||
            !lua_field((uintptr_t)rows[i].bits,"teamid",again) || again.tag!=3 || again.bits!=club.bits) return false;
        memcpy(&clubId,&club.bits,8); memcpy(&teamSide,&side.bits,8);
        if (!(clubId>0 && clubId<=1000000) || teamSide!=(double)i) return false;
        if (clubId==1043) { supported=true; clubSide=i; }
    }
    LuaValue confirmed={};
    if (!get(lua+0x78,confirmed) || confirmed.bits!=globals.bits || confirmed.tag!=5) return false;
    key=(uintptr_t)players.bits ^ (uintptr_t)rows[0].bits ^ ((uintptr_t)rows[1].bits<<11);
    return supported && key;
}
static bool match(uintptr_t& key,bool& scoreZero) {
    uintptr_t sceneKey=0;
    if (scene_match(sceneKey)) {
        key=sceneKey; scoreZero=true;
        uintptr_t cache=0,rows=0; int home=0,away=0;
        if (get(image+0x34a30b0,cache) && same(cache,image+0x21141f0) && get(cache+8,rows) &&
            get(rows+21*16,home) && get(rows+6*16,away)) scoreZero=home==0 && away==0;
        return true;
    }
    uintptr_t manager=0,world=0,game=0,registry=0,pairs=0;
    int k=0,count=0;
    if (!get(image+0x3517420,manager) || !same(manager,image+0x2226730) ||
        !get(manager+8,world) || !same(world,image+0x2225d90) ||
        !get(world+0x10,game) || !same(game,image+0x2309370) ||
        !get(game+0x20,registry) || !registry ||
        !get(registry+8+15*32,k) || k!=15 ||
        !get(registry+8+15*32+16,count) || count!=2 ||
        !get(registry+8+15*32+24,pairs)) return false;
    uintptr_t teams[2]={}; int clubs[2]={};
    for (int i=0;i<2;++i) {
        uintptr_t team=0,owner=0,stats=0; int side=-1,club=0;
        if (!get(pairs+i*16+8,team) || !same(team,image+0x22fe9f0) ||
            !get(team+0x30,owner) || owner!=registry || !get(team+0x58,side) ||
            side<0 || side>1 || teams[side] || !get(team+0x50,stats) ||
            !get(stats+0x80,club) || club<=0 || club>1000000) return false;
        teams[side]=team; clubs[side]=club;
    }
    uintptr_t cache=0,rows=0; int home=0,away=0;
    if (!get(image+0x34a30b0,cache) || !same(cache,image+0x21141f0) ||
        !get(cache+8,rows) || !same(rows+21*16+8,image+0x3acc040) ||
        !same(rows+6*16+8,image+0x3acc040) ||
        !get(rows+21*16,home) || !get(rows+6*16,away) || home<0 || home>99 || away<0 || away>99) return false;
    clubSide=clubs[0]==1043?0:(clubs[1]==1043?1:-1);
    scoreZero=home==0 && away==0;
    key=registry ^ rows ^ teams[0] ^ ((teams[1]<<11)|(teams[1]>>53));
    return key && (clubs[0]==1043 || clubs[1]==1043);
}
// Never pass a handle to the native tree helpers until the exact instance is
// found. Those helpers dereference the sentinel for missing IDs.
static uintptr_t instance_for(uintptr_t manager,int handle) {
    uintptr_t node=0;
    if (handle<0 || !get(manager+0x30,node)) return 0;
    for (int depth=0;node && depth<128;++depth) {
        int id=-1; uintptr_t child=0,instance=0;
        if (!get(node+0x20,id)) return 0;
        if (id==handle) return get(node+0x28,instance)?instance:0;
        if (!get(node+(handle<id?8:0),child) || child==node) return 0;
        node=child;
    }
    return 0;
}
static bool owned() {
    uintptr_t p=0,s=0,m=0,effect=0; char name[32]={};
    return configured && get(image+0x3504500+31*8,p) && p==activeObject &&
        same(p,image+0x2209f70) && get(p+0x10,s) && s==activeState &&
        get(s+0x58,m) && m==activeManager && get(s+8,name) &&
        !memcmp(name,effectName,sizeof(effectName)) && get(m+0x10,effect) &&
        (!activeEffect || effect==activeEffect);
}
static bool valid_slot(int i) {
    int current=-1;
    return owned() && handles[i]>=0 && get(activeState+0x60+i*4,current) &&
        current==handles[i] && instance_for(activeManager,handles[i])==activeInstances[i] && activeInstances[i];
}
static void forget_resource() {
    configured=false; activeEffect=0; showing=false; deadline=0;
    for (int i=0;i<emitterCount;++i) { handles[i]=-1; activeInstances[i]=0; }
}
static void cleanup() {
    if (showing && owned()) {
        wait_jobs();
        for (int i=0;i<emitterCount;++i) if (valid_slot(i)) {
            ((Slot)(image+0x441c720))((void*)activeManager,handles[i]);
            ((Slot)(image+0x441c940))((void*)activeManager,handles[i]);
        }
        // Keep definition, asset and instances alive until native scene teardown.
        // Do not emit replay-recorded Delete/Hide/SetDefinition/Reload commands.
        if (showing) log_event("SHOW_STOPPED emission_disabled asset_retained_for_replay");
    } else if (configured) {
        log_event("RESOURCE_CHANGED discarded_stale_handles_without_native_calls");
        forget_resource();
    }
    showing=false; deadline=0;
}
static bool configure() {
    uintptr_t p=0,s=0,m=0,resource=0,task=0; int index=-1,capacity=0;
    unsigned char definition[68]={};
    if (!get(image+0x3504500+31*8,p) || !same(p,image+0x2209f70) ||
        !get(p+0x10,s) || !get(s,index) || index!=31 ||
        !get(s+0x264,capacity) || capacity!=100 ||
        !get(s+8,definition) || definition[0] ||
        !get(s+0x268,task) || task || !get(s+0x58,m) || !m ||
        !get(s+0x50,resource) || !resource) return false;
    for (int i=0;i<100;++i) { int slot=0; if (!get(s+0x60+i*4,slot) || slot!=-1) return false; }
    memcpy(savedDefinition,definition,68);
    memcpy(definition,effectName,sizeof(effectName));
    const int asset=1043; memcpy(definition+64,&asset,4);
    // Native SetDefinition updates the RNA record used by ParticlesUpdate;
    // its normal asset binder then resolves particles/flamengo_1043.{lnx,rx3}.
    wait_jobs();
    ((void (__fastcall*)(void*,const void*))(image+0x4385860))((void*)p,definition);
    ((void (__fastcall*)(void*,unsigned char))(image+0x43856b0))((void*)p,0);
    activeObject=p; activeState=s; activeManager=m; configured=true;
    log_event("definition_requested Flamengo=1043 renderer=31 stadiumDependent=false");
    return true;
}
static int active_count() { return goalShow?6:10; }
static bool emit() {
    uintptr_t resource=0,effect=0;
    if (!owned() || !get(activeState+0x50,resource) || !resource) return false;
    if (!((unsigned char (__fastcall*)(void*))(image+0x4383e30))((void*)activeObject) ||
        !get(activeManager+0x10,effect) || !effect) return false;
    wait_jobs();
    activeEffect=effect;
    for (int i=0;i<active_count();++i) {
        int current=-1;
        if (!get(activeState+0x60+i*4,current)) return false;
        if (handles[i]<0) {
            if (current!=-1) return false;
            // Direct manager Create: no replay-recorded renderer command.
            handles[i]=((int (__fastcall*)(void*,float,float,float,float,float,float))(image+0x441bce0))
                ((void*)activeManager,0,0,0,0,0,0);
            activeInstances[i]=instance_for(activeManager,handles[i]);
            if (handles[i]<0 || !activeInstances[i]) return false;
            *(int*)(activeState+0x60+i*4)=handles[i];
        }
        if (!valid_slot(i)) return false;
        __declspec(align(16)) float matrix[16]={1,0,0,0, 0,1,0,0, 0,0,1,0, 0,35,0,1};
        if (!goalShow && i<6) {
            matrix[12]=(float)((i/2-1)*2800);
            matrix[14]=(i%2==0)?-3650.0f:3650.0f;
        } else {
            matrix[12]=(i%2==0)?-5850.0f:5850.0f;
            matrix[14]=goalShow?(float)((i/2-1)*1800):(float)((i/2-3)*2-1)*1800;
        }
        ((void (__fastcall*)(void*,int,const float*))(image+0x441cd90))((void*)activeManager,handles[i],matrix);
        ((Slot)(image+0x441c720))((void*)activeManager,handles[i]);
        ((Slot)(image+0x441c940))((void*)activeManager,handles[i]);
        emitterStarted[i]=false;
    }
    *(unsigned char*)(activeState+4)=0;
    log_event("SHOW_STARTED confetti_red_black intro_six_sideline_four_goal_or_goal_six max_ms=30000 kickoff_tail_ms=8000"); return true;
}
static bool read_score(int& home,int& away) {
    uintptr_t cache=0,rows=0,again=0; int h2=0,a2=0;
    return get(image+0x34a30b0,cache) && same(cache,image+0x21141f0) &&
        get(cache+8,rows) && same(rows+21*16+8,image+0x3acc040) &&
        same(rows+6*16+8,image+0x3acc040) && get(rows+21*16,home) &&
        get(rows+6*16,away) && home>=0 && home<=99 && away>=0 && away<=99 &&
        get(rows+21*16,h2) && get(rows+6*16,a2) && h2==home && a2==away &&
        get(image+0x34a30b0,again) && again==cache;
}
static bool gameplay_present() {
    uintptr_t manager=0,world=0,game=0,registry=0;
    return get(image+0x3517420,manager) && same(manager,image+0x2226730) &&
        get(manager+8,world) && same(world,image+0x2225d90) &&
        get(world+0x10,game) && same(game,image+0x2309370) &&
        get(game+0x20,registry) && registry;
}
static void tick(void* batch) {
    const ULONGLONG now=GetTickCount64();
    if (now-lastSample<100 && !stopping) return;
    lastSample=now;
    if(!enabled && !stopping) return;
    bool pendingGoal=false;
    // Dormant gameplay path: no renderer validation, tree walk, or job wait.
    if(!stopping && !showing && consumed && sessionKey && cachedMatch &&
        now-lastMatchSample<2000) {
        int home=0,away=0;
        pendingGoal=read_score(home,away) && goals.update(now,home,away,clubSide);
        if(!pendingGoal) return;
    }
    uintptr_t impl=0;
    if (!same((uintptr_t)batch,image+0x2214500) || !get((uintptr_t)batch+0x10,impl) || !impl) return;
    batchImpl=impl;
    if (stopping) { cleanup(); return; }
    // Fully automatic: keyboard input cannot arm, cancel or restart the show.
    uintptr_t key=0; bool zero=false;
    if (!lastMatchSample || now-lastMatchSample>=(showing || !consumed ? 500ULL : 2000ULL)) {
        cachedMatch=match(key,zero); cachedZero=zero; lastMatchSample=now;
    } else { key=sessionKey; zero=cachedZero; }
    if (!cachedMatch) {
        cleanup();
        if (lastValid && now-lastValid>30000) { sessionKey=0; consumed=false; candidateSince=0; kickoffSince=0; }
        return;
    }
    lastValid=now;
    if (key!=sessionKey) {
        cleanup(); sessionKey=key; consumed=!automatic || !zero;
        candidateSince=now; kickoffSince=0; goals=PyroGoals{}; goalShow=false;
        log_event("MATCH_DETECTED automatic_intro_armed");
    }
    if (configured && (showing || !consumed) && !owned()) { forget_resource(); consumed=!zero; candidateSince=now; }
    int h=0,a=0;
    if ((pendingGoal || (read_score(h,a) && goals.update(now,h,a,clubSide))) && enabled) {
        cleanup(); consumed=false; candidateSince=now; kickoffSince=0; goalShow=true;
        log_event("FLAMENGO_GOAL_CONFIRMED automatic_show_armed");
    }
    if (!enabled) return;
    if (showing) {
        if (!kickoffSince && gameplay_present()) kickoffSince=now;
        if (goalShow ? (now<showStarted || now-showStarted>=8000) : pyro_expired(now,showStarted,kickoffSince)) { cleanup(); consumed=true; return; }
        bool waited=false;
        for (int i=0;i<active_count();++i) {
            if (!emitterStarted[i] && now-showStarted>=(ULONGLONG)(i/2)*160) {
                if (!waited) { wait_jobs(); waited=true; }
                if (!valid_slot(i)) { cleanup(); consumed=true; return; }
                ((Slot)(image+0x441ce00))((void*)activeManager,handles[i]);
                ((Slot)(image+0x441c8d0))((void*)activeManager,handles[i]);
                emitterStarted[i]=true;
            }
        }
        return;
    }
    if (consumed) return;
    if (!configured) {
        if (now-candidateSince<750) return;
        if (!configure()) {
            if (now-candidateSince>15000) { consumed=true; log_event("SLOT_UNAVAILABLE no_show"); }
            return;
        }
        assetSince=now;
    }
    if (emit()) {
        consumed=true; showing=true; showStarted=now; deadline=now+durationMs;
        kickoffSince=gameplay_present()?now:0;
        for(int i=0;i<2;++i) if(valid_slot(i)) {
            ((Slot)(image+0x441ce00))((void*)activeManager,handles[i]);
            ((Slot)(image+0x441c8d0))((void*)activeManager,handles[i]); emitterStarted[i]=true;
        }
    } else if (now-assetSince>15000) { cleanup(); consumed=true; log_event("ASSET_TIMEOUT"); }
}
static void __fastcall draw_hook(void* self,int phase) {
    if (phase>=0 && phase<8) {
        const LONG bit=1L<<phase;
        if (!(InterlockedOr(&phasesSeen,bit)&bit)) {
            char event[160]; uintptr_t vt=0; get((uintptr_t)self,vt);
            _snprintf_s(event,sizeof(event),_TRUNCATE,"draw_seen phase=%d self_vtable=%llx",phase,(unsigned long long)(vt-image));
            log_event(event);
        }
    }
    if (phase==0 && (stopping || GetTickCount64()-lastSample>=100) && !faulted && !InterlockedCompareExchange(&busy,1,0)) {
        LARGE_INTEGER before={},after={},freq={};
        QueryPerformanceCounter(&before);
        __try { tick(self); }
        __except(EXCEPTION_EXECUTE_HANDLER) {
            InterlockedExchange(&faulted,1); log_event("FAULT disabled_native_calls restart_game");
        }
        QueryPerformanceCounter(&after); QueryPerformanceFrequency(&freq);
        static double totalMs=0,maxMs=0; static unsigned samples=0;
        static ULONGLONG reported=0;
        const double ms=1000.0*(double)(after.QuadPart-before.QuadPart)/(double)freq.QuadPart;
        totalMs+=ms; if(ms>maxMs)maxMs=ms; ++samples;
        const ULONGLONG measured=GetTickCount64();
        if(!reported)reported=measured;
        if(measured-reported>=10000) {
            char report[192];
            _snprintf_s(report,sizeof(report),_TRUNCATE,"CPU_PROFILE interval_ms=%llu callbacks=%u module_total_ms=%.3f callback_max_ms=%.3f showing=%d (not_GPU_or_FPS)",measured-reported,samples,totalMs,maxMs,showing?1:0);
            log_event(report);reported=measured;totalMs=maxMs=0;samples=0;
        }
        InterlockedExchange(&busy,0);
    }
    original(self,phase);
}
static bool swap(void* before,void* after) {
    auto slot=(void* volatile*)(image+0x2214520); DWORD old=0,ignored=0;
    if (!VirtualProtect((void*)slot,8,PAGE_READWRITE,&old)) return false;
    void* found=InterlockedCompareExchangePointer(slot,after,before);
    VirtualProtect((void*)slot,8,old,&ignored); return found==before;
}
#include "native_signatures_v6.h"
static DWORD WINAPI install_worker(void*) {
    for (int attempt=0;attempt<600 && !stopping;++attempt) {
        uintptr_t target=0;
        bool acceptable=get(image+0x2214520,target) && target==image+0x43f14e0;
        if (!acceptable && target) {
            HMODULE owner=nullptr; char path[MAX_PATH]={};
            if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,(LPCSTR)target,&owner)) {
                GetModuleFileNameA(owner,path,MAX_PATH);const char* name=strrchr(path,'\\');
                acceptable=name && (!strcmp(name+1,"flamengo_pyro_v3.dll") || !strcmp(name+1,"flamengo_pyro_v4.dll") || !strcmp(name+1,"flamengo_pyro_v5.dll"));
                if (acceptable) GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCSTR)target,&owner);
                FreeLibrary(owner);
            }
        }
        if (check_signatures(image) && acceptable) {
            original=(Draw)target;
            if (swap((void*)original,(void*)draw_hook)) {
                log_event("installed v12 automatic_intro_and_Flamengo_goals no_hotkeys finite_confetti no_instance_delete"); return 0;
            }
        }
        Sleep(200);
    }
    log_event("INSTALL_TIMEOUT loaded_code_or_render_slot_unavailable"); return 0;
}
extern "C" __declspec(dllexport) unsigned int WINAPI Fifa16ModGetApiVersion() { return 1; }
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char* root) {
    if (!root || InterlockedCompareExchange(&started,1,0)) return FALSE;
    _snprintf_s(logPath,MAX_PATH,_TRUNCATE,"%s\\..\\logs\\flamengo_pyro_v12.log",root);
    _snprintf_s(configPath,MAX_PATH,_TRUNCATE,"%s\\flamengo_pyro\\pyro.ini",root);
    enabled=GetPrivateProfileIntA("pyro","enabled",1,configPath)!=0;
    automatic=true;
    for (int& handle:handles) handle=-1;
    image=(uintptr_t)GetModuleHandleA(nullptr);
    IMAGE_DOS_HEADER dos={}; IMAGE_NT_HEADERS64 nt={};
    if (!get(image,dos) || dos.e_magic!=IMAGE_DOS_SIGNATURE || dos.e_lfanew<=0 ||
        !get(image+(uintptr_t)dos.e_lfanew,nt) || nt.Signature!=IMAGE_NT_SIGNATURE ||
        nt.FileHeader.TimeDateStamp!=0x577de45c || nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64) {
        log_event("UNSUPPORTED_IMAGE"); return FALSE;
    }
    HMODULE pin=nullptr;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCSTR)&started,&pin)) return FALSE;
    log_event("waiting_for_loaded_native_code");
    HANDLE thread=CreateThread(nullptr,0,install_worker,nullptr,0,nullptr);
    if (!thread) return FALSE; CloseHandle(thread); return TRUE;
}
extern "C" __declspec(dllexport) DWORD WINAPI Fifa16PyroReplay(void*) { InterlockedExchange(&replayRequested,1); return 1; }
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStop() {
    InterlockedExchange(&stopping,1);
    // Leave the pinned pass-through callback until the render thread cleans up.
    // No worker-thread deletes of instances while particle jobs are running.
    log_event("stop_requested render_thread_cleanup"); return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE h,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h); return TRUE;
}
