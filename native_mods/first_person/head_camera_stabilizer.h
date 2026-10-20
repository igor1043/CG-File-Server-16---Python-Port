#pragma once
#include "head_camera_math.h"
namespace fp {
inline float wrap(float a){return std::remainder(a,6.28318530718f);}
inline float response(float dt,float time){return -std::expm1(-dt/time);}
inline void axes(Pose& p){
    const float h=p.heading,t=p.pitch,r=p.roll;
    p.forward={std::cos(t)*std::cos(h),-std::sin(t),-std::cos(t)*std::sin(h)};
    const Vec right{std::sin(h),0,std::cos(h)};
    const Vec up{std::sin(t)*std::cos(h),std::cos(t),-std::sin(t)*std::sin(h)};
    p.up=up*std::cos(r)-right*std::sin(r);
}
struct Settings{float heading,pitch,roll,horizontal,vertical,rollGain;};
inline Settings settings(int profile){
    // The former fixed strong setting is the user's new "Média" baseline.
    if(profile==1)return {0.19f,0.30f,0.44f,0.18f,0.30f,0.065f};
    if(profile==2)return {0.27f,0.42f,0.60f,0.25f,0.40f,0.035f};
    if(profile==3)return {0.38f,0.58f,0.80f,0.34f,0.54f,0.015f};
    return {0.13f,0.22f,0.32f,0.13f,0.22f,0.10f};
}
class Stabilizer {
    bool ready=false;
    Pose filtered{};
    Vec localEye{},previousAnchor{};
public:
    void reset(){ready=false;}
    Pose update(Pose target,Vec anchor,float dt,int profile=0,bool immediateAnchor=false){
        const auto config=settings(profile);
        // Dampen lateral head tilt; keep deliberate heading changes intact.
        target.roll*=config.rollGain;
        const Vec local=target.eye-anchor,travel=anchor-previousAnchor,localJump=local-localEye;
        if(!ready||!std::isfinite(dt)||dt<=0||dt>0.25f||dot(travel,travel)>350.f*350.f||dot(localJump,localJump)>45.f*45.f){
            filtered=target;localEye=local;ready=true;
        }else{
            filtered.heading=wrap(filtered.heading+wrap(target.heading-filtered.heading)*response(dt,config.heading));
            filtered.pitch+=wrap(target.pitch-filtered.pitch)*response(dt,config.pitch);
            filtered.roll+=wrap(target.roll-filtered.roll)*response(dt,config.roll);
            // Filter the head's movement relative to the player, so running does
            // not drag the camera behind the body or through the player's head.
            const float horizontal=response(dt,config.horizontal),vertical=response(dt,config.vertical);
            localEye.x+=(local.x-localEye.x)*horizontal;
            localEye.y+=(local.y-localEye.y)*vertical;
            localEye.z+=(local.z-localEye.z)*horizontal;
        }
        // At kickoff the camera must attach to the current head immediately,
        // including a corrected starting animation with a stationary body root.
        if(immediateAnchor)localEye=local;
        previousAnchor=anchor;filtered.eye=anchor+localEye;axes(filtered);return filtered;
    }
};
}
