// Isolated mapping and hidden windows; never injects FIFA or sends real input.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
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
    bool keys[256]={},old_keys[256]={};
    keys['M']=true;
    assert(!keyboard_shortcut_edge(keys,old_keys));
    for (int key=VK_F1;key<=VK_F3;++key) {
        memset(keys,0,sizeof(keys)); memset(old_keys,0,sizeof(old_keys));
        keys[key]=true;
        assert(function_action_edge(keys,old_keys)==key-VK_F1+1);
        old_keys[key]=true;
        assert(function_action_edge(keys,old_keys)==0);
    }
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
        auto layout=selector_layout(size.first,size.second,1000,790);
        assert(layout.keyboard);
        assert(layout.card_y+560*layout.card_scale<layout.keyboard_y);
        assert(layout.keyboard_y+230*layout.keyboard_scale<size.second);
        LONG x=0,y=0;
        assert(selector_hit(layout,layout.card_x+100*layout.card_scale,layout.card_y+100*layout.card_scale,x,y));
        assert(abs(x-100)<=1 && abs(y-100)<=1);
        assert(selector_hit(layout,layout.keyboard_x+50*layout.keyboard_scale,layout.keyboard_y+80*layout.keyboard_scale,x,y));
        assert(abs(x-50)<=1 && abs(y-640)<=1);
        assert(!selector_hit(layout,0,0,x,y));
    }
    selector_tick(child,1280,720);
    assert(shared->ready==7);
    // Exercise the same shortcut dispatcher used by the render tick, with
    // synthetic keyboard/gamepad snapshots (no real key or pad events).
    auto reset_events=[&](LONG mode) {
        shared->enabled=mode; shared->visible=0;
        shared->read_index=shared->write_index=0; g_start_pending=0;
    };
    for (LONG mode : {1L,2L}) {
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
    for (WORD first : {WORD(0),WORD(XINPUT_GAMEPAD_START),WORD(XINPUT_GAMEPAD_BACK)}) {
        reset_events(2);
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
    DestroyWindow(child); DestroyWindow(root); DestroyWindow(other);
    UnmapViewOfFile(g_selector); g_selector=nullptr;
    UnmapViewOfFile(shared); CloseHandle(map);
    puts("F12/Start/Select+Start dispatch, late channel, child/root, restart and timer tests passed");
    return 0;
}
