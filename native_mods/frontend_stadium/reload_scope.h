#pragma once
#include <cstdint>
#include "menu_page.h"

namespace frontend_stadium {
// StatisticsData and BackgroundDP can have different owners, even inside
// the same FluxHub. Career readiness alone cannot authorize background UI.
struct ReloadScope {
    uintptr_t view=0,background=0,backgroundRegistry=0,commands=0;
    uintptr_t careerService=0,careerRegistry=0;
    uint32_t epoch=0,team=0,ownerThread=0,careerThread=0;
    PageKind page=PageKind::Transition;
    bool career=false,frontendCallback=false,resolved=false;
    bool valid()const{
        return frontendCallback&&resolved&&ownerThread&&view&&background
            &&backgroundRegistry&&commands&&team&&isBackgroundPage(page)
            &&(career||(page!=PageKind::Hub&&page!=PageKind::ClubBrowser&&page!=PageKind::PlayerCareer))
            &&(!career||(epoch&&careerService&&careerRegistry&&careerThread));
    }
    bool same(const ReloadScope& other)const{
        return view==other.view&&background==other.background
            &&backgroundRegistry==other.backgroundRegistry&&commands==other.commands
            &&careerService==other.careerService&&careerRegistry==other.careerRegistry
            &&epoch==other.epoch&&team==other.team&&ownerThread==other.ownerThread
            &&careerThread==other.careerThread&&page==other.page&&career==other.career
            &&frontendCallback==other.frontendCallback&&resolved==other.resolved;
    }
};
inline bool canDispatchReload(const ReloadScope& expected,const ReloadScope& current,int state,bool backgroundReady=false){
    return expected.valid()&&current.valid()&&current.same(expected)
        &&(backgroundReady?state==14:(state==0||state==12));
}
struct ReloadScopeGuard {
    ReloadScope scope{};
    uint64_t since=0;
    bool observed=false;
    void reset(){scope={};since=0;observed=false;}
    bool observe(const ReloadScope& current,uint64_t now){
        if(!current.valid()){reset();return false;}
        if(!observed||!scope.same(current)||now<since){
            scope=current;since=now;observed=true;return false;
        }
        // Debounce page/context identity, not extractor completion time.
        // Reusing the same FluxHub address across saves is common.
        return now-since>=500;
    }
};
}
