#include "keeper_pitch_sheet.h"
typedef void (__cdecl *KeeperPitchSerializer)(void*,void*,const void*,void*);
typedef struct {LONG ready,calls,repairs,error,team;uint32_t before,after;} KeeperPitchStats;
__declspec(dllexport) volatile KeeperPitchStats Fifa16UiAssetsKeeperStats;
static KeeperPitchSerializer keeper_pitch_original;

static void __cdecl keeper_pitch_serialize(void *context,void *output,const void *sheet,void *players)
{
    unsigned char fixed[KEEPER_SHEET_SIZE];
    const void *view=sheet;
    InterlockedIncrement(&Fifa16UiAssetsKeeperStats.calls);
    if(sheet && keeper_pitch_repair((const unsigned char*)sheet,fixed)) {
        uint32_t team,kit;
        memcpy(&team,fixed+KEEPER_SHEET_TEAM,4);memcpy(&kit,fixed+KEEPER_SHEET_TEAM_KIT,4);
        Fifa16UiAssetsKeeperStats.team=(LONG)team;
        Fifa16UiAssetsKeeperStats.before=UINT32_MAX;Fifa16UiAssetsKeeperStats.after=kit;
        InterlockedIncrement(&Fifa16UiAssetsKeeperStats.repairs);view=fixed;
    }
    keeper_pitch_original(context,output,view,players);
}

static void *keeper_pitch_relay(BYTE *site)
{
    uintptr_t origin=(uintptr_t)site&~(uintptr_t)0xffff,delta;
    for(delta=0x10000;delta<0x40000000;delta+=0x10000) {
        void *relay=VirtualAlloc((void*)(origin+delta),4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        if(relay)return relay;
        if(origin>delta){relay=VirtualAlloc((void*)(origin-delta),4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);if(relay)return relay;}
    }
    return NULL;
}

static BOOL install_keeper_pitch_hook(void)
{
    static const BYTE expected[5]={0xe8,0x49,0x49,0x01,0x00};
    BYTE *base=(BYTE*)GetModuleHandleA(NULL),*site=base+0x40b59f2,*relay;
    BYTE before[5],patch[5]={0xe8},signature[24];IMAGE_DOS_HEADER dos;IMAGE_NT_HEADERS64 nt;
    HANDLE snapshot,threads[256];THREADENTRY32 entry={0};size_t count=0,i;
    BOOL next,ok=TRUE;DWORD old=0,ignored;int64_t delta;int32_t relative;void *wrapper=(void*)keeper_pitch_serialize;
    if(Fifa16UiAssetsKeeperStats.ready)return TRUE;
    if(!read_memory(base,&dos,sizeof(dos)) || dos.e_magic!=IMAGE_DOS_SIGNATURE || dos.e_lfanew<0 || dos.e_lfanew>4096 ||
       !read_memory(base+dos.e_lfanew,&nt,sizeof(nt)) || nt.Signature!=IMAGE_NT_SIGNATURE ||
       nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 || nt.FileHeader.TimeDateStamp!=0x577de45c ||
       !read_memory(site,before,5) || memcmp(before,expected,5))return FALSE;
    /* Verify the live serializer's own TeamID source and the keeper-only path.
       The on-disk executable is packed, so these checks use decoded RAM. */
    if(!read_memory(base+0x40ca402,signature,17) || memcmp(signature,"\x44\x8b\x46\x04",4) ||
       !read_memory(base+0x40ca8f8,signature,21) || (signature[10]!=0x74 && signature[10]!=0x7e))return FALSE;
    /* The central kit-key table preserves the native signed automatic fallback.
       Accept that corrected JLE as well as the legacy JE; all other bytes match. */
    signature[10]=0x74;
    if(memcmp(signature,"\x4d\x85\xff\x75\x2f\x8b\x5e\x08\x85\xdb\x74\x06\xc1\xeb\x0e\xeb\x04",17))return FALSE;
    relay=(BYTE*)keeper_pitch_relay(site);if(!relay)return FALSE;
    relay[0]=0xff;relay[1]=0x25;memset(relay+2,0,4);memcpy(relay+6,&wrapper,8);
    if(!VirtualProtect(relay,4096,PAGE_EXECUTE_READ,&old)){VirtualFree(relay,0,MEM_RELEASE);return FALSE;}
    FlushInstructionCache(GetCurrentProcess(),relay,14);
    delta=(int64_t)(uintptr_t)relay-(int64_t)(uintptr_t)(site+5);
    if(delta<INT32_MIN || delta>INT32_MAX){VirtualFree(relay,0,MEM_RELEASE);return FALSE;}
    relative=(int32_t)delta;memcpy(patch+1,&relative,4);
    keeper_pitch_original=(KeeperPitchSerializer)(base+0x40ca340);
    snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);if(snapshot==INVALID_HANDLE_VALUE){VirtualFree(relay,0,MEM_RELEASE);return FALSE;}
    entry.dwSize=sizeof(entry);next=Thread32First(snapshot,&entry);
    while(next) {
        if(entry.th32OwnerProcessID==GetCurrentProcessId() && entry.th32ThreadID!=GetCurrentThreadId()) {
            HANDLE thread;CONTEXT context={0};
            if(count==256){ok=FALSE;break;}
            thread=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT,FALSE,entry.th32ThreadID);
            if(!thread){ok=FALSE;break;}
            if(SuspendThread(thread)==(DWORD)-1){CloseHandle(thread);ok=FALSE;break;}
            threads[count++]=thread;context.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(thread,&context) || (context.Rip>=(uintptr_t)site && context.Rip<(uintptr_t)site+5)){ok=FALSE;break;}
        }
        next=Thread32Next(snapshot,&entry);
    }
    CloseHandle(snapshot);
    if(ok && memcmp(site,expected,5))ok=FALSE;
    if(ok && !VirtualProtect(site,5,PAGE_EXECUTE_READWRITE,&old))ok=FALSE;
    if(ok){memcpy(site,patch,5);FlushInstructionCache(GetCurrentProcess(),site,5);VirtualProtect(site,5,old,&ignored);Fifa16UiAssetsKeeperStats.ready=1;}
    for(i=count;i>0;--i){ResumeThread(threads[i-1]);CloseHandle(threads[i-1]);}
    if(!ok)VirtualFree(relay,0,MEM_RELEASE);
    return ok;
}
