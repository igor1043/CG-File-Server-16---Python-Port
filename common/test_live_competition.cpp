#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
static HMODULE WINAPI mock_module(LPCSTR);
static FARPROC WINAPI mock_proc(HMODULE,LPCSTR);
#define GetModuleHandleA mock_module
#define GetProcAddress mock_proc
#include "live_competition.h"
#undef GetModuleHandleA
#undef GetProcAddress
static CompIdentityIndex installed;
static const FceModel *snapshot_model;
static bool module_available=true,cached_available=true,snapshot_available=true;
static int cached_calls,live_calls,release_calls;
static void *WINAPI cached_acquire(){++cached_calls;return snapshot_available?(void*)snapshot_model:nullptr;}
static void *WINAPI live_acquire(){++live_calls;return snapshot_available?(void*)snapshot_model:nullptr;}
static const FceModel *WINAPI get_model(const void *snapshot){return (const FceModel*)snapshot;}
static void WINAPI release_snapshot(void *snapshot){assert(snapshot==snapshot_model);++release_calls;}
static HMODULE WINAPI mock_module(LPCSTR name){assert(!strcmp(name,"dinput8.dll"));return module_available?(HMODULE)1:nullptr;}
static FARPROC WINAPI mock_proc(HMODULE module,LPCSTR name){
    assert(module==(HMODULE)1);
    if(!strcmp(name,"Fifa16CareerAcquireCachedSnapshot"))return cached_available?(FARPROC)cached_acquire:nullptr;
    if(!strcmp(name,"Fifa16CareerAcquireSnapshot"))return (FARPROC)live_acquire;
    if(!strcmp(name,"Fifa16CareerGetSnapshotModel"))return (FARPROC)get_model;
    if(!strcmp(name,"Fifa16CareerReleaseSnapshot"))return (FARPROC)release_snapshot;
    return nullptr;
}
static void add(int id,int parent,int type,const char *name,const char *display){
    auto &n=installed.nodes[installed.count];n.id=id;n.parent=parent;n.type=type;
    strcpy_s(n.name,name);strcpy_s(n.display,display);installed.slot[id]=(unsigned short)++installed.count;
}
int main(){
    add(1761,1619,3,"C7","TrophyName_Abbr15_7");
    add(1762,1761,4,"S1","FCE_League_Stage");
    add(1460,1384,3,"C1003","TrophyName_Abbr15_1003");
    add(1480,1460,4,"S6","FCE_Finals");
    const FceCompNode old[]={{1738,1596,3,7,0},{1739,1738,4,-1,FCE_STAGE_GROUP},
        {1437,1361,3,1003,0},{1458,1437,4,-1,FCE_STAGE_FINAL}};
    FceModel model{};model.nodes=const_cast<FceCompNode*>(old);model.node_count=4;
    unsigned comp=1738,round=1739;
    assert(comp_live_translate(&installed,&model,comp,round)==1 && comp==1761 && round==1762);
    comp=1437;round=1458;
    assert(comp_live_translate(&installed,&model,comp,round)==1 && comp==1460 && round==1480);
    snapshot_model=&model;comp=1437;round=1458;
    assert(comp_live_current(&installed,comp,round)==1 && comp==1460 && round==1480);
    assert(cached_calls==1 && live_calls==0 && release_calls==1);
    snapshot_available=false;comp=1437;round=1458;
    assert(comp_live_current(&installed,comp,round)==0 && comp==1437 && round==1458);
    assert(cached_calls==2 && live_calls==0 && release_calls==1);
    snapshot_available=true;cached_available=false;
    assert(comp_live_current(&installed,comp,round)==1 && comp==1460 && round==1480);
    assert(live_calls==1 && release_calls==2);
    module_available=false;
    assert(comp_live_current(&installed,comp,round)==0 && release_calls==2);
    comp=1738;round=1458;assert(comp_live_translate(&installed,&model,comp,round)==-1);
    comp=999;round=0;assert(comp_live_translate(&installed,&model,comp,round)==-1);
    comp=1761;round=1762;assert(comp_live_translate(&installed,nullptr,comp,round)==0 && comp==1761 && round==1762);
    const FceCompNode current[]={{1761,1619,3,7,0},{1762,1761,4,-1,FCE_STAGE_GROUP}};
    model.nodes=const_cast<FceCompNode*>(current);model.node_count=2;
    assert(comp_live_translate(&installed,&model,comp,round)==1 && comp==1761 && round==1762);
    puts("PASS old/current career identities; cached scene acquisition without native registry/date; compatibility and snapshot release");
}
