#ifndef FIFA_SWISS_DELTA_H
#define FIFA_SWISS_DELTA_H
#include <windows.h>
/* Adds selected Swiss routines to the original host and original L9.65.
 * Never starts the Swiss DLL or its whole-module initializer. */
#define SWISS_READY_NATIVE 1
#define SWISS_READY_DIRECTINPUT 2
void swiss_delta_notify_ready(HMODULE host, const char *game_dir, const char *mod_dir, LONG stage);
#endif
