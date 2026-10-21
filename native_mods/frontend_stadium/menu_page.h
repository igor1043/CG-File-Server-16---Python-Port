#pragma once
#include <cstdint>
#include <cstring>

namespace frontend_stadium {
enum class PageKind { Transition, Menu, Other };
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
    if(!leaf)return PageKind::Other;
    return !std::strcmp(leaf,"/fluxhub")||!std::strcmp(leaf,"/profile")||
           !std::strcmp(leaf,"/selectfavoriteteam")||!std::strcmp(leaf,"/stadiumpan")?PageKind::Menu:PageKind::Other;
}
template<class Read> bool reloadPage(uintptr_t image,Read read){
    return pageKind(image,read)==PageKind::Menu;
}
}
