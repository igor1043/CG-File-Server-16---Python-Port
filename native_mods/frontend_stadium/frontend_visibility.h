#pragma once
#include <array>
#include <cstdint>
#include <cstring>

namespace frontend_stadium {
// DispatchStatic only reads this state. Preserve every resource, material,
// pass mask and animation field, replacing only its camera visibility result.
// A menu camera must not reuse occlusion results from the native slot's scene.
struct PanoramaVisibility {
    std::array<unsigned char,0x26a0> state{};
    std::array<uint32_t,2048> visible{};
};
template<class Read> bool panoramaVisibility(uintptr_t input,int bucket,PanoramaVisibility& out,Read read){
    if(bucket<0||bucket>=16||!read(input,out.state.data(),out.state.size()))return false;
    uintptr_t begin=0,end=0;
    std::memcpy(&begin,out.state.data()+0x2060+bucket*0x30,8);
    std::memcpy(&end,out.state.data()+0x2068+bucket*0x30,8);
    if(end<begin||(end-begin)%0x50||end-begin>out.visible.size()*0x50)return false;
    if(begin==end)return false;
    const auto visibility=reinterpret_cast<uintptr_t>(out.visible.data());
    std::memcpy(out.state.data()+0x1ed0,&visibility,8);
    return true;
}
}
