// Adapted from the local FIFA Mods Dev input gate for the CGFS selector.
#define WIN32_LEAN_AND_MEAN
#include "mod_xinput_gate.h"
#include "mod_overlay_screens.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef DWORD (WINAPI *StateFn)(DWORD, XINPUT_STATE *);
struct XInputEntry {
    const char *name;
    StateFn filter;
    StateFn raw;
    const unsigned char *signature;
    LONG captured;
    bool installed;
    bool rejected_logged;
};
static DWORD WINAPI get_state_91(DWORD index, XINPUT_STATE *state);
static DWORD WINAPI get_state_14(DWORD index, XINPUT_STATE *state);
/* Complete instructions, no RIP-relative operands, captured read-only from
 * the loaded Microsoft DLLs on 2026-10-01. Unknown builds are not patched. */
static const unsigned char k_prologue_91[13] = {
    0x48,0x89,0x5C,0x24,0x08,0x57,0x48,0x83,0xEC,0x20,0x48,0x8B,0xDA
};
static const unsigned char k_prologue_14[13] = {
    0x48,0x89,0x5C,0x24,0x08,0x56,0x57,0x41,0x56,0x48,0x83,0xEC,0x30
};
static XInputEntry g_entries[] = {
    {"xinput9_1_0.dll",get_state_91,NULL,k_prologue_91,0,false,false},
    {"xinput1_4.dll",get_state_14,NULL,k_prologue_14,0,false,false}
};
struct HeldPad { WORD buttons; BYTE axes; };
static SRWLOCK g_pad_lock = SRWLOCK_INIT;
static HeldPad g_held[4];
static volatile LONG g_installing;
static volatile LONG g_packet;
static void (*g_log)(const char *);
static thread_local unsigned g_raw_depth;
struct RawReadScope {
    RawReadScope() { ++g_raw_depth; }
    ~RawReadScope() { --g_raw_depth; }
};

static bool axis_down(SHORT value, SHORT deadzone)
{ return value > deadzone || value < -deadzone; }
static DWORD filter_state(XInputEntry &entry, DWORD index, XINPUT_STATE *state)
{
    if (!entry.raw) return ERROR_DEVICE_NOT_CONNECTED;
    /* 9.1 can delegate to 1.4: a trampoline alone does not guarantee a raw
     * feed. Nested system calls on this thread bypass every export filter. */
    if (g_raw_depth) return entry.raw(index,state);
    DWORD result;
    { RawReadScope raw_read; result = entry.raw(index,state); }
    if (result != ERROR_SUCCESS || !state || index >= 4) return result;
    bool capture = mod_screen_captures_input() != FALSE;
    AcquireSRWLockExclusive(&g_pad_lock);
    HeldPad &held = g_held[index];
    XINPUT_GAMEPAD &pad = state->Gamepad;
    if (capture) {
        held.buttons = pad.wButtons;
        held.axes = (BYTE)((axis_down(pad.sThumbLX,XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE) ? 1 : 0) |
            (axis_down(pad.sThumbLY,XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE) ? 2 : 0) |
            (axis_down(pad.sThumbRX,XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE) ? 4 : 0) |
            (axis_down(pad.sThumbRY,XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE) ? 8 : 0) |
            (pad.bLeftTrigger > XINPUT_GAMEPAD_TRIGGER_THRESHOLD ? 16 : 0) |
            (pad.bRightTrigger > XINPUT_GAMEPAD_TRIGGER_THRESHOLD ? 32 : 0));
        memset(&pad,0,sizeof(pad));
        InterlockedIncrement(&entry.captured);
        state->dwPacketNumber = (DWORD)InterlockedIncrement(&g_packet);
    } else {
        if (selector_shortcut_enabled()) {
            if (selector_audio_mode()) {
                const WORD combo=XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
                if ((pad.wButtons & combo)==combo) pad.wButtons &= (WORD)~combo;
            } else if (!(pad.wButtons & XINPUT_GAMEPAD_BACK))
                pad.wButtons &= (WORD)~XINPUT_GAMEPAD_START;
        }
        WORD previous_buttons = held.buttons;
        held.buttons &= pad.wButtons;
        pad.wButtons &= (WORD)~previous_buttons;
        BYTE previous_axes = held.axes;
#define RELEASE_AXIS(bit,field,deadzone) \
        if (held.axes & (bit)) { \
            if (!axis_down(pad.field,deadzone)) held.axes &= (BYTE)~(bit); \
            pad.field = 0; \
        }
        RELEASE_AXIS(1,sThumbLX,XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE)
        RELEASE_AXIS(2,sThumbLY,XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE)
        RELEASE_AXIS(4,sThumbRX,XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE)
        RELEASE_AXIS(8,sThumbRY,XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE)
#undef RELEASE_AXIS
        if (held.axes & 16) { if (pad.bLeftTrigger <= XINPUT_GAMEPAD_TRIGGER_THRESHOLD) held.axes &= ~16; pad.bLeftTrigger = 0; }
        if (held.axes & 32) { if (pad.bRightTrigger <= XINPUT_GAMEPAD_TRIGGER_THRESHOLD) held.axes &= ~32; pad.bRightTrigger = 0; }
        if (previous_buttons || previous_axes)
            state->dwPacketNumber = (DWORD)InterlockedIncrement(&g_packet);
    }
    ReleaseSRWLockExclusive(&g_pad_lock);
    return result;
}
static DWORD WINAPI get_state_91(DWORD index, XINPUT_STATE *state)
{ return filter_state(g_entries[0],index,state); }
static DWORD WINAPI get_state_14(DWORD index, XINPUT_STATE *state)
{ return filter_state(g_entries[1],index,state); }
extern "C" DWORD WINAPI mod_xinput_read_raw(DWORD index, XINPUT_STATE *state)
{
    /* Trampolines bypass the filters. Prefer the original 9.1 feed retained
     * by the ranking implementation, falling back to 1.4 if only it exists. */
    DWORD result=ERROR_DEVICE_NOT_CONNECTED;
    for (const XInputEntry &entry : g_entries)
        if (entry.raw) {
            RawReadScope raw_read; result=entry.raw(index,state);
            if (result==ERROR_SUCCESS) return result;
        }
    return result;
}
static void jump_to(unsigned char *code, const void *destination)
{
    code[0]=0x48; code[1]=0xB8;
    memcpy(code+2,&destination,sizeof(destination));
    code[10]=0xFF; code[11]=0xE0;
}
static bool install_export(XInputEntry &entry, unsigned char *target)
{
    if (entry.installed) return true;
    if (!target) return false;
    StateFn previous_gate=nullptr;
    const bool original=memcmp(target,entry.signature,13)==0;
    if (!original) {
        // Chain the exact absolute detour used by FIFA Mods Dev. Never
        // decode/copy unknown instructions or replace its retained raw feed.
        if (target[0]!=0x48 || target[1]!=0xB8 || target[10]!=0xFF || target[11]!=0xE0 || target[12]!=0x90)
            return false;
        memcpy(&previous_gate,target+2,sizeof(previous_gate));
        MEMORY_BASIC_INFORMATION region={};
        if (!previous_gate || previous_gate==entry.filter || previous_gate==(StateFn)target ||
            !VirtualQuery((void *)previous_gate,&region,sizeof(region)) || region.State!=MEM_COMMIT ||
            (region.Protect & (PAGE_GUARD|PAGE_NOACCESS)) ||
            !(region.Protect & (PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY)))
            return false;
    }
    unsigned char *trampoline=nullptr;
    if (original) {
        trampoline=(unsigned char *)VirtualAlloc(NULL,25,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        if (!trampoline) return false;
        memcpy(trampoline,target,13);
        jump_to(trampoline+13,target+13);
    }
    DWORD previous,ignored;
    if ((trampoline && !VirtualProtect(trampoline,25,PAGE_EXECUTE_READ,&ignored)) ||
        !VirtualProtect(target,13,PAGE_EXECUTE_READWRITE,&previous)) {
        if (trampoline) VirtualFree(trampoline,0,MEM_RELEASE);
        return false;
    }
    /* Save the callable raw feed before publishing the process-local hook. */
    entry.raw = trampoline ? (StateFn)trampoline : previous_gate;
    unsigned char patch[13]; jump_to(patch,(const void *)entry.filter); patch[12]=0x90;
    if (trampoline) FlushInstructionCache(GetCurrentProcess(),trampoline,25);
    memcpy(target,patch,13);
    FlushInstructionCache(GetCurrentProcess(),target,13);
    VirtualProtect(target,13,previous,&ignored);
    entry.installed = true;
    if (previous_gate && g_log) g_log("Compatible existing XInput detour chained; prior gate preserved");
    return true;
}
static bool microsoft_module(HMODULE module,const char *name)
{
    char path[MAX_PATH],system[MAX_PATH],expected[MAX_PATH];
    if (!GetModuleFileNameA(module,path,sizeof(path)) ||
        !GetSystemDirectoryA(system,sizeof(system))) return false;
    _snprintf_s(expected,sizeof(expected),_TRUNCATE,"%s\\%s",system,name);
    return !_stricmp(path,expected);
}
static bool patch_game_imports(HMODULE module)
{
    unsigned char *base = (unsigned char *)module;
    if (!base) return false;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return false;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return false;
    DWORD rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return false;
    bool changed = false;
    for (IMAGE_IMPORT_DESCRIPTOR *imp=(IMAGE_IMPORT_DESCRIPTOR *)(base+rva);imp->Name;++imp) {
        for (XInputEntry &entry : g_entries) {
            if (!entry.installed || _stricmp((const char *)(base+imp->Name),entry.name)) continue;
            IMAGE_THUNK_DATA64 *slot=(IMAGE_THUNK_DATA64 *)(base+imp->FirstThunk);
            IMAGE_THUNK_DATA64 *names=imp->OriginalFirstThunk ? (IMAGE_THUNK_DATA64 *)(base+imp->OriginalFirstThunk) : NULL;
            StateFn export_fn=(StateFn)GetProcAddress(GetModuleHandleA(entry.name),"XInputGetState");
            for (size_t i=0;slot[i].u1.Function;++i) {
                bool match;
                if (names) {
                    match=!IMAGE_SNAP_BY_ORDINAL64(names[i].u1.Ordinal) &&
                        !strcmp((const char *)((IMAGE_IMPORT_BY_NAME *)(base+names[i].u1.AddressOfData))->Name,"XInputGetState");
                } else match=(StateFn)slot[i].u1.Function==export_fn || (StateFn)slot[i].u1.Function==entry.filter;
                if (!match || (StateFn)slot[i].u1.Function==entry.filter) continue;
                DWORD previous,ignored;
                if (VirtualProtect(&slot[i].u1.Function,sizeof(void *),PAGE_READWRITE,&previous)) {
                    InterlockedExchangePointer((PVOID volatile *)&slot[i].u1.Function,(void *)entry.filter);
                    VirtualProtect(&slot[i].u1.Function,sizeof(void *),previous,&ignored);
                    changed=true;
                }
            }
        }
    }
    return changed;
}
extern "C" BOOL mod_xinput_install(void (*logger)(const char *))
{
    if (InterlockedCompareExchange(&g_installing,1,0)) return FALSE;
    g_log=logger;
    BOOL ready=FALSE;
    for (XInputEntry &entry : g_entries) {
        HMODULE module=GetModuleHandleA(entry.name);
        if (!module || !microsoft_module(module,entry.name)) continue;
        if (!entry.installed) {
            if (install_export(entry,(unsigned char *)GetProcAddress(module,"XInputGetState"))) {
                if (g_log) { char message[200]; _snprintf_s(message,sizeof(message),_TRUNCATE,
                    "exclusive XInput export gate installed: %s; cached GetState pointers covered; raw trampoline preserved",entry.name); g_log(message); }
            } else if (!entry.rejected_logged) {
                entry.rejected_logged=true;
                if (g_log) { char message[180]; _snprintf_s(message,sizeof(message),_TRUNCATE,
                    "XInput export gate rejected: %s unknown prologue; no bytes changed",entry.name); g_log(message); }
            }
        }
        ready=ready || entry.installed;
    }
    HMODULE frontend=GetModuleHandleA(NULL),gameplay=GetModuleHandleA("fifa16.bin");
    if (patch_game_imports(frontend) && g_log) g_log("exclusive XInput IAT gate refreshed in FIFA frontend");
    if (gameplay!=frontend && patch_game_imports(gameplay) && g_log) g_log("exclusive XInput IAT gate refreshed in fifa16.bin");
    InterlockedExchange(&g_installing,0);
    return ready;
}
extern "C" void mod_xinput_log_capture_stats(void)
{
    if (!g_log) return;
    for (XInputEntry &entry : g_entries) {
        char message[160];
        LONG count=InterlockedExchange(&entry.captured,0);
        _snprintf_s(message,sizeof(message),_TRUNCATE,
            "XInput capture evidence: %s installed=%d filtered_calls=%ld",entry.name,entry.installed?1:0,count);
        g_log(message);
    }
}
