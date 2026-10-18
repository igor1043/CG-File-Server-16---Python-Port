#pragma once
#include "game_framing.h"

namespace fp {
// A close third-person chase view anchored to the selected player's body.
// Keep the head animation out of camera height, pitch and roll; only use its
// horizontal gaze as the heading reference, with a strong orbit filter.
class CareerCamera {
    bool ready=false;
    float heading=0.f;
    float boom=480.f,height=230.f;
    Vec previousRoot{};
public:
    void reset(){ready=false;}
    FramedView update(const Pose& head,Vec root,Vec ball,float dt,float baseFov,int distancePreset=0){
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
        const bool continuous=ready&&std::isfinite(dt)&&dt>0&&dt<=.25f&&dot(travel,travel)<=350.f*350.f;
        const float wantedBoom=distancePreset==2?1150.f:distancePreset==1?750.f:480.f;
        const float wantedHeight=distancePreset==2?450.f:distancePreset==1?320.f:230.f;
        boom=continuous?boom+(wantedBoom-boom)*response(dt,.30f):wantedBoom;
        height=continuous?height+(wantedHeight-height)*response(dt,.30f):wantedHeight;
        heading=continuous?wrap(heading+wrap(wanted-heading)*response(dt,.32f)):wanted;
        previousRoot=root;ready=true;
        const Vec forward{std::cos(heading),0.f,-std::sin(heading)};
        Pose view{};
        // A longer camera distance and moderate lens preserve the player's
        // proportions instead of projecting a nearby body through a wide lens.
        view.eye=root-forward*boom+Vec{0.f,height,0.f};
        const Vec focus=root+forward*850.f+Vec{0.f,110.f,0.f};
        view.heading=heading;
        view.pitch=std::atan2(view.eye.y-focus.y,std::hypot(focus.x-view.eye.x,focus.z-view.eye.z));
        view.roll=0.f;axes(view);
        return {view,clamp(baseFov,60.f,90.f)*degrees};
    }
};
}
