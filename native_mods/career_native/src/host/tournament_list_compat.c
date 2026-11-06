#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include "tournament_list_compat.h"

/* PID 12676: loading competition 2235 faults at EXE+05B17AAE after the
 * original getter +05BB57C0 scans only 100 entries and returns NULL.
 * L9-10 has not applied any of its 61 edits: two encoded loop immediates
 * differ from its descriptors, although their decoded counts are 99/100.
 * Adapt ONLY these two descriptors in the original L9 worker's data.
 * The original worker retains responsibility for the complete 400-entry
 * layout, constructor, destructor, counters and search trampolines.
 * No save format, save file, database or executable instruction is patched
 * directly here. Never start a second worker that edits the same 61 sites.
 */
typedef struct CounterSite {
    DWORD slot, seed_rva, instruction_rva, immediate_rva;
    BYTE seed_opcode, lea_opcode;
    DWORD count, original_before, original_after;
} CounterSite;
static const CounterSite g_sites[2]={
    {31,0x05B383CB,0x05B383DE,0x05B383E0,0xBE,0xB6,99,0x3CB15E54,0x3CB15F80},
    {32,0x05B5C4D7,0x05B5C4DC,0x05B5C4DE,0xBF,0xBF,100,0x3C6F5E55,0x3C6F5F81}
};
static char g_ini[MAX_PATH],g_log[MAX_PATH];
static volatile LONG g_started;
static void log_line(const char *format, ...) {
    FILE *file;char message[768];va_list args;
    va_start(args,format);vsnprintf(message,sizeof(message),format,args);va_end(args);
    file=fopen(g_log,"ab");
    if(file){fprintf(file,"pid=%lu %s\r\n",GetCurrentProcessId(),message);fclose(file);}
}
static BOOL accessible(const void *address,SIZE_T size,BOOL writable) {
    MEMORY_BASIC_INFORMATION m;uintptr_t first=(uintptr_t)address,last;
    if(!address || size>UINTPTR_MAX-first)return FALSE;
    last=first+size;
    while(first<last){
        uintptr_t end;
        if(!VirtualQuery((const void*)first,&m,sizeof(m)) || m.State!=MEM_COMMIT ||
           (m.Protect&(PAGE_GUARD|PAGE_NOACCESS)))return FALSE;
        if(writable && !(m.Protect&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)))return FALSE;
        end=(uintptr_t)m.BaseAddress+m.RegionSize;
        if(end<=first)return FALSE;
        first=end;
    }
    return TRUE;
}
static DWORD get_u32(const BYTE *p){DWORD v;memcpy(&v,p,4);return v;}
static unsigned count_applied(const BYTE *descriptors,const BYTE *exe,DWORD image_size) {
    unsigned i,matched=0;
    for(i=0;i<61;i++){
        const BYTE *d=descriptors+i*72;uintptr_t target;SIZE_T length=d[8];
        memcpy(&target,d,8);
        if(length<1 || length>9 || target<(uintptr_t)exe ||
           target-(uintptr_t)exe>=image_size || length>image_size-(target-(uintptr_t)exe) ||
           !accessible((const void*)target,length,FALSE))return 0;
        if(!memcmp((const void*)target,d+18,length))matched++;
    }
    return matched;
}
static DWORD WINAPI compat_worker(LPVOID unused) {
    BYTE *exe=(BYTE*)GetModuleHandleA(NULL),*chain=NULL,*descriptors=NULL;
    IMAGE_NT_HEADERS64 *nt;ULONGLONG start=GetTickCount64();DWORD before[2],after[2];
    unsigned i,adjusted=0;BOOL ready=FALSE;(void)unused;
    if(!GetPrivateProfileIntA("TournamentListCompat","Aktiv",1,g_ini) ||
       !GetPrivateProfileIntA("Turnierliste","Aktiv",1,g_ini)){
        log_line("DISABLED; original competition-list behavior retained");return 0;
    }
    nt=(IMAGE_NT_HEADERS64*)(exe+((IMAGE_DOS_HEADER*)exe)->e_lfanew);
    if(nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 ||
       nt->FileHeader.TimeDateStamp!=0x577DE45C || nt->OptionalHeader.SizeOfImage<0x05BB5900){
        log_line("SKIPPED unsupported executable");return 1;
    }
    while(GetTickCount64()-start<600000){
        chain=(BYTE*)GetModuleHandleA("dinput8_l9_chain.dll");
        if(chain && accessible(chain+0x239A0,61*72,TRUE)){
            IMAGE_NT_HEADERS64 *l9=(IMAGE_NT_HEADERS64*)(chain+((IMAGE_DOS_HEADER*)chain)->e_lfanew);
            static const BYTE worker_prefix[8]={0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54};
            if(l9->FileHeader.TimeDateStamp!=0 || l9->OptionalHeader.SizeOfImage!=0x2D000 ||
               memcmp(chain+0x3DF0,worker_prefix,sizeof(worker_prefix))){
                log_line("SKIPPED unsupported original L9 worker");return 2;
            }
            descriptors=chain+0x239A0;
            if(count_applied(descriptors,exe,nt->OptionalHeader.SizeOfImage)==61){
                log_line("APPLIED original L9-10 already complete: 61/61, 400 entries");return 0;
            }
            ready=TRUE;
            for(i=0;i<2;i++){
                const CounterSite *s=g_sites+i;BYTE *d=descriptors+s->slot*72;uintptr_t target;
                memcpy(&target,d,8);
                if(target!=(uintptr_t)(exe+s->immediate_rva) || d[8]!=4 ||
                   get_u32(d+9)!=s->original_before || get_u32(d+18)!=s->original_after ||
                   !accessible(exe+s->seed_rva,5,FALSE) || !accessible(exe+s->instruction_rva,6,FALSE) ||
                   exe[s->seed_rva]!=s->seed_opcode || exe[s->instruction_rva]!=0x8D ||
                   exe[s->instruction_rva+1]!=s->lea_opcode){ready=FALSE;break;}
                before[i]=get_u32(exe+s->immediate_rva);
                if(get_u32(exe+s->seed_rva+1)+before[i]!=s->count){ready=FALSE;break;}
                after[i]=before[i]+300; /* 99 -> 399, 100 -> 400, modulo uint32. */
            }
            if(ready)break;
        }
        Sleep(20);
    }
    if(!ready){log_line("SKIPPED verified original descriptors/counts unavailable; no writes");return 3;}
    /* Publish BOTH replacement values first. The original readiness scan
     * cannot accept the mismatching descriptors until the before values
     * are published after the memory barrier. Cache-line-contained DWORD
     * stores preserve the original worker's all-sites-ready gate.
     */
    for(i=0;i<2;i++)if(before[i]!=g_sites[i].original_before){
        BYTE *d=descriptors+g_sites[i].slot*72;
        *(volatile DWORD*)(void*)(d+18)=after[i];adjusted++;
    }
    MemoryBarrier();
    for(i=0;i<2;i++)if(before[i]!=g_sites[i].original_before){
        BYTE *d=descriptors+g_sites[i].slot*72;
        *(volatile DWORD*)(void*)(d+9)=before[i];
        log_line("ADAPTED slot=%lu exe+%08lX encoded=%08lX->%08lX decoded=%lu->%lu",
                 g_sites[i].slot,g_sites[i].immediate_rva,before[i],after[i],g_sites[i].count,g_sites[i].count+300);
    }
    log_line("DESCRIPTORS adjusted=%u; original L9 worker owns all 61 executable edits",adjusted);
    start=GetTickCount64();
    while(GetTickCount64()-start<600000){
        if(count_applied(descriptors,exe,nt->OptionalHeader.SizeOfImage)==61){
            log_line("APPLIED original L9-10 complete: 61/61, 400 entries; constructor/destructor/search aligned");return 0;
        }
        Sleep(20);
    }
    log_line("ERROR original L9-10 completion not confirmed; matched=%u/61",
             count_applied(descriptors,exe,nt->OptionalHeader.SizeOfImage));return 4;
}
BOOL tournament_list_compat_start(const char *game_dir,const char *mod_dir) {
    HANDLE thread;
    if(InterlockedCompareExchange(&g_started,1,0))return TRUE;
    snprintf(g_ini,sizeof(g_ini),"%s\\dinput8_L9.ini",game_dir);
    snprintf(g_log,sizeof(g_log),"%s\\logs\\tournament_list_compat.log",mod_dir);
    thread=CreateThread(NULL,0,compat_worker,NULL,0,NULL);
    if(!thread){log_line("ERROR worker creation: %lu",GetLastError());return FALSE;}
    CloseHandle(thread);return TRUE;
}
