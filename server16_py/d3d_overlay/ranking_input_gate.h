#ifndef FIFA16_RANKING_INPUT_GATE_H
#define FIFA16_RANKING_INPUT_GATE_H
#include <windows.h>
#ifdef __cplusplus
extern "C" {
#endif
void ranking_input_attach_directinput(void *input, const GUID *interface_id);
BOOL ranking_input_install_cursor_import(HMODULE module);
void ranking_input_set_logger(void (*logger)(const char *));
BOOL ranking_input_bootstrap(void);
#ifdef __cplusplus
}
#endif
#endif
