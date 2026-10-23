#include <cassert>
#include <map>
#include <string>
#include "../native_mods/frontend_stadium/background_provider.h"
#include "../native_mods/frontend_stadium/frontend_visibility.h"
#include "../native_mods/frontend_stadium/scene_context.h"
#include "../native_mods/frontend_stadium/menu_page.h"
#include "../native_mods/frontend_stadium/profile_reload.h"
#include "../native_mods/frontend_stadium/stadium_metadata.h"

struct BackgroundProvider {
    std::map<std::string,std::string> fields{{"Id","FIFA"},{"Param","BOOTFLOW"}};
    int writes=0;
};
static void __fastcall setString(void* raw,const char* field,const char* value){
    auto& provider=*static_cast<BackgroundProvider*>(raw);
    provider.fields[field]=value;provider.writes++;
}
int main(){
    assert(frontend_stadium::metadataCount(L"",-1)==-1);
    assert(frontend_stadium::metadataCount(L"0",-1)==0);
    assert(frontend_stadium::metadataCount(L"50000",0)==50000);
    assert(frontend_stadium::metadataCount(L"-1",-1)==-1);
    assert(frontend_stadium::metadataCount(L"9999999999999",-1)==-1);
    using Photo=frontend_stadium::Photograph;
    assert(frontend_stadium::photographPolicy(false,false,false,false,false)==Photo::Friends);
    assert(frontend_stadium::photographPolicy(false,true,true,false,false)==Photo::Friends);
    assert(frontend_stadium::photographPolicy(true,true,false,false,false)==Photo::Friends);
    assert(frontend_stadium::photographPolicy(true,true,false,true,true)==Photo::Stadium);
    assert(frontend_stadium::photographPolicy(false,true,false,true,true)==Photo::Original);
    // Career exit has already finished loading, but its page is temporarily
    // absent. The profile's photograph (229/Grêmio here) must stay covered.
    assert(frontend_stadium::photographPolicy(false,true,false,true,true,true)==Photo::Friends);
    assert(frontend_stadium::photographPolicy(false,true,false,false,false,true)==Photo::Friends);
    assert(frontend_stadium::photographPolicy(true,true,false,true,true,false)==Photo::Stadium);
    // FIFA compares its saved stadium ID before starting the loader. A custom
    // route changes assets without changing that ID; the force byte is vital.
    const auto unchangedProfile=[](int command,void* input){
        assert(command==0x18);
        auto* request=static_cast<frontend_stadium::ProfileReloadRequest*>(input);
        assert(request->loading==0);
        request->loading=request->force?1u:0u;
    };
    assert(frontend_stadium::requestProfileReload(unchangedProfile));
    assert(!frontend_stadium::requestProfileReload([](int,void*){})); // native state busy
    // Replay the RAM failure: preparation succeeded, then FreeRoam remained
    // in state 14. That state needs command 0x1a, never another start.
    using Step=frontend_stadium::ReloadStep;
    frontend_stadium::ProfileReloadProgress reload;
    reload.reset(1000);
    assert(reload.next(0,true,1499)==Step::Wait);
    assert(reload.next(0,true,1500)==Step::Start);
    assert(reload.next(14,true,1750)==Step::BackgroundReady);
    assert(reload.started);
    for(uint64_t t=2000;t<12000;t+=250)assert(reload.next(14,true,t)==Step::Wait);
    assert(reload.attempts==1);
    reload.reset(12000);
    assert(reload.next(11,true,13000)==Step::Wait); // boot uses the same callback; do not bypass it
    assert(reload.next(14,false,13000)==Step::Wait); // no prepared transaction
    reload.reset(14000);
    for(uint64_t t=14500;t<=18000;t+=500)assert(reload.next(0,true,t)==Step::Start);
    assert(reload.next(0,true,18500)==Step::Failed);
    for(uint64_t t=19000;t<30000;t+=250)assert(reload.next(0,true,t)==Step::Wait);
    reload.reset(30000); // a fresh Apply is allowed to retry
    assert(reload.next(0,true,30500)==Step::Start);
    reload.fail();
    assert(reload.next(14,true,31000)==Step::Wait);
    // Two Apply operations with the same saved stadium ID must each finish
    // inside one running session. Mock only the verified native command ABI.
    int nativeState=0,starts=0,modelLoads=0;
    auto native=[&](int command,void* data){
        if(command==0x18){
            auto& request=*static_cast<frontend_stadium::ProfileReloadRequest*>(data);
            assert(nativeState==0&&request.force==1);
            nativeState=14;request.loading=1;++starts;
        }else{
            assert(command==0x1a&&nativeState==14);
            nativeState=0;++modelLoads;
        }
    };
    for(uint64_t base:{40000u,50000u}){
        reload.reset(base);
        assert(reload.next(nativeState,true,base+500)==Step::Start);
        reload.started=frontend_stadium::requestProfileReload(native);
        assert(reload.next(nativeState,true,base+750)==Step::BackgroundReady);
        frontend_stadium::profileBackgroundReady(native);
        assert(reload.next(nativeState,true,base+1000)==Step::Wait);
    }
    assert(starts==2&&modelLoads==2);
    // Boot has a valid 3D scene but no fully loaded profile/player rig. A
    // profile-change event there caused the captured 44bb987 null-rig crash.
    std::map<uintptr_t,uintptr_t> pages{{0x3809030,0x10000},{0x100e8,0x20000},
        {0x200c0,0x30000},{0x30088,0x40000},{0x401d8,0x50000}};
    std::string page="game/screens/bootflow/Legal";
    auto pageRead=[&](uintptr_t input,void* output,size_t size){
        if(input==0x50000){std::memset(output,0,size);std::memcpy(output,page.data(),page.size());return true;}
        const auto entry=pages.find(input);if(entry==pages.end()||size!=8)return false;
        std::memcpy(output,&entry->second,8);return true;
    };
    assert(!frontend_stadium::reloadPage(0,pageRead));
    assert(frontend_stadium::pageKind(0,pageRead)==frontend_stadium::PageKind::Other);
    page="";
    assert(frontend_stadium::pageKind(0,pageRead)==frontend_stadium::PageKind::Transition);
    assert(!frontend_stadium::reloadPage(0,pageRead));
    page="game/screens/fluxHub/FluxHub";
    assert(frontend_stadium::reloadPage(0,pageRead));
    page="game/screens/saveload_pc/profile";
    assert(frontend_stadium::reloadPage(0,pageRead));
    page="game/screens/playNow/KickOffHub";
    assert(!frontend_stadium::reloadPage(0,pageRead));
    assert(frontend_stadium::pageKind(0,pageRead)==frontend_stadium::PageKind::Other);
    pages.erase(0x30088);
    assert(!frontend_stadium::reloadPage(0,pageRead));
    assert(frontend_stadium::pageKind(0,pageRead)==frontend_stadium::PageKind::Transition);
    // A native profile reload has two separate event payloads. Both must
    // carry the chosen FE slot, retaining every match/save field.
    frontend_stadium::SceneContext profile{};
    for(size_t i=0;i<profile.size();++i)profile[i]=static_cast<unsigned char>(i);
    auto preparation=profile,loading=profile;
    frontend_stadium::routeContext(preparation,261);
    frontend_stadium::routeContext(loading,261);
    assert(preparation==loading);
    for(size_t i=0;i<profile.size();++i)if(i<0xe8||i>=0xf0)assert(preparation[i]==profile[i]);
    int slot=0,light=0;std::memcpy(&slot,loading.data()+0xe8,4);std::memcpy(&light,loading.data()+0xec,4);
    assert(slot==261&&light==1);
    BackgroundProvider provider;
    // Regression from the captured v1 session: Id was overwritten, so the
    // framework could no longer select its FIFA background component.
    assert(!frontend_stadium::routePhotograph(&provider,&setString,"Id"));
    assert(provider.fields.at("Id")=="FIFA");
    assert(provider.fields.at("Param")=="BOOTFLOW");
    assert(provider.writes==0);
    assert(frontend_stadium::routePhotograph(&provider,&setString,"Param"));
    assert(provider.fields.at("Id")=="FIFA");
    assert(provider.fields.at("Param")=="server16_frontend_clear");
    assert(provider.writes==1);
    assert(!frontend_stadium::routePhotograph(nullptr,&setString,"Param"));
    assert(!frontend_stadium::routePhotograph(&provider,nullptr,"Param"));
    std::array<unsigned char,0x26a0> state{};
    const uintptr_t begin=0x10000,end=begin+83*0x50,oldVisibility=0xdeadbeef;
    std::memcpy(state.data()+0x2090,&begin,8);std::memcpy(state.data()+0x2098,&end,8);
    std::memcpy(state.data()+0x1ed0,&oldVisibility,8);
    const auto before=state;
    frontend_stadium::PanoramaVisibility panorama;
    auto read=[&](uintptr_t input,void* output,size_t size){if(input!=123||size!=state.size())return false;std::memcpy(output,state.data(),size);return true;};
    assert(frontend_stadium::panoramaVisibility(123,1,panorama,read));
    assert(state==before);
    std::memcpy(panorama.state.data()+0x1ed0,&oldVisibility,8);
    assert(panorama.state==before);
    for(const auto visible:panorama.visible)assert(visible==0);
    assert(!frontend_stadium::panoramaVisibility(123,16,panorama,read));
    return 0;
}
