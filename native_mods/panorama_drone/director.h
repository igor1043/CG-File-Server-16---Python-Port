#pragma once
#include "motions.h"
#include <cstring>
namespace panorama {
inline bool eligibleCamera(int phase,const char* name){return phase==1&&name&&!std::strncmp(name,"BC: Stadium FE ",15)&&name[15]>='0'&&name[15]<='9';}
struct Settings {bool enabled=true;float duration=52,gap=24,initial=8,transition=3,heightLimit=11000,scale=1;uint64_t mask=allMotionsMask;};
struct Decision {bool active=false;unsigned motion=0;float progress=0,opacity=0;};
// Show the high orbit, the lower profile and the full halfway line first.
// The remaining 36 shots use a coprime permutation, without early repetition.
class Director {
 enum class Stage {Gap,FadeOutNative,CutToDrone,FadeInDrone,Drone,FadeOutDrone,CutToNative,FadeInNative};
 double elapsed_=0,shotElapsed_=0;unsigned cursor_=0,selected_=0;bool ready_=false;
 Stage stage_=Stage::Gap;
 void advance(Stage next){stage_=next;elapsed_=0;}
public:
 void reset(){*this=Director{};}
 Decision tick(double dt,bool eligible,const Settings& cfg){
  if(!eligible||!cfg.enabled||!cfg.mask){reset();return {};}
  if(!std::isfinite(dt)||dt<0||dt>.5)dt=0;
  if(!ready_){ready_=true;elapsed_=-std::clamp(cfg.initial,0.f,120.f);}
  elapsed_+=dt;
  const float shotDuration=duration(selected_,cfg.duration);
  const float fade=std::clamp(cfg.transition*.5f,.5f,4.f);
  // At least one completely black frame precedes each cut. Never process
  // two stages in one tick, even after a long frame or pause.
  Decision result{false,selected_,static_cast<float>(std::clamp(shotElapsed_/shotDuration,0.,1.)),0};
  switch(stage_){
  case Stage::Gap:{
   if(elapsed_<0)return {};
   bool found=false;
   for(unsigned attempt=0;attempt<motionCount;++attempt){
    const unsigned position=cursor_++%motionCount,priority=motionCount-36;
    const unsigned n=position<priority?36+position:((position-priority)*5)%36;
    if((cfg.mask&(uint64_t{1}<<n))&&available(n,cfg.heightLimit)){selected_=n;found=true;break;}
   }
   if(!found)return {};shotElapsed_=0;advance(Stage::FadeOutNative);result.motion=selected_;return result;
  }
  case Stage::FadeOutNative:
   result.opacity=smooth(static_cast<float>(elapsed_/fade));
   if(elapsed_>=fade)advance(Stage::CutToDrone);
   return result;
  case Stage::CutToDrone:
   result.active=true;result.progress=0;result.opacity=1;
   if(elapsed_>=.18)advance(Stage::FadeInDrone);
   return result;
  case Stage::FadeInDrone:
   result.active=true;result.opacity=1-smooth(static_cast<float>(elapsed_/fade));
   if(elapsed_>=fade)advance(Stage::Drone);
   return result;
  case Stage::Drone:
   shotElapsed_=std::min(static_cast<double>(shotDuration),shotElapsed_+dt);
   result.active=true;result.progress=static_cast<float>(shotElapsed_/shotDuration);
   if(shotElapsed_>=shotDuration)advance(Stage::FadeOutDrone);
   return result;
  case Stage::FadeOutDrone:
   result.active=true;result.progress=1;result.opacity=smooth(static_cast<float>(elapsed_/fade));
   if(elapsed_>=fade)advance(Stage::CutToNative);
   return result;
  case Stage::CutToNative:
   result.opacity=1;
   if(elapsed_>=.18)advance(Stage::FadeInNative);
   return result;
  case Stage::FadeInNative:
   result.opacity=1-smooth(static_cast<float>(elapsed_/fade));
   if(elapsed_>=fade){advance(Stage::Gap);elapsed_=-std::clamp(cfg.gap,10.f,180.f);}
   return result;
  }
  return {};
 }
};
}
