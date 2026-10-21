#pragma once
#include <cstdint>
#include "scene_math.h"
#include "reaction_policy.h"
namespace extra {
// Transform readiness only: never requests meshes or edits render descriptors.
class ActorReadiness {
 uint64_t identity_=0,first_=0,last_=0,stamp_=0;
 unsigned samples_=0;
 Vec root_{};
public:
 void reset(){*this=ActorReadiness{};}
 void observe(uint64_t identity,uint64_t stamp,uint64_t now,const Actor* actor){
  if(!identity||!stamp||!actor||!finite(actor->root)||!finite(actor->head)||
     actor->head.y-actor->root.y<100||actor->head.y-actor->root.y>300){reset();return;}
  if(identity_!=identity||now<last_||now-last_>400||length(actor->root-root_)>100){
   reset();identity_=identity;first_=now;
  }
  if(stamp!=stamp_){stamp_=stamp;++samples_;}
  root_=actor->root;last_=now;
 }
 bool ready(uint64_t now)const{return identity_&&samples_>=3&&now>=first_&&now-first_>=150&&now>=last_&&now-last_<=200;}
};
inline bool sceneOpportunity(bool test,bool preview,uint64_t now,uint64_t lastEnd,unsigned cooldown,unsigned serial,unsigned chance){
 return test||preview||(now>=lastEnd&&now-lastEnd>=cooldown&&reactionChance(serial,chance));
}
}
