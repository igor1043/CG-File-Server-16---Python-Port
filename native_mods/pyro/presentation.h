#pragma once
#include <cstring>
#include <cstddef>
#include <stdint.h>
enum class PyroPage { Unreadable, Outside, Match, Pause };
inline PyroPage pyro_page(const char* text, bool known, bool matchSession=false) {
    if(!known || !text)return PyroPage::Unreadable;
    char page[192]={};
    std::size_t n=0;
    for(;text[n] && n+1<sizeof(page);++n) {
        char c=text[n];page[n]=(c>='A' && c<='Z')?static_cast<char>(c+32):c;
    }
    if(text[n])return PyroPage::Unreadable;
    bool blank=true;
    for(std::size_t i=0;i<n;++i)if(page[i]!=' ' && page[i]!='\r' && page[i]!='\n' && page[i]!='\t')blank=false;
    if(blank || !std::strcmp(page,"game/screens/tv/bumper") || !std::strcmp(page,"tv/bumper") ||
       !std::strcmp(page,"game/screens/misc/stadiumpan"))return PyroPage::Match;
    if(!std::strcmp(page,"game/screens/fluxhub/fluxhub") ||
       std::strstr(page,"game/screens/instantreplay/") ||
       std::strstr(page,"game/screens/pause/"))return PyroPage::Pause;
    // FIFA also uses these pre-match pages as overlays of a running match.
    // They must preserve the consumed opening when reached from pause.
    if(matchSession && (!std::strcmp(page,"game/screens/playnow/sideselect") ||
                        !std::strcmp(page,"game/screens/matchdetails/matchdetails")))return PyroPage::Pause;
    // Selection, kit preview, training, results and other named menus cannot arm a show.
    return PyroPage::Outside;
}
inline bool pyro_can_start(PyroPage page,bool nativeTwoTeams) {
    return page==PyroPage::Match && nativeTwoTeams;
}
inline bool pyro_can_continue(PyroPage page,bool nativeTwoTeams,bool matchSession) {
    return nativeTwoTeams && (page==PyroPage::Match || (page==PyroPage::Pause && matchSession));
}

struct PyroMatchSession {
    uintptr_t key=0;
    int home=0,away=0;
    bool observe(uintptr_t sceneKey,int homeClub,int awayClub) {
        if(!sceneKey || homeClub<=0 || awayClub<=0)return false;
        // Lua tables/render resources can be rebuilt on pause and replay.
        // Only a new fixture, a confirmed restart or leaving the match rearms.
        if(key && home==homeClub && away==awayClub)return false;
        key=sceneKey;home=homeClub;away=awayClub;return true;
    }
};
