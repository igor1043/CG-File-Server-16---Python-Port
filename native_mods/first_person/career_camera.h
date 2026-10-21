#pragma once
#include "game_framing.h"

namespace fp {
// A close third-person chase view anchored to the selected player's body.
// Follow the body/trajectory, never the animated head's gaze after acquisition.
class CareerCamera {
    bool ready=false;
    float heading=0.f;
    float yawSpeed=0.f;
    float reference=0.f,ballBias=0.f;
    int rearBallSide=0;
    Vec velocity{};
    float boom=480.f,height=230.f;
    float boomTarget=480.f,heightTarget=230.f;
    Vec previousRoot{},anchorTarget{},anchor{};
public:
    void reset(){ready=false;}
    FramedView update(const Pose& head,Vec root,Vec ball,float dt,float baseFov,int distancePreset=0,bool playerChanged=false,bool bodyValid=false,float bodyHeading=0.f,bool possessing=true){
        constexpr float degrees=.01745329252f;
        const Vec travel=root-previousRoot;
        const float maxTravel=playerChanged?2500.f:350.f;
        const bool continuous=ready&&std::isfinite(dt)&&dt>0&&dt<=.25f&&dot(travel,travel)<=maxTravel*maxTravel;
        const bool body=bodyValid&&std::isfinite(bodyHeading);
        if(!continuous||playerChanged){reference=body?bodyHeading:head.heading;velocity={};ballBias=0.f;rearBallSide=0;}
        else {
            const Vec instantaneous{travel.x/dt,0.f,travel.z/dt};
            velocity=velocity+(instantaneous-velocity)*response(dt,.35f);
            float desired=reference;
            if(body)desired=bodyHeading;
            else if(dot(velocity,velocity)>80.f*80.f){
                const float direction=std::atan2(-velocity.z,velocity.x);
                // Backward steps and lateral dribble feints must not flip the boom.
                if(std::fabs(wrap(direction-reference))<1.9f)desired=direction;
            }
            reference=wrap(reference+wrap(desired-reference)*response(dt,.32f));
        }
        float wantedBias=0.f;
        if(possessing)rearBallSide=0;
        const Vec ballDelta=ball-root;
        const float distance=std::hypot(ballDelta.x,ballDelta.z);
        if(std::isfinite(distance)&&distance>250.f&&distance<(possessing?5000.f:20000.f)){
            const float direction=std::atan2(-ballDelta.z,ballDelta.x);
            float angle=wrap(direction-reference);
            // Without possession, turn partway toward the play. Hysteresis
            // keeps a ball directly behind from choosing alternate orbit sides.
            if(!possessing){
                if(std::fabs(angle)<2.2f)rearBallSide=0;
                else if(!rearBallSide&&std::fabs(angle)>2.6f)rearBallSide=angle<0.f?-1:1;
                if(rearBallSide&&std::fabs(angle)>2.2f)angle=std::copysign(std::fabs(angle),static_cast<float>(rearBallSide));
                wantedBias=clamp(angle*.45f,-.8f,.8f)*clamp((distance-250.f)/800.f,0.f,1.f);
            }else if(std::fabs(angle)<1.5707963f)
                wantedBias=clamp(angle,-.65f,.65f)*.12f*clamp((distance-250.f)/800.f,0.f,1.f);
        }
        ballBias=continuous?ballBias+(wantedBias-ballBias)*response(dt,.65f):wantedBias;
        const float wanted=reference+ballBias;
        const float wantedBoom=distancePreset==2?1150.f:distancePreset==1?750.f:480.f;
        const float wantedHeight=distancePreset==2?450.f:distancePreset==1?320.f:230.f;
        if(continuous){
            // Two stages ease into body translation and preset changes, so a
            // first frame of movement cannot transfer directly to the camera.
            Vec tracked=root;
            const Vec delta=root-anchorTarget;
            const float horizontal=std::hypot(delta.x,delta.z);
            // Ignore small body-root animation around a stationary ground pivot.
            if(horizontal<=4.f){tracked.x=anchorTarget.x;tracked.z=anchorTarget.z;}
            else {tracked.x-=delta.x*4.f/horizontal;tracked.z-=delta.z*4.f/horizontal;}
            anchorTarget=anchorTarget+(tracked-anchorTarget)*response(dt,.10f);
            anchor=anchor+(anchorTarget-anchor)*response(dt,.14f);
            boomTarget+=(wantedBoom-boomTarget)*response(dt,.16f);
            heightTarget+=(wantedHeight-heightTarget)*response(dt,.16f);
            boom+=(boomTarget-boom)*response(dt,.18f);
            height+=(heightTarget-height)*response(dt,.18f);
            const float rawError=wrap(wanted-heading);
            const float error=std::fabs(rawError)<=2.f*degrees?0.f:rawError-std::copysign(2.f*degrees,rawError);
            const float desiredSpeed=clamp(error/.60f,-.75f,.75f);
            yawSpeed+=clamp(desiredSpeed-yawSpeed,-1.8f*dt,1.8f*dt);
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
