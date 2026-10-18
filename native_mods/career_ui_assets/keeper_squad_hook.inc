#include "keeper_squad_branch.h"
__declspec(dllexport) volatile LONG Fifa16UiAssetsSquadKeeperReady;
static BOOL install_keeper_squad_branch(BYTE *branch,size_t size,size_t offset,
    int (*signature)(const unsigned char*,size_t))
{
    BYTE actual[64];DWORD old=0,ignored;BYTE *condition=branch+offset;
    if(size>sizeof(actual) || offset>=size || !read_memory(branch,actual,size) || !signature(actual,size))return FALSE;
    if(actual[offset]==0x7e)return TRUE;
    if(!VirtualProtect(condition,1,PAGE_EXECUTE_READWRITE,&old))return FALSE;
    if(memcmp(branch,actual,size)){VirtualProtect(condition,1,old,&ignored);return FALSE;}
    *condition=0x7e;FlushInstructionCache(GetCurrentProcess(),condition,1);
    VirtualProtect(condition,1,old,&ignored);return TRUE;
}
static BOOL install_keeper_squad_hook(void)
{
    BYTE *base=(BYTE*)GetModuleHandleA(NULL);IMAGE_DOS_HEADER dos;IMAGE_NT_HEADERS64 nt;
    if(Fifa16UiAssetsSquadKeeperReady)return TRUE;
    if(!read_memory(base,&dos,sizeof(dos)) || dos.e_magic!=IMAGE_DOS_SIGNATURE ||
       dos.e_lfanew<0 || dos.e_lfanew>4096 ||
       !read_memory(base+dos.e_lfanew,&nt,sizeof(nt)) || nt.Signature!=IMAGE_NT_SIGNATURE ||
       nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 || nt.FileHeader.TimeDateStamp!=0x577de45c)return FALSE;
    /* One aligned byte, with unchanged instruction length/displacement. A
     * concurrent fetch sees either valid branch, never a partial instruction. */
    if(!install_keeper_squad_branch(base+0x40948a5,sizeof(keeper_squad_native),KEEPER_SQUAD_CONDITION,keeper_squad_signature) ||
       !install_keeper_squad_branch(base+0x409979e,sizeof(keeper_roster_native),KEEPER_ROSTER_CONDITION,keeper_roster_signature))return FALSE;
    Fifa16UiAssetsSquadKeeperReady=1;
    return TRUE;
}
