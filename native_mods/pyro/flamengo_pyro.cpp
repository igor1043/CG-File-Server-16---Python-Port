#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "timing_v14.h"
#include "goals.h"
#include "teams.h"
#include "palette.h"
#include "lifecycle_v17.h"
#include "ending.h"

// FIFA 16 PC x64 577de45c only. All particle mutations occur before the
// native BatchParticles phase 0, after its previous-frame jobs have completed.
using Draw = void (__fastcall*)(void*,int);
using One = void (__fastcall*)(void*);
using Slot = void (__fastcall*)(void*,int);
static uintptr_t image;
static Draw original;
static LONG started, stopping, busy, faulted, replayRequested, phasesSeen;
static constexpr int emitterCount=10;
static constexpr ULONGLONG durationMs=60000;
static constexpr char effectName[]="flamengo_pyro";
static char logPath[MAX_PATH], configPath[MAX_PATH];
static bool enabled=true, automatic=true;
static PyroGoals goals;
static bool goalShow=false;
static int matchHomeTeam=0;
static uintptr_t batchImpl=0;
static ULONGLONG lastMatchSample=0;
static bool cachedMatch=false,cachedZero=false;
static void wait_jobs() { if(batchImpl) ((One)(image+0x43f31d0))((void*)batchImpl); }
static uintptr_t activeEffect=0, activeInstances[emitterCount]={};
static ULONGLONG kickoffSince=0, assetSince=0;
static bool showing=false;
static ULONGLONG showStarted=0;
static bool emitterStarted[emitterCount]={};
static bool emitterDraining[emitterCount]={};
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
// Read only stadium metadata, without waiting for player tables.
static bool stadium_match(uintptr_t& key) {
    uintptr_t lua=0; LuaValue globals={},db={},stadiums={};
    if(!get(image+0x3613fd0,lua) || !get(lua+0x78,globals) || globals.tag!=5 ||
        !lua_field((uintptr_t)globals.bits,"db",db) || db.tag!=5 ||
        !lua_field((uintptr_t)db.bits,"stadium",stadiums) || stadiums.tag!=5)return false;
    for(int i=0;i<4;++i) {
        LuaValue row={},h={},a={};double home=0,away=0;
        if(!lua_index((uintptr_t)stadiums.bits,i,row) || row.tag!=5 ||
            !lua_field((uintptr_t)row.bits,"homeTeamID",h) || h.tag!=3 ||
            !lua_field((uintptr_t)row.bits,"awayTeamID",a) || a.tag!=3)continue;
        memcpy(&home,&h.bits,8);memcpy(&away,&a.bits,8);
        if(!pyro_team_valid(home) || !pyro_team_valid(away))continue;
        key=pyro_team_key((uintptr_t)row.bits,(int)home,(int)away);matchHomeTeam=(int)home;return key!=0;
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
    int clubIds[2]={};
    for (int i=0;i<2;++i) {
        LuaValue club={},side={},again={}; double clubId=0,teamSide=0;
        if (!lua_field((uintptr_t)rows[i].bits,"teamid",club) || club.tag!=3 ||
            !lua_field((uintptr_t)rows[i].bits,"teamside",side) || side.tag!=3 ||
            !lua_field((uintptr_t)rows[i].bits,"teamid",again) || again.tag!=3 || again.bits!=club.bits) return false;
        memcpy(&clubId,&club.bits,8); memcpy(&teamSide,&side.bits,8);
        if (!pyro_team_valid(clubId) || teamSide!=(double)i) return false;
        clubIds[i]=(int)clubId;
    }
    LuaValue confirmed={};
    if (!get(lua+0x78,confirmed) || confirmed.bits!=globals.bits || confirmed.tag!=5) return false;
    key=(uintptr_t)players.bits ^ (uintptr_t)rows[0].bits ^ ((uintptr_t)rows[1].bits<<11);
    key=pyro_team_key(key,clubIds[0],clubIds[1]);matchHomeTeam=clubIds[0];return key!=0;
}
static bool match(uintptr_t& key,bool& scoreZero) {
    uintptr_t sceneKey=0;
    if (stadium_match(sceneKey) || scene_match(sceneKey)) {
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
    scoreZero=home==0 && away==0;
    key=registry ^ rows ^ teams[0] ^ ((teams[1]<<11)|(teams[1]>>53));
    key=pyro_team_key(key,clubs[0],clubs[1]);matchHomeTeam=clubs[0];return key!=0;
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
#include "palette_runtime.inc"
static void forget_resource() {
    paletteHome=0;paletteEffect=0;
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
    } else if (configured && !owned()) {
        log_event("RESOURCE_CHANGED discarded_stale_handles_without_native_calls");
        forget_resource();
    }
    showing=false; deadline=0;
}
static int active_count();
static void finish_naturally() {
    // Normally all sources drained for >=7s. If rendering stalled or was paused,
    // do not freeze/clear particles merely because wall-clock time has elapsed.
    if(showing && owned()) {
        bool waited=false;
        for(int i=0;i<active_count();++i)if(!emitterDraining[i] && valid_slot(i)) {
            if(!waited) {wait_jobs();waited=true;}
            ((Slot)(image+0x441c980))((void*)activeManager,handles[i]);
            emitterDraining[i]=true;
        }
    }
    showing=false;deadline=0;
    log_event("SHOW_FINISHED natural_fade particle_lists_retained");
}
static bool configure() {
    uintptr_t p=0,s=0,m=0,resource=0,task=0; int index=-1,capacity=0;
    unsigned char definition[68]={};
    if (!get(image+0x3504500+31*8,p) || !same(p,image+0x2209f70) ||
        !get(p+0x10,s) || !get(s,index) || index!=31 ||
        !get(s+0x264,capacity) || capacity!=100 ||
        !get(s+8,definition) ||
        !get(s+0x268,task) || task || !get(s+0x58,m) || !m ||
        !get(s+0x50,resource) || !resource) return false;
    if (!memcmp(definition,effectName,sizeof(effectName))) {
        int assetId=0;memcpy(&assetId,definition+64,4);
        if(assetId!=1043)return false;
        activeObject=p;activeState=s;activeManager=m;activeEffect=0;configured=true;
        for(int i=0;i<emitterCount;++i) {
            int handle=-1;
            if(!get(s+0x60+i*4,handle)) {forget_resource();return false;}
            const uintptr_t instance=handle<0?0:instance_for(m,handle);
            if(handle>=0 && !instance) {forget_resource();return false;}
            handles[i]=handle;activeInstances[i]=instance;
        }
        log_event("OWN_DEFINITION_RECOVERED after_native_resource_reload");return true;
    }
    if(definition[0])return false;
    for (int i=0;i<100;++i) { int slot=0; if (!get(s+0x60+i*4,slot) || slot!=-1) return false; }
    memcpy(savedDefinition,definition,68);
    memcpy(definition,effectName,sizeof(effectName));
    const int asset=1043; memcpy(definition+64,&asset,4);
    // Native SetDefinition updates the RNA record used by ParticlesUpdate;
    // its normal asset binder then resolves particles/flamengo_pyro_1043.{lnx,rx3}.
    wait_jobs();
    ((void (__fastcall*)(void*,const void*))(image+0x4385860))((void*)p,definition);
    ((void (__fastcall*)(void*,unsigned char))(image+0x43856b0))((void*)p,0);
    activeObject=p; activeState=s; activeManager=m; configured=true;
    log_event("definition_requested teams=any asset=1043 renderer=31 stadiumDependent=false");
    return true;
}
static int active_count() { return goalShow?8:10; }
static bool emit() {
    uintptr_t resource=0,effect=0;
    if (!owned() || !get(activeState+0x50,resource) || !resource) return false;
    if (!((unsigned char (__fastcall*)(void*))(image+0x4383e30))((void*)activeObject) ||
        !get(activeManager+0x10,effect) || !effect) return false;
    wait_jobs();
    activeEffect=effect;
    if(!apply_home_palette())return false;
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
            matrix[14]=goalShow?((float)(i/2)-1.5f)*1400.0f:(float)((i/2-3)*2-1)*1800;
        }
        ((void (__fastcall*)(void*,int,const float*))(image+0x441cd90))((void*)activeManager,handles[i],matrix);
        ((Slot)(image+0x441c720))((void*)activeManager,handles[i]);
        ((Slot)(image+0x441c940))((void*)activeManager,handles[i]);
        emitterStarted[i]=false; emitterDraining[i]=false;
    }
    *(unsigned char*)(activeState+4)=0;
    log_event("SHOW_STARTED confetti_home_palette intro_six_sideline_four_goal_or_goal_eight intro_ms=60000 goal_ms=25000 test_extended"); return true;
}
static ULONGLONG lastPreload=0,lastDiagnostic=0;
static void preload(ULONGLONG now) {
    if(now-lastPreload<500)return;lastPreload=now;
    if(configured && !owned()) { forget_resource(); assetSince=0; }
    if(!configured) {
        if(!configure())return;
        assetSince=now;log_event("EARLY_PRELOAD configured_before_team_detection");
    }
    if(activeEffect)return;
    uintptr_t resource=0,effect=0;
    if(!get(activeState+0x50,resource) || !resource)return;
    const bool ready=((unsigned char (__fastcall*)(void*))(image+0x4383e30))((void*)activeObject)!=0;
    if(ready && get(activeManager+0x10,effect) && effect && !activeEffect) {
        activeEffect=effect;log_event("EARLY_PRELOAD ready_native_initialization_completed");
    }
    if(!ready && now-lastDiagnostic>=5000) {
        lastDiagnostic=now; unsigned char fileReady=0,nativeReady=0;uintptr_t task=0;
        get(resource+0x10,fileReady);get(activeState+5,nativeReady);get(activeState+0x268,task);
        char event[144];_snprintf_s(event,sizeof(event),_TRUNCATE,"LOAD_STATE file_ready=%u native_ready=%u task=%llx",fileReady,nativeReady,(unsigned long long)task);
        log_event(event);
    }
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
static PyroLifecycle lifecycle;
static ULONGLONG lastLifecycleSample=0;
template<size_t N> static bool chain(uintptr_t rva,const unsigned int (&offsets)[N],uintptr_t& out) {
    uintptr_t p=0;if(!get(image+rva,p) || !p)return false;
    for(size_t i=0;i+1<N;++i)if(!get(p+offsets[i],p) || !p)return false;
    out=p+offsets[N-1];return true;
}
static bool restarted(ULONGLONG now) {
    if(now-lastLifecycleSample<250)return false;lastLifecycleSample=now;
    uintptr_t stats=0,pageAddress=0;int clock=0,h=0,a=0;char page[192]={};
    const unsigned int pageOffsets[]={232,192,136,472,0};
    const bool valid=get(image+56299464,stats) && stats && get(stats+5500,clock) &&
        clock>=0 && clock<100000000 && read_score(h,a);
    bool replay=false;
    const bool pageKnown=chain(58757168,pageOffsets,pageAddress) && get(pageAddress,page);
    if(pageKnown) {
        page[sizeof(page)-1]=0;
        for(char* c=page;*c;++c)if(*c>='A' && *c<='Z')*c=(char)(*c+32);
        replay=strstr(page,"replay")!=nullptr;
    }
    return lifecycle.sample(valid,clock,h,a,!pageKnown || replay,now);
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
    if(sessionKey && restarted(now)) {
        // Ensure any old show is stopped on the render thread before resetting.
        uintptr_t impl=0;
        if(!same((uintptr_t)batch,image+0x2214500) || !get((uintptr_t)batch+0x10,impl) || !impl)return;
        batchImpl=impl;cleanup();
        goals=PyroGoals{};sessionKey=0;consumed=false;goalShow=false;
        kickoffSince=0;candidateSince=now;showStarted=0;deadline=0;
        lastMatchSample=0;cachedMatch=false;cachedZero=false;
        for(int i=0;i<emitterCount;++i)emitterStarted[i]=false;
        log_event("MATCH_RESTART_CONFIRMED reset_intro_and_goal_baseline");
    }
    bool pendingGoal=false;
    // Dormant gameplay path: no renderer validation, tree walk, or job wait.
    if(!stopping && !showing && consumed && sessionKey && cachedMatch &&
        now-lastMatchSample<2000) {
        int home=0,away=0;
        pendingGoal=read_score(home,away) && goals.update(now,home,away);
        if(!pendingGoal) return;
    }
    uintptr_t impl=0;
    if (!same((uintptr_t)batch,image+0x2214500) || !get((uintptr_t)batch+0x10,impl) || !impl) return;
    batchImpl=impl;
    if (stopping) { cleanup(); return; }
    // Preload in the first available batch while the player tables are still loading.
    if(!showing)preload(now);
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
        candidateSince=now; kickoffSince=0; goals=PyroGoals{}; goalShow=false; lifecycle=PyroLifecycle{}; paletteHome=0;paletteEffect=0;
        log_event("MATCH_DETECTED automatic_intro_armed");
    }
    if (configured && (showing || !consumed) && !owned()) {
        const bool wasIntro=showing && !goalShow;
        forget_resource(); consumed=wasIntro?false:!zero; candidateSince=now;assetSince=0;
        log_event("RESOURCE_REBUILD rearm_pending_show_without_stale_pointers");
    }
    int h=0,a=0;
    if ((pendingGoal || (read_score(h,a) && goals.update(now,h,a))) && enabled) {
        cleanup(); consumed=false; candidateSince=now; kickoffSince=0; goalShow=true;
        log_event("HOME_GOAL_CONFIRMED automatic_show_armed");
    }
    if (!enabled) return;
    if (showing) {
        if (!kickoffSince && gameplay_present()) kickoffSince=now;
        if (pyro_show_expired(now,showStarted,goalShow)) { finish_naturally(); consumed=true; return; }
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
        for(int i=0;i<active_count();++i) {
            if(emitterStarted[i] && !emitterDraining[i] && pyro_drain_due(now,showStarted,goalShow,i)) {
                if(!waited) {wait_jobs();waited=true;}
                if(!valid_slot(i)) {cleanup();consumed=true;return;}
                // Native state 2 suppresses new emission but continues particle updates.
                ((Slot)(image+0x441c980))((void*)activeManager,handles[i]);
                emitterDraining[i]=true;
                if(i%2==0)log_event("SHOW_DRAIN_STEP paired_sources_stop_emitting existing_particles_fade");
            }
        }
        return;
    }
    if (consumed) return;
    if (!configured) {
        if (now-candidateSince<100) return;
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
#include "native_signatures.h"
static DWORD WINAPI install_worker(void*) {
    for (int attempt=0;attempt<600 && !stopping;++attempt) {
        uintptr_t target=0;
        bool acceptable=get(image+0x2214520,target) && target==image+0x43f14e0;
        if (check_signatures(image) && acceptable) {
            original=(Draw)target;
            if (swap((void*)original,(void*)draw_hook)) {
                log_event("installed automatic_intro_and_home_goals smoke_layers=2 no_hotkeys finite_confetti no_instance_delete"); return 0;
            }
        }
        Sleep(200);
    }
    log_event("INSTALL_TIMEOUT loaded_code_or_render_slot_unavailable"); return 0;
}
extern "C" __declspec(dllexport) unsigned int WINAPI Fifa16ModGetApiVersion() { return 1; }
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char* root) {
    if (!root || InterlockedCompareExchange(&started,1,0)) return FALSE;
    _snprintf_s(logPath,MAX_PATH,_TRUNCATE,"%s\\..\\logs\\flamengo_pyro.log",root);
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
