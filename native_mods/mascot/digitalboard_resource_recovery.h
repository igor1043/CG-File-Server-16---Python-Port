#pragma once
// Resource preparation only. Never change board visibility, numbers, graph
// selection or the referee's animation. Resolve the current Lua object anew.
static PlayerResourceRetry digitalBoardRetry;
static uintptr_t digitalBoardMatch=0;
static uint64_t digitalBoardPoll=0;
static uintptr_t resource_lua_field(uintptr_t table,const char* key) {
    const unsigned power=resource_get<unsigned char>(table+11);
    if(resource_get<unsigned char>(table+8)!=5||power>14)return 0;
    const auto nodes=resource_get<uintptr_t>(table+32);const size_t count=size_t(1)<<power,length=strlen(key);
    if(!readable(nodes,count*40))return 0;
    // The scene callback owns this Lua snapshot. Check the node array once;
    // do not issue a system memory query for every empty hash bucket.
    for(size_t i=0;i<count;++i){
        const auto node=(const unsigned char*)(nodes+i*40);int tag=0;memcpy(&tag,node+24,4);
        if(tag!=4)continue;
        uintptr_t text=0;memcpy(&text,node+16,8);
        if(resource_get<size_t>(text+16)==length&&readable(text+24,length)&&!memcmp((void*)(text+24),key,length))return nodes+i*40;
    }
    return 0;
}
static uintptr_t digitalboard_object() {
    const auto lua=resource_get<uintptr_t>(image+0x3613fd0);
    if(resource_get<int>(lua+0x80)!=5)return 0;
    auto value=resource_lua_field(resource_get<uintptr_t>(lua+0x78),"gRenderObj");
    if(resource_get<int>(value+8)!=5)return 0;
    value=resource_lua_field(resource_get<uintptr_t>(value),"digitalboard");
    if(resource_get<int>(value+8)!=5)return 0;
    const auto table=resource_get<uintptr_t>(value);
    const auto power=resource_get<unsigned char>(table+11);
    if(power>8)return 0;
    const auto nodes=resource_get<uintptr_t>(table+32);
    for(unsigned i=0;i<(1u<<power);++i){
        const auto at=nodes+i*40;
        if(resource_get<int>(at+24)==3&&resource_get<double>(at+16)==0&&resource_get<int>(at+8)==2)return resource_get<uintptr_t>(at);
    }
    return 0;
}
static void recover_digitalboard_resources(uint64_t now) {
    if(now<digitalBoardPoll)return;
    digitalBoardPoll=now+250;
    if(!playerResourceMatch||!resource_match_page())return;
    const auto manager=resource_get<uintptr_t>(image+0x3517420),world=resource_get<uintptr_t>(manager+8),game=resource_get<uintptr_t>(world+0x10);
    if(game!=playerResourceMatch||resource_get<uintptr_t>(game)!=image+0x2309370||resource_get<uintptr_t>(image+0x3616ba8))return;
    const int phase=resource_get<int>(resource_get<uintptr_t>(image+0x3517c10)+0x3c);
    if(phase<0||phase>15||phase==1||phase==13)return;
    if(digitalBoardMatch!=playerResourceMatch){digitalBoardMatch=playerResourceMatch;digitalBoardRetry={};}
    const auto object=digitalboard_object();
    if(!object||resource_get<uintptr_t>(object)!=image+0x2211960)return;
    const auto impl=resource_get<uintptr_t>(object+0x20);
    if(resource_get<unsigned>(impl+0x18)!=1)return;
    const auto composite=resource_get<uintptr_t>(resource_get<uintptr_t>(impl+0x20));
    if(digitalBoardRetry.object==object&&digitalBoardRetry.impl==impl&&digitalBoardRetry.composite==composite&&digitalBoardRetry.repaired&&
       !resource_get<unsigned char>(composite+16)&&resource_get<unsigned char>(resource_get<uintptr_t>(composite)+0x50)){
        const unsigned char initialize[]={0x55,0x53,0x48,0x8d,0xac,0x24,0xd8,0xfd};
        if(readable(image+0x4add100,sizeof initialize)&&!memcmp((void*)(image+0x4add100),initialize,sizeof initialize))
            reinterpret_cast<int(__fastcall*)(void*)>(image+0x4add100)((void*)composite);
    }
    const bool empty=player_resource_empty(composite);
    if(digitalBoardRetry.repaired&&!empty&&resource_get<unsigned char>(composite+16)){
        log_event("digitalboard_resources_recovered attempts=%u",digitalBoardRetry.attempts);digitalBoardRetry.repaired=false;
    }
    if(!digitalBoardRetry.observe(now,object,impl,composite,0,empty))return;
    // SetDBInt uses the same native parameter publication as gRenderables.
    // It invalidates a stale unloaded binding before its normal prepare.
    const unsigned char expected[]={0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10};
    if(!readable(image+0x4ad7f80,sizeof expected)||memcmp((void*)(image+0x4ad7f80),expected,sizeof expected))return;
    const unsigned char prepare[]={0x53,0x48,0x83,0xec,0x20,0x48,0x8b,0x59,0x20,0x80};
    if(!readable(image+0x4ad7e50,sizeof prepare)||memcmp((void*)(image+0x4ad7e50),prepare,sizeof prepare))return;
    if(digitalboard_object()!=object||resource_get<uintptr_t>(object+0x20)!=impl)return;
    log_event("digitalboard_resources_retry attempt=%u reason=empty_native_assets visibility=unchanged",digitalBoardRetry.attempts);
    reinterpret_cast<void(__fastcall*)(void*,const char*,int)>(image+0x4ad7f80)((void*)impl,"server16_board_recovery",digitalBoardRetry.attempts);
    reinterpret_cast<void(__fastcall*)(void*,bool)>(image+0x4ad7e50)((void*)object,true);
}
