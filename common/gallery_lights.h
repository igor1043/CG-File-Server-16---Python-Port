#pragma once
#include <array>
namespace gallery_lights {
struct Source {float x,y,z;};
inline constexpr unsigned count=26;
inline constexpr auto sources=[](){
 std::array<Source,36> result{};unsigned i=0;
 for(float x:{-470.f,470.f})for(float z:{-575.f,-287.f,0.f,287.f,575.f})result[i++]={x,299.f,z};
 for(float x:{-572.f,572.f})for(unsigned z=0;z<8;++z)result[i++]={x,265.f,-630.f+z*180.f};
 return result;
}();
}
