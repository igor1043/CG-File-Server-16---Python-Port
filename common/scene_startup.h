#pragma once
#include <cstdint>
namespace scene_startup {
struct Sample {
 unsigned club=0,epoch=0,request=0,slot=0;
 uintptr_t service=0,registry=0;
 bool context=false,loaderIdle=false,routeRequired=false,routeCurrent=false;
 int phase=0;
};
struct Gate {
 Sample previous{};uint64_t since=0;unsigned reason=0;
 void reset(){previous={};since=0;reason=0;}
 bool allow(const Sample&s,uint64_t now){
  const bool route=!s.routeRequired||(s.routeCurrent&&(s.phase==3||s.phase==4||s.phase==-1));
  reason=!s.context||!s.club||!s.epoch?1:!s.loaderIdle?2:!route?3:0;
  if(reason){since=0;previous=s;return false;}
  if(!since||s.club!=previous.club||s.epoch!=previous.epoch||s.service!=previous.service||s.registry!=previous.registry||s.request!=previous.request||s.slot!=previous.slot){since=now;previous=s;}
  // Observe a completed route, not just the first frame of a new Hub. The
  // camera must remain native until FIFA has rendered/finished that route.
  if(now-since<750){reason=4;return false;}
  return true;
 }
};
}
