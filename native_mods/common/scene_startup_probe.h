#pragma once
#include "scene_lua.h"
#include "scene_startup_recovery.h"

struct SceneStartupSample { bool known=false,opening=false,suspended=false; };
inline SceneStartupSample scene_startup_sample(uintptr_t image) {
    uintptr_t state=0,vtable=0,stats=0,pagePointer=0;
    unsigned char ready=0,replay=0;int sports=-1,clock=-1;
    if(!scene_lua_read(image+0x3517c10,state)||
       !scene_lua_read(state,vtable)||vtable!=image+0x20ff390||
       !scene_lua_read(state+8,ready)||!scene_lua_read(state+0x39,replay)||
       !scene_lua_read(state+0x3c,sports)||
       !scene_lua_read(image+56299464,stats)||!stats||
       !scene_lua_read(stats+5500,clock)||clock<0||clock>100000000)return {};
    if(!scene_lua_read(image+58757168,pagePointer)||!pagePointer)return {};
    const unsigned offsets[]={232,192,136,472};
    for(unsigned offset:offsets)
        if(!scene_lua_read(pagePointer+offset,pagePointer)||!pagePointer)return {};
    char page[64]{};
    if(!scene_lua_read(pagePointer,page)||!std::memchr(page,0,sizeof(page)))return {};
    for(char& c:page)if(c>='A'&&c<='Z')c=(char)(c+32);
    const bool suspended=replay||std::strstr(page,"game/screens/pause/")||
        std::strstr(page,"game/screens/instantreplay/")||
        !std::strcmp(page,"game/screens/fluxhub/fluxhub");
    const bool matchPage=!page[0]||!std::strncmp(page,"game/screens/tv/",16)||
        !std::strcmp(page,"game/screens/misc/stadiumpan");
    return {true,ready!=0&&sports==2&&clock==0&&matchPage,suspended};
}
struct SceneStartupProbe {
    SceneStartupRecovery recovery;
    uint64_t nextSample=0;
    bool poll(uintptr_t image,uint64_t now) {
        if(now<nextSample)return false;
        nextSample=now+250;
        const auto sample=scene_startup_sample(image);
        return recovery.poll(now,sample.known,sample.opening,sample.suspended);
    }
    bool confirm(bool ready){return recovery.confirm(ready);}
    bool take_timeout(){const bool result=recovery.expired;recovery.expired=false;return result;}
};
