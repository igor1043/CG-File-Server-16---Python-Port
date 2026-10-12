#pragma once
#include <stdint.h>
// Same attacked goal (world X); Z chooses a side of that goal, in centimetres.
// These destinations are shared by spawn placement and future locomotion.
static constexpr float mascotGoalLineDestinations[]={
 3150.0f,2700.0f,2100.0f,1500.0f,900.0f,
 -900.0f,-1500.0f,-2100.0f,-2700.0f,-3150.0f
};
static constexpr unsigned int mascotGoalLineDestinationCount=
 sizeof(mascotGoalLineDestinations)/sizeof(mascotGoalLineDestinations[0]);
static uint32_t mascot_mix_position_seed(uint32_t seed){
 seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;
}
static float mascot_lateral_from_seed(uint32_t seed){
 seed=mascot_mix_position_seed(seed);
 if(seed%100<75)return mascotGoalLineDestinations[0];
 return mascotGoalLineDestinations[1+(seed/100)%(mascotGoalLineDestinationCount-1)];
}
static float mascot_lateral_without_repeat(uint32_t seed,float previous){
 const float candidate=mascot_lateral_from_seed(seed);
 if(candidate!=previous)return candidate;
 float remaining[mascotGoalLineDestinationCount];unsigned int n=0;
 for(float z:mascotGoalLineDestinations)if(z!=previous)remaining[n++]=z;
 return remaining[mascot_mix_position_seed(seed^0x9e3779b9U)%n];
}
struct MascotPlacementChoice{
 uintptr_t key=0;int home=-1,stadium=-1;bool ready=false;float lateral=3150.0f;
 bool update(uintptr_t nextKey,int nextHome,int nextStadium,uint32_t seed){
  const bool sameFixture=ready && home==nextHome && stadium==nextStadium;
  if(sameFixture && (!key || !nextKey || key==nextKey)){
   if(!key)key=nextKey;return false;
  }
  const float previous=lateral;
  key=nextKey;home=nextHome;stadium=nextStadium;ready=true;
  lateral=sameFixture?mascot_lateral_without_repeat(seed,previous):mascot_lateral_from_seed(seed);return true;
 }
};
