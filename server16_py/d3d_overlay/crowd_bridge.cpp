#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "crowd_bridge.h"
#include <cmath>
#include <cstring>
#include <cstdio>

// Same deterministic record and allocation offset as the validated crowd DLL.
// Never search for a float/signature at arbitrary offsets or edit disk assets.
static const SIZE_T RECORD_OFFSET=0x364D0;
static const BYTE RECORD_KEY[8]={0x2e,0x4b,0x96,0xd2,0x25,0x96,0x20,0xa0};
struct CrowdTarget { BYTE *allocation; float baseline, written; bool owned; };
static CrowdTarget g_targets[2]={};
static size_t g_target_count;
static CrowdShared *g_crowd;
static LONG g_manual=-1;
static void (*g_crowd_log)(const char *);
static decltype(&GetPrivateProfileIntA) g_profile=GetPrivateProfileIntA;
static void crowd_status(LONG status) {
    static LONG previous=-1;
    g_crowd->status=status;
    if (status!=previous && g_crowd_log) {
        char message[180];
        sprintf_s(message,"Crowd bridge: status=%ld (0=unsupported,1=locating,2=ready,3=applied,4=failed); targets=%llu",status,(unsigned long long)g_target_count);
        g_crowd_log(message);
    }
    previous=status;
}

static bool writable(DWORD protection) {
    if (protection&(PAGE_GUARD|PAGE_NOACCESS)) return false;
    DWORD p=protection&255;
    return p==PAGE_READWRITE || p==PAGE_WRITECOPY ||
           p==PAGE_EXECUTE_READWRITE || p==PAGE_EXECUTE_WRITECOPY;
}
static bool record_valid(const BYTE *record) {
    float value=0; memcpy(&value,record+8,4);
    return !memcmp(record,RECORD_KEY,8) && std::isfinite(value) && value>=0 && value<=1.2f;
}
static bool read_target(const CrowdTarget &target,float &value) {
    BYTE *record=target.allocation+RECORD_OFFSET;
    MEMORY_BASIC_INFORMATION region={}; BYTE bytes[12]={}; SIZE_T read=0;
    if (!VirtualQuery(record,&region,sizeof(region)) || region.State!=MEM_COMMIT ||
        region.Type!=MEM_PRIVATE || region.AllocationBase!=target.allocation ||
        !writable(region.Protect) || record<(BYTE *)region.BaseAddress ||
        record+12>(BYTE *)region.BaseAddress+region.RegionSize ||
        !ReadProcessMemory(GetCurrentProcess(),record,bytes,sizeof(bytes),&read) || read!=12 ||
        !record_valid(bytes)) return false;
    memcpy(&value,bytes+8,4); return true;
}
static bool write_target(CrowdTarget &target,float value) {
    float current; SIZE_T written=0;
    if (!std::isfinite(value) || value<0 || value>1.2f || !read_target(target,current)) return false;
    if (fabsf(current-value)>.0001f &&
        (!WriteProcessMemory(GetCurrentProcess(),target.allocation+RECORD_OFFSET+8,
                            &value,4,&written) || written!=4)) return false;
    return read_target(target,current) && fabsf(current-value)<.0001f;
}
static bool known_plugin(HMODULE plugin) {
    if (!plugin) return false;
    auto base=(BYTE *)plugin; auto dos=(IMAGE_DOS_HEADER *)base;
    if (dos->e_magic!=IMAGE_DOS_SIGNATURE) return false;
    auto nt=(IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    const BYTE locator[16]={0x48,0x85,0xc9,0x0f,0x84,0x2f,0x02,0,0,0x4c,0x8b,0xdc,0x53,0x48,0x81,0xec};
    return nt->Signature==IMAGE_NT_SIGNATURE && nt->FileHeader.TimeDateStamp==0x6ab7f3db &&
        nt->OptionalHeader.SizeOfImage==0x4a000 && !memcmp(base+0x21380,RECORD_KEY,8) &&
        !memcmp(base+0x3600,locator,16);
}
static bool channel_live() {
    return g_crowd && g_crowd->owner_pid && g_crowd->game_pid==GetCurrentProcessId() &&
        (DWORD)(GetTickCount()-g_crowd->heartbeat)<2000;
}
// Override only this plugin's static input. The career controller still computes
// and publishes its own automatic value, which is recovered after this fixture.
static UINT WINAPI crowd_profile(LPCSTR section,LPCSTR key,INT fallback,LPCSTR file) {
    LONG manual=InterlockedCompareExchange(&g_manual,0,0);
    if (manual>=0 && manual<=100 && channel_live() && g_crowd->phase &&
        g_crowd->requested_percent==manual && section && key &&
        !_stricmp(section,"crowd") && !_stricmp(key,"static_factor_percent")) return (UINT)manual;
    return g_profile(section,key,fallback,file);
}
static bool install_profile_bridge(HMODULE plugin) {
    auto base=(BYTE *)plugin; auto dos=(IMAGE_DOS_HEADER *)base;
    auto nt=(IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    DWORD rva=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return false;
    for (auto imp=(IMAGE_IMPORT_DESCRIPTOR *)(base+rva);imp->Name;++imp) {
        if (!imp->OriginalFirstThunk) continue;
        auto slot=(IMAGE_THUNK_DATA64 *)(base+imp->FirstThunk);
        auto names=(IMAGE_THUNK_DATA64 *)(base+imp->OriginalFirstThunk);
        for (int i=0;names[i].u1.AddressOfData;++i) {
            if (IMAGE_SNAP_BY_ORDINAL64(names[i].u1.Ordinal)) continue;
            auto symbol=(IMAGE_IMPORT_BY_NAME *)(base+names[i].u1.AddressOfData);
            if (strcmp((char *)symbol->Name,"GetPrivateProfileIntA")) continue;
            if ((void *)slot[i].u1.Function==(void *)crowd_profile) return true;
            // Refuse to chain an unknown third-party config hook.
            if ((void *)slot[i].u1.Function!=(void *)GetPrivateProfileIntA) return false;
            DWORD old,ignored;
            if (!VirtualProtect(&slot[i].u1.Function,sizeof(void *),PAGE_READWRITE,&old)) return false;
            InterlockedExchangePointer((PVOID volatile *)&slot[i].u1.Function,(void *)crowd_profile);
            VirtualProtect(&slot[i].u1.Function,sizeof(void *),old,&ignored);
            return true;
        }
    }
    return false;
}
static int career_automatic_percent() {
    HMODULE career=GetModuleHandleW(L"dinput8.dll");
    auto version=(DWORD (WINAPI *)())GetProcAddress(career,"Fifa16CareerApiVersion");
    auto state=(BOOL (WINAPI *)(LONG *,LONG *))GetProcAddress(career,"Fifa16CareerGetState");
    LONG club=0,competition=0;
    if (!version || !state || version()!=1 || !state(&club,&competition)) return -1;
    wchar_t path[MAX_PATH]={}; GetModuleFileNameW(nullptr,path,MAX_PATH);
    auto slash=wcsrchr(path,L'\\'); if (!slash) return -1; *slash=0;
    if (wcslen(path)+wcslen(L"\\ModCarrerMode\\crowd.ini")>=MAX_PATH) return -1;
    wcscat_s(path,L"\\ModCarrerMode\\crowd.ini");
    int percent=(int)GetPrivateProfileIntW(L"crowd",L"static_factor_percent",-1,path);
    return percent>=0 && percent<=100 ? percent : -1;
}
static void restore_targets() {
    InterlockedExchange(&g_manual,-1);
    bool owned=false;
    for (size_t i=0;i<g_target_count;++i) owned=owned || g_targets[i].owned;
    if (!owned) return;
    int automatic=career_automatic_percent();
    for (size_t i=0;i<g_target_count;++i) {
        auto &target=g_targets[i]; float current;
        if (target.owned && read_target(target,current) && fabsf(current-target.written)<.0001f) {
            if (!write_target(target,automatic>=0 ? automatic/100.f : target.baseline)) {
                if (g_crowd_log) g_crowd_log("Crowd restore deferred: validated target unavailable");
                continue;
            }
        }
        target.owned=false;
    }
    if (g_crowd_log) g_crowd_log("Crowd manual override released; automatic controller preserved");
}
static void locate_targets() {
    g_target_count=0;
    SYSTEM_INFO info={}; GetSystemInfo(&info);
    BYTE *address=(BYTE *)info.lpMinimumApplicationAddress;
    while (address<(BYTE *)info.lpMaximumApplicationAddress) {
        MEMORY_BASIC_INFORMATION region={};
        if (!VirtualQuery(address,&region,sizeof(region))) break;
        BYTE *next=(BYTE *)region.BaseAddress+region.RegionSize;
        if (next<=address) break;
        if (region.State==MEM_COMMIT && region.Type==MEM_PRIVATE &&
            region.BaseAddress==region.AllocationBase && writable(region.Protect) &&
            region.RegionSize>=0x100000 && region.RegionSize<=0x1000000) {
            CrowdTarget target={(BYTE *)region.AllocationBase,0,0,false}; float value;
            if (read_target(target,value)) {
                // More matches than the original DLL supports is ambiguous.
                if (g_target_count==2) { g_target_count=0; return; }
                target.baseline=value; g_targets[g_target_count++]=target;
            }
        }
        address=next;
    }
}
static DWORD WINAPI crowd_worker(void *) {
    LONG generation=-1,home=0,away=0; DWORD next_scan=0;
    bool hooked=false;
    for (;;) {
        if (!g_crowd) {
            HANDLE map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,L"Local\\CGFS16_Crowd_v1");
            if (map) { g_crowd=(CrowdShared *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(CrowdShared)); CloseHandle(map); }
        }
        bool live=channel_live();
        LONG phase=live ? g_crowd->phase : 0;
        if (!phase || generation!=g_crowd->generation || home!=g_crowd->home_id || away!=g_crowd->away_id) {
            restore_targets();
            if (live) { generation=g_crowd->generation; home=g_crowd->home_id; away=g_crowd->away_id; }
        }
        if (!live || !phase) { Sleep(100); continue; }
        HMODULE plugin=GetModuleHandleW(L"crowd_plugin.dll");
        if (!known_plugin(plugin) || (!hooked && !(hooked=install_profile_bridge(plugin)))) {
            restore_targets();
            crowd_status(0); Sleep(250); continue;
        }
        float value=0;
        bool valid=g_target_count>0;
        for (size_t i=0;i<g_target_count;++i) valid=read_target(g_targets[i],value) && valid;
        if (!valid) {
            restore_targets();
            g_target_count=0;
            if ((LONG)(GetTickCount()-next_scan)>=0) { locate_targets(); next_scan=GetTickCount()+2000; }
            if (!g_target_count) { crowd_status(1); Sleep(100); continue; }
        }
        LONG command=g_crowd->command,requested=g_crowd->requested_percent;
        if (command<0) { Sleep(10); continue; }
        if (requested<0) {
            restore_targets();
            for (size_t i=0;i<g_target_count;++i) read_target(g_targets[i],g_targets[i].baseline);
            crowd_status(2);
        } else if (requested<=100 && channel_live() && g_crowd->phase && g_crowd->command==command &&
                   g_crowd->generation==generation && g_crowd->home_id==home && g_crowd->away_id==away) {
            bool success=true;
            for (size_t i=0;i<g_target_count;++i) {
                auto &target=g_targets[i];
                if (!target.owned) {
                    success=read_target(target,target.baseline) && success;
                    target.owned=true;
                }
            }
            InterlockedExchange(&g_manual,requested);
            for (size_t i=0;i<g_target_count;++i) {
                auto &target=g_targets[i];
                target.written=requested/100.f;
                success=write_target(target,target.written) && success;
            }
            if (!success) { restore_targets(); crowd_status(4); }
            else {
                crowd_status(3);
                if (g_crowd->ack!=command && g_crowd_log) {
                    char message[120]; sprintf_s(message,"Crowd applied: percent=%ld fixture=%ld:%ld generation=%ld",requested,home,away,generation);
                    g_crowd_log(message);
                }
            }
        }
        if (read_target(g_targets[0],value)) g_crowd->current_percent=(LONG)std::lround(value*100);
        int automatic=career_automatic_percent();
        g_crowd->automatic_percent=automatic>=0 ? automatic : (LONG)std::lround(g_targets[0].baseline*100);
        if (g_crowd->command==command && g_crowd->generation==generation &&
            g_crowd->home_id==home && g_crowd->away_id==away && g_crowd->status!=4) {
            MemoryBarrier();
            g_crowd->ack=command;
        }
        Sleep(100);
    }
}
void crowd_bridge_start(void (*logger)(const char *)) {
    static LONG started=0;
    if (InterlockedCompareExchange(&started,1,0)) return;
    g_crowd_log=logger;
    HANDLE thread=CreateThread(nullptr,0,crowd_worker,nullptr,0,nullptr);
    if (thread) CloseHandle(thread); else { InterlockedExchange(&started,0); if (logger) logger("Crowd bridge thread failed to start"); }
}
