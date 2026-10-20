// Adapted from the local FIFA Mods Dev input gate for the CGFS selector.
#define WIN32_LEAN_AND_MEAN
#define DIRECTINPUT_VERSION 0x0800
#include <windows.h>
#include <dinput.h>
#include <stdint.h>
#include <string.h>
#include <vector>
#include "ranking_input_gate.h"
#include "mod_overlay_screens.h"
#pragma comment(lib, "dinput8.lib")
#pragma comment(lib, "dxguid.lib")

/* Filter the polling paths too: swallowing window messages does not stop
 * DirectInput or the separate frontend image's controller/cursor polling.
 * The overlay itself continues to read the real system state in our DLL. */
typedef HRESULT (WINAPI *CreateDeviceFn)(void *, REFGUID, void **, IUnknown *);
typedef HRESULT (WINAPI *DeviceStateFn)(void *, DWORD, void *);
typedef HRESULT (WINAPI *DeviceDataFn)(void *, DWORD, DIDEVICEOBJECTDATA *, DWORD *, DWORD);
typedef HRESULT (WINAPI *DataFormatFn)(void *, const DIDATAFORMAT *);
typedef HRESULT (WINAPI *PropertyFn)(void *, REFGUID, DIPROPHEADER *);
struct InputTable { void **table; CreateDeviceFn create; };
struct DeviceTable { void **table; DeviceStateFn state; DeviceDataFn data; DataFormatFn format; };
struct ObjectRule { DWORD offset, type; };
struct DeviceFormat {
    void *device;
    DWORD size;
    std::vector<ObjectRule> rules;
    std::vector<DWORD> held_buttons;
};
static SRWLOCK g_lock = SRWLOCK_INIT;
static std::vector<InputTable> g_inputs;
static std::vector<DeviceTable> g_devices;
static std::vector<DeviceFormat> g_formats;
static void (*g_logger)(const char *);
static volatile LONGLONG g_cursor_position;
static volatile LONG g_cursor_seen;

static bool replace_slot(void **slot, void *target)
{
    DWORD previous, ignored;
    if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &previous)) return false;
    InterlockedExchangePointer((PVOID volatile *)slot, target);
    VirtualProtect(slot, sizeof(void *), previous, &ignored);
    return true;
}
static DeviceTable device_table(void *device)
{
    DeviceTable result = {};
    AcquireSRWLockShared(&g_lock);
    for (const DeviceTable &item : g_devices)
        if (item.table == *(void ***)device) { result = item; break; }
    ReleaseSRWLockShared(&g_lock);
    return result;
}
static DeviceFormat *device_format_locked(void *device)
{
    for (DeviceFormat &item : g_formats) if (item.device == device) return &item;
    return NULL;
}
static void held_button(DeviceFormat &format, DWORD offset, bool down)
{
    for (size_t i = 0; i < format.held_buttons.size(); ++i)
        if (format.held_buttons[i] == offset) {
            if (!down) format.held_buttons.erase(format.held_buttons.begin() + i);
            return;
        }
    if (down) format.held_buttons.push_back(offset);
}
static bool is_button(const DeviceFormat &format, DWORD offset)
{
    for (const ObjectRule &rule : format.rules)
        if (rule.offset == offset && (rule.type & DIDFT_BUTTON)) return true;
    return false;
}
static HRESULT WINAPI gated_device_state(void *device, DWORD size, void *state)
{
    DeviceTable hooks = device_table(device);
    if (!hooks.state) return DIERR_NOTINITIALIZED;
    HRESULT result = hooks.state(device, size, state);
    if (FAILED(result) || !state) return result;
    bool capture = mod_screen_captures_input() != FALSE;
    AcquireSRWLockExclusive(&g_lock);
    DeviceFormat *format = device_format_locked(device);
    try {
    if (!format && (size == 256 || size == sizeof(DIMOUSESTATE) ||
        size == sizeof(DIMOUSESTATE2) || size == sizeof(DIJOYSTATE) || size == sizeof(DIJOYSTATE2))) {
        // Devices already created before injection use the standard DI layouts.
        DeviceFormat known = {}; known.device = device; known.size = size;
        if (size == 256) {
            for (DWORD i=0; i<256; ++i) known.rules.push_back({i,DIDFT_BUTTON});
        } else if (size == sizeof(DIMOUSESTATE) || size == sizeof(DIMOUSESTATE2)) {
            for (DWORD i=12; i<size; ++i) known.rules.push_back({i,DIDFT_BUTTON});
        } else {
            for (DWORD i=0; i<32; i+=4) known.rules.push_back({i,DIDFT_ABSAXIS});
            for (DWORD i=32; i<48; i+=4) known.rules.push_back({i,DIDFT_POV});
            for (DWORD i=48; i<80; ++i) known.rules.push_back({i,DIDFT_BUTTON});
        }
        g_formats.push_back(known); format = &g_formats.back();
    }
    } catch (...) {
        ReleaseSRWLockExclusive(&g_lock);
        return capture ? DIERR_NOTACQUIRED : result;
    }
    if (format && format->size == size) {
        unsigned char *bytes = (unsigned char *)state;
        try {
            if (capture) {
                for (const ObjectRule &rule : format->rules)
                    if ((rule.type & DIDFT_BUTTON) && rule.offset < size)
                        held_button(*format, rule.offset, (bytes[rule.offset] & 0x80) != 0);
                memset(state, 0, size);
                PropertyFn property = (PropertyFn)(*(void ***)device)[5];
                for (const ObjectRule &rule : format->rules) {
                    if (rule.offset > size || size - rule.offset < sizeof(LONG)) continue;
                    LONG neutral = 0;
                    if (rule.type & DIDFT_POV) neutral = -1;
                    else if (rule.type & DIDFT_ABSAXIS) {
                        DIPROPRANGE range = {};
                        range.diph.dwSize = sizeof(range);
                        range.diph.dwHeaderSize = sizeof(range.diph);
                        range.diph.dwObj = rule.offset;
                        range.diph.dwHow = DIPH_BYOFFSET;
                        neutral = property && SUCCEEDED(property(device, DIPROP_RANGE, &range.diph))
                            ? (LONG)((int64_t(range.lMin) + int64_t(range.lMax)) / 2) : 32767;
                    }
                    else if (!(rule.type & DIDFT_RELAXIS)) continue;
                    memcpy(bytes + rule.offset, &neutral, sizeof(neutral));
                }
            } else {
                if (size == 256 && selector_shortcut_enabled()) bytes[DIK_F12] = 0;
                /* A key/button held while closing must be released before it
                 * can act on the Hub; axes immediately return to the game. */
                for (size_t i = 0; i < format->held_buttons.size();) {
                    DWORD offset = format->held_buttons[i];
                    if (offset >= size || !(bytes[offset] & 0x80))
                        format->held_buttons.erase(format->held_buttons.begin() + i);
                    else { bytes[offset] = 0; ++i; }
                }
            }
        } catch (...) { if (capture) result = DIERR_NOTACQUIRED; }
    } else if (capture) {
        /* SetDataFormat normally precedes polling. Never invent a joystick
         * axis layout for an unknown/custom format: report no acquired input. */
        ReleaseSRWLockExclusive(&g_lock);
        return DIERR_NOTACQUIRED;
    }
    ReleaseSRWLockExclusive(&g_lock);
    return result;
}
static HRESULT WINAPI gated_device_data(void *device, DWORD stride,
    DIDEVICEOBJECTDATA *events, DWORD *count, DWORD flags)
{
    DeviceTable hooks = device_table(device);
    if (!hooks.data) return DIERR_NOTINITIALIZED;
    bool capture = mod_screen_captures_input() != FALSE;
    /* A peek must drain the real queue during capture, or hidden clicks would
     * be delivered to FIFA as soon as the overlay closes. */
    HRESULT result = hooks.data(device, stride, events, count,
        capture ? flags & ~DIGDD_PEEK : flags);
    if (FAILED(result) || !count) return result;
    AcquireSRWLockExclusive(&g_lock);
    DeviceFormat *format = device_format_locked(device);
    if (events && format && stride >= 16 && stride <= sizeof(DIDEVICEOBJECTDATA)) {
        DWORD kept = 0;
        try {
            for (DWORD i = 0; i < *count; ++i) {
                unsigned char *entry = (unsigned char *)events + size_t(i) * stride;
                DWORD offset, value;
                memcpy(&offset, entry, 4); memcpy(&value, entry + 4, 4);
                bool suppress = capture;
                if (!capture && format->size==256 && offset==DIK_F12 && selector_shortcut_enabled()) suppress=true;
                if (is_button(*format, offset)) {
                    if (capture) held_button(*format, offset, (value & 0x80) != 0);
                    else for (DWORD held : format->held_buttons)
                        if (held == offset) { suppress = true; break; }
                    if (!capture && suppress && !(value & 0x80)) held_button(*format, offset, false);
                }
                if (!suppress) {
                    if (kept != i) memmove((unsigned char *)events + size_t(kept) * stride, entry, stride);
                    ++kept;
                }
            }
        } catch (...) { if (capture) kept = 0; }
        *count = kept;
    } else if (capture) *count = 0;
    ReleaseSRWLockExclusive(&g_lock);
    return result;
}
static HRESULT WINAPI gated_data_format(void *device, const DIDATAFORMAT *source)
{
    DeviceTable hooks = device_table(device);
    if (!hooks.format) return DIERR_NOTINITIALIZED;
    HRESULT result = hooks.format(device, source);
    if (FAILED(result) || !source) return result;
    if (!source->rgodf || source->dwObjSize < sizeof(DIOBJECTDATAFORMAT) ||
        source->dwObjSize > 256 || source->dwNumObjs > 2048 ||
        !source->dwDataSize || source->dwDataSize > 65536) return result;
    DeviceFormat format = {};
    try {
        format.device = device; format.size = source->dwDataSize;
        for (DWORD i = 0; i < source->dwNumObjs; ++i) {
            const DIOBJECTDATAFORMAT *object = (const DIOBJECTDATAFORMAT *)
                ((const unsigned char *)source->rgodf + size_t(i) * source->dwObjSize);
            DWORD type = object->dwType & 0xFF;
            if ((type & DIDFT_AXIS) && (source->dwFlags & DIDF_RELAXIS)) type = DIDFT_RELAXIS;
            if (object->dwOfs < format.size) format.rules.push_back({object->dwOfs, type});
        }
        AcquireSRWLockExclusive(&g_lock);
        try {
            DeviceFormat *existing = device_format_locked(device);
            if (existing) *existing = format; else g_formats.push_back(format);
        } catch (...) { ReleaseSRWLockExclusive(&g_lock); return result; }
        ReleaseSRWLockExclusive(&g_lock);
    } catch (...) {}
    return result;
}
static void attach_device(void *device)
{
    void **table = *(void ***)device;
    AcquireSRWLockExclusive(&g_lock);
    for (const DeviceTable &item : g_devices)
        if (item.table == table) { ReleaseSRWLockExclusive(&g_lock); return; }
    DeviceTable hooks = {table, (DeviceStateFn)table[9], (DeviceDataFn)table[10], (DataFormatFn)table[11]};
    try { g_devices.push_back(hooks); }
    catch (...) { ReleaseSRWLockExclusive(&g_lock); return; }
    if (!replace_slot(table + 9, (void *)gated_device_state) ||
        !replace_slot(table + 10, (void *)gated_device_data) ||
        !replace_slot(table + 11, (void *)gated_data_format)) {
        replace_slot(table + 9, (void *)hooks.state);
        replace_slot(table + 10, (void *)hooks.data);
        replace_slot(table + 11, (void *)hooks.format);
        g_devices.pop_back();
    } else if (g_logger) g_logger("DirectInput device polling captured by ranking gate");
    ReleaseSRWLockExclusive(&g_lock);
}
static HRESULT WINAPI gated_create_device(void *input, REFGUID guid, void **device, IUnknown *outer)
{
    CreateDeviceFn original = NULL;
    AcquireSRWLockShared(&g_lock);
    for (const InputTable &item : g_inputs)
        if (item.table == *(void ***)input) { original = item.create; break; }
    ReleaseSRWLockShared(&g_lock);
    if (!original) return DIERR_NOTINITIALIZED;
    HRESULT result = original(input, guid, device, outer);
    if (SUCCEEDED(result) && device && *device) attach_device(*device);
    return result;
}
extern "C" void ranking_input_attach_directinput(void *input, const GUID *iid)
{
    /* IDirectInput8A/W share this ABI. Do not treat a requested IUnknown as
     * an IDirectInput8 interface or change any unsupported interface. */
    static const GUID ansi = {0xBF798030,0x483A,0x4DA2,{0xAA,0x99,0x5D,0x64,0xED,0x36,0x97,0x00}};
    static const GUID wide = {0xBF798031,0x483A,0x4DA2,{0xAA,0x99,0x5D,0x64,0xED,0x36,0x97,0x00}};
    if (!input || !iid || (memcmp(iid, &ansi, sizeof(ansi)) && memcmp(iid, &wide, sizeof(wide)))) return;
    void **table = *(void ***)input;
    AcquireSRWLockExclusive(&g_lock);
    for (const InputTable &item : g_inputs)
        if (item.table == table) { ReleaseSRWLockExclusive(&g_lock); return; }
    InputTable hooks = {table, (CreateDeviceFn)table[3]};
    try { g_inputs.push_back(hooks); }
    catch (...) { ReleaseSRWLockExclusive(&g_lock); return; }
    if (!replace_slot(table + 3, (void *)gated_create_device)) g_inputs.pop_back();
    else if (g_logger) g_logger("DirectInput8 CreateDevice intercepted for exclusive ranking input");
    ReleaseSRWLockExclusive(&g_lock);
}
static BOOL WINAPI gated_cursor_position(POINT *position)
{
    BOOL result = GetCursorPos(position); /* our DLL's import is never patched */
    if (!result || !position) return result;
    LONGLONG packed; memcpy(&packed, position, sizeof(packed));
    if (!mod_screen_captures_input() || !InterlockedCompareExchange(&g_cursor_seen, 0, 0)) {
        InterlockedExchange64(&g_cursor_position, packed);
        InterlockedExchange(&g_cursor_seen, 1);
    } else {
        packed = InterlockedCompareExchange64(&g_cursor_position, 0, 0);
        memcpy(position, &packed, sizeof(packed));
    }
    return result;
}
extern "C" BOOL ranking_input_install_cursor_import(HMODULE module)
{
    unsigned char *base = (unsigned char *)module;
    if (!base) return FALSE;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return FALSE;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return FALSE;
    DWORD rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return FALSE;
    BOOL installed = FALSE;
    for (IMAGE_IMPORT_DESCRIPTOR *entry = (IMAGE_IMPORT_DESCRIPTOR *)(base + rva); entry->Name; ++entry) {
        if (_stricmp((const char *)(base + entry->Name), "USER32.dll")) continue;
        IMAGE_THUNK_DATA64 *slot = (IMAGE_THUNK_DATA64 *)(base + entry->FirstThunk);
        if (!entry->OriginalFirstThunk) continue;
        IMAGE_THUNK_DATA64 *name = (IMAGE_THUNK_DATA64 *)(base + entry->OriginalFirstThunk);
        for (; name->u1.AddressOfData; ++name, ++slot) {
            if (IMAGE_SNAP_BY_ORDINAL64(name->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *symbol = (IMAGE_IMPORT_BY_NAME *)(base + name->u1.AddressOfData);
            if (strcmp((const char *)symbol->Name, "GetCursorPos")) continue;
            if ((void *)slot->u1.Function == (void *)gated_cursor_position) installed = TRUE;
            else if (replace_slot((void **)&slot->u1.Function, (void *)gated_cursor_position)) {
                installed = TRUE;
                if (g_logger) g_logger("FIFA cursor polling captured; overlay retains real cursor");
            }
        }
    }
    return installed;
}
extern "C" void ranking_input_set_logger(void (*logger)(const char *)) { g_logger = logger; }

static BOOL CALLBACK bootstrap_device(const DIDEVICEINSTANCEW *instance, void *context)
{
    IDirectInputDevice8W *device = NULL;
    if (SUCCEEDED(((IDirectInput8W *)context)->CreateDevice(instance->guidInstance,&device,NULL))) {
        attach_device(device);
        device->Release();
    }
    return DIENUM_CONTINUE;
}
static BOOL CALLBACK bootstrap_device_ansi(const DIDEVICEINSTANCEA *instance, void *context)
{
    IDirectInputDevice8A *device = NULL;
    if (SUCCEEDED(((IDirectInput8A *)context)->CreateDevice(instance->guidInstance,&device,NULL))) {
        attach_device(device);
        device->Release();
    }
    return DIENUM_CONTINUE;
}
extern "C" BOOL ranking_input_bootstrap(void)
{
    IDirectInput8W *input = NULL;
    if (FAILED(DirectInput8Create(GetModuleHandleW(NULL),DIRECTINPUT_VERSION,
        IID_IDirectInput8W,(void **)&input,NULL))) return FALSE;
    ranking_input_attach_directinput(input,&IID_IDirectInput8W);
    // Shared COM vtables also cover devices the game created before injection.
    IDirectInputDevice8W *device = NULL;
    if (SUCCEEDED(input->CreateDevice(GUID_SysKeyboard,&device,NULL))) { attach_device(device); device->Release(); }
    if (SUCCEEDED(input->CreateDevice(GUID_SysMouse,&device,NULL))) { attach_device(device); device->Release(); }
    input->EnumDevices(DI8DEVCLASS_GAMECTRL,bootstrap_device,input,DIEDFL_ATTACHEDONLY);
    input->Release();
    // A and W have separate device vtables. FIFA can create the ANSI devices
    // before injection; hooking only the Unicode table leaves them unfiltered.
    IDirectInput8A *ansi = NULL;
    if (FAILED(DirectInput8Create(GetModuleHandleW(NULL),DIRECTINPUT_VERSION,
        IID_IDirectInput8A,(void **)&ansi,NULL))) return FALSE;
    ranking_input_attach_directinput(ansi,&IID_IDirectInput8A);
    IDirectInputDevice8A *ansi_device = NULL;
    if (SUCCEEDED(ansi->CreateDevice(GUID_SysKeyboard,&ansi_device,NULL))) { attach_device(ansi_device); ansi_device->Release(); }
    if (SUCCEEDED(ansi->CreateDevice(GUID_SysMouse,&ansi_device,NULL))) { attach_device(ansi_device); ansi_device->Release(); }
    ansi->EnumDevices(DI8DEVCLASS_GAMECTRL,bootstrap_device_ansi,ansi,DIEDFL_ATTACHEDONLY);
    ansi->Release();
    if (g_logger) g_logger("Exclusive DirectInput capture ready for ANSI and Unicode devices");
    return TRUE;
}
