#include <assert.h>
#include <stdio.h>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "keeper_pitch_sheet.h"
#include "keeper_native_branches.h"

typedef void (__cdecl *NativeBranch)(const void*,uint32_t*);
static NativeBranch make_native_branch(const unsigned char *branch,size_t length)
{
    /* Microsoft x64 arguments: RCX sheet, RDX result[team,type,year]. Preserve
       the native branch's nonvolatile registers and original stack slot. */
    static const unsigned char before[]={0x53,0x56,0x57,0x48,0x83,0xec,0x40,
        0x48,0x89,0xce,0x49,0x89,0xd2,0xc7,0x44,0x24,0x38,0,0,0,0};
    static const unsigned char after[]={0x41,0x89,0x0a,0x41,0x89,0x52,0x04,
        0x45,0x89,0x42,0x08,0x48,0x83,0xc4,0x40,0x5f,0x5e,0x5b,0xc3};
    unsigned char *code;DWORD previous;
    code=(unsigned char*)VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(code);
    memcpy(code,before,sizeof(before));memcpy(code+sizeof(before),branch,length);
    memcpy(code+sizeof(before)+length,after,sizeof(after));
    assert(VirtualProtect(code,4096,PAGE_EXECUTE_READ,&previous));
    FlushInstructionCache(GetCurrentProcess(),code,4096);return (NativeBranch)code;
}

static void check_eleven(NativeBranch keeper,NativeBranch outfield,NativeBranch reference_keeper,NativeBranch reference_outfield,uint32_t club,uint32_t selector)
{
    unsigned char source[KEEPER_SHEET_SIZE]={0},original[KEEPER_SHEET_SIZE],fixed[KEEPER_SHEET_SIZE];
    const unsigned char *view;uint32_t result[3],unfixed[3];unsigned row;
    memcpy(source+4,&club,4);memcpy(source+8,&selector,4);memcpy(original,source,sizeof(source));
    view=keeper_pitch_repair(source,fixed)?fixed:source;
    for(row=0;row<11;++row) {
        NativeBranch native=row?outfield:keeper;
        native(view,result);
        assert(result[0]==club && result[1]==(row?0u:2u) && result[2]==0);
        (row?reference_outfield:reference_keeper)(source,unfixed);
        assert(!memcmp(result,unfixed,sizeof(result))); /* Live backup behavior. */
        if(row){native(source,unfixed);assert(!memcmp(result,unfixed,sizeof(result)));}
    }
    assert(!memcmp(source,original,sizeof(source)));
}

static void check(uint32_t team,uint32_t kit,int repair)
{
    unsigned char source[KEEPER_SHEET_SIZE],before[KEEPER_SHEET_SIZE],copy[KEEPER_SHEET_SIZE];
    uint32_t result;unsigned i;
    for(i=0;i<sizeof(source);++i)source[i]=(unsigned char)(i*17u+3u);
    memcpy(source+4,&team,4);memcpy(source+8,&kit,4);memcpy(before,source,sizeof(source));memset(copy,0xa5,sizeof(copy));
    assert(keeper_pitch_repair(source,copy)==repair);
    assert(!memcmp(source,before,sizeof(source))); /* Career save/team sheet stays untouched. */
    if(repair){
        memcpy(&result,copy+8,4);assert(result==0);
        memcpy(copy+8,&kit,4);assert(!memcmp(source,copy,sizeof(source)));
    }else for(i=0;i<sizeof(copy);++i)assert(copy[i]==0xa5);
}
int main(void)
{
    uint32_t clubs[]={1,1043,1328,110636,131072,200000,262142};unsigned i;
    NativeBranch keeper=make_native_branch(native_keeper_branch,sizeof(native_keeper_branch));
    NativeBranch outfield=make_native_branch(native_outfield_branch,sizeof(native_outfield_branch));
    NativeBranch reference_keeper=make_native_branch(backup_keeper_branch,sizeof(backup_keeper_branch));
    NativeBranch reference_outfield=make_native_branch(backup_outfield_branch,sizeof(backup_outfield_branch));
    {
        unsigned char original[KEEPER_SHEET_SIZE]={0};uint32_t club=1043,selector=UINT32_MAX,result[3];
        memcpy(original+4,&club,4);memcpy(original+8,&selector,4);
        keeper(original,result);assert(result[0]==262143 && result[1]==2);
        outfield(original,result);assert(result[0]==1043 && result[1]==0);
        /* Reproduce the reported regression with the previous positive key. */
        selector=(club<<14)|2u;memcpy(original+8,&selector,4);
        outfield(original,result);assert(result[0]==1043 && result[1]==2);
    }
    for(i=0;i<sizeof(clubs)/sizeof(clubs[0]);++i){
        check(clubs[i],UINT32_MAX,1);check(clubs[i],0,0);
        check(clubs[i],(clubs[i]<<14)|2u,0);check(clubs[i],(7u<<14)|2u,0);
        check_eleven(keeper,outfield,reference_keeper,reference_outfield,clubs[i],UINT32_MAX);
        check_eleven(keeper,outfield,reference_keeper,reference_outfield,clubs[i],0);
    }
    check(0,UINT32_MAX,0);check(262143,UINT32_MAX,0);check(UINT32_MAX,UINT32_MAX,0);
    VirtualFree((void*)keeper,0,MEM_RELEASE);VirtualFree((void*)outfield,0,MEM_RELEASE);
    VirtualFree((void*)reference_keeper,0,MEM_RELEASE);VirtualFree((void*)reference_outfield,0,MEM_RELEASE);
    puts("PASS: native x64 branches match live backup for 11 rows x 7 clubs x sentinel/automatic selectors; keeper kit 2, ten outfield kit 0; prior all-blue regression reproduced and source preserved");return 0;
}
