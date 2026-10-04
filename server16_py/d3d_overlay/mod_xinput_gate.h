#ifndef FIFA16_MOD_XINPUT_GATE_H
#define FIFA16_MOD_XINPUT_GATE_H
#include <windows.h>
#include <Xinput.h>
#ifdef __cplusplus
extern "C" {
#endif
BOOL mod_xinput_install(void (*logger)(const char *));
DWORD WINAPI mod_xinput_read_raw(DWORD index, XINPUT_STATE *state);
void mod_xinput_log_capture_stats(void);
#ifdef __cplusplus
}
#endif
#endif
