#pragma once
#include <windows.h>
struct SelectorEvent { LONG kind; LONG value; };
struct SelectorShared {
    DWORD owner_pid, heartbeat;
    LONG enabled, visible, ready, render_ready;
    LONG width, height, read_index, write_index;
    SelectorEvent events[64];
    wchar_t image_path[512];
};
extern SelectorShared *g_selector;
extern LONG g_selector_draw_width,g_selector_draw_height;
void selector_initialize(void (*logger)(const char *) = nullptr);
void selector_tick(HWND window, float width, float height);
bool selector_visible();
