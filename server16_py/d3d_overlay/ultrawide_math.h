#pragma once
#include <cmath>
#include <stddef.h>
#include <stdint.h>

namespace ultrawide {
constexpr float native_aspect=16.0f/9.0f;
struct Region {float x,width,scale;};
inline Region ui_region(float width,float height) {
    if(width<=0||height<=0||width/height<=native_aspect+0.001f)return {0,width,1};
    float uiWidth=height*native_aspect;return {(width-uiWidth)*.5f,uiWidth,uiWidth/width};
}
inline float aspect(unsigned width,unsigned height) {
    if(width<64||height<64)return native_aspect;
    float ratio=float(width)/height;
    return ratio<native_aspect?native_aspect:ratio>6?6:ratio;
}
// Physical pointer -> the native, full-window UI coordinate system. This is
// the inverse of ui_region, not an OS cursor movement. Native UI input keeps
// using the full client width even when the scene is restricted to 16:9.
inline float ui_pointer_x(float x,float clientWidth,float renderWidth,float renderHeight) {
    auto region=ui_region(renderWidth,renderHeight);
    if(clientWidth<=0||region.scale==1)return x;
    return (x-clientWidth*(1-region.scale)*.5f)/region.scale;
}
// A viewport already centred by a mod must not be narrowed a second time.
inline bool centred_view(float x,float w,float renderWidth,float renderHeight) {
    auto region=ui_region(renderWidth,renderHeight);
    return region.scale<1&&fabsf(x-region.x)<1&&fabsf(w-region.width)<1;
}
// The aspect constant immediately before FIFA's fixed colour table. Unique in
// the supported executable. No addresses or executable bytes are written on disk.
constexpr uint8_t anchor[]={0x39,0x8e,0xe3,0x3f,1,0,0,0,0,0,0xff,0xff,0xff,0xff,0xff,0xff,
    0,0xff,0,0xff,0xff,0,0,0xff,0xff,0,0xff,0xff,0,0xff,0xff,0xff,0xff,0xff,0,0xff,0x80,0x80,0x80,0xff};
inline size_t find_anchor(const uint8_t *data,size_t size,size_t &at) {
    size_t hits=0;for(size_t i=0;i+sizeof(anchor)<=size;++i) {
        bool match=true;for(size_t k=0;k<sizeof(anchor);++k)if(data[i+k]!=anchor[k]){match=false;break;}
        if(match){at=i;++hits;}
    }return hits;
}
}
