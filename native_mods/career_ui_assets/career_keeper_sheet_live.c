#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <string.h>
static BOOL read_memory(const void *p,void *out,SIZE_T size)
{SIZE_T got=0;return p && ReadProcessMemory(GetCurrentProcess(),p,out,size,&got) && got==size;}
#include "keeper_pitch_hook.inc"
__declspec(dllexport) DWORD WINAPI Fifa16KeeperSheetStart(void *unused)
{
    HMODULE pinned;(void)unused;
    if(!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCSTR)&Fifa16UiAssetsKeeperStats,&pinned))return 1;
    return install_keeper_pitch_hook()?0:2;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved)
{(void)reserved;if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);return TRUE;}
