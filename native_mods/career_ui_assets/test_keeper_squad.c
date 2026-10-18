#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "keeper_squad_branch.h"
#include "keeper_pitch_sheet.h"
/* Exact outfield branch captured from the same Squad producer, stopping
 * before its kit helper CALL at RVA 4094916. */
static const unsigned char squad_outfield[]={
    0x8b,0x85,0x08,0x01,0x00,0x00,0xb1,0x01,0x85,0xc0,0x7f,0x08,0x8b,0x85,0x04,0x01,
    0x00,0x00,0x30,0xc9,0x31,0xdb,0x44,0x89,0xea,0x89,0xc7,0x84,0xc9,0x74,0x1b,0x89,
    0xc3,0xc1,0xef,0x0e,0xc1,0xfb,0x05,0x81,0xe3,0xff,0x01,0x00,0x00,0x7e,0x06,0x81,
    0xc3,0x08,0x07,0x00,0x00,0x89,0xc2,0x83,0xe2,0x1f,0x41,0x89,0xd8,0x89,0xf9
};
typedef void (__cdecl *Branch)(const void*,uint32_t*);
static const unsigned char roster_outfield[]={
    0x8b,0x45,0x68,0xb1,0x01,0x85,0xc0,0x7f,0x05,0x8b,0x45,0x64,0x30,0xc9,0x31,0xdb,
    0x89,0xfa,0x89,0xc7,0x84,0xc9,0x74,0x1b,0x89,0xc3,0xc1,0xef,0x0e,0xc1,0xfb,0x05,
    0x81,0xe3,0xff,0x01,0x00,0x00,0x7e,0x06,0x81,0xc3,0x08,0x07,0x00,0x00,0x89,0xc2,
    0x83,0xe2,0x1f,0x41,0x89,0xd8,0x89,0xf9
};
static Branch executable(const unsigned char *branch,size_t length,int32_t frame)
{
    /* RCX=sheet, RDX=outputs. Recreate the Squad frame: sheet==RBP+100.
     * Preserve every nonvolatile register touched by either captured branch. */
    unsigned char before[]={0x53,0x55,0x56,0x57,0x41,0x55,0x48,0x83,0xec,0x40,
        0x48,0x8d,0xa9,0x00,0xff,0xff,0xff,0x49,0x89,0xd2,0x45,0x31,0xed,0x31,0xff};
    static const unsigned char after[]={0x41,0x89,0x0a,0x41,0x89,0x52,0x04,0x45,0x89,0x42,0x08,
        0x48,0x83,0xc4,0x40,0x41,0x5d,0x5f,0x5e,0x5d,0x5b,0xc3};
    unsigned char *code=VirtualAlloc(NULL,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);DWORD old;
    assert(code);memcpy(before+13,&frame,4);memcpy(code,before,sizeof(before));memcpy(code+sizeof(before),branch,length);
    memcpy(code+sizeof(before)+length,after,sizeof(after));
    assert(VirtualProtect(code,4096,PAGE_EXECUTE_READ,&old));FlushInstructionCache(GetCurrentProcess(),code,4096);
    return (Branch)code;
}
int main(void)
{
    uint32_t clubs[]={1,1043,1328,110636,131072,200000,262142};
    uint32_t selectors[]={UINT32_MAX,0,0xfffffffeu,(1043u<<14)|2u,(7u<<14)|1u};
    unsigned char fixed[sizeof(keeper_squad_native)],sheet[KEEPER_SHEET_SIZE],before[KEEPER_SHEET_SIZE];
    Branch old_keeper,keeper,outfield;unsigned i,j,row,screen;
    const unsigned char *keepers[]={keeper_squad_native,keeper_roster_native};
    const unsigned char *lines[]={squad_outfield,roster_outfield};
    size_t sizes[]={sizeof(keeper_squad_native),sizeof(keeper_roster_native)};
    size_t line_sizes[]={sizeof(squad_outfield),sizeof(roster_outfield)};
    unsigned conditions[]={KEEPER_SQUAD_CONDITION,KEEPER_ROSTER_CONDITION};
    int32_t frames[]={-0x100,-0x60};
    int (*signatures[])(const unsigned char*,size_t)={keeper_squad_signature,keeper_roster_signature};
    for(screen=0;screen<2;++screen) {
    memcpy(fixed,keepers[screen],sizes[screen]);
    assert(signatures[screen](fixed,sizes[screen]));
    fixed[conditions[screen]]=0x7e;assert(signatures[screen](fixed,sizes[screen]));
    old_keeper=executable(keepers[screen],sizes[screen],frames[screen]);
    keeper=executable(fixed,sizes[screen],frames[screen]);outfield=executable(lines[screen],line_sizes[screen],frames[screen]);
    fixed[0]^=1;assert(!signatures[screen](fixed,sizes[screen]));
    assert(!signatures[screen](NULL,sizes[screen]) && !signatures[screen](fixed,sizes[screen]-1));
    for(i=0;i<sizeof(clubs)/sizeof(clubs[0]);++i)for(j=0;j<sizeof(selectors)/sizeof(selectors[0]);++j) {
        uint32_t result[3],original[3],selector=selectors[j];
        memset(sheet,0xa5,sizeof(sheet));memcpy(sheet+4,&clubs[i],4);memcpy(sheet+8,&selector,4);
        memcpy(before,sheet,sizeof(sheet));
        for(row=0;row<11;++row) {
            (row?outfield:keeper)(sheet,result);
            (row?outfield:old_keeper)(sheet,original);
            if(row || (int32_t)selector>0)assert(!memcmp(result,original,sizeof(result)));
            if((int32_t)selector<=0)assert(result[0]==clubs[i] && result[1]==(row?0u:2u) && result[2]==0);
            if(!row && selector==UINT32_MAX)assert(original[0]==262143 && result[0]!=262143);
        }
        assert(!memcmp(sheet,before,sizeof(sheet)));
    }
    VirtualFree((void*)old_keeper,0,MEM_RELEASE);VirtualFree((void*)keeper,0,MEM_RELEASE);VirtualFree((void*)outfield,0,MEM_RELEASE);
    }
    puts("PASS roster AND formation native x64: both invalid GK paths reproduced; seven clubs, 11 rows, automatic/negative/explicit selectors; ten outfield rows, positive overrides and source sheets unchanged; signature guards");
    return 0;
}
