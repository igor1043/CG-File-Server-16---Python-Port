#pragma once
#include <stdint.h>

// A cached ready bit is insufficient after a native resource cycle. Only
// retry the observed inconsistent state: a requested, initialized on-pitch
// player with every LOD unready and no outstanding asset handles at all.
struct PlayerResourceRetry {
    uintptr_t object=0,impl=0,composite=0;
    int player=-1;
    uint64_t since=0,next=0;
    unsigned attempts=0;
    bool repaired=false;
    bool observe(uint64_t now,uintptr_t o,uintptr_t p,uintptr_t c,int id,bool stalled) {
        if(object!=o||impl!=p||composite!=c||player!=id){*this={};object=o;impl=p;composite=c;player=id;}
        if(!stalled){since=0;return false;}
        if(!since)since=now;
        if(now-since<1500||now<next||attempts>=2)return false;
        ++attempts;next=now+5000;repaired=true;return true;
    }
};

#ifndef PLAYER_RESOURCE_POLICY_ONLY
template<class T>static T resource_get(uintptr_t at){T value{};get(at,value);return value;}
static PlayerResourceRetry playerResourceRetries[58];
static uint64_t playerResourcePoll=0;
static uintptr_t playerResourceMatch=0;
static bool resource_match_page() {
    auto p=resource_get<uintptr_t>(image+0x3809030);
    const unsigned offsets[]={232u,192u,136u,472u};
    for(unsigned offset:offsets){p=resource_get<uintptr_t>(p+offset);if(!p)return false;}
    char page[128]{};
    if(!readable(p,sizeof page))return false;
    memcpy(page,(void*)p,sizeof page);
    if(!memchr(page,0,sizeof page))return false;
    for(auto& c:page)if(c>='A'&&c<='Z')c=char(c-'A'+'a');
    return !page[0]||!strcmp(page,"game/screens/match/match")||!strcmp(page,"game/screens/fluxhub/fluxhub")||
        !strcmp(page,"game/screens/misc/stadiumpan")||strstr(page,"/instantreplay")||strstr(page,"/teamsheets/");
}

static bool player_resource_empty(uintptr_t composite) {
    if(!composite||resource_get<unsigned char>(composite+16))return false;
    const uintptr_t resource=resource_get<uintptr_t>(composite);
    if(!resource||resource_get<unsigned char>(resource+0x50)||resource_get<unsigned char>(resource+0x51))return false;
    const uintptr_t first=resource_get<uintptr_t>(resource+0x58),end=resource_get<uintptr_t>(resource+0x60);
    if(first<0x10000||end<=first||end-first>72*128||(end-first)%72||!readable(first,end-first))return false;
    for(uintptr_t at=first;at<end;at+=72)if(resource_get<uintptr_t>(at+0x28))return false;
    return true;
}
static void recover_player_resources(uint64_t now) {
    if(now<playerResourcePoll)return;
    playerResourcePoll=now+250;
    if(!resource_match_page())return;
    const auto manager=resource_get<uintptr_t>(image+0x3517420),world=resource_get<uintptr_t>(manager+8),game=resource_get<uintptr_t>(world+0x10);
    if(resource_get<uintptr_t>(manager)!=image+0x2226730||resource_get<uintptr_t>(world)!=image+0x2225d90||resource_get<uintptr_t>(game)!=image+0x2309370)return;
    if(playerResourceMatch!=game){playerResourceMatch=game;for(auto& retry:playerResourceRetries)retry={};}
    const auto phase=resource_get<int>(resource_get<uintptr_t>(image+0x3517c10)+0x3c);
    if(phase<0||phase>15||phase==1||phase==13)return;
    // Native prepare opens its own asset batch. Never nest it inside an
    // in-flight batch from FIFA or another resource provider.
    if(resource_get<uintptr_t>(image+0x3616ba8))return;
    const unsigned char expected[]={0x48,0x89,0x5c,0x24,0x20,0x55,0x48,0x83,0xec,0x20};
    if(!readable(image+0x437c2d0,sizeof expected)||memcmp((void*)(image+0x437c2d0),expected,sizeof expected))return;
    for(unsigned slot=0;slot<58;++slot){
        const auto object=resource_get<uintptr_t>(image+0x34fbf70+slot*8);
        if(!object||resource_get<uintptr_t>(object)!=image+0x2207230)continue;
        const auto impl=resource_get<uintptr_t>(object+0x18);
        const int id=resource_get<int>(image+0x34fbda0+slot*8),side=resource_get<int>(image+0x34fbda0+slot*8+4);
        if(!impl||resource_get<int>(impl)!=static_cast<int>(slot)||id<=0||side<0||side>1)continue;
        const auto first=resource_get<uintptr_t>(impl+8);
        bool stalled=(resource_get<unsigned>(impl+0x80)&1)!=0&&resource_get<unsigned char>(impl+0x84)&&resource_get<unsigned char>(impl+0x86);
        for(unsigned lod=0;stalled&&lod<4;++lod)stalled=player_resource_empty(resource_get<uintptr_t>(impl+8+lod*8));
        auto& retry=playerResourceRetries[slot];
        if(retry.repaired&&!stalled&&resource_get<unsigned char>(first+16)){
            log_event("player_resources_recovered slot=%u player=%d attempts=%u",slot,id,retry.attempts);retry.repaired=false;
        }
        if(!retry.observe(now,object,impl,first,id,stalled))continue;
        if(resource_get<uintptr_t>(image+0x34fbf70+slot*8)!=object||resource_get<uintptr_t>(object+0x18)!=impl||resource_get<uintptr_t>(impl+8)!=first)continue;
        log_event("player_resources_retry slot=%u player=%d side=%d attempt=%u reason=ready_cached_but_all_lods_empty",slot,id,side,retry.attempts);
        // This is FIFA's own deferred prepare/reload, on the scene owner
        // callback. It queues resources; no visibility bit or asset is faked.
        reinterpret_cast<void(__fastcall*)(void*,bool)>(image+0x437c2d0)((void*)object,true);
    }
}
#endif
