#pragma once
#include <cstring>
#include <cstddef>
enum class PyroPage { Unreadable, Outside, Match, Pause };
inline PyroPage pyro_page(const char* text, bool known) {
    if(!known || !text)return PyroPage::Unreadable;
    char page[192]={};
    std::size_t n=0;
    for(;text[n] && n+1<sizeof(page);++n) {
        char c=text[n];page[n]=(c>='A' && c<='Z')?static_cast<char>(c+32):c;
    }
    if(text[n])return PyroPage::Unreadable;
    bool blank=true;
    for(std::size_t i=0;i<n;++i)if(page[i]!=' ' && page[i]!='\r' && page[i]!='\n' && page[i]!='\t')blank=false;
    if(blank || !std::strcmp(page,"game/screens/tv/bumper"))return PyroPage::Match;
    if(!std::strcmp(page,"game/screens/misc/stadiumpan") ||
       !std::strcmp(page,"game/screens/fluxhub/fluxhub") ||
       std::strstr(page,"game/screens/instantreplay/") ||
       std::strstr(page,"game/screens/pause/"))return PyroPage::Pause;
    // Selection, kit preview, training, results and other named menus cannot arm a show.
    return PyroPage::Outside;
}
inline bool pyro_can_start(PyroPage page,bool nativeTwoTeams) {
    return page==PyroPage::Match && nativeTwoTeams;
}
inline bool pyro_can_continue(PyroPage page,bool nativeTwoTeams,bool matchSession) {
    return nativeTwoTeams && (page==PyroPage::Match || (page==PyroPage::Pause && matchSession));
}
