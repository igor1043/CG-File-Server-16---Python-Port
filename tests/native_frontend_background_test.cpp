#define NOMINMAX
#include <cassert>
#include <map>
#include <string>
#include <windows.h>
#include "../native_mods/frontend_stadium/background_provider.h"
#include "../native_mods/frontend_stadium/room_cover.h"
#include "../native_mods/frontend_stadium/frontend_visibility.h"
#include "../native_mods/frontend_stadium/scene_context.h"
#include "../native_mods/frontend_stadium/menu_page.h"
#include "../native_mods/frontend_stadium/profile_reload.h"
#include "../native_mods/frontend_stadium/stadium_metadata.h"

static bool profileEngineLoaded=true;
static HMODULE WINAPI profileModule(LPCWSTR name){
    return reinterpret_cast<HMODULE>(static_cast<uintptr_t>(std::wcscmp(name,L"dinput8.dll")==0?0x70000000:
        (profileEngineLoaded?0x60000000:0)));
}
static FARPROC WINAPI profileExport(HMODULE,LPCSTR name){
    return std::strcmp(name,"Fifa16CareerContextRead")==0?reinterpret_cast<FARPROC>(0x71000000):nullptr;
}
#define GetModuleHandleW profileModule
#define GetProcAddress profileExport
#include "../native_mods/frontend_stadium/career_profile.h"
#undef GetModuleHandleW
#undef GetProcAddress

static void testCareerIdentity(){
    struct Record {uint32_t schema=1,size=48,sequence=2,pid=GetCurrentProcessId();uintptr_t service=0x80000000,vtable=0x140123456,registry=0x81000000;uint32_t epoch=7,thread=123;} identity;
    int selected=0,team=1629;bool resolved=false;
    const uintptr_t game=0x140000000;
    auto read=[&](uintptr_t address,void* output,size_t size){
        if(address==0x71000000&&size==sizeof identity){std::memcpy(output,&identity,size);return true;}
        if(address==game+0x5aafff0){const unsigned char code[]={0x48,0x63,0x41,0x14,0x83,0xf8,0xff,0x75,3,0x31,0xc0,0xc3,0x48,0x69,0xc0,0x18,3,0,0,0x48,3,0x41};std::memcpy(output,code,size);return true;}
        if(address==game+0x44575e0&&size==24){std::memset(output,0,size);auto* p=static_cast<unsigned char*>(output);p[7]=0xc7;p[8]=1;p[9]=121;return true;}
        if(address==identity.service+0x14&&size==4){std::memcpy(output,&selected,size);return true;}
        if(address==0x82000000+0x1a4&&size==4){std::memcpy(output,&team,size);return true;}
        const std::map<uintptr_t,uintptr_t> values{{0x600b13f0,1},{identity.registry+121*32+24,0x83000000},{0x83000000,identity.service},{identity.service,identity.vtable},{identity.service+0x18,0x82000000}};
        const auto at=values.find(address);if(at==values.end()||size!=8)return false;
        std::memcpy(output,&at->second,size);return true;
    };
    assert(activeCareerClub(game,read,&resolved)==1629&&resolved); // No deferred card owner exists.
    team=0;assert(activeCareerClub(game,read,&resolved)==0&&!resolved);team=1629;
    identity.sequence=3;assert(activeCareerClub(game,read,&resolved)==0&&!resolved);identity.sequence=2;
    selected=-1;assert(activeCareerClub(game,read,&resolved)==0&&resolved); // A genuine exit permits the favourite club.
    selected=0;identity.pid++;assert(activeCareerClub(game,read,&resolved)==0&&!resolved);
    profileEngineLoaded=false;assert(activeCareerClub(game,read,&resolved)==0&&resolved);profileEngineLoaded=true;
}

struct BackgroundProvider {
    std::map<std::string,std::string> fields{{"Id","FIFA"},{"Param","BOOTFLOW"}};
    int writes=0;
};
static void __fastcall setString(void* raw,const char* field,const char* value){
    auto& provider=*static_cast<BackgroundProvider*>(raw);
    provider.fields[field]=value;provider.writes++;
}
int main(){
    testCareerIdentity();
    {BackgroundProvider p;
     assert(frontend_stadium::routeRoomPhotograph(&p,setString,false));assert(p.writes==1&&p.fields["Id"]=="FIFA"&&p.fields["Param"]=="BOOTFLOW");
     assert(frontend_stadium::routeRoomPhotograph(&p,setString,true));assert(p.writes==2&&p.fields["Param"]=="server16_frontend_clear");
     assert(!frontend_stadium::routeRoomPhotograph(nullptr,setString,true)&&!frontend_stadium::routeRoomPhotograph(&p,nullptr,true));assert(p.writes==2);}
    // Stadium readiness must not uncover a still-preparing dressing room.
    scene_loading::Status room;
    room.club=112893;room.visible=1;room.variant=4;
    assert(!frontend_stadium::roomCoverReady(112893,true,&room));
    room.ready=1;
    assert(!frontend_stadium::roomCoverReady(112893,true,&room)); // no published resource set yet
    room.total=256;room.loaded=255;
    assert(!frontend_stadium::roomCoverReady(112893,true,&room)); // resident shell is not the full room
    room.loaded=256;
    assert(!frontend_stadium::roomCoverReady(112893,false,&room)); // stadium in flight
    assert(frontend_stadium::roomCoverReady(112893,true,&room));
    room.club=1043;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.club=112893;
    room.visible=0;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.visible=1;
    room.variant=0;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.variant=4;
    room.error=9;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.error=0;
    room.version=2;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.version=1;
    room.size=0;assert(!frontend_stadium::roomCoverReady(112893,true,&room));room.size=sizeof room;
    assert(!frontend_stadium::roomCoverReady(0,true,&room));
    assert(!frontend_stadium::roomCoverReady(112893,true,nullptr));
    assert(frontend_stadium::roomCoverStamp(1043,true)!=frontend_stadium::roomCoverStamp(112893,true));
    assert(frontend_stadium::roomCoverStamp(112893,false)!=frontend_stadium::roomCoverStamp(112893,true));
    // A loading room must not hide a fully loaded stadium panorama.
    assert(frontend_stadium::roomPanoramaReady(1043,true,1043,true,true));
    assert(!frontend_stadium::roomPanoramaReady(1043,false,1043,true,true));
    assert(!frontend_stadium::roomPanoramaReady(1043,true,112893,true,true));
    assert(!frontend_stadium::roomPanoramaReady(1043,true,1043,false,true));
    assert(!frontend_stadium::roomPanoramaReady(1043,true,1043,true,false));
    assert(!frontend_stadium::roomPanoramaReady(0,true,0,true,true));
    using Page=frontend_stadium::PageKind;
    for(auto page:{Page::Hub,Page::IdlePanorama,Page::Menu,Page::Transition})assert(frontend_stadium::roomCoverPage(page));
    for(auto page:{Page::ClubBrowser,Page::ManagerFace,Page::ManagerPreferences,Page::PlayerCareer,Page::Other})assert(!frontend_stadium::roomCoverPage(page));
    assert(frontend_stadium::roomCoverSelected(Page::Hub,true,-1,true)); // before club publication
    assert(frontend_stadium::roomCoverSelected(Page::Hub,true,1,true));
    assert(!frontend_stadium::roomCoverSelected(Page::Hub,false,1,true));
    assert(!frontend_stadium::roomCoverSelected(Page::Hub,true,0,true)); // player career
    assert(!frontend_stadium::roomCoverSelected(Page::Hub,true,1,false)); // playing a match
    assert(!frontend_stadium::roomCoverSelected(Page::Menu,true,-1,true)); // initial favourite-club stadium
    assert(!frontend_stadium::roomCoverSelected(Page::ClubBrowser,true,1,true));
    assert(frontend_stadium::roomCoverStamp(0,false)!=0);
    assert(frontend_stadium::isBackgroundPage(Page::ManagerPreferences)&&frontend_stadium::isBackgroundPage(Page::ManagerFace));
    assert(!frontend_stadium::forcesStadium(Page::ManagerPreferences)&&frontend_stadium::forcesStadium(Page::ManagerFace));
    assert(frontend_stadium::preservesPhotograph(Page::ManagerPreferences));
    assert(!frontend_stadium::preservesPhotograph(Page::ManagerFace)&&!frontend_stadium::preservesPhotograph(Page::Menu));
    assert(frontend_stadium::refreshOnMenuReturn(Page::ManagerPreferences,Page::ManagerFace,true,true));
    assert(frontend_stadium::refreshOnMenuReturn(Page::ManagerFace,Page::ManagerPreferences,true,true));
    assert(frontend_stadium::refreshOnMenuReturn(Page::Other,Page::Menu,true,true));
    assert(frontend_stadium::refreshOnMenuReturn(Page::Transition,Page::Menu,true,true));
    assert(!frontend_stadium::refreshOnMenuReturn(Page::Menu,Page::Menu,true,true));
    assert(!frontend_stadium::refreshOnMenuReturn(Page::Other,Page::Menu,true,false));
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
    assert(frontend_stadium::photographPolicy(false,true,false,true,true)==Photo::Stadium);
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
    assert(frontend_stadium::pageKind(0,pageRead)==Page::Hub);
    page="game/screens/misc/StadiumPan";
    assert(frontend_stadium::pageKind(0,pageRead)==Page::IdlePanorama);
    assert(frontend_stadium::refreshOnMenuReturn(Page::Hub,Page::IdlePanorama,true,true));
    assert(frontend_stadium::refreshOnMenuReturn(Page::IdlePanorama,Page::Hub,true,true));
    page="game/screens/saveload_pc/profile";
    assert(frontend_stadium::reloadPage(0,pageRead));
    page="game/screens/career/server16/ClubBrowser";
    assert(frontend_stadium::pageKind(0,pageRead)==frontend_stadium::PageKind::ClubBrowser);
    page="game/screens/career/ManagerPreferences";
    assert(frontend_stadium::pageKind(0,pageRead)==Page::ManagerPreferences);
    assert(frontend_stadium::preservesPhotograph(frontend_stadium::pageKind(0,pageRead)));
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
    assert(frontend_stadium::sameCareerRoute(true,8,8));
    assert(!frontend_stadium::sameCareerRoute(true,2,8));
    assert(!frontend_stadium::sameCareerRoute(true,8,0));
    assert(frontend_stadium::sameCareerRoute(false,0,0));
    assert(!frontend_stadium::photographRefreshReady(true,true,0,1000));
    assert(!frontend_stadium::photographRefreshReady(false,false,0,1000));
    assert(!frontend_stadium::photographRefreshReady(false,true,14,1000));
    assert(!frontend_stadium::photographRefreshReady(false,true,12,499));
    assert(frontend_stadium::photographRefreshReady(false,true,0,500));
    return 0;
}
