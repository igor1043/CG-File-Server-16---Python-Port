#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include "league_query_batches.h"

/* Verified build: FIFA 16 EXE RVA 05B82550. A fresh PID 7396 fault unwinds
 * through this builder with 96 team IDs, then WHERE/Lua expression evaluation,
 * then a corrupted PPMalloc free-list at 05810EC4. The suggested allocator
 * global 0379C940 is non-NULL. The existing 64 node slots are not exhausted.
 *
 * This wrapper retains the original builder and its six attribute passes.
 * Each pass receives <=30 distinct IDs. Original code appends results to the
 * supplied output vector (05B82704..05B8276A), so the batches preserve every
 * club and pass ordering. Normal queries stay on the original single call.
 * It does not catch exceptions, ignore a club, fake an allocator or alter
 * competition data. The root cause of the parser corruption is not claimed
 * to be conclusively identified by this mitigation.
 */
typedef struct TeamIds {
    const int32_t *data;
    int32_t count;
    int32_t attributes;
} TeamIds;
typedef void (__fastcall *BuildQuery)(void *, const TeamIds *, void *, int, int, int);
static BuildQuery g_original;
static char g_log[MAX_PATH],g_ini[MAX_PATH];
static SRWLOCK g_lock=SRWLOCK_INIT;
static volatile LONG g_started,g_calls;
static PRUNTIME_FUNCTION g_unwind;
static int g_batch_size=30;
static unsigned char *g_trampoline;

static void log_line(const char *format, ...) {
    char line[768];va_list args;FILE *file;SYSTEMTIME now;
    va_start(args,format);vsnprintf(line,sizeof(line),format,args);va_end(args);
    GetLocalTime(&now);AcquireSRWLockExclusive(&g_lock);
    file=fopen(g_log,"ab");
    if(file) {
        fprintf(file,"[%04u-%02u-%02u %02u:%02u:%02u] pid=%lu %s\r\n",
                now.wYear,now.wMonth,now.wDay,now.wHour,now.wMinute,now.wSecond,
                GetCurrentProcessId(),line);fclose(file);
    }
    ReleaseSRWLockExclusive(&g_lock);
}
static BOOL readable(const void *p,SIZE_T size) {
    MEMORY_BASIC_INFORMATION memory;
    uintptr_t cursor=(uintptr_t)p,end;
    if(!p || size>UINTPTR_MAX-cursor)return FALSE;
    end=cursor+size;
    while(cursor<end) {
        uintptr_t boundary;
        if(!VirtualQuery((const void *)cursor,&memory,sizeof(memory)) ||
           memory.State!=MEM_COMMIT || (memory.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return FALSE;
        boundary=(uintptr_t)memory.BaseAddress+memory.RegionSize;
        if(boundary<=cursor)return FALSE;
        cursor=boundary;
    }
    return TRUE;
}
static void __fastcall bounded_query(void *context,const TeamIds *ids,
                                    void *output,int flags,int arg5,int arg6) {
    int32_t unique[102];int count=0,i,j,pass,calls=0;
    TeamIds slice;
    LONG invocation;
    if(!readable(ids,sizeof(*ids)) || ids->count<=g_batch_size ||
       ids->count>102 || flags<=0 || !readable(ids->data,(SIZE_T)ids->count*sizeof(int32_t))) {
        g_original(context,ids,output,flags,arg5,arg6);return;
    }
    /* WHERE predicates already treat repeated IDs as a set. Deduplication
     * prevents cross-batch duplicates without changing that behavior. */
    for(i=0;i<ids->count;i++) {
        for(j=0;j<count && unique[j]!=ids->data[i];j++) {}
        if(j==count)unique[count++]=ids->data[i];
    }
    slice.attributes=ids->attributes;
    /* Keep original pass-major order; flags outside the original six passes
     * are ignored by the original builder too. Output is shared and appended. */
    for(pass=0;pass<6;pass++) if(flags&(1<<pass)) {
        for(i=0;i<count;i+=g_batch_size) {
            slice.data=unique+i;
            slice.count=count-i<g_batch_size?count-i:g_batch_size;
            g_original(context,&slice,output,1<<pass,arg5,arg6);calls++;
        }
    }
    invocation=InterlockedIncrement(&g_calls);
    if(invocation<=64 || invocation%100==0)
        log_line("BATCHED invocation=%ld input=%d distinct=%d flags=%X batch_max=%d native_calls=%d",
                 invocation,ids->count,count,(unsigned int)flags,g_batch_size,calls);
}
static void absolute_jump(unsigned char *p,const void *target) {
    uint64_t address=(uint64_t)(uintptr_t)target;
    p[0]=0xff;p[1]=0x25;memset(p+2,0,4);memcpy(p+6,&address,8);
}
static DWORD WINAPI install_worker(LPVOID unused) {
    static const unsigned char original[15]={
        0x48,0x89,0x5c,0x24,0x10,0x4c,0x89,0x44,0x24,0x18,0x48,0x89,0x4c,0x24,0x08};
    unsigned char *exe=(unsigned char *)GetModuleHandleA(NULL),*target=exe+0x05B82550;
    unsigned char replacement[15];DWORD protection,ignored;ULONGLONG start=GetTickCount64();
    IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64 *)(exe+((IMAGE_DOS_HEADER *)exe)->e_lfanew);
    void *callback=NULL;(void)unused;
    if(nt->FileHeader.TimeDateStamp!=0x577DE45C || nt->OptionalHeader.SizeOfImage<=0x05B8255F) {
        log_line("SKIPPED unsupported executable build");return 1;
    }
    while(!readable(target,sizeof(original)) || memcmp(target,original,sizeof(original))) {
        if(GetTickCount64()-start>=600000) {log_line("SKIPPED builder signature unavailable; original retained");return 2;}
        Sleep(50);
    }
    g_trampoline=(unsigned char *)VirtualAlloc(NULL,0x1000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    g_unwind=(PRUNTIME_FUNCTION)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*g_unwind));
    if(!g_trampoline || !g_unwind) {log_line("ERROR trampoline allocation");return 3;}
    memcpy(g_trampoline,original,sizeof(original));absolute_jump(g_trampoline+15,target+15);
    /* The stolen prologue saves RBX at entry RSP+10h and does not adjust RSP.
     * Register AMD64 unwind metadata for the trampoline, including its jump. */
    g_trampoline[32]=1;g_trampoline[33]=15;g_trampoline[34]=2;g_trampoline[35]=0;
    g_trampoline[36]=5;g_trampoline[37]=0x34;g_trampoline[38]=2;g_trampoline[39]=0;
    g_unwind->BeginAddress=0;g_unwind->EndAddress=29;g_unwind->UnwindData=32;
    if(!RtlAddFunctionTable(g_unwind,1,(DWORD64)(uintptr_t)g_trampoline) ||
       !VirtualProtect(g_trampoline,0x1000,PAGE_EXECUTE_READ,&protection)) {
        log_line("ERROR trampoline registration/protection; original retained");return 4;
    }
    memcpy(&g_original,&g_trampoline,sizeof(g_original));
    { BuildQuery entry=bounded_query;memcpy(&callback,&entry,sizeof(callback)); }
    absolute_jump(replacement,callback);replacement[14]=0x90;
    if(memcmp(target,original,sizeof(original)) ||
       !VirtualProtect(target,sizeof(original),PAGE_EXECUTE_READWRITE,&protection)) {
        log_line("ERROR builder changed/protection; original retained");return 5;
    }
    memcpy(target,replacement,sizeof(replacement));
    FlushInstructionCache(GetCurrentProcess(),target,sizeof(replacement));
    VirtualProtect(target,sizeof(replacement),protection,&ignored);
    log_line("APPLIED exe+05B82550; max=%d IDs per query; original builder/results retained",g_batch_size);
    return 0;
}
BOOL league_query_batches_start(const char *game_dir,const char *mod_dir) {
    HANDLE thread;
    if(InterlockedCompareExchange(&g_started,1,0))return TRUE;
    snprintf(g_ini,sizeof(g_ini),"%s\\dinput8_L9.ini",game_dir);
    snprintf(g_log,sizeof(g_log),"%s\\logs\\league_query_batches.log",mod_dir);
    if(GetPrivateProfileIntA("LeagueQueryBatches","Aktiv",1,g_ini)!=1) {
        log_line("disabled; original builder retained");return TRUE;
    }
    g_batch_size=(int)GetPrivateProfileIntA("LeagueQueryBatches","MaxTeamsPerQuery",30,g_ini);
    if(g_batch_size<1 || g_batch_size>30) {log_line("ERROR batch size must be 1..30");return FALSE;}
    thread=CreateThread(NULL,0,install_worker,NULL,0,NULL);
    if(!thread) {log_line("ERROR creating installation thread");return FALSE;}
    CloseHandle(thread);return TRUE;
}
