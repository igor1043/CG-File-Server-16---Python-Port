#pragma once
#include <cstdint>
#include <cstring>

namespace frontend_stadium {
enum class PageKind { Transition, Menu, ClubBrowser, PlayerCareer, Other };
inline bool isBackgroundPage(PageKind page){return page==PageKind::Menu||page==PageKind::ClubBrowser||page==PageKind::PlayerCareer;}
inline bool forcesStadium(PageKind page){return page==PageKind::ClubBrowser;}
inline bool enabledForPage(bool configured,PageKind page){return configured||forcesStadium(page);}
template<class Read> PageKind pageKind(uintptr_t image,Read read){
    auto pointer=[&](uintptr_t at){uintptr_t value=0;if(at>=0x10000)read(at,&value,sizeof value);return value;};
    auto page=pointer(image+0x3809030);
    for(const uintptr_t offset:{0xe8,0xc0,0x88,0x1d8}){
        if(!page)return PageKind::Transition;
        page=pointer(page+offset);
    }
    char name[128]{};
    if(page<0x10000||!read(page,name,sizeof name-1)||!name[0])return PageKind::Transition;
    // Page names are ASCII asset identifiers. Normalize without locale state.
    for(auto& letter:name)if(letter>='A'&&letter<='Z')letter+=('a'-'A');
    const auto leaf=std::strrchr(name,'/');
    if(std::strstr(name,"clubbrowser"))return PageKind::ClubBrowser;
    // Player Career screens are not part of the manager-career hub. Keep
    // them on the same cover path when FIFA exposes their page IDs.
    if(std::strstr(name,"playercareer")||std::strstr(name,"careerplayer")||
       std::strstr(name,"myplayercareer")||std::strstr(name,"beaplayer")||
       std::strstr(name,"becomeaplayer")||std::strstr(name,"player-career"))return PageKind::PlayerCareer;
    if(std::strstr(name,"mainmenuwithstadium")||std::strstr(name,"mainmenuhub"))return PageKind::Menu;
    if(!leaf)return PageKind::Other;
    return !std::strcmp(leaf,"/fluxhub")||!std::strcmp(leaf,"/profile")||
           !std::strcmp(leaf,"/selectfavoriteteam")||!std::strcmp(leaf,"/stadiumpan")
           ?PageKind::Menu:PageKind::Other;
}
template<class Read> bool reloadPage(uintptr_t image,Read read){
    return isBackgroundPage(pageKind(image,read));
}
inline bool refreshOnMenuReturn(PageKind previous,PageKind current,bool ready,bool enabled){
    return isBackgroundPage(current)&&previous!=current&&ready&&enabled;
}
}
