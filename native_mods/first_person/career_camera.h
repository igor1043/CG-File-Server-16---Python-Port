#pragma once
#include "game_framing.h"

namespace fp {
// A close third-person chase view anchored to the selected player's body.
// Keep the head animation out of camera height, pitch and roll; only use its
// horizontal gaze as the heading reference, with a strong orbit filter.
class CareerCamera {
    bool ready=false;
    float heading=0.f;
    float yawSpeed=0.f;
    float boom=480.f,height=230.f;
    float boomTarget=480.f,heightTarget=230.f;
    Vec previousRoot{},anchorTarget{},anchor{};
public:
    void reset(){ready=false;}
    FramedView update(const Pose& head,Vec root,Vec ball,float dt,float baseFov,int distancePreset=0,bool playerChanged=false){
        constexpr float degrees=.01745329252f;
        float wanted=head.heading;
        const Vec ballDelta=ball-root;
        const float distance=std::hypot(ballDelta.x,ballDelta.z);
        if(std::isfinite(distance)&&distance>60.f&&distance<5000.f){
            const float direction=std::atan2(-ballDelta.z,ballDelta.x);
            const float angle=wrap(direction-head.heading);
            // Give a forward ball some space without circling the player
            // toward a ball behind them or changing the selected player.
            if(std::fabs(angle)<1.5707963f)
                wanted+=clamp(angle,-.65f,.65f)*.30f*clamp(distance/600.f,0.f,1.f);
        }
        const Vec travel=root-previousRoot;
        // Nearby player switches can blend. A restart, long time gap or a
        // remote player must reacquire instead of sweeping across the pitch.
        const float maxTravel=playerChanged?2500.f:350.f;
        const bool continuous=ready&&std::isfinite(dt)&&dt>0&&dt<=.25f&&dot(travel,travel)<=maxTravel*maxTravel;
        const float wantedBoom=distancePreset==2?1150.f:distancePreset==1?750.f:480.f;
        const float wantedHeight=distancePreset==2?450.f:distancePreset==1?320.f:230.f;
        if(continuous){
            // Two stages ease into body translation and preset changes, so a
            // first frame of movement cannot transfer directly to the camera.
            anchorTarget=anchorTarget+(root-anchorTarget)*response(dt,.10f);
            anchor=anchor+(anchorTarget-anchor)*response(dt,.14f);
            boomTarget+=(wantedBoom-boomTarget)*response(dt,.16f);
            heightTarget+=(wantedHeight-heightTarget)*response(dt,.16f);
            boom+=(boomTarget-boom)*response(dt,.18f);
            height+=(heightTarget-height)*response(dt,.18f);
            const float error=wrap(wanted-heading);
            const float desiredSpeed=clamp(error/.40f,-1.5f,1.5f);
            yawSpeed+=clamp(desiredSpeed-yawSpeed,-4.f*dt,4.f*dt);
            heading=wrap(heading+yawSpeed*dt);
        }else{
            anchorTarget=anchor=root;boomTarget=boom=wantedBoom;heightTarget=height=wantedHeight;
            heading=wanted;yawSpeed=0.f;
        }
        previousRoot=root;ready=true;
        const Vec forward{std::cos(heading),0.f,-std::sin(heading)};
        Pose view{};
        // A longer camera distance and moderate lens preserve the player's
        // proportions instead of projecting a nearby body through a wide lens.
        view.eye=anchor-forward*boom+Vec{0.f,height,0.f};
        const Vec focus=anchor+forward*850.f+Vec{0.f,110.f,0.f};
        view.heading=heading;
        view.pitch=std::atan2(view.eye.y-focus.y,std::hypot(focus.x-view.eye.x,focus.z-view.eye.z));
        view.roll=0.f;axes(view);
        return {view,clamp(baseFov,60.f,90.f)*degrees};
    }
};
}
