#pragma once
#include "scene_math.h"
#include <cstdint>
namespace extra {
class SceneRandom {
 uint64_t state_;
public:
 explicit SceneRandom(uint64_t seed):state_(seed?seed:0x9e3779b97f4a7c15ull){}
 uint32_t next(){state_^=state_>>12;state_^=state_<<25;state_^=state_>>27;return static_cast<uint32_t>((state_*2685821657736338717ull)>>32);}
 unsigned below(unsigned bound){if(!bound)return 0;const auto threshold=(uint32_t{0}-bound)%bound;uint32_t n;do{n=next();}while(n<threshold);return n%bound;}
 bool chance(unsigned percent){return percent>=100||(percent&&below(100)<percent);}
};
constexpr unsigned shotVariants=5;
inline Lens shotLens(Lens base,unsigned variant,bool portrait){
 const int angles[]={0,-22,22,-35,35};
 base.angle=std::clamp(base.angle+angles[variant%shotVariants],-40,40);
 if(variant%shotVariants>=3){
  base.distance=std::clamp(base.distance*115/100,250,1600);
  base.height=portrait?158:100;base.fov=std::clamp(base.fov+2,8,65);
 }
 return base;
}
inline bool frontal(const Actor& actor,const Camera& camera,float minimum=.70f){
 Vec front=actor.forward,ray=camera.eye-actor.root;front.y=ray.y=0;
 return unit(front)&&unit(ray)&&dot(front,ray)>=minimum;
}
}
