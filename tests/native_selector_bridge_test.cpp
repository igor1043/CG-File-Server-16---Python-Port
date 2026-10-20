// Isolated mapping and hidden windows; never injects FIFA or sends real input.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
static HWND simulated_foreground;
static HWND test_foreground_window() { return simulated_foreground; }
#define GetForegroundWindow test_foreground_window
static wchar_t test_mapping_name[100];
#define CGFS16_SELECTOR_MAPPING_NAME test_mapping_name
#include "../server16_py/d3d_overlay/stadium_selector_bridge.cpp"
#include <cassert>
static void print_log(const char *message) { puts(message); }
int main() {
    setvbuf(stdout,nullptr,_IONBF,0);
    static_assert(sizeof(SelectorShared)==1576,"Python/native protocol size mismatch");
    const WORD combo=XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
    assert(audio_combo_edge(combo,0));
    assert(audio_combo_edge(combo,XINPUT_GAMEPAD_START));
    assert(audio_combo_edge(combo,XINPUT_GAMEPAD_BACK));
    assert(!audio_combo_edge(combo,combo));
    assert(!audio_combo_edge(XINPUT_GAMEPAD_START,0));
    assert(!audio_combo_edge(XINPUT_GAMEPAD_BACK,0));
    assert(audio_pad_action(true,XINPUT_GAMEPAD_X)==1);
    assert(audio_pad_action(true,XINPUT_GAMEPAD_Y)==2);
    assert(audio_pad_action(true,0)==0);
    assert(audio_pad_action(false,XINPUT_GAMEPAD_Y)==0);
    bool keys[256]={},old_keys[256]={};
    keys['M']=true;
    assert(!keyboard_shortcut_edge(keys,old_keys));
    const int panel_keys[]={VK_F3,VK_F4,VK_F5,VK_F8,VK_F9};
    for (int action=0;action<5;++action) {
        const int key=panel_keys[action];
        memset(keys,0,sizeof(keys)); memset(old_keys,0,sizeof(old_keys));
        keys[key]=true;
        assert(function_action_edge(keys,old_keys)==action+1);
        old_keys[key]=true;
        assert(function_action_edge(keys,old_keys)==0);
    }
    for (int key:{VK_F1,VK_F2,VK_F6,VK_F7}) {
        memset(keys,0,sizeof(keys));memset(old_keys,0,sizeof(old_keys));
        keys[key]=true;assert(function_action_edge(keys,old_keys)==0);
    }
    puts("Panel function keys F3/F4/F5/F8/F9: all action edges, held keys and F1/F2/F6/F7 exclusion passed");
    keys[VK_F12]=true;
    assert(keyboard_shortcut_edge(keys,old_keys));
    old_keys[VK_F12]=true;
    assert(!keyboard_shortcut_edge(keys,old_keys));
    POINT previous={}; bool tracked=false;
    assert(!cursor_moved({100,200},previous,tracked)); // Stationary cursor never steals gamepad focus.
    assert(!cursor_moved({100,200},previous,tracked));
    assert(cursor_moved({101,200},previous,tracked));
    assert(!cursor_moved({101,200},previous,tracked));
    tracked=false;
    assert(!cursor_moved({150,200},previous,tracked)); // Reopening starts with a fresh snapshot.
    swprintf_s(test_mapping_name,L"Local\\CGFS16_Selector_test_%lu",GetCurrentProcessId());
    selector_initialize(print_log);
    assert(!g_selector);
    HANDLE map=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(SelectorShared),test_mapping_name);
    assert(map);
    auto shared=(SelectorShared *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(SelectorShared));
    assert(shared);
    shared->owner_pid=GetCurrentProcessId(); shared->heartbeat=GetTickCount();
    g_next_attach=0;
    selector_tick(nullptr,1,1);
    assert(g_selector && shared->ready==3);
    HWND root=CreateWindowExW(0,L"STATIC",L"",WS_POPUP,0,0,1280,720,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    HWND child=CreateWindowExW(0,L"STATIC",L"",WS_CHILD,0,0,1280,720,root,nullptr,GetModuleHandleW(nullptr),nullptr);
    HWND other=CreateWindowExW(0,L"STATIC",L"",WS_POPUP,0,0,1,1,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    assert(root && child && other);
    assert(same_game_window(child,root));
    assert(same_game_window(root,child));
    assert(!same_game_window(child,other));
    assert(!same_game_window(child,nullptr));
    assert(!release_hold_active(0,0x90000000));
    assert(release_hold_active(30,0xfffffff0));
    assert(!release_hold_active(30,31));
    for (auto size : {std::pair<float,float>(1280,720),{1920,1080},{3440,1440},{800,600}}) {
        auto layout=selector_layout(size.first,size.second,1000,830);
        assert(layout.keyboard);
        assert(layout.card_y+600*layout.card_scale<layout.keyboard_y);
        assert(layout.keyboard_y+230*layout.keyboard_scale<size.second);
        LONG x=0,y=0;
        assert(selector_hit(layout,layout.card_x+100*layout.card_scale,layout.card_y+100*layout.card_scale,x,y));
        assert(abs(x-100)<=1 && abs(y-100)<=1);
        assert(selector_hit(layout,layout.keyboard_x+50*layout.keyboard_scale,layout.keyboard_y+80*layout.keyboard_scale,x,y));
        assert(abs(x-50)<=1 && abs(y-680)<=1);
        assert(!selector_hit(layout,0,0,x,y));
    }
    selector_tick(child,1280,720);
    assert(shared->ready==7);
    assert((WNDPROC)GetWindowLongPtrW(root,GWLP_WNDPROC)==window_proc);
    assert((WNDPROC)GetWindowLongPtrW(child,GWLP_WNDPROC)==window_proc);
    simulated_foreground=root;
    for (LONG mode : {1L,2L,3L}) {
        shared->enabled=mode; shared->visible=1; g_release_until=0;
        assert(mod_screen_captures_input());
        for (UINT message : {WM_KEYDOWN,WM_LBUTTONDOWN,WM_MOUSEWHEEL,WM_INPUT}) {
            assert(window_proc(root,message,0,0)==0);
            assert(window_proc(child,message,0,0)==0);
        }
        shared->visible=0;
        assert(!mod_screen_captures_input());
        g_release_until=GetTickCount()+250;
        assert(mod_screen_captures_input());
        g_release_until=0;
    }
    shared->visible=1; simulated_foreground=other;
    assert(!mod_screen_captures_input());
    simulated_foreground=nullptr; shared->visible=0;
    puts("Exclusive capture: prematch, match and career; root/child messages; close release; focus loss passed");
    bool direction_keys[256]={};
    assert(navigation_direction(direction_keys,0,-18000,28000,0)==4);
    assert(navigation_direction(direction_keys,0,18000,20000,4)==4);
    assert(navigation_direction(direction_keys,0,29000,17000,4)==3);
    assert(navigation_direction(direction_keys,0,9000,9000,3)==0);
    assert(shared->events[0].kind==17);
    assert(shared->events[0].value==0 || shared->events[0].value==1);
    // Exercise the same shortcut dispatcher used by the render tick, with
    // synthetic keyboard/gamepad snapshots (no real key or pad events).
    auto reset_events=[&](LONG mode) {
        shared->enabled=mode; shared->visible=0;
        shared->read_index=shared->write_index=0; g_start_pending=0;
    };
    for (LONG mode : {1L,2L,3L}) {
        reset_events(mode);
        assert(handle_shortcut(true,false,true,0,0,0,100)); // F12 opens both cards.
        assert(shared->visible && shared->events[0].kind==1 && shared->write_index==1);
        assert(handle_shortcut(true,true,true,0,0,0,200)); // F12 closes without applying.
        assert(shared->events[1].kind==11);
    }
    reset_events(1);
    assert(!handle_shortcut(true,false,false,XINPUT_GAMEPAD_START,XINPUT_GAMEPAD_START,0,100));
    assert(!handle_shortcut(true,false,false,XINPUT_GAMEPAD_START,0,XINPUT_GAMEPAD_START,449));
    assert(handle_shortcut(true,false,false,XINPUT_GAMEPAD_START,0,XINPUT_GAMEPAD_START,450));
    assert(shared->events[0].kind==1);
    assert(!handle_shortcut(true,true,false,XINPUT_GAMEPAD_START,0,XINPUT_GAMEPAD_START,500));
    for (LONG mode : {2L,3L})
    for (WORD first : {WORD(0),WORD(XINPUT_GAMEPAD_START),WORD(XINPUT_GAMEPAD_BACK)}) {
        reset_events(mode);
        if (first) assert(!handle_shortcut(true,false,false,first,first,0,100));
        assert(handle_shortcut(true,false,false,combo,combo&~first,first,200));
        assert(shared->events[0].kind==1);
        assert(!handle_shortcut(true,true,false,combo,0,combo,300)); // Holding never repeats.
        assert(!handle_shortcut(true,true,false,0,0,combo,400));
        assert(handle_shortcut(true,true,false,combo,combo,0,500));
        assert(shared->events[1].kind==11);
    }
    reset_events(0);
    assert(!handle_shortcut(false,false,true,0,0,0,100));
    assert(shared->write_index==0 && !shared->visible);
    shared->ready=0; // Python restarts while DLL stays loaded.
    selector_tick(child,1280,720);
    assert(shared->ready==7);
    assert(!shared->visible && !selector_shortcut_enabled());
    shared->owner_pid=0; // Dead Server: reconnect the named channel.
    selector_tick(child,1280,720);
    assert(g_selector && shared->ready==7);
    shared->owner_pid=GetCurrentProcessId();
    shared->heartbeat=GetTickCount();
    DestroyWindow(child); DestroyWindow(root); DestroyWindow(other);
    UnmapViewOfFile(g_selector); g_selector=nullptr;
    UnmapViewOfFile(shared); CloseHandle(map);
    puts("F12/Start/Select+Start dispatch, late channel, child/root, restart and timer tests passed");
    return 0;
}
