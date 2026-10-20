#pragma once
#include <windows.h>
#include <wchar.h>

// Dedicated file shared by the two existing plugins. Never patches the
// executable, loader, stadium files or crowd controller configuration.
struct MatchPresentationOptions {
    bool mascots=true, pyrotechnics=false, entrance=false, goal=false;
    unsigned entranceSeconds=60,goalSeconds=25;
    unsigned entranceEmitters=(1u<<20)-1,goalEmitters=(1u<<12)-1;
    bool entrance_allowed() const { return pyrotechnics && entrance && entranceEmitters; }
    bool goal_allowed() const { return pyrotechnics && goal && goalEmitters; }
    unsigned duration_ms(bool afterGoal) const { return (afterGoal?goalSeconds:entranceSeconds)*1000u; }
    unsigned emitter_mask(bool afterGoal) const { return afterGoal?goalEmitters:entranceEmitters; }
};

class MatchPresentationConfig {
    wchar_t path[MAX_PATH]{};
    DWORD nextCheck=0;
    MatchPresentationOptions options;
public:
    static unsigned seconds(unsigned value,unsigned fallback) {return value>=15 && value<=120?value:fallback;}
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
            options.entranceSeconds=seconds(GetPrivateProfileIntW(L"match",L"smoke_entrance_seconds",60,path),60);
            options.goalSeconds=seconds(GetPrivateProfileIntW(L"match",L"smoke_goal_seconds",25,path),25);
            options.entranceEmitters=GetPrivateProfileIntW(L"match",L"smoke_entrance_emitters",(1u<<20)-1,path)&((1u<<20)-1);
            options.goalEmitters=GetPrivateProfileIntW(L"match",L"smoke_goal_emitters",(1u<<12)-1,path)&((1u<<12)-1);
        }
        return options;
    }
};
