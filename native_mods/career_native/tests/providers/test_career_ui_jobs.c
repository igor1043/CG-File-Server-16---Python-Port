#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include <stdio.h>
static int stable,drains,calls,disabled;
static DWORD callback_thread;
static void drain_pending_stats_refresh(void) {++drains;}
static int fce_runtime_is_stable(void) {return stable;}
static void append_loader_log(const char *message) {(void)message;++disabled;}
#include "../../src/host/career_ui_jobs.inc"
static void command(void) {++calls;callback_thread=GetCurrentThreadId();}
static void different(void) {}
static void broken(void) {RaiseException(0xe1640001,0,0,NULL);}
int main(void)
{
    assert(!Fifa16CareerRegisterJobUiCallback(NULL));
    assert(Fifa16CareerRegisterJobUiCallback(command));
    assert(Fifa16CareerRegisterJobUiCallback(command));
    assert(!Fifa16CareerRegisterJobUiCallback(different));
    assert(calls==0);career_ui_jobs_tick();assert(drains==1 && !calls);
    stable=1;career_ui_jobs_tick();assert(drains==2 && calls==1);
    assert(callback_thread==GetCurrentThreadId());
    InterlockedExchangePointer(&g_career_job_ui_callback,NULL);
    assert(Fifa16CareerRegisterJobUiCallback(broken));
    career_ui_jobs_tick();assert(disabled==1 && !g_career_job_ui_callback);
    assert(Fifa16CareerRegisterJobUiCallback(command));career_ui_jobs_tick();assert(calls==2);
    puts("PASS: UI commands stay on the stable engine caller; registration never runs callbacks; a second owner is rejected; failing callback is disabled; existing refresh pump always runs");
    return 0;
}
