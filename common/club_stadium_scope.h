#pragma once
#include <windows.h>
namespace club_stadium_scope {
// Optional, read-only bridge. No dependency on DLL load order or user INI edits.
inline int selected(){
 const auto module=GetModuleHandleW(L"club_browser.dll");
 const auto query=reinterpret_cast<int(WINAPI*)()>(module?GetProcAddress(module,"Fifa16ClubBrowserStadiumClub"):nullptr);
 const int id=query?query():0;return id>0&&id<2000000?id:0;
}
inline int target(int actual,int selected){return selected>0&&selected<2000000?selected:actual;}
}
