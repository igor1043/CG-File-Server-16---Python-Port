#define WIN32_LEAN_AND_MEAN
#include "preload_status.h"
#include "../stadium_pyrotechnics/presentation.h"
#include <cassert>
#include <initializer_list>
int main(){
    for(const char* page:{"game/screens/playNow/KickOffHub","game/screens/playNow/KitSelect","game/screens/PrematchHub"}){
        assert(scene_preload_preview(page));
        assert(!pyro_can_start(pyro_page(page,true),true));
    }
    for(const char* page:{"","game/screens/playNow/SideSelect","game/screens/playNow/SelectTeam","game/screens/career/Hub","game/screens/instantReplay/Replay"})assert(!scene_preload_preview(page));
    scene_preload_publish(0,ScenePreloadState::Loading);
    wchar_t name[80]{};swprintf_s(name,L"Local\\FIFA16_PresentationLoad_v1_%lu",GetCurrentProcessId());
    HANDLE map=OpenFileMappingW(FILE_MAP_READ,FALSE,name);assert(map);
    auto shared=(const ScenePreloadShared*)MapViewOfFile(map,FILE_MAP_READ,0,0,sizeof(ScenePreloadShared));assert(shared);
    assert(shared->version==1&&shared->process==GetCurrentProcessId());
    assert(shared->rows[0].state==(LONG)ScenePreloadState::Loading&&!(shared->rows[0].sequence&1));
    const LONG sequence=shared->rows[0].sequence;
    scene_preload_publish(0,ScenePreloadState::Loading);assert(shared->rows[0].sequence==sequence);
    scene_preload_publish(0,ScenePreloadState::Ready);assert(shared->rows[0].state==(LONG)ScenePreloadState::Ready);
    char temporary[MAX_PATH]{},root[MAX_PATH]{},runtime[MAX_PATH]{},file[MAX_PATH]{};
    assert(GetTempPathA(MAX_PATH,temporary));
    _snprintf_s(root,MAX_PATH,_TRUNCATE,"%sFifaPreloadTest_%lu",temporary,GetCurrentProcessId());
    _snprintf_s(runtime,MAX_PATH,_TRUNCATE,"%s\\runtime",root);
    _snprintf_s(file,MAX_PATH,_TRUNCATE,"%s\\entrance_props_context.ini",runtime);
    CreateDirectoryA(root,nullptr);CreateDirectoryA(runtime,nullptr);
    char pid[24]{};_snprintf_s(pid,sizeof(pid),_TRUNCATE,"%lu",GetCurrentProcessId());
    assert(WritePrivateProfileStringA("selection","schema","1",file));
    assert(WritePrivateProfileStringA("selection","process_id",pid,file));
    assert(WritePrivateProfileStringA("selection","preview","1",file));
    assert(WritePrivateProfileStringA("selection","home","1043",file));
    assert(WritePrivateProfileStringA("selection","away","567",file));
    assert(WritePrivateProfileStringA("selection","competition","1615",file));
    assert(WritePrivateProfileStringA("selection","round","0",file));
    uintptr_t fixture=0;unsigned competition=0,round=0;
    assert(scene_preload_context(root,true,fixture,competition,round));
    assert(fixture==((uintptr_t)1043<<32|567)&&competition==1615&&round==0);
    assert(!scene_preload_context(root,false,fixture,competition,round)&&fixture==0);
    assert(WritePrivateProfileStringA("selection","process_id","1",file));
    assert(!scene_preload_context(root,true,fixture,competition,round));
    assert(WritePrivateProfileStringA("selection","process_id",pid,file));
    assert(WritePrivateProfileStringA("selection","preview","0",file));
    assert(!scene_preload_context(root,true,fixture,competition,round));
    DeleteFileA(file);RemoveDirectoryA(runtime);RemoveDirectoryA(root);
    UnmapViewOfFile(shared);CloseHandle(map);
    puts("Preview preparation cannot arm pyrotechnics; telemetry ABI, process guards and throttling passed");
}
