#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "stadium_selector_bridge.h"
#include "mod_overlay_screens.h"
#include "mod_xinput_gate.h"
#include "ranking_input_gate.h"
#include "selector_layout.h"
#include "crowd_bridge.h"
#include <stdint.h>
#include <algorithm>
#include <cstring>
#include <cstdio>

SelectorShared *g_selector = nullptr;
LONG g_selector_draw_width=0,g_selector_draw_height=0;
static HWND g_window;
static WNDPROC g_original;
static WNDPROC g_render_original;
static bool g_keyboard[256] = {};
static WORD g_buttons;
static DWORD g_start_pending, g_repeat_at;
static int g_direction;
static DWORD g_release_until;
static BYTE g_held_keys[256];
static bool g_di_ready,g_xi_ready;
static void (*g_log)(const char *);
static DWORD g_next_attach;
static POINT g_hover_point;
static bool g_hover_tracked;
static DWORD g_next_hover;

static bool cursor_moved(POINT current, POINT &previous, bool &tracked) {
    if (!tracked) { previous=current; tracked=true; return false; }
    bool moved=current.x!=previous.x || current.y!=previous.y;
    previous=current;
    return moved;
}

#ifndef CGFS16_SELECTOR_MAPPING_NAME
#define CGFS16_SELECTOR_MAPPING_NAME L"Local\\CGFS16_Selector_v1"
#endif

static bool same_game_window(HWND window,HWND foreground) {
    return window && foreground &&
        GetAncestor(foreground,GA_ROOT)==GetAncestor(window,GA_ROOT);
}

static bool game_foreground(HWND window) {
    return same_game_window(window,GetForegroundWindow());
}
static bool release_hold_active(DWORD deadline,DWORD now) {
    return deadline && (LONG)(deadline-now)>0;
}

static bool alive() {
    return g_selector && g_selector->owner_pid &&
        (DWORD)(GetTickCount()-g_selector->heartbeat)<2000;
}
extern "C" BOOL selector_shortcut_enabled(void) {
    return alive() && g_selector->enabled && g_selector->ready==7 && game_foreground(g_window);
}
// Modes 2 (match) and 3 (career) share Select+Start and panel navigation.
// The career panel is rendered and dispatched separately by Python.
extern "C" BOOL selector_audio_mode(void) { return g_selector && (g_selector->enabled==2 || g_selector->enabled==3); }
static bool audio_combo_edge(WORD buttons,WORD previous) {
    const WORD combo=XINPUT_GAMEPAD_START|XINPUT_GAMEPAD_BACK;
    return (buttons&combo)==combo && (previous&combo)!=combo;
}
static bool keyboard_shortcut_edge(const bool *keys,const bool *previous) {
    return keys[VK_F12] && !previous[VK_F12];
}
static LONG function_action_edge(const bool *keys,const bool *previous) {
    // Keep F1/F2 out of panel actions and F6/F7 for the cloth comparison/reload.
    static constexpr int action_keys[]={VK_F3,VK_F4,VK_F5,VK_F8,VK_F9};
    for (int action=0;action<5;++action) {
        const int key=action_keys[action];
        if (keys[key] && !previous[key]) return action+1;
    }
    return 0;
}
static LONG audio_pad_action(bool audio,WORD pressed) {
    if (!audio) return 0;
    if (pressed & XINPUT_GAMEPAD_X) return 1;
    if (pressed & XINPUT_GAMEPAD_Y) return 2;
    return 0;
}
static int navigation_direction(const bool *keys,WORD buttons,SHORT lx,SHORT ly,int previous) {
    if (keys[VK_LEFT] || (buttons&XINPUT_GAMEPAD_DPAD_LEFT)) return 2;
    if (keys[VK_RIGHT] || (buttons&XINPUT_GAMEPAD_DPAD_RIGHT)) return 3;
    if (keys[VK_UP] || (buttons&XINPUT_GAMEPAD_DPAD_UP)) return 4;
    if (keys[VK_DOWN] || (buttons&XINPUT_GAMEPAD_DPAD_DOWN)) return 5;
    int x=abs((int)lx),y=abs((int)ly),threshold=previous?12000:16000;
    if (std::max(x,y)<threshold) return 0;
    // Follow the dominant axis, retaining it around diagonals until the
    // other axis is clearly stronger. This prevents a tilted Up from Left.
    bool horizontal=x>y;
    if (previous==2 || previous==3) horizontal=x*12>=y*10;
    else if (previous==4 || previous==5) horizontal=x*10>y*12;
    return horizontal ? (lx<0?2:3) : (ly>0?4:5);
}
bool selector_visible() { return alive() && g_selector->visible; }
extern "C" BOOL mod_screen_captures_input(void) {
    return alive() && game_foreground(g_window) &&
        (g_selector->visible || release_hold_active(g_release_until,GetTickCount()));
}
static void emit(LONG kind,LONG value=0) {
    if (!g_selector) return;
    LONG write=g_selector->write_index, next=(write+1)%64;
    if (next==g_selector->read_index) return;
    g_selector->events[write]={kind,value};
    MemoryBarrier(); InterlockedExchange(&g_selector->write_index,next);
}
static bool handle_shortcut(bool enabled,bool shown,bool keyboard_edge,WORD buttons,WORD pressed,WORD previous,DWORD now) {
    bool start=false;
    if (selector_audio_mode()) {
        g_start_pending=0;
        start=audio_combo_edge(buttons,previous);
    } else {
        if ((enabled || shown) && (pressed & XINPUT_GAMEPAD_START)) g_start_pending=now;
        if (buttons & XINPUT_GAMEPAD_BACK) g_start_pending=0;
        start=g_start_pending && (DWORD)(now-g_start_pending)>=350;
        if (start) g_start_pending=0;
    }
    if (!(enabled || shown) || !(keyboard_edge || start)) return false;
    if (!shown) { g_selector->visible=1; emit(1); }
    else { emit(11); g_release_until=now+250; }
    return true;
}
static LRESULT CALLBACK window_proc(HWND hwnd,UINT message,WPARAM w,LPARAM l) {
    if (mod_screen_captures_input() &&
        ((message>=WM_KEYFIRST && message<=WM_KEYLAST) ||
         (message>=WM_MOUSEFIRST && message<=WM_MOUSELAST) || message==WM_INPUT)) return 0;
    if (selector_shortcut_enabled() && (message==WM_KEYDOWN || message==WM_KEYUP) && w==VK_F12) return 0;
    WNDPROC original=(hwnd==g_window && g_render_original) ? g_render_original : g_original;
    return CallWindowProcW(original,hwnd,message,w,l);
}
static SHORT filter_key(int key, SHORT result) {
    if (mod_screen_captures_input()) { g_held_keys[key&255]=(result&0x8000)!=0; return 0; }
    if (g_held_keys[key&255]) { if (!(result&0x8000)) g_held_keys[key&255]=0; return 0; }
    if (key==VK_F12 && selector_shortcut_enabled()) return 0;
    return result;
}
// Keep raw polling independent of patched host imports (also in the isolated
// test host). The selector must never read its own filtered keyboard state.
static SHORT raw_async(int key) {
    static auto fn=(decltype(&GetAsyncKeyState))GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetAsyncKeyState");
    return fn ? fn(key) : 0;
}
static SHORT WINAPI gated_async(int key) { return filter_key(key,raw_async(key)); }
static SHORT WINAPI gated_key(int key) {
    static auto fn=(decltype(&GetKeyState))GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetKeyState");
    return filter_key(key,fn ? fn(key) : 0);
}
static BOOL WINAPI gated_keyboard(PBYTE keys) {
    static auto fn=(decltype(&GetKeyboardState))GetProcAddress(GetModuleHandleW(L"user32.dll"),"GetKeyboardState");
    BOOL ok=fn && fn(keys);
    if (ok) {
        bool capture=mod_screen_captures_input()!=FALSE;
        for (int i=0; i<256; ++i) {
            if (capture) { g_held_keys[i]=(keys[i]&0x80)!=0; keys[i]=0; }
            else if (g_held_keys[i]) { if (!(keys[i]&0x80)) g_held_keys[i]=0; keys[i]=0; }
        }
        if (!capture && selector_shortcut_enabled()) keys[VK_F12]=0;
    }
    return ok;
}
static void patch_keyboard_imports(HMODULE module) {
    if (!module) return;
    auto base=(BYTE *)module;
    auto dos=(IMAGE_DOS_HEADER *)base;
    if (dos->e_magic!=IMAGE_DOS_SIGNATURE) return;
    auto nt=(IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    if (nt->Signature!=IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC) return;
    DWORD rva=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return;
    for (auto imp=(IMAGE_IMPORT_DESCRIPTOR *)(base+rva); imp->Name; ++imp) {
        if (_stricmp((char *)(base+imp->Name),"user32.dll") || !imp->OriginalFirstThunk) continue;
        auto slot=(IMAGE_THUNK_DATA64 *)(base+imp->FirstThunk);
        auto names=(IMAGE_THUNK_DATA64 *)(base+imp->OriginalFirstThunk);
        for (int i=0; names[i].u1.AddressOfData; ++i) {
            if (IMAGE_SNAP_BY_ORDINAL64(names[i].u1.Ordinal)) continue;
            auto symbol=(IMAGE_IMPORT_BY_NAME *)(base+names[i].u1.AddressOfData);
            void *fn=nullptr;
            if (!strcmp((char *)symbol->Name,"GetAsyncKeyState")) fn=(void *)gated_async;
            if (!strcmp((char *)symbol->Name,"GetKeyState")) fn=(void *)gated_key;
            if (!strcmp((char *)symbol->Name,"GetKeyboardState")) fn=(void *)gated_keyboard;
            if (fn && (void *)slot[i].u1.Function!=fn) {
                DWORD old,ignored;
                if (VirtualProtect(&slot[i].u1.Function,sizeof(void *),PAGE_READWRITE,&old)) {
                    InterlockedExchangePointer((PVOID volatile *)&slot[i].u1.Function,fn);
                    VirtualProtect(&slot[i].u1.Function,sizeof(void *),old,&ignored);
                }
            }
        }
    }
}
static void attach_channel() {
    if (g_selector) return;
    DWORD now=GetTickCount();
    if (g_next_attach && (LONG)(now-g_next_attach)<0) return;
    g_next_attach=now+1000;
    HANDLE map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,CGFS16_SELECTOR_MAPPING_NAME);
    if (map) { g_selector=(SelectorShared *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(SelectorShared)); CloseHandle(map); }
    if (g_selector) {
        if (g_log) g_log("Shared selector channel connected");
        LoadLibraryExW(L"xinput1_4.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
        BOOL di=ranking_input_bootstrap();
        g_di_ready=di!=FALSE;
        BOOL xi=mod_xinput_install(g_log);
        g_xi_ready=xi!=FALSE;
        g_selector->ready=(di ? 1 : 0) | (xi ? 2 : 0);
    } else {
        static bool reported=false;
        if (!reported && g_log) g_log("Shared selector channel not available yet; attachment will retry");
        reported=true;
    }
}
void selector_initialize(void (*logger)(const char *)) {
    g_log=logger;
    crowd_bridge_start(logger);
    ranking_input_set_logger(logger);
    attach_channel();
}
void selector_tick(HWND window,float width,float height) {
    // A dead Python owner can leave our mapped view alive after Windows has
    // removed the named handle. A restarted Server may create a new object
    // with the same name. Reopen it instead of retaining that stale view.
    if (g_selector && !alive()) {
        UnmapViewOfFile(g_selector);
        g_selector=nullptr;
        g_next_attach=0;
        g_start_pending=0;
    }
    attach_channel();
    if (!g_selector) return;
    if (width && width<300) return;
    if (g_window && window!=g_window) return;
    if (g_di_ready) g_selector->ready|=1;
    if (g_xi_ready) g_selector->ready|=2;
    if (g_window) g_selector->ready|=4;
    if (!g_window && window) {
        g_window=window;
        SetLastError(0);
        HWND input_window=GetAncestor(window,GA_ROOT);
        g_original=(WNDPROC)SetWindowLongPtrW(input_window,GWLP_WNDPROC,(LONG_PTR)window_proc);
        if (!g_original) {
            if (g_log) { char message[120]; sprintf_s(message,"Window input hook failed: error=%lu",GetLastError()); g_log(message); }
            g_window=nullptr; return;
        }
        // WM_INPUT and mouse messages can target the render child directly;
        // they do not bubble through the root window's procedure.
        if (input_window!=window) {
            g_render_original=(WNDPROC)SetWindowLongPtrW(window,GWLP_WNDPROC,(LONG_PTR)window_proc);
            if (!g_render_original) {
                SetWindowLongPtrW(input_window,GWLP_WNDPROC,(LONG_PTR)g_original);
                g_original=nullptr; g_window=nullptr;
                if (g_log) g_log("Render child input hook failed; selector remains disabled");
                return;
            }
        }
        patch_keyboard_imports(GetModuleHandleW(nullptr));
        patch_keyboard_imports(GetModuleHandleW(L"fifa16.bin"));
        ranking_input_install_cursor_import(GetModuleHandleW(nullptr));
        ranking_input_install_cursor_import(GetModuleHandleW(L"fifa16.bin"));
        mod_xinput_install(g_log);
        g_selector->ready |= 4;
        if (g_log) g_log("Exclusive window input capture installed on render and root windows");
    }
    bool foreground=game_foreground(window);
    bool shown=selector_visible();
    if (!shown || !foreground) g_hover_tracked=false;
    static bool previously_shown=false;
    if (previously_shown && !shown && alive()) g_release_until=GetTickCount()+250;
    previously_shown=shown;
    XINPUT_STATE state={};
    WORD buttons=0; SHORT lx=0,ly=0;
    bool controller_connected=false;
    for (DWORD i=0;i<4;++i) if (mod_xinput_read_raw(i,&state)==ERROR_SUCCESS) {
        controller_connected=true;
        buttons=state.Gamepad.wButtons; lx=state.Gamepad.sThumbLX; ly=state.Gamepad.sThumbLY; break;
    }
    // No shared-structure ABI change. Report state while closed too, and
    // periodically repeat for a restarted Python owner / a temporarily full queue.
    static int previous_connection=-1;
    static DWORD next_connection_report=0,last_connection_owner=0;
    const DWORD connection_now=GetTickCount();
    if (alive() && (previous_connection!=(int)controller_connected ||
        last_connection_owner!=g_selector->owner_pid ||
        (LONG)(connection_now-next_connection_report)>=0)) {
        emit(17,controller_connected?1:0);
        previous_connection=(int)controller_connected;
        last_connection_owner=g_selector->owner_pid;
        next_connection_report=connection_now+1000;
    }
    // Gate installation is required even when no controller is connected.
    static DWORD next_install=0;
    if (!next_install || (LONG)(GetTickCount()-next_install)>=0) {
        if (!g_di_ready) g_di_ready=ranking_input_bootstrap()!=FALSE;
        if (g_di_ready) g_selector->ready|=1;
        if (mod_xinput_install(g_log)) { g_xi_ready=true; g_selector->ready|=2; }
        next_install=GetTickCount()+1000;
    }
    bool enabled=selector_shortcut_enabled()!=FALSE;
    static LONG last_ready=-1,last_enabled=-1;
    if (g_selector->ready!=last_ready || g_selector->enabled!=last_enabled) {
        if (g_log) { char message[180]; sprintf_s(message,"Status: ready=%ld/7 enabled=%ld foreground=%d owner=%lu",g_selector->ready,g_selector->enabled,foreground?1:0,g_selector->owner_pid); g_log(message); }
        last_ready=g_selector->ready; last_enabled=g_selector->enabled;
    }
    WORD previous_buttons=g_buttons;
    WORD pressed=buttons & ~g_buttons; g_buttons=buttons;
    bool keys[256]={};
    for (int i=0;i<256;++i) keys[i]=(raw_async(i)&0x8000)!=0;
    auto edge=[&](int key){ return keys[key] && !g_keyboard[key]; };
    const bool keyboard_edge=keyboard_shortcut_edge(keys,g_keyboard);
    DWORD now=GetTickCount();
    if (foreground && (keyboard_edge || (pressed & XINPUT_GAMEPAD_START)) && g_log) {
        char message[180]; sprintf_s(message,"Shortcut %s: alive=%d enabled=%d ready=%ld visible=%d",keyboard_edge?"F12":"Start",alive()?1:0,enabled?1:0,g_selector->ready,shown?1:0); g_log(message);
    }
    if (!alive() || !foreground) {
        g_selector->visible=0; g_start_pending=0;
    } else {
        if (!handle_shortcut(enabled,shown,keyboard_edge,buttons,pressed,previous_buttons,now) && shown) {
            if (!selector_audio_mode()) {
                if (pressed & XINPUT_GAMEPAD_LEFT_SHOULDER) emit(13);
                else if (pressed & XINPUT_GAMEPAD_RIGHT_SHOULDER) emit(14);
            }
            if ((selector_audio_mode() && edge(VK_ESCAPE)) || (pressed & XINPUT_GAMEPAD_B)) { emit(7); g_release_until=now+250; }
            else if (edge(VK_RETURN) || (pressed & XINPUT_GAMEPAD_A)) emit(6);
            if (edge(VK_TAB) || (!selector_audio_mode() && (pressed & XINPUT_GAMEPAD_Y))) emit(9);
            LONG pad_action=audio_pad_action(selector_audio_mode()!=FALSE,pressed);
            if (pad_action) emit(18,pad_action);
            LONG function_action=function_action_edge(keys,g_keyboard);
            if (function_action) emit(16,function_action);
            int direction=navigation_direction(keys,buttons,lx,ly,g_direction);
            if (direction && (direction!=g_direction || (LONG)(now-g_repeat_at)>=0)) {
                emit(direction); g_repeat_at=now+(direction!=g_direction?260:110);
            }
            g_direction=direction;
            static DWORD next_drag=0;
            static POINT last_drag={-1,-1};
            if ((edge(VK_LBUTTON) || (keys[VK_LBUTTON] && (LONG)(now-next_drag)>=0)) && g_selector->render_ready>0) {
                POINT p; GetCursorPos(&p); ScreenToClient(window,&p);
                RECT rect; GetClientRect(window,&rect);
                float clientW=(float)(rect.right-rect.left), clientH=(float)(rect.bottom-rect.top);
                auto layout=selector_layout(clientW,clientH,g_selector_draw_width ? g_selector_draw_width : g_selector->width,
                    g_selector_draw_height ? g_selector_draw_height : g_selector->height);
                LONG cx=0,cy=0;
                if (selector_hit(layout,(float)p.x,(float)p.y,cx,cy) &&
                    (edge(VK_LBUTTON) || p.x!=last_drag.x || p.y!=last_drag.y))
                    emit(edge(VK_LBUTTON) ? 8 : 12,(cy<<16)|cx);
                last_drag=p; next_drag=now+40;
            }
            if (!keys[VK_LBUTTON] && g_selector->render_ready>0 && (!g_next_hover || (LONG)(now-g_next_hover)>=0)) {
                POINT p;
                if (GetCursorPos(&p) && ScreenToClient(window,&p) && cursor_moved(p,g_hover_point,g_hover_tracked)) {
                    RECT rect;
                    if (GetClientRect(window,&rect)) {
                        auto layout=selector_layout((float)(rect.right-rect.left),(float)(rect.bottom-rect.top),
                            g_selector_draw_width ? g_selector_draw_width : g_selector->width,
                            g_selector_draw_height ? g_selector_draw_height : g_selector->height);
                        LONG cx=0,cy=0;
                        if (selector_hit(layout,(float)p.x,(float)p.y,cx,cy)) emit(15,(cy<<16)|cx);
                    }
                }
                g_next_hover=now+60;
            }
            for (int k='A'; k<='Z'; ++k) if (edge(k)) emit(10,k);
            for (int k='0'; k<='9'; ++k) if (edge(k)) emit(10,k);
            if (edge(VK_SPACE)) emit(10,' ');
            if (edge(VK_BACK)) emit(10,8);
        }
    }
    memcpy(g_keyboard,keys,sizeof(keys));
}
