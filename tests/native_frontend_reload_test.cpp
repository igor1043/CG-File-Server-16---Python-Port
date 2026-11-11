#define NOMINMAX
#include <cassert>
#include <cstdio>
#include <map>
#include <string>
#include "../native_mods/frontend_stadium/reload_scope.h"
#include "../native_mods/frontend_stadium/profile_reload.h"
using namespace frontend_stadium;

static ReloadScope careerScope(){
    ReloadScope scope;
    scope.view=0x7f879d70;scope.background=0x100000;scope.backgroundRegistry=0x200000;
    scope.commands=0x300000;scope.careerService=0x400000;scope.careerRegistry=0x500000;
    scope.epoch=8;scope.team=1043;scope.ownerThread=39744;scope.careerThread=15884;
    scope.page=PageKind::Hub;scope.career=scope.frontendCallback=scope.resolved=true;
    return scope;
}
static void capturedCrash(){
    auto scope=careerScope();ReloadScopeGuard guard;
    // PID 18840: the statistics owner (15884) started the background command
    // while its genuine frontend owner was 39744. Career readiness is not UI ownership.
    auto stats=scope;stats.frontendCallback=false;stats.ownerThread=15884;
    assert(!guard.observe(stats,1000)&&!guard.observe(stats,5000));
    assert(!canDispatchReload(stats,stats,0));
    assert(!guard.observe(scope,5000)&&!guard.observe(scope,5499));
    assert(guard.observe(scope,5500));
    assert(canDispatchReload(scope,scope,0)); // Different legitimate owners must not deadlock.
    assert(canDispatchReload(scope,scope,12));
    for(int state:{-1,1,11,13,14,15})assert(!canDispatchReload(scope,scope,state));
    assert(canDispatchReload(scope,scope,14,true));
    assert(!canDispatchReload(scope,scope,11,true));
}
static void reloadAndSwitchSaves(){
    auto original=careerScope();ReloadScopeGuard guard;
    assert(!guard.observe(original,0));assert(guard.observe(original,500));
    auto reloaded=original;++reloaded.epoch; // Same team AND recycled FluxHub address.
    assert(!canDispatchReload(original,reloaded,0));
    assert(!guard.observe(reloaded,1000)&&!guard.observe(reloaded,1499));
    assert(guard.observe(reloaded,1500));
    auto otherSave=reloaded;otherSave.team=567;
    assert(!canDispatchReload(reloaded,otherSave,0));assert(!guard.observe(otherSave,2000));
    assert(guard.observe(otherSave,2500));
    for(auto page:{PageKind::Transition,PageKind::Other}){
        auto gap=otherSave;gap.page=page;assert(!guard.observe(gap,3000));
        assert(!guard.observe(otherSave,4000));assert(guard.observe(otherSave,4500));
    }
    auto changed=otherSave;changed.backgroundRegistry+=8;
    assert(!canDispatchReload(otherSave,changed,0));assert(!guard.observe(changed,5000));
    assert(guard.observe(changed,5500));
    changed.ownerThread++;assert(!guard.observe(changed,6000));assert(guard.observe(changed,6500));
    // A recheck immediately before the call catches mutations after releasing the staging lock.
    auto newCommands=changed;newCommands.commands+=16;
    assert(!canDispatchReload(changed,newCommands,0));
    assert(!guard.observe(changed,1)); // clock reset never authorizes an old sample
}
static void missingIdentity(){
    auto good=careerScope();
    for(unsigned field=0;field<12;++field){
        auto scope=good;
        switch(field){
        case 0:scope.view=0;break;case 1:scope.background=0;break;
        case 2:scope.backgroundRegistry=0;break;case 3:scope.commands=0;break;
        case 4:scope.epoch=0;break;case 5:scope.careerService=0;break;
        case 6:scope.careerRegistry=0;break;case 7:scope.team=0;break;
        case 8:scope.ownerThread=0;break;case 9:scope.careerThread=0;break;
        case 10:scope.resolved=false;break;case 11:scope.frontendCallback=false;break;
        }
        ReloadScopeGuard guard;assert(!scope.valid());
        assert(!guard.observe(scope,1)&&!guard.observe(scope,10000));
        assert(!canDispatchReload(good,scope,0));
    }
    auto menu=good;menu.career=false;menu.epoch=0;menu.careerService=menu.careerRegistry=0;
    menu.careerThread=0;menu.page=PageKind::Menu;
    assert(menu.valid()&&canDispatchReload(menu,menu,0));
    for(auto page:{PageKind::Hub,PageKind::ClubBrowser,PageKind::PlayerCareer}){
        menu.page=page;assert(!menu.valid());
    }
}
static void repeatedApply(){
    auto scope=careerScope();ReloadScopeGuard guard;ProfileReloadProgress progress;
    int state=0,starts=0,loads=0;
    const auto dispatch=[&](int command,void* data){
        assert(canDispatchReload(scope,scope,state,command==0x1a));
        if(command==0x18){auto& request=*static_cast<ProfileReloadRequest*>(data);
            assert(request.force==1);request.loading=1;state=14;++starts;
        }else{assert(command==0x1a);state=0;++loads;}
    };
    for(unsigned i=0;i<10;++i){
        const uint64_t base=i*5000;
        if(i){++scope.epoch;guard.reset();}
        progress.reset(base);
        assert(!guard.observe(scope,base));assert(guard.observe(scope,base+500));
        assert(progress.next(state,true,base+500)==ReloadStep::Start);
        progress.started=requestProfileReload(dispatch);
        assert(progress.next(state,true,base+750)==ReloadStep::BackgroundReady);
        profileBackgroundReady(dispatch);
        assert(progress.next(state,true,base+1000)==ReloadStep::Wait);
    }
    assert(starts==10&&loads==10);
}
static void pageIdentity(){
    std::map<uintptr_t,uintptr_t> pointers{{0x3809030,0x10000},{0x100e8,0x20000},
        {0x200c0,0x30000},{0x30088,0x40000},{0x401d8,0x50000}};
    std::string name="game/screens/fluxHub/FluxHub";bool replace=false;int assetReads=0;
    auto read=[&](uintptr_t at,void* output,size_t size){
        if(at==0x50000){std::memset(output,0,size);std::memcpy(output,name.data(),name.size());return true;}
        if(at==0x401d8&&replace&&++assetReads==2){uintptr_t changed=0x60000;std::memcpy(output,&changed,8);return true;}
        const auto entry=pointers.find(at);if(entry==pointers.end()||size!=8)return false;
        std::memcpy(output,&entry->second,8);return true;
    };
    assert(pageView(0,read)==0x40000);
    replace=true;assert(!pageView(0,read));replace=false;
    name="";assert(!pageView(0,read));name="game/screens/fluxHub/FluxHub";
    pointers.erase(0x30088);assert(!pageView(0,read));
}
int main(){
    capturedCrash();reloadAndSwitchSaves();missingIdentity();repeatedApply();pageIdentity();
    std::puts("PASS frontend reload: captured wrong-owner crash, stable page/epoch, stale requests, save switches, boot exclusions, repeated reloads, page teardown");
}
