#pragma once
#include <windows.h>
#include <wchar.h>

// Dedicated file shared by the two existing plugins. Never patches the
// executable, loader, stadium files or crowd controller configuration.
struct MatchPresentationOptions {
    bool mascots=true, pyrotechnics=false, entrance=false, goal=false;
    bool entrance_allowed() const { return pyrotechnics && entrance; }
    bool goal_allowed() const { return pyrotechnics && goal; }
};

class MatchPresentationConfig {
    wchar_t path[MAX_PATH]{};
    DWORD nextCheck=0;
    MatchPresentationOptions options;
public:
    bool initialize() {
        wchar_t game[MAX_PATH]{};
        if (!GetModuleFileNameW(nullptr,game,MAX_PATH)) return false;
        wchar_t* end=wcsrchr(game,L'\\');
        if (!end) return false;
        *end=0;
        return _snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%ls\\ModCarrerMode\\config\\match_presentation.ini",game)>=0;
    }
    const MatchPresentationOptions& read(DWORD now) {
        if (path[0] && (!nextCheck || (LONG)(now-nextCheck)>=0)) {
            nextCheck=now+250;
            options.mascots=GetPrivateProfileIntW(L"match",L"mascots",1,path)!=0;
            options.pyrotechnics=GetPrivateProfileIntW(L"match",L"pyrotechnics",0,path)!=0;
            options.entrance=GetPrivateProfileIntW(L"match",L"entrance",0,path)!=0;
            options.goal=GetPrivateProfileIntW(L"match",L"goal",0,path)!=0;
        }
        return options;
    }
};
