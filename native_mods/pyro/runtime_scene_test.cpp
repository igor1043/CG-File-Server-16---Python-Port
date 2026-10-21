// Runs the real tick against a private fake FIFA memory image. Native calls are
// counted stubs; this process never opens or writes to a running FIFA process.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <cstring>
#include <filesystem>
static ULONGLONG testNow=10000;
static ULONGLONG WINAPI test_tick_count() {return testNow;}
#define GetTickCount64 test_tick_count
#include "stadium_pyrotechnics.cpp"
#undef GetTickCount64
struct Memory {alignas(16) unsigned char data[0x1800]{};uintptr_t address() {return (uintptr_t)data;}};
static Memory fixtureManager,worldObject,gameObject,registryObject,teamObjects[2],teamStats[2],pairsObject;
static Memory cacheObject,scoreRows,clockObject,gameClock,pageObjects[5],batchObject,implObject;
static Memory particleObject,particleState,particleManager,effectObjects[2],resourceObject;
static Memory nodes[emitterCount],instances[emitterCount],groups[emitterCount],groupPointers[emitterCount];
static unsigned stops=0,clears=0,triggers=0,plays=0,waits=0;
static bool ready=false;
template<class T> static void put(uintptr_t address,T value) {memcpy((void*)address,&value,sizeof(value));}
static void __fastcall fake_wait(void*) {++waits;}
static unsigned char __fastcall fake_ready(void*) {return ready?1:0;}
static void __fastcall fake_stop(void*,int id) {++stops;put(instances[id].address()+0x284,4);}
static void __fastcall fake_clear(void*,int id) {++clears;put(groups[id].address()+0x1c,0);}
static void __fastcall fake_trigger(void*,int) {++triggers;}
static void __fastcall fake_play(void*,int id) {++plays;put(instances[id].address()+0x284,0);}
static void __fastcall fake_drain(void*,int id) {put(instances[id].address()+0x284,2);}
static void __fastcall fake_matrix(void*,int id,const float* matrix) {memcpy((void*)(instances[id].address()+0x10),matrix,64);}
template<class F> static void stub(uintptr_t rva,F target) {
    unsigned char jump[12]={0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xe0};
    const auto address=(uintptr_t)target;memcpy(jump+2,&address,8);memcpy((void*)(image+rva),jump,sizeof(jump));
}
static void page(const char* text) {strcpy_s((char*)pageObjects[4].data,64,text);}
static void advance(uint64_t ms,ULONGLONG wallMs=500,bool replay=false) {
    testNow+=wallMs;put(gameClock.address()+0x20,(double)ms);put(gameClock.address()+0x39,(unsigned char)replay);
    tick((void*)batchObject.address());
}
static void cache_palette(int effect=0) {paletteHome=1043;paletteEffect=effectObjects[effect].address();}
static void setup() {
    image=(uintptr_t)VirtualAlloc(nullptr,0x5000000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);assert(image);
    stub(0x43f31d0,fake_wait);stub(0x4383e30,fake_ready);stub(0x441c720,fake_stop);
    stub(0x441c940,fake_clear);stub(0x441ce00,fake_trigger);stub(0x441c8d0,fake_play);
    stub(0x441c980,fake_drain);stub(0x441cd90,fake_matrix);
    put(image+0x3517420,fixtureManager.address());put(fixtureManager.address(),image+0x2226730);
    put(fixtureManager.address()+8,worldObject.address());put(worldObject.address(),image+0x2225d90);
    put(worldObject.address()+0x10,gameObject.address());put(gameObject.address(),image+0x2309370);
    put(gameObject.address()+0x20,registryObject.address());
    put(registryObject.address()+8+15*32,15);put(registryObject.address()+8+15*32+16,2);
    put(registryObject.address()+8+15*32+24,pairsObject.address());
    for(int i=0;i<2;++i) {
        put(pairsObject.address()+i*16+8,teamObjects[i].address());put(teamObjects[i].address(),image+0x22fe9f0);
        put(teamObjects[i].address()+0x30,registryObject.address());put(teamObjects[i].address()+0x58,i);
        put(teamObjects[i].address()+0x50,teamStats[i].address());put(teamStats[i].address()+0x80,1043+i);
    }
    put(image+0x34a30b0,cacheObject.address());put(cacheObject.address(),image+0x21141f0);
    put(cacheObject.address()+8,scoreRows.address());
    for(int index:{6,21})put(scoreRows.address()+index*16+8,image+0x3acc040);
    put(image+56299464,clockObject.address());
    put(image+0x3517c10,gameClock.address());put(gameClock.address(),image+0x20ff390);
    put(gameClock.address()+0x3c,2); // Native kickoff, as required for a true restart.
    put(image+0x20ff390+0x30,image+0x39fee10);put(image+0x20ff390+0x70,image+0x3a00d60);
    put(image+58757168,pageObjects[0].address());
    const unsigned offsets[]={232,192,136,472};
    for(int i=0;i<4;++i)put(pageObjects[i].address()+offsets[i],pageObjects[i+1].address());
    put(batchObject.address(),image+0x2214500);put(batchObject.address()+0x10,implObject.address());
    put(image+0x3504500+31*8,particleObject.address());put(particleObject.address(),image+0x2209f70);
    put(particleObject.address()+16,particleState.address());put(particleState.address(),31);
    memcpy((void*)(particleState.address()+8),effectName,sizeof(effectName));
    put(particleState.address()+0x264,100);put(particleState.address()+0x50,resourceObject.address());
    put(particleState.address()+0x58,particleManager.address());put(particleManager.address()+16,effectObjects[0].address());
    put(particleManager.address()+0x30,nodes[0].address());
    for(int i=0;i<emitterCount;++i) {
        put(particleState.address()+0x60+i*4,i);put(nodes[i].address()+0x20,i);
        put(nodes[i].address()+0x28,instances[i].address());
        if(i+1<emitterCount)put(nodes[i].address(),nodes[i+1].address());
        put(instances[i].address()+0x238,groupPointers[i].address());put(instances[i].address()+0x240,1);
        put(groupPointers[i].address(),groups[i].address());
    }
    char executable[MAX_PATH]{};assert(GetModuleFileNameA(nullptr,executable,MAX_PATH));
    const auto root=std::filesystem::path(executable).parent_path();
    std::filesystem::create_directories(root/"ModCarrerMode/config");
    FILE* config=nullptr;assert(!fopen_s(&config,(root/"ModCarrerMode/config/match_presentation.ini").string().c_str(),"wb"));
    fputs("[match]\npyrotechnics=1\nentrance=1\ngoal=1\n",config);fclose(config);
    strcpy_s(logPath,(root/"runtime_scene_test.log").string().c_str());assert(presentationConfig.initialize());
    for(int& handle:handles)handle=-1;
}
int main() {
    setup();
    page("game/screens/playNow/KickOffHub");advance(100);
    assert(!showing && !session.key && !configured && triggers==0);
    page("game/screens/misc/StadiumPan");advance(500);
    assert(session.key && !consumed && !showing); // real opening, assets not ready yet
    ready=true;cache_palette();advance(600);
    assert(showing && !goalShow && triggers==2);
    advance(3000,2500);assert(showing && triggers==20);
    const auto initialStops=stops,initialClears=clears;
    for(int i=0;i<emitterCount;++i)put(groups[i].address()+0x1c,25);
    // Exact failing transition: blank match page with temporarily absent teams.
    page("");put(registryObject.address()+8+15*32+16,0);advance(3100);
    assert(showing && stops==initialStops && clears==initialClears);
    put(registryObject.address()+8+15*32+16,2);advance(3200);
    assert(showing && stops==initialStops);
    // A missing secondary score/Lua sample must not stop an owned show either.
    put(scoreRows.address()+21*16+8,(uintptr_t)0);advance(3300);
    assert(showing && stops==initialStops && clears==initialClears);
    put(scoreRows.address()+21*16+8,image+0x3acc040);advance(3400);
    page("game/screens/fluxHub/FluxHub");advance(3400);
    const uint64_t elapsed=showClock.elapsed;
    advance(3400,60000);assert(showing && showClock.elapsed==elapsed);
    // Replay can have a blank page and backwards scene time.
    page("");const auto beforeReplay=triggers;advance(100,500,true);
    assert(showing && triggers==beforeReplay+20 && stops==initialStops && clears==initialClears);
    int live=0;assert(get(groups[0].address()+0x1c,live) && live==25);
    advance(20000,60000,true);assert(showClock.elapsed==elapsed);
    const auto seekTriggers=triggers;
    advance(3400);assert(showing && triggers==seekTriggers+20 && showClock.elapsed==elapsed);
    advance(4000,600);assert(showClock.elapsed==elapsed+600);
    // Native effect replacement restores the same event and remaining duration.
    put(particleManager.address()+16,effectObjects[1].address());advance(4100);
    assert(recoveringShow && !showing && !consumed);
    cache_palette(1);const auto kept=showClock.elapsed;advance(4200);
    assert(showing && !recoveringShow && consumed && showClock.elapsed==kept);
    // Restart before kickoff, score/football clock both still zero.
    advance(8000);advance(50);advance(600);
    assert(!goalShow && !recoveringShow && !consumed && session.key);
    cache_palette(1);advance(700);assert(showing && showClock.elapsed==0);
    // A real home goal triggers all 12 rear machines; away goals do not.
    put(scoreRows.address()+21*16,1);advance(1000);advance(1200);
    assert(showing && goalShow && active_count()==12 && showClock.elapsed==0);
    const auto homeGoalTriggers=triggers;
    put(scoreRows.address()+6*16,1);advance(1400);advance(1600);
    assert(triggers==homeGoalTriggers);
    const auto goalStops=stops,goalClears=clears;
    for(int i=0;i<12;++i)put(groups[i].address()+0x1c,40);
    advance(500,500,true);advance(20000,60000,true);advance(1600);
    assert(showing && goalShow && stops==goalStops && clears==goalClears);
    advance(15000,13400);advance(27000,12000);assert(!showing && consumed && stops==goalStops && clears==goalClears);
    const auto idleWaits=waits,idleTriggers=triggers;
    LARGE_INTEGER before{},after{},frequency{};QueryPerformanceCounter(&before);QueryPerformanceFrequency(&frequency);
    for(unsigned i=0;i<2000;++i)advance(27100+i*100,100);
    QueryPerformanceCounter(&after);
    assert(waits==idleWaits && triggers==idleTriggers && stops==goalStops && clears==goalClears);
    std::printf("Dormant gameplay: 2000 ticks, zero native particle/job calls; mean CPU %.4f ms (synthetic process, not FPS)\n",
        1000.0*(double)(after.QuadPart-before.QuadPart)/(double)frequency.QuadPart/2000.0);
    page("game/screens/playNow/KickOffHub");advance(28000);
    assert(!showing && !session.key && !recoveringShow);
    const auto menuTriggers=triggers;advance(29000);
    assert(triggers==menuTriggers);
    // Reproduce the actual regression: native time advances by ~60 units/s,
    // while real monotonic milliseconds control the 60s/25s show boundaries.
    put(scoreRows.address()+21*16,0);put(scoreRows.address()+6*16,0);
    page("game/screens/misc/StadiumPan");ready=false;advance(0);
    ready=true;cache_palette(1);advance(0,100);assert(showing && !goalShow);
    const auto openingStart=testNow;
    for(uint64_t ms=100;ms<=60000;ms+=100) {
        advance(ms*60/1000,100);
        if(ms<60000)assert(showing);
    }
    assert(testNow-openingStart==60000 && !showing && consumed);
    put(scoreRows.address()+21*16,1);advance(3610,100);advance(3616,100);
    assert(showing && goalShow);
    const auto goalStart=testNow;
    for(uint64_t ms=100;ms<=25000;ms+=100) {
        advance(3616+ms*60/1000,100);
        if(ms<25000)assert(showing);
    }
    assert(testNow-goalStart==25000 && !showing && consumed);
    const auto endTriggers=triggers,endWaits=waits;
    advance(5200,1000);assert(!showing && triggers==endTriggers && waits==endWaits);
    std::puts("Real tick with native clock at 60 units/s: opening stops at 60000 real ms, goal at 25000 real ms, no idle retrigger: PASS");
    std::puts("Real tick: intro pan, blank-page team gap, score gap, long pause, native replay, resource recovery, 0:0 restart, home/away goals and natural fade: PASS");
    // User-selected masks and duration are read before the next event; current
    // shows retain their settings through replay and native resource recovery.
    char executable[MAX_PATH]{};assert(GetModuleFileNameA(nullptr,executable,MAX_PATH));
    const auto config=(std::filesystem::path(executable).parent_path()/"ModCarrerMode/config/match_presentation.ini").string();
    assert(WritePrivateProfileStringA("match","smoke_entrance_seconds","15",config.c_str()));
    assert(WritePrivateProfileStringA("match","smoke_goal_seconds","20",config.c_str()));
    const unsigned introMask=(1u<<2)|(1u<<18),goalMask=(1u<<1)|(1u<<10);
    char maskText[32]{};sprintf_s(maskText,"%u",introMask);
    assert(WritePrivateProfileStringA("match","smoke_entrance_emitters",maskText,config.c_str()));
    sprintf_s(maskText,"%u",goalMask);
    assert(WritePrivateProfileStringA("match","smoke_goal_emitters",maskText,config.c_str()));
    page("game/screens/playNow/KickOffHub");advance(0);
    put(scoreRows.address()+21*16,0);put(scoreRows.address()+6*16,0);
    page("game/screens/misc/StadiumPan");ready=false;advance(0);
    const auto selectedIntroTriggers=triggers;
    ready=true;cache_palette(1);advance(0,100);
    assert(showing && !goalShow && showLengthMs==15000 && showEmitterMask==introMask);
    assert(triggers==selectedIntroTriggers); // The immediate first pair is disabled.
    advance(180,3000);assert(triggers==selectedIntroTriggers+2);
    for(int i=0;i<active_count();++i)assert(emitterStarted[i]==(i==2 || i==18));
    assert(WritePrivateProfileStringA("match","smoke_entrance_seconds","120",config.c_str()));
    advance(240,1000);assert(showLengthMs==15000); // No mid-event extension.
    advance(900,11000);assert(!showing && consumed);
    put(scoreRows.address()+21*16,1);advance(910,100);advance(920,100);
    assert(showing && goalShow && showLengthMs==20000 && showEmitterMask==goalMask);
    for(int i=0;i<active_count();++i)assert(emitterStarted[i]==(i==1 || i==10));
    const auto selectedGoalTriggers=triggers;
    advance(2120,20000);assert(!showing && triggers==selectedGoalTriggers);
    assert(WritePrivateProfileStringA("match","smoke_goal_emitters","0",config.c_str()));
    advance(2200,500);put(scoreRows.address()+21*16,2);advance(2300);advance(2400);
    assert(!showing && triggers==selectedGoalTriggers);
    std::puts("Selected intro/goal emitters, 15s/20s actual event bounds, zero mask and frozen current-show options: PASS");
    // The penalty-order page belongs to postGameFlow but is not match exit.
    assert(WritePrivateProfileStringA("match","smoke_goal_emitters","4095",config.c_str()));
    page("");put(gameClock.address()+0x3c,7);advance(2500);
    put(scoreRows.address()+21*16,3);advance(2600);advance(2700);
    assert(showing && goalShow); // An ordinary in-match penalty goal still emits.
    put(clockObject.address()+5500,7200);advance(2800);
    put(clockObject.address()+5500,0);put(gameClock.address()+0x3c,1);
    advance(0);advance(50,600);assert(showing && goalShow); // End-half rewind is not Restart.
    const auto beforeShootout=triggers;
    const auto matchKey=session.key;
    page("game/screens/postGameFlow/PenaltyKickSelect");advance(100);
    assert(shootout.active && !showing && !recoveringShow && consumed && session.key==matchKey);
    const auto clearedAtShootout=clears;
    page("");put(gameClock.address()+0x3c,11);advance(200);
    for(int i=0;i<6;++i) {
        put(scoreRows.address()+21*16,4+i);advance(300+i*100);
        put(gameClock.address()+0x3c,14);advance(350+i*100);
        page("game/screens/fluxHub/FluxHub");advance(400+i*100);
        page("");advance(450+i*100,500,true);advance(500+i*100);
    }
    assert(shootout.active && !showing && triggers==beforeShootout && clears==clearedAtShootout);
    page("game/screens/playNow/KickOffHub");advance(1200);
    assert(!shootout.active && !session.key);
    put(scoreRows.address()+21*16,0);put(scoreRows.address()+6*16,0);
    put(gameClock.address()+0x3c,2);page("game/screens/misc/StadiumPan");ready=false;advance(0);
    ready=true;cache_palette(1);advance(0,100);assert(showing && !goalShow);
    const auto beforeNativeShootout=triggers;
    page("");put(gameClock.address()+0x3c,11);advance(100);
    assert(shootout.active && !showing && triggers==beforeNativeShootout);
    std::puts("Shootout: selector/native phase, retained session, no intro or scored-kick smoke, pause/replay and next-match recovery: PASS");
    VirtualFree((void*)image,0,MEM_RELEASE);
}
