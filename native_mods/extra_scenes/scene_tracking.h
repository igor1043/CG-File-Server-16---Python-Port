#pragma once
#include <cstdint>
#include "scene_math.h"
namespace extra {
// A planted broadcast camera. Animation bones determine only the initial frame.
// Subsequent pans follow ground displacement, never head rotation or body sway.
class Tripod {
 Camera camera_{};
 Vec origin_{},anchor_{},baseTarget_{},filtered_{},velocity_{},previousRoot_{};
 uint64_t last_=0;
 bool ready_=false,portrait_=false;
public:
 void reset(){*this=Tripod{};}
 bool current(Camera& out)const{if(!ready_)return false;out=camera_;return true;}
 bool begin(const Actor& actor,const Camera& camera,uint64_t now,bool portrait){
  reset();if(!finite(actor.root)||!finite(camera.eye)||!finite(camera.target))return false;
  camera_=camera;if(!aim(camera_))return false;
  origin_=anchor_=previousRoot_=actor.root;baseTarget_=filtered_=camera.target;
  portrait_=portrait;last_=now;ready_=true;return true;
 }
 bool update(const Actor& actor,uint64_t now,Camera& out){
  if(!ready_||now<last_||!finite(actor.root)||!finite(actor.forward))return false;
  Vec displacement=actor.root-previousRoot_;displacement.y=0;
  if(length(displacement)>250)return false; // A relocation is not a pan.
  // A reaction can turn/nod the head without moving the person. Keep the
  // planted camera: only displacement/framing can invalidate this shot.
  Vec residual=actor.root-anchor_;residual.y=0;
  const float distance=length(residual),deadZone=portrait_?18.f:30.f;
  if(distance>deadZone)anchor_=anchor_+residual*((distance-deadZone)/distance);
  Vec offset=anchor_-origin_;offset.y=0;
  const Vec desired=baseTarget_+offset;
  const float dt=std::min(.1f,static_cast<float>(now-last_)*.001f);
  last_=now;previousRoot_=actor.root;
  // Critically damped translation removes acceleration jolts. Frame-time based.
  constexpr float omega=4.f;
  const Vec error=filtered_-desired;
  const Vec impulse=(velocity_+error*omega)*dt;
  const float decay=std::exp(-omega*dt);
  filtered_=desired+(error+impulse)*decay;
  velocity_=(velocity_-impulse*omega)*decay;
  Vec oldRay=camera_.target-camera_.eye,newRay=filtered_-camera_.eye;
  const float range=length(newRay);
  if(!unit(oldRay)||!unit(newRay))return false;
  const float angle=std::acos(std::clamp(dot(oldRay,newRay),-1.f,1.f));
  const float maxAngle=8.f*.01745329252f*dt;
  if(angle>maxAngle&&angle>.00001f){
   const float t=maxAngle/angle,sine=std::sin(angle);
   if(sine<.00001f)return false;
   newRay=oldRay*(std::sin((1-t)*angle)/sine)+newRay*(std::sin(t*angle)/sine);
  }
  camera_.target=camera_.eye+newRay*range;
  // Keep the actor within the lens instead of whipping around or orbiting him.
  Vec subject=baseTarget_+(actor.root-origin_);subject.y=baseTarget_.y;
  Vec aimed=camera_.target-camera_.eye,actual=subject-camera_.eye;
  if(!unit(aimed)||!unit(actual))return false;
  const float errorAngle=std::acos(std::clamp(dot(aimed,actual),-1.f,1.f));
  if(errorAngle>camera_.fov*.4f||!aim(camera_))return false;
  out=camera_;return true;
 }
};
}
