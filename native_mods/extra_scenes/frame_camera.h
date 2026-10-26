#pragma once
#include <cstdint>
#include <cstring>
#include "scene_math.h"
namespace extra {
// The native update reserves a frame, invokes its +0x88 callback, then
// publishes writeIndex. No consumer-owned or published slot can be edited.
inline bool producerFrame(uint64_t pool,int published,int writing,uint64_t frame){
 return pool&&published>0&&writing>0&&published!=writing&&
        published%6!=writing%6&&frame==pool+static_cast<uint64_t>(writing%6)*0xd70+0x10;
}
inline bool cameraFrame(unsigned char* frame,size_t size,const Camera& camera){
 if(!frame||size<0xc4||!finite(camera.eye)||!finite(camera.target)||
    !std::isfinite(camera.focus)||!std::isfinite(camera.fov)||camera.focus<200||
    camera.fov<.1f||camera.fov>1.2f)return false;
 float oldX=0,oldY=0;std::memcpy(&oldX,frame+0x88,4);std::memcpy(&oldY,frame+0x8c,4);
 const float aspect=oldY>0?oldX/oldY:0;
 if(!std::isfinite(aspect)||aspect<=.5f||aspect>=4.f)return false;
 for(float value:camera.matrix)if(!std::isfinite(value))return false;
 const float scaleY=std::tan(camera.fov*.5f),scaleX=scaleY*aspect,zero=0;
 std::memcpy(frame+0x30,camera.matrix,sizeof camera.matrix);
 std::memcpy(frame+0x88,&scaleX,4);std::memcpy(frame+0x8c,&scaleY,4);
 std::memcpy(frame+0xa0,&camera.focus,4);frame[0xb0]=0;
 std::memcpy(frame+0xbc,&zero,4);std::memcpy(frame+0xc0,&zero,4);
 return true;
}
}
