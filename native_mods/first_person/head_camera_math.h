#pragma once
#include <cmath>
namespace fp {
struct Vec {float x,y,z;};
inline Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline Vec operator*(Vec a,float v){return {a.x*v,a.y*v,a.z*v};}
inline float dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline bool normalize(Vec& a){const float v=dot(a,a);if(!std::isfinite(v)||v<0.01f||v>9.f)return false;a=a*(1.f/std::sqrt(v));return true;}
struct Pose{Vec eye,forward,up;float heading,pitch,roll;};
inline bool solve(const float* m,Pose& p){
    for(int i=0;i<16;++i)if(!std::isfinite(m[i]))return false;
    Vec u{m[0],m[1],m[2]},f{m[4],m[5],m[6]},head{m[12],m[13],m[14]};
    if(!normalize(f)||!normalize(u)||std::fabs(dot(f,u))>0.1f)return false;
    u=u-f*dot(f,u);if(!normalize(u))return false;
    if(std::fabs(head.x)>20000.f||std::fabs(head.z)>20000.f||head.y<10.f||head.y>1000.f)return false;
    p.forward=f;p.up=u;p.eye=head+f*14.f+u*5.f;
    p.heading=std::atan2(-f.z,f.x);p.pitch=std::atan2(-f.y,std::hypot(f.x,f.z));
    const Vec right{std::sin(p.heading),0.f,std::cos(p.heading)};
    const Vec neutralUp{std::sin(p.pitch)*std::cos(p.heading),std::cos(p.pitch),-std::sin(p.pitch)*std::sin(p.heading)};
    p.roll=std::atan2(-dot(u,right),dot(u,neutralUp));
    return std::isfinite(p.roll);
}
}
