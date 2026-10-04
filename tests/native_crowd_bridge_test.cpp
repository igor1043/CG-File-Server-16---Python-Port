// Validated fake AttribDB allocations only. Does not open or inject FIFA.
#include "../server16_py/d3d_overlay/crowd_bridge.cpp"
#include <cassert>
#include <limits>
int wmain(int argc,wchar_t **argv) {
    assert(argc==1 || argc==2);
    if (argc==2) {
        // Inspect the real reference PE without DllMain or plugin workers.
        HMODULE reference=LoadLibraryExW(argv[1],nullptr,DONT_RESOLVE_DLL_REFERENCES);
        assert(reference && known_plugin(reference));
        FreeLibrary(reference);
    }
    static_assert(sizeof(CrowdShared)==52,"Crowd Python/native layout mismatch");
    assert(!known_plugin(nullptr));
    assert(writable(PAGE_READWRITE));
    assert(!writable(PAGE_READONLY));
    assert(!writable(PAGE_READWRITE|PAGE_GUARD));
    BYTE *allocation=(BYTE *)VirtualAlloc(nullptr,0x100000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    assert(allocation);
    BYTE *record=allocation+RECORD_OFFSET;
    memcpy(record,RECORD_KEY,8); float initial=.65f;
    memcpy(record+8,&initial,4);
    locate_targets();
    assert(g_target_count==1 && g_targets[0].allocation==allocation);
    allocation[RECORD_OFFSET-1]=0xab; record[12]=0xcd;
    CrowdTarget target={allocation,initial,.2f,true}; float current=0;
    assert(read_target(target,current) && fabsf(current-initial)<.0001f);
    assert(write_target(target,.2f));
    assert(allocation[RECORD_OFFSET-1]==0xab && record[12]==0xcd);
    assert(!write_target(target,-.1f));
    assert(!write_target(target,1.21f));
    assert(!write_target(target,std::numeric_limits<float>::quiet_NaN()));
    g_targets[0]=target; g_target_count=1;
    restore_targets();
    assert(read_target(target,current) && fabsf(current-initial)<.0001f);
    assert(write_target(g_targets[0],0)); // An empty stadium is supported.
    assert(write_target(g_targets[0],1));
    // An unrelated writer changed the value: do not overwrite its new value.
    g_targets[0].owned=true; g_targets[0].written=.2f;
    restore_targets();
    assert(read_target(target,current) && current==1);
    record[0]^=1;
    assert(!read_target(target,current));
    assert(!write_target(target,.4f));
    record[0]^=1;
    CrowdShared channel={}; g_crowd=&channel;
    channel.owner_pid=GetCurrentProcessId(); channel.game_pid=GetCurrentProcessId();
    channel.heartbeat=GetTickCount(); channel.phase=1; channel.requested_percent=56;
    InterlockedExchange(&g_manual,56);
    assert(crowd_profile("crowd","static_factor_percent",-1,"nonexistent.ini")==56);
    assert(crowd_profile("other","static_factor_percent",17,"nonexistent.ini")==17);
    channel.phase=0;
    assert(crowd_profile("crowd","static_factor_percent",17,"nonexistent.ini")==17);
    channel.phase=1; channel.heartbeat=GetTickCount()-3000;
    assert(crowd_profile("crowd","static_factor_percent",17,"nonexistent.ini")==17);
    channel.heartbeat=GetTickCount(); channel.game_pid++;
    assert(!channel_live());
    g_crowd=nullptr; g_target_count=0;
    VirtualFree(allocation,0,MEM_RELEASE);
    puts("Crowd record validation, 0/100%, restore/ownership and stale channel tests passed");
}
