#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int visible, shown, hidden, timers;
static UINT delay;
static LRESULT CALLBACK retirement_feedback_window_proc(HWND, UINT, WPARAM, LPARAM);
static HWND mock_foreground(void) { return NULL; }
static int mock_metrics(int index) { (void)index; return 1920; }
static BOOL mock_visible(HWND window) { (void)window; return visible; }
static BOOL mock_position(HWND window, HWND after, int x, int y, int w, int h, UINT flags)
{
    (void)window; (void)after; (void)x; (void)y; (void)w; (void)h;
    assert(flags & SWP_NOACTIVATE); visible=1; ++shown; return TRUE;
}
static UINT_PTR mock_timer(HWND window, UINT_PTR id, UINT milliseconds, TIMERPROC callback)
{
    (void)window; (void)callback; delay=milliseconds; ++timers; return id;
}
static BOOL mock_invalidate(HWND window, const RECT *rect, BOOL erase)
{ (void)window; (void)rect; (void)erase; return TRUE; }
static BOOL mock_kill(HWND window, UINT_PTR id) { (void)window; (void)id; return TRUE; }
static BOOL mock_show(HWND window, int command)
{ (void)window; if(command==SW_HIDE) { visible=0; ++hidden; } return TRUE; }
static LRESULT mock_message(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
{ return retirement_feedback_window_proc(window,message,wparam,lparam); }

#define GetForegroundWindow mock_foreground
#define GetSystemMetrics mock_metrics
#define IsWindowVisible mock_visible
#define SetWindowPos mock_position
#define SetTimer mock_timer
#define InvalidateRect mock_invalidate
#define KillTimer mock_kill
#define ShowWindow mock_show
#define SendMessageA mock_message
#include "../../src/features/retirement/retirement_engine.c"

int main(void)
{
    HWND window=(HWND)(UINT_PTR)1;
    char text[]="Proposta confirmada. Aceite ou recuse no FIFA.";
    COPYDATASTRUCT copy={ RETIREMENT_FEEDBACK_RESULT, sizeof(text), text };
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(shown==1 && timers==1 && delay==5000U);
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(shown==1 && timers==1); /* Duplicate cannot restart the countdown. */
    retirement_feedback_window_proc(window,WM_TIMER,RETIREMENT_FEEDBACK_HIDE_TIMER,0);
    assert(!visible && hidden==1);
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(shown==2 && timers==2 && delay==5000U);
    copy.dwData=0x16402U;
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(visible && g_retirement_feedback_persistent && shown==3 && timers==2);
    retirement_feedback_window_proc(window,WM_TIMER,RETIREMENT_FEEDBACK_HIDE_TIMER,0);
    assert(visible); /* A timer queued before pinning cannot dismiss progress. */
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(shown==3 && timers==2);
    copy.dwData=RETIREMENT_FEEDBACK_RESULT;
    assert(retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy)==1);
    assert(!g_retirement_feedback_persistent && timers==3 && delay==5000U);
    retirement_feedback_window_proc(window,WM_TIMER,RETIREMENT_FEEDBACK_HIDE_TIMER,0);
    assert(!visible);
    copy.dwData=0x16402U;
    retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy);
    copy.dwData=0x16403U;
    retirement_feedback_window_proc(window,WM_COPYDATA,0,(LPARAM)&copy);
    assert(!visible && !g_retirement_feedback_persistent);
    puts("PASS: five-second notices; persistent progress survives timers until completion or dismissal; no real windows used");
    return 0;
}
