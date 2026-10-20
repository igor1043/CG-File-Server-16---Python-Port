// Synthetic input only: no hooks installed and no FIFA process accessed.
#include "../server16_py/d3d_overlay/mod_xinput_gate.cpp"
#include "../server16_py/d3d_overlay/ranking_input_gate.cpp"
#include <cassert>
static BOOL capturing=FALSE, shortcuts=FALSE;
static BOOL audio_mode=FALSE;
extern "C" BOOL mod_screen_captures_input(void) { return capturing; }
extern "C" BOOL selector_shortcut_enabled(void) { return shortcuts; }
extern "C" BOOL selector_audio_mode(void) { return audio_mode; }
static XINPUT_STATE fake_pad;
static BYTE fake_keys[256];
static DIMOUSESTATE2 fake_mouse;
static DWORD observed_buffer_flags;
static HRESULT WINAPI read_mouse(void *,DWORD size,void *state) {
    if(size!=sizeof(fake_mouse)) return DIERR_INVALIDPARAM;
    memcpy(state,&fake_mouse,size); return DI_OK;
}
static HRESULT WINAPI read_buffer(void *,DWORD,DIDEVICEOBJECTDATA *events,DWORD *count,DWORD flags) {
    observed_buffer_flags=flags;
    if(events && *count) { events[0]={};events[0].dwOfs=12;events[0].dwData=0x80;*count=1; }
    return DI_OK;
}
static DWORD WINAPI read_pad(DWORD index,XINPUT_STATE *state) {
    if (index>=4 || !state) return ERROR_DEVICE_NOT_CONNECTED;
    *state=fake_pad; return ERROR_SUCCESS;
}
static DWORD WINAPI disconnected_pad(DWORD,XINPUT_STATE *) { return ERROR_DEVICE_NOT_CONNECTED; }
static HRESULT WINAPI read_keys(void *,DWORD size,void *state) {
    if (size!=256) return DIERR_INVALIDPARAM;
    memcpy(state,fake_keys,256); return DI_OK;
}
static void print_log(const char *message) { puts(message); }
int main(int argc,char **) {
    if (argc>1) {
        LoadLibraryExW(L"xinput1_4.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
        ranking_input_set_logger(print_log);
        BOOL di=ranking_input_bootstrap();
        BOOL xi=mod_xinput_install(print_log);
        printf("Live system bootstrap: DirectInput=%d XInput=%d\n",di,xi);
        return di && xi ? 0 : 1;
    }
    XInputEntry entry={}; entry.raw=read_pad;
    fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_A;
    fake_pad.Gamepad.sThumbLX=20000;
    XINPUT_STATE result={};
    assert(filter_state(entry,0,&result)==ERROR_SUCCESS);
    assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_A);
    capturing=TRUE; filter_state(entry,0,&result);
    assert(result.Gamepad.wButtons==0 && result.Gamepad.sThumbLX==0);
    capturing=FALSE; filter_state(entry,0,&result);
    assert(result.Gamepad.wButtons==0 && result.Gamepad.sThumbLX==0);
    fake_pad.Gamepad={}; filter_state(entry,0,&result);
    fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_A; filter_state(entry,0,&result);
    assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_A);
    shortcuts=TRUE; fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_START;
    filter_state(entry,0,&result); assert(result.Gamepad.wButtons==0);
    fake_pad.Gamepad.wButtons|=XINPUT_GAMEPAD_BACK;
    filter_state(entry,0,&result); assert(result.Gamepad.wButtons&XINPUT_GAMEPAD_START);
    audio_mode=TRUE;
    filter_state(entry,0,&result); assert(result.Gamepad.wButtons==0);
    fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_START;
    filter_state(entry,0,&result); assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_START);
    fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_BACK;
    filter_state(entry,0,&result); assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_BACK);
    audio_mode=FALSE;
    shortcuts=FALSE;
    // A compatible pre-existing FIFA Mods Dev hook must be chained, not
    // treated as an unknown Windows function prologue (ready=5/7).
    auto detour=(unsigned char *)VirtualAlloc(nullptr,64,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
    assert(detour);
    memset(detour,0xCC,64);
    XInputEntry chained={}; chained.filter=get_state_14; chained.signature=k_prologue_14;
    assert(!install_export(chained,detour));
    assert(!chained.installed && detour[0]==0xCC);
    jump_to(detour,nullptr); detour[12]=0x90;
    assert(!install_export(chained,detour));
    jump_to(detour,detour); detour[12]=0x90;
    assert(!install_export(chained,detour));
    jump_to(detour,(void *)read_pad); detour[12]=0x90;
    assert(install_export(chained,detour));
    assert(chained.raw==read_pad && chained.installed);
    fake_pad.Gamepad.wButtons=XINPUT_GAMEPAD_A;
    assert(filter_state(chained,0,&result)==ERROR_SUCCESS);
    assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_A);
    capturing=TRUE; filter_state(chained,0,&result);
    assert(result.Gamepad.wButtons==0);
    capturing=FALSE;
    VirtualFree(detour,0,MEM_RELEASE);
    g_entries[0].raw=disconnected_pad;
    g_entries[1].raw=read_pad;
    assert(mod_xinput_read_raw(0,&result)==ERROR_SUCCESS);
    assert(result.Gamepad.wButtons==XINPUT_GAMEPAD_A);
    void *table[32]={}; void **device=table;
    g_devices.push_back({table,read_keys,nullptr,nullptr});
    BYTE keys[256]={}; fake_keys[DIK_A]=0x80;
    gated_device_state(&device,256,keys); assert(keys[DIK_A]==0x80);
    capturing=TRUE; gated_device_state(&device,256,keys); assert(keys[DIK_A]==0);
    capturing=FALSE; gated_device_state(&device,256,keys); assert(keys[DIK_A]==0);
    fake_keys[DIK_A]=0; gated_device_state(&device,256,keys);
    fake_keys[DIK_A]=0x80; gated_device_state(&device,256,keys); assert(keys[DIK_A]==0x80);
    shortcuts=TRUE; fake_keys[DIK_M]=fake_keys[DIK_F12]=0x80;
    gated_device_state(&device,256,keys);
    assert(keys[DIK_F12]==0 && keys[DIK_M]==0x80 && keys[DIK_A]==0x80);
    void *mouse_table[32]={};void **mouse_device=mouse_table;
    g_devices.push_back({mouse_table,read_mouse,read_buffer,nullptr});
    fake_mouse.lX=150;fake_mouse.lY=-90;fake_mouse.lZ=120;fake_mouse.rgbButtons[0]=0x80;
    DIMOUSESTATE2 mouse={};capturing=TRUE;
    assert(SUCCEEDED(gated_device_state(&mouse_device,sizeof(mouse),&mouse)));
    assert(!mouse.lX && !mouse.lY && !mouse.lZ && !mouse.rgbButtons[0]);
    DIDEVICEOBJECTDATA event={};DWORD event_count=1;
    assert(SUCCEEDED(gated_device_data(&mouse_device,sizeof(event),&event,&event_count,DIGDD_PEEK)));
    assert(event_count==0 && !(observed_buffer_flags&DIGDD_PEEK));
    capturing=FALSE;gated_device_state(&mouse_device,sizeof(mouse),&mouse);
    assert(!mouse.rgbButtons[0]); // Closing cannot deliver the held click.
    fake_mouse.rgbButtons[0]=0;gated_device_state(&mouse_device,sizeof(mouse),&mouse);
    fake_mouse.rgbButtons[0]=0x80;gated_device_state(&mouse_device,sizeof(mouse),&mouse);
    assert(mouse.rgbButtons[0]==0x80 && mouse.lX==150);
    puts("Mouse movement/buttons/wheel and buffered events captured; held close-click released safely");
    puts("XInput and DirectInput synthetic gate tests passed");
    return 0;
}
