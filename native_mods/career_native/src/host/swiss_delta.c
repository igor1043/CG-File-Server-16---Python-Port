#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "swiss_delta.h"
#include "swiss_byte_patches.h"
#include "league_query_batches.h"
#include "tournament_list_compat.h"

/* The original L9.65 image is kept byte-for-byte. Resource 102 contains ONLY
 * eight selected Swiss patch routines, callbacks and supporting functions.
 * Its format is a sparse image, with no PE header, entry point or exports.
 * Worker addresses are pinned to the reviewed donor SHA in the extractor.
 * The V12 code owns configuration, import binding, startup and shared sites.
 * Kit-key and league-size byte changes are reconstructed in this C source.
 * Startup requires BOTH the V12 native hooks and original DirectInput ready.
 */
typedef struct DeltaState {
    HMODULE host;
    char game[MAX_PATH], mod[MAX_PATH], ini[MAX_PATH], log[MAX_PATH];
    unsigned char *image;
    DWORD image_size;
    PRUNTIME_FUNCTION unwind;
    DWORD unwind_count;
    HANDLE log_handle;
} DeltaState;
static DeltaState g_delta;
static volatile LONG g_started;
static volatile LONG g_ready;
static SRWLOCK g_log_lock=SRWLOCK_INIT;

static void delta_log(const char *format, ...) {
    char line[1024]; va_list args; FILE *out; SYSTEMTIME now;
    GetLocalTime(&now);
    va_start(args,format); vsnprintf(line,sizeof(line),format,args); va_end(args);
    AcquireSRWLockExclusive(&g_log_lock);
    out=fopen(g_delta.log,"ab");
    if(out) { fprintf(out,"[%04u-%02u-%02u %02u:%02u:%02u] [V12 Swiss pid=%lu] %s\r\n", now.wYear,now.wMonth,now.wDay,now.wHour,now.wMinute,now.wSecond,GetCurrentProcessId(),line); fclose(out); }
    ReleaseSRWLockExclusive(&g_log_lock);
}
static BOOL range_valid(DWORD rva, DWORD size) {
    return rva <= g_delta.image_size && size <= g_delta.image_size-rva;
}
static BOOL take(const unsigned char **cursor, const unsigned char *end,
                 void *out, size_t size) {
    if ((size_t)(end-*cursor)<size) return FALSE;
    if(out) memcpy(out,*cursor,size);
    *cursor+=size; return TRUE;
}
static BOOL load_selected_resource(void) {
    HRSRC resource=FindResourceA(g_delta.host,MAKEINTRESOURCEA(102),RT_RCDATA);
    HGLOBAL loaded; const unsigned char *cursor,*end; char magic[8];
    uint64_t original_base; DWORD counts[5],i,protection;
    if(!resource) return FALSE;
    loaded=LoadResource(g_delta.host,resource);
    if(!loaded) return FALSE;
    cursor=(const unsigned char*)LockResource(loaded);
    end=cursor+SizeofResource(g_delta.host,resource);
    if(!cursor || !take(&cursor,end,magic,8) || memcmp(magic,"SWDELTA1",8) ||
       !take(&cursor,end,&original_base,8) || !take(&cursor,end,counts,sizeof(counts))) return FALSE;
    if(counts[0]!=0x38000 || counts[1]>128 || counts[2]>1024 ||
       counts[3]>128 || counts[4]>128) return FALSE;
    g_delta.image_size=counts[0];
    g_delta.image=(unsigned char*)VirtualAlloc(NULL,g_delta.image_size,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    if(!g_delta.image) return FALSE;
    memset(g_delta.image+0x1000,0xCC,0x1B000);
    for(i=0;i<counts[1];i++) {
        DWORD record[3];
        if(!take(&cursor,end,record,sizeof(record)) || !range_valid(record[0],record[1]) ||
           !take(&cursor,end,g_delta.image+record[0],record[1])) return FALSE;
    }
    for(i=0;i<counts[2];i++) {
        DWORD rva; uint64_t value;
        if(!take(&cursor,end,&rva,4) || !range_valid(rva,8)) return FALSE;
        memcpy(&value,g_delta.image+rva,8);
        if(value<original_base || value-original_base>=g_delta.image_size) return FALSE;
        value=(uint64_t)(uintptr_t)g_delta.image+(value-original_base);
        memcpy(g_delta.image+rva,&value,8);
    }
    for(i=0;i<counts[3];i++) {
        DWORD rva; WORD lengths[2]; const char *library,*name; HMODULE imported; FARPROC symbol;
        if(!take(&cursor,end,&rva,4) || !take(&cursor,end,lengths,4) ||
           !range_valid(rva,8) || !lengths[0] || !lengths[1]) return FALSE;
        library=(const char*)cursor;
        if(!take(&cursor,end,NULL,lengths[0]) || library[lengths[0]-1]) return FALSE;
        name=(const char*)cursor;
        if(!take(&cursor,end,NULL,lengths[1]) || name[lengths[1]-1]) return FALSE;
        if(_stricmp(library,"KERNEL32.dll") && _stricmp(library,"msvcrt.dll")) return FALSE;
        imported=GetModuleHandleA(library);
        if(!imported) imported=LoadLibraryExA(library,NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!imported || !(symbol=GetProcAddress(imported,name))) return FALSE;
        memcpy(g_delta.image+rva,&symbol,8);
    }
    g_delta.unwind_count=counts[4];
    g_delta.unwind=(PRUNTIME_FUNCTION)calloc(counts[4],sizeof(RUNTIME_FUNCTION));
    if(!g_delta.unwind) return FALSE;
    if(!take(&cursor,end,g_delta.unwind,counts[4]*sizeof(RUNTIME_FUNCTION)) || cursor!=end) return FALSE;
    for(i=0;i<counts[4];i++) {
        RUNTIME_FUNCTION *entry=g_delta.unwind+i;
        if(entry->BeginAddress>=entry->EndAddress || !range_valid(entry->BeginAddress,entry->EndAddress-entry->BeginAddress) ||
           !range_valid(entry->UnwindData,4)) return FALSE;
    }
    if(!RtlAddFunctionTable(g_delta.unwind,counts[4],(DWORD64)(uintptr_t)g_delta.image)) return FALSE;
    if(!VirtualProtect(g_delta.image+0x1000,0x1B000,PAGE_EXECUTE_READ,&protection)) return FALSE;
    FlushInstructionCache(GetCurrentProcess(),g_delta.image+0x1000,0x1B000);
    return TRUE;
}
static int active(const char *section,int fallback) {
    return GetPrivateProfileIntA(section,"Aktiv",fallback,g_delta.ini)==1;
}
static void put_int(DWORD rva,int value) { memcpy(g_delta.image+rva,&value,4); }
static BOOL configure_scoreboards(void) {
    char entries[8192],*entry; int league_count=0,tournament_count=0;
    DWORD result=GetPrivateProfileSectionA("Scoreboards",entries,sizeof(entries),g_delta.ini);
    if(result>=sizeof(entries)-2) return FALSE;
    put_int(0x2D6E8,active("Scoreboards",0));
    put_int(0x2D6EC,(int)GetPrivateProfileIntA("Scoreboards","Sonde",0,g_delta.ini));
    for(entry=entries;*entry;entry+=strlen(entry)+1) {
        const char *number=NULL; char *finish; long id,set; DWORD id_rva,set_rva; int *count;
        if(!_strnicmp(entry,"Liga",4)) { number=entry+4; id_rva=0x2D6F8;set_rva=0x2D778;count=&league_count; }
        else if(!_strnicmp(entry,"Turnier",7)) { number=entry+7;id_rva=0x2D7F8;set_rva=0x2D878;count=&tournament_count; }
        else continue;
        id=strtol(number,&finish,10);
        if(finish==number || *finish!='=' || id<=0 || id>99999 || *count>=32) return FALSE;
        number=finish+1;set=strtol(number,&finish,10);
        while(*finish==' '||*finish=='\t') finish++;
        if(finish==number || (*finish && *finish!=';' && *finish!='#') || set<0 || set>99) return FALSE;
        put_int(id_rva+4*(DWORD)*count,(int)id);
        put_int(set_rva+4*(DWORD)*count,(int)set);
        (*count)++;
    }
    put_int(0x2D6F0,league_count);put_int(0x2D6F4,tournament_count);
    return TRUE;
}
static BOOL configure_ids(const char *section,const char *key,DWORD count_rva,
                          DWORD list_rva,int capacity,BOOL continental) {
    char text[1024],*at,*end; int count=0; long id;
    GetPrivateProfileStringA(section,key,"",text,sizeof(text),g_delta.ini);
    at=text;
    while(*at && *at!=';' && *at!='#') {
        while(*at==' '||*at=='\t'||*at==',') at++;
        if(!*at || *at==';'||*at=='#') break;
        id=strtol(at,&end,10);
        if(end==at || id<=0 || id>99999 || count>=capacity ||
           (continental && id!=940 && id!=950 && id!=960)) return FALSE;
        put_int(list_rva+4*(DWORD)count++,(int)id);at=end;
    }
    put_int(count_rva,count); return count>0;
}
static void start_selected(const char *label,DWORD rva) {
    HANDLE thread;
    LPTHREAD_START_ROUTINE entry;void *address=g_delta.image+rva;
    memcpy(&entry,&address,sizeof(entry));
    thread=CreateThread(NULL,0,entry,NULL,0,NULL);
    if(thread) { CloseHandle(thread);delta_log("started selected routine: %s rva=%08lX",label,rva); }
    else delta_log("ERROR starting selected routine: %s error=%lu",label,GetLastError());
}
static BOOL readable(const void *pointer,SIZE_T size) {
    MEMORY_BASIC_INFORMATION memory;
    if(!VirtualQuery(pointer,&memory,sizeof(memory)) || memory.State!=MEM_COMMIT ||
       (memory.Protect&(PAGE_NOACCESS|PAGE_GUARD))) return FALSE;
    return (uintptr_t)pointer+size <= (uintptr_t)memory.BaseAddress+memory.RegionSize;
}
static BOOL write_expected(void *target,const void *expected,const void *replacement,SIZE_T size) {
    DWORD protection,ignored;
    if(!readable(target,size) || memcmp(target,expected,size)) return FALSE;
    if(!VirtualProtect(target,size,PAGE_EXECUTE_READWRITE,&protection)) return FALSE;
    memcpy(target,replacement,size);FlushInstructionCache(GetCurrentProcess(),target,size);
    VirtualProtect(target,size,protection,&ignored);
    return !memcmp(target,replacement,size);
}
typedef struct SwissByteJob {
    const char *label;
    const SwissBytePatch *patches;
    size_t count;
} SwissByteJob;
static const SwissByteJob g_byte_jobs[2]={
    {"unsigned kit keys",swiss_kit_keys,sizeof(swiss_kit_keys)/sizeof(swiss_kit_keys[0])},
    {"league capacity",swiss_league_capacity,sizeof(swiss_league_capacity)/sizeof(swiss_league_capacity[0])}
};
static DWORD WINAPI apply_byte_job(LPVOID parameter) {
    const SwissByteJob *job=(const SwissByteJob*)parameter;
    unsigned char *exe=(unsigned char*)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64*)(exe+((IMAGE_DOS_HEADER*)exe)->e_lfanew);
    DWORD image_size=nt->OptionalHeader.SizeOfImage;
    ULONGLONG start=GetTickCount64();BYTE changed[49];size_t i;
    if(job->count>sizeof(changed)) return 1;
    for(;;) {
        BOOL ready=TRUE;
        for(i=0;i<job->count;i++) {
            const SwissBytePatch *p=job->patches+i;
            if(p->rva>image_size || p->length>image_size-p->rva || !readable(exe+p->rva,p->length) ||
               (memcmp(exe+p->rva,p->before,p->length) && memcmp(exe+p->rva,p->after,p->length))) {
                ready=FALSE;break;
            }
        }
        if(ready) break;
        if(GetTickCount64()-start>=600000) {
            delta_log("SKIPPED %s: original signature unavailable; original game code retained",job->label);
            return 2;
        }
        Sleep(50);
    }
    memset(changed,0,sizeof(changed));
    for(i=0;i<job->count;i++) {
        const SwissBytePatch *p=job->patches+i;
        if(!memcmp(exe+p->rva,p->after,p->length)) continue;
        if(!write_expected(exe+p->rva,p->before,p->after,p->length)) {
            size_t j=i;
            while(j) {
                const SwissBytePatch *undo=job->patches+--j;
                if(changed[j]) (void)write_expected(exe+undo->rva,undo->after,undo->before,undo->length);
            }
            delta_log("ERROR %s: byte transaction refused; preceding writes rolled back",job->label);
            return 3;
        }
        changed[i]=1;
    }
    delta_log("APPLIED in original host C: %s, %zu/%zu byte sites",job->label,job->count,job->count);
    return 0;
}
static void start_byte_job(size_t index) {
    HANDLE thread=CreateThread(NULL,0,apply_byte_job,(LPVOID)(g_byte_jobs+index),0,NULL);
    if(thread) CloseHandle(thread);
    else delta_log("ERROR starting C byte transaction: %s",g_byte_jobs[index].label);
}
static BOOL rel32(unsigned char *at,const void *destination) {
    intptr_t value=(const unsigned char*)destination-(at+4);
    int32_t packed_distance=(int32_t)value;
    if(value!=(intptr_t)packed_distance) return FALSE;
    memcpy(at,&packed_distance,4);return TRUE;
}
static unsigned char *near_page(unsigned char *base) {
    uintptr_t origin=(uintptr_t)base&~(uintptr_t)0xFFFF,step;
    for(step=0x10000;step<0x70000000;step+=0x10000) {
        unsigned char *page;
        page=(unsigned char*)VirtualAlloc((void*)(origin+step),0x2000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
        if(page) return page;
        if(origin>step) {
            page=(unsigned char*)VirtualAlloc((void*)(origin-step),0x2000,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
            if(page) return page;
        }
    }
    return NULL;
}
/* Only the THIRD FCE guard is ported. The two original guards are still
 * installed by the unchanged L9.65; they are not overwritten or restarted.
 * This reconstruction follows donor descriptor 0x23C80 and emitter 0x7116.
 */
static DWORD WINAPI fce_delta_worker(LPVOID unused) {
    static const unsigned char expected[6]={0x48,0x8B,0xD0,0x41,0x8B,0xC4};
    static const unsigned char exit_expected[3]={0x0F,0x57,0xC0};
    HMODULE previous=NULL;unsigned char *page=NULL;DWORD reported=0;
    (void)unused;
    for(;;) {
        unsigned char *fce=(unsigned char*)GetModuleHandleA("FootballCompEngzf.dll");
        if(!fce) { previous=NULL;Sleep(200);continue; }
        if(readable(fce+0x6700A,6) && readable(fce+0x67065,3) &&
           readable(fce+0x1044C,5) && !memcmp(fce+0x6700A,expected,6) &&
           !memcmp(fce+0x67065,exit_expected,3) && fce[0x1044C]==0x3D) {
            DWORD limit;memcpy(&limit,fce+0x1044D,4);
            if(limit==1000 || limit==10000) {
                unsigned char hook[6]={0xE9,0,0,0,0,0x90};DWORD protection;
                page=near_page(fce);
                if(page) {
                    static const unsigned char prefix[9]={0x48,0x85,0xC0,0x0F,0x84,0x0B,0,0,0};
                    memcpy(page,prefix,9);memcpy(page+9,expected,6);
                    page[15]=0xE9;page[20]=0xF0;page[21]=0xFF;page[22]=0x05;page[27]=0xE9;
                    if(rel32(page+16,fce+0x67010) && rel32(page+23,page+0x1000) &&
                       rel32(page+28,fce+0x67065)) {
                        intptr_t displacement=page-(fce+0x6700F);int32_t packed_distance=(int32_t)displacement;
                        memcpy(hook+1,&packed_distance,4);
                        if(displacement==(intptr_t)packed_distance && VirtualProtect(page,0x1000,PAGE_EXECUTE_READ,&protection)) {
                            DWORD next=10000;
                            FlushInstructionCache(GetCurrentProcess(),page,0x1000);
                            if(limit==10000 || write_expected(fce+0x1044D,&limit,&next,4)) {
                                if(write_expected(fce+0x6700A,expected,hook,6)) {
                                    previous=(HMODULE)fce;reported=0;
                                    delta_log("FCE delta applied: THIRD guard +6700A, capacity 10000; original two guards retained");
                                } else if(limit==1000) {
                                    (void)write_expected(fce+0x1044D,&next,&limit,4);
                                }
                            }
                        }
                    }
                    if((HMODULE)fce!=previous) { VirtualFree(page,0,MEM_RELEASE);page=NULL; }
                }
            }
        }
        if(previous && page) {
            DWORD count=*(volatile DWORD*)(page+0x1000);
            if(count!=reported) { delta_log("FCE third guard hits=%lu",count);reported=count; }
        }
        Sleep(200);
    }
}
/* Shared budget sites are handed over AFTER the original L9.65 worker has
 * installed its original values. No competing budget worker is imported.
 */
static DWORD WINAPI budget_delta_worker(LPVOID unused) {
    unsigned char *exe=(unsigned char*)GetModuleHandleA(NULL);ULONGLONG start=GetTickCount64();
    DWORD before[2]={2500000,2300000},after[2],rva[2]={0x032DC2E0,0x032DCFA8};
    int done[2]={0,0};(void)unused;
    after[0]=GetPrivateProfileIntA("Speicherbudget","Karriere",2500000,g_delta.ini);
    after[1]=GetPrivateProfileIntA("Speicherbudget","Turnier",2300000,g_delta.ini);
    if(after[0]<1000000 || after[0]>20000000 || after[1]<1000000 || after[1]>20000000) {
        delta_log("ERROR invalid budget configuration; original values retained");return 1;
    }
    while(GetTickCount64()-start<600000 && (!done[0] || !done[1])) {
        int i;
        for(i=0;i<2;i++) if(!done[i] && readable(exe+rva[i],4)) {
            DWORD value;memcpy(&value,exe+rva[i],4);
            if(value==after[i]) done[i]=1;
            else if(value==before[i] && write_expected(exe+rva[i],before+i,after+i,4)) {
                done[i]=1;delta_log("budget handover %d: %lu -> %lu",i,before[i],after[i]);
            }
        }
        if(!done[0] || !done[1]) Sleep(50);
    }
    if(!done[0] || !done[1]) delta_log("ERROR budget handover incomplete %d/2",done[0]+done[1]);
    return (DWORD)(done[0]+done[1]!=2);
}
static DWORD WINAPI delta_worker(LPVOID unused) {
    ULONGLONG start=GetTickCount64();unsigned char *exe;DWORD size;HANDLE thread;
    IMAGE_DOS_HEADER *dos;IMAGE_NT_HEADERS64 *nt;char runtime_log[MAX_PATH];
    (void)unused;
    if(!active("SwissIntegration",0)) { delta_log("disabled; original host/L9.65 active");return 0; }
    while(!GetModuleHandleA("dinput8_l9_chain.dll")) {
        if(GetTickCount64()-start>600000) {delta_log("ERROR original L9.65 not loaded");return 1;}
        Sleep(50);
    }
    /* Both ready notifications have already arrived. No guessed delay. */
    if(!load_selected_resource()) {delta_log("ERROR loading selected-function resource; original host/L9 retained");return 2;}
    exe=(unsigned char*)GetModuleHandleA(NULL);dos=(IMAGE_DOS_HEADER*)exe;
    nt=(IMAGE_NT_HEADERS64*)(exe+dos->e_lfanew);size=nt->OptionalHeader.SizeOfImage;
    memcpy(g_delta.image+0x312D8,&exe,8);memcpy(g_delta.image+0x312D4,&size,4);
    InitializeCriticalSection((LPCRITICAL_SECTION)(void*)(g_delta.image+0x31400));
    snprintf(runtime_log,sizeof(runtime_log),"%s\\logs\\swiss_delta_patches.log",g_delta.mod);
    g_delta.log_handle=CreateFileA(runtime_log,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    memcpy(g_delta.image+0x1C020,&g_delta.log_handle,8);
    delta_log("restart revision 7: V12 native hooks AND original DirectInput ready; original L9.65 retained");
    (void)tournament_list_compat_start(g_delta.game,g_delta.mod);
    (void)league_query_batches_start(g_delta.game,g_delta.mod);
    if(active("Trikotschluessel",0)) start_byte_job(0);
    if(active("Ligengroesse",0)) start_byte_job(1);
    if(active("Karrierewaechter",1)) start_selected("career lookup guard",0x4C80);
    if(active("Tabellenwaechter",1)) start_selected("weekly standings guard",0x5330);
    if(active("Entlinkschutz",1)) start_selected("list unlink guard",0x57A0);
    if(active("Trikotliste",1)) start_selected("kit carousel",0x5BE0);
    if(configure_scoreboards() && (active("Scoreboards",0) || GetPrivateProfileIntA("Scoreboards","Sonde",0,g_delta.ini))) {
        start_selected("scoreboards BCE",0x6930);start_selected("scoreboards EXE",0xCFE0);
    }
    if(active("Ligensperre",0) && configure_ids("Ligensperre","Ligen",0x2D994,0x2D9A0,16,FALSE))
        start_selected("league filter (optional)",0x3E90);
    if(active("Kontinentalturniere",0) && configure_ids("Kontinentalturniere","Turniere",0x2D980,0x2D988,3,TRUE))
        start_selected("continental routing (optional)",0x4500);
    if(active("FCEWaechter",1)) {
        thread=CreateThread(NULL,0,fce_delta_worker,NULL,0,NULL);if(thread) CloseHandle(thread);
    }
    if(active("Speicherbudget",1)) {
        thread=CreateThread(NULL,0,budget_delta_worker,NULL,0,NULL);if(thread) CloseHandle(thread);
    }
    return 0;
}
static BOOL swiss_delta_start(HMODULE host,const char *game_dir,const char *mod_dir) {
    HANDLE thread;
    if(InterlockedCompareExchange(&g_started,1,0)) return TRUE;
    g_delta.host=host;
    strncpy_s(g_delta.game,sizeof(g_delta.game),game_dir,_TRUNCATE);
    strncpy_s(g_delta.mod,sizeof(g_delta.mod),mod_dir,_TRUNCATE);
    snprintf(g_delta.ini,sizeof(g_delta.ini),"%s\\dinput8_L9.ini",game_dir);
    snprintf(g_delta.log,sizeof(g_delta.log),"%s\\logs\\swiss_delta_loader.log",mod_dir);
    thread=CreateThread(NULL,0,delta_worker,NULL,0,NULL);
    if(!thread) {delta_log("ERROR starting adapter error=%lu",GetLastError());return FALSE;}
    CloseHandle(thread);return TRUE;
}

/* Either completion order is valid. The second notification starts once.
 * Failure of either original V12 path leaves all Swiss writes inactive. */
void swiss_delta_notify_ready(HMODULE host,const char *game_dir,const char *mod_dir,LONG stage) {
    LONG previous=InterlockedOr(&g_ready,stage);
    if(((previous|stage)&3)==3) (void)swiss_delta_start(host,game_dir,mod_dir);
}
