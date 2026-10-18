#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <intrin.h>
#include <errno.h>

static char game_dir[MAX_PATH],log_path[MAX_PATH];
static volatile LONG started,capacity_ready;
static BOOL read_memory(const void *p,void *out,SIZE_T size) {
    SIZE_T got=0;return p && ReadProcessMemory(GetCurrentProcess(),p,out,size,&got) && got==size;
}
static int integer(const BYTE *p) {int value;memcpy(&value,p,4);return value;}
static BOOL valid_dds(const char *path) {
    FILE *file=fopen(path,"rb");BYTE header[128];size_t got;
    if(!file)return FALSE;
    got=fread(header,1,sizeof(header),file);fclose(file);
    return got==128 && !memcmp(header,"DDS ",4) && integer(header+4)==124 &&
        integer(header+12)>0 && integer(header+12)<=4096 && integer(header+16)>0 && integer(header+16)<=4096;
}
static void log_line(const char *message,int a,int b) {
    FILE *file=fopen(log_path,"ab");if(!file)return;
    fprintf(file,"pid=%lu %s %d %d\r\n",GetCurrentProcessId(),message,a,b);fclose(file);
}
static BOOL expanded_layout_ready(void) {
    BYTE *exe=(BYTE*)GetModuleHandleA(NULL),*chain=(BYTE*)GetModuleHandleA("dinput8_l9_chain.dll");
    IMAGE_DOS_HEADER dos;IMAGE_NT_HEADERS64 nt;BYTE descriptors[61*72];unsigned i;
    if(InterlockedCompareExchange(&capacity_ready,0,0))return TRUE;
    if(!exe || !chain || !read_memory(exe,&dos,sizeof(dos)) || dos.e_lfanew<0 || dos.e_lfanew>0x1000 ||
       !read_memory(exe+dos.e_lfanew,&nt,sizeof(nt)) || nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 ||
       nt.FileHeader.TimeDateStamp!=0x577DE45C || !read_memory(chain+0x239A0,descriptors,sizeof(descriptors)))return FALSE;
    for(i=0;i<61;i++) {
        const BYTE *d=descriptors+i*72;uintptr_t target;BYTE actual[9];unsigned size=d[8];memcpy(&target,d,8);
        if(!size || size>9 || target<(uintptr_t)exe || target-(uintptr_t)exe>=nt.OptionalHeader.SizeOfImage ||
           size>nt.OptionalHeader.SizeOfImage-(target-(uintptr_t)exe) || !read_memory((void*)target,actual,size) || memcmp(actual,d+18,size))return FALSE;
    }
    InterlockedExchange(&capacity_ready,1);return TRUE;
}
static int resolve_rows(const BYTE *rows,size_t count,int root) {
    size_t i;int found=0;
    for(i=0;i<count;i++) {
        const BYTE *row=rows+i*0x5c;
        if(integer(row)!=root)continue;
        if(integer(row+4)!=3 || memcmp(row+12,"CRTR\0",5) || memcmp(row+17,"cm_pst_",7) || !memchr(row+17,0,35))return 0;
        if(found)return 0;
        found=integer(row+0x54);
        if(!((found>=820 && found<=822) || (found>=840 && found<=851) || (found>=860 && found<=871)))return 0;
    }
    return found;
}
static BOOL existing_calendar(int asset);
__declspec(dllexport) int WINAPI Fifa16UiAssetsResolvePreseason(int root,const void *registry) {
    BYTE *wrapper=NULL,*competition=NULL;BYTE rows[400*0x5c];int asset;
    if(root<=0 || root>65535 || !registry || !game_dir[0] || !expanded_layout_ready())return 0;
    if(!read_memory((const BYTE*)registry+20*32+24,&wrapper,sizeof(wrapper)) || !read_memory(wrapper,&competition,sizeof(competition)) ||
       !competition || !read_memory(competition+0x10,rows,sizeof(rows)))return 0;
    asset=resolve_rows(rows,400,root);if(!asset)return 0;
    return existing_calendar(asset)?asset:0;
}
#include "asset_catalog.inc"
#include "compat_aliases.inc"
#ifndef UI_ASSETS_TEST
#include "path_hooks.inc"
#include "keeper_pitch_hook.inc"
#include "keeper_squad_hook.inc"
#endif
static DWORD WINAPI worker(void *unused) {
    unsigned attempt;(void)unused;prepare_aliases(game_dir);build_catalog();
    if(!calendar_count)log_line("EMPTY careerCompetitionIcons; keeper repair remains enabled",4,0);
#ifndef UI_ASSETS_TEST
    {
        BOOL calendar_ready=FALSE,keeper_ready=FALSE,squad_ready=FALSE;
        for(attempt=0;attempt<900;attempt++) {
            if(expanded_layout_ready()) {
                if(!keeper_ready)keeper_ready=install_keeper_pitch_hook();
                if(!squad_ready)squad_ready=install_keeper_squad_hook();
                if(!calendar_ready)calendar_ready=install_path_hooks();
                if(keeper_ready && calendar_ready && squad_ready){log_line("READY calendar resolver, Starting XI and squad keeper repair",5,0);return 0;}
            }
            Sleep(100);
        }
        log_line("UNSUPPORTED or busy calendar/keeper hooks",calendar_ready,keeper_ready);
        log_line("SQUAD keeper hook ready",squad_ready,0);
    }
#else
    (void)attempt;
#endif
    return 0;
}
__declspec(dllexport) unsigned WINAPI Fifa16ModGetApiVersion(void) {return 1;}
__declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char *mods_root) {
    char *slash;HANDLE thread;HMODULE pinned;
    if(!mods_root || strlen(mods_root)>MAX_PATH-110)return FALSE;
    if(InterlockedCompareExchange(&started,1,0))return TRUE;
    snprintf(game_dir,sizeof(game_dir),"%s",mods_root);
    slash=strrchr(game_dir,'\\');if(!slash)return FALSE;*slash=0;
    snprintf(log_path,sizeof(log_path),"%s\\logs\\career_ui_assets.log",game_dir);
    slash=strrchr(game_dir,'\\');if(!slash)return FALSE;*slash=0;
    if(!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCSTR)&started,&pinned))return FALSE;
    thread=CreateThread(NULL,0,worker,NULL,0,NULL);if(!thread)return FALSE;CloseHandle(thread);return TRUE;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved) {(void)reserved;if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);return TRUE;}
