#pragma once
#include <array>
#include <cstdint>
#include <cstring>
namespace frontend_stadium {
using SceneContext=std::array<unsigned char,0x110>;
inline void routeContext(SceneContext& context,int slot){
    const int day=1;
    std::memcpy(context.data()+0xe8,&slot,4);
    std::memcpy(context.data()+0xec,&day,4);
}
}
