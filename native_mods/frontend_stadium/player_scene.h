#pragma once
#include "scene_context.h"
namespace frontend_stadium {
// FIFA 577DE45C PrepareFEWorld (435e8c0..435f449) consumes six arrays
// of eight scalar actor descriptors, presentation flags, actor count +dc,
// eight per-actor bytes +e0, and selected actor +fc. No actor/asset pointer
// is retained. Stadium/light (+e8/+ec) always belong to the new route.
struct PlayerScene {
    std::array<unsigned char,0xe8> actors{};
    int selected=-1,club=0;uint32_t epoch=0;bool valid=false;
    void clear(){*this=PlayerScene{};}
    static int integer(const SceneContext&c,size_t at){int v=0;std::memcpy(&v,c.data()+at,4);return v;}
    bool matches(int team,uint32_t generation,int role)const{return valid&&team==club&&generation&&generation==epoch&&(role==0||role==2);}
    void capture(const SceneContext&c,int team,uint32_t generation,int role){
        if(!(role==0||role==2)||team<=0||!generation){clear();return;}
        int count=integer(c,0xdc),focus=integer(c,0xfc);
        if(count<1||count>8||focus< -1||focus>=count){clear();return;}
        std::memcpy(actors.data(),c.data(),actors.size());selected=focus;club=team;epoch=generation;valid=true;
    }
    bool restore(SceneContext&c,int team,uint32_t generation,int role)const{
        if(!matches(team,generation,role))return false;
        std::memcpy(c.data(),actors.data(),actors.size());std::memcpy(c.data()+0xfc,&selected,4);return true;
    }
};
}
