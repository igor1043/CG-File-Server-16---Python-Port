#pragma once
#include <cmath>
#include <cstring>
#include <algorithm>
namespace extra {
struct Vec {float x=0,y=0,z=0;};
inline Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline Vec operator*(Vec a,float n){return {a.x*n,a.y*n,a.z*n};}
inline float length(Vec a){return std::sqrt(a.x*a.x+a.y*a.y+a.z*a.z);}
inline bool finite(Vec a){return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);}
inline float dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline bool unit(Vec& v){const float n=length(v);if(!std::isfinite(n)||n<.01f)return false;v=v*(1.f/n);return true;}
struct Actor {Vec root,head,forward;float height=190;};
struct Lens {int distance=650,fov=24,height=115,angle=0;};
struct Camera {Vec eye,target;float matrix[16]{},fov=0,focus=0;};
inline bool aim(Camera& out){
 if(!finite(out.eye)||!finite(out.target)||!std::isfinite(out.fov))return false;
 Vec back=out.eye-out.target;const float range=length(back);
 if(range<200||range>2000||!unit(back))return false;
 Vec right=cross({0,1,0},back);if(!unit(right))return false;
 const Vec up=cross(back,right);std::memset(out.matrix,0,sizeof out.matrix);
 const Vec rows[]={right,up,back,out.eye};
 for(int i=0;i<4;++i){out.matrix[i*4]=rows[i].x;out.matrix[i*4+1]=rows[i].y;out.matrix[i*4+2]=rows[i].z;}
 out.matrix[15]=1;out.focus=range;return true;
}
inline bool build(const Actor& actor,const Lens& lens,bool portrait,Camera& out){
 if(!finite(actor.root)||!finite(actor.head)||!finite(actor.forward)||actor.height<100||actor.height>350)return false;
 Vec front={actor.forward.x,0,actor.forward.z};if(!unit(front))return false;
 const float dist=static_cast<float>(std::clamp(lens.distance,250,1600));
 const float offsets[]={0,15,-15,30,-30,45,-45,60,-60};
 bool found=false;Vec best{};float score=1e9f;
 for(float offset:offsets){
  const float angle=(static_cast<float>(std::clamp(lens.angle,-45,45))+offset)*.01745329252f;
  Vec direction={front.x*std::cos(angle)+front.z*std::sin(angle),0,-front.x*std::sin(angle)+front.z*std::cos(angle)};
  if(dot(front,direction)<.70f)continue; // Never orbit behind the face.
  Vec eye=actor.root+direction*dist;
  // Cameras stay on the playing surface, clear of stands/dugouts/boards.
  // If a frontal view cannot fit there, skip this extra rather than film behind.
  if(std::fabs(eye.x)>5150||std::fabs(eye.z)>3250)continue;
  const float s=std::fabs(offset);
  if(s<score){best=eye;score=s;found=true;}
 }
 if(!found)return false;
 out.target=portrait?actor.head:actor.root+Vec{0,actor.height*.48f,0};
 out.eye=best;out.eye.y=portrait?actor.head.y+8+static_cast<float>(lens.height-170):actor.root.y+static_cast<float>(std::clamp(lens.height,80,220));
 const float range=length(out.eye-out.target);if(range<200||range>2000)return false;
 out.fov=static_cast<float>(std::clamp(lens.fov,8,65))*.01745329252f;
 if(!portrait){
  // Fit feet and the full model, with margin, even for tall mascot packages.
  const float required=2.f*std::atan((actor.height*.58f)/range);
  out.fov=std::max(out.fov,required);
 }
 return aim(out);
}
inline bool exportedCamera(const Camera& subjectSpace,Camera& engine){
 // Actor poses from the scene renderer are already in rendered world space.
 // Do not apply the CameraBehavior simulation Z conversion a second time.
 engine=subjectSpace;return aim(engine);
}
}
