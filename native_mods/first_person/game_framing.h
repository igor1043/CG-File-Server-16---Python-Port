#pragma once
#include <algorithm>
#include "head_camera_stabilizer.h"
namespace fp {
inline float clamp(float value,float low,float high){return value<low?low:value>high?high:value;}
// The native Professional behavior keeps updating the selected player during
// OutOfPlay (14), including the wait before a restart. Rejecting 14 returned
// to the native camera while the player could already move before the whistle.
inline bool playerCameraPhase(int state){return state==2||state==14||state==15;}
inline Pose gameFraming(Pose head,Vec root,Vec ball){
    // Keep the player's heading, while reducing animation-driven nodding.
    head.pitch=clamp(head.pitch*0.45f+0.10f,-0.18f,0.70f);
    head.roll=clamp(head.roll,-0.35f,0.35f);
    const Vec delta=ball-head.eye;
    const float distance=std::hypot(delta.x,delta.z);
    const float front=delta.x*std::cos(head.heading)-delta.z*std::sin(head.heading);
    if(std::isfinite(distance)&&std::isfinite(ball.y)&&ball.y-root.y<120.f&&ball.y-root.y>-30.f&&front>-25.f&&distance<360.f){
        const float angle=std::atan2(head.eye.y-ball.y,std::max(distance,25.f));
        // Put a nearby ball within the lower portion of the wider lens; do not
        // lock the view onto it or rotate away from the selected player's gaze.
        const float target=clamp(angle-0.43f,0.12f,0.78f);
        const float weight=clamp((360.f-distance)/160.f,0.f,1.f);
        head.pitch+=std::max(0.f,target-head.pitch)*weight;
    }
    axes(head);return head;
}
struct FramedView {Pose pose;float fov;};
inline void headClearance(Pose& view,const Pose& raw){
    // Recover the animated skull anchor from solve()'s 14 cm / 5 cm eye offset.
    // Enforce a small clearance in front of the current head even when the view
    // direction and the position filter are lagging behind a quick head turn.
    const Vec skull=raw.eye-raw.forward*14.f-raw.up*5.f;
    const float forward=dot(view.eye-skull,raw.forward);
    if(std::isfinite(forward)&&forward<21.f)view.eye=view.eye+raw.forward*(21.f-forward);
}
class PossessionFraming {
    bool ready=false,wasPossessing=false;
    Vec previousBall{};
    float lens=1.5707963f;
    float releaseLook=0.f;
public:
    void reset(){ready=false;wasPossessing=false;lens=1.5707963f;releaseLook=0.f;}
    FramedView update(Pose head,Vec root,Vec ball,bool possessing,float dt,bool closeControl=false,float baseFov=90.f){
        constexpr float degrees=0.01745329252f;
        const bool continuous=ready&&std::isfinite(dt)&&dt>0&&dt<=.25f;
        const Vec relative=ball-root;
        const Vec delta=ball-head.eye;
        const float distance=std::hypot(delta.x,delta.z);
        const bool finite=std::isfinite(distance)&&std::isfinite(ball.y);
        baseFov=clamp(baseFov,75.f,150.f);
        float targetLens=baseFov*degrees;
        Pose target=gameFraming(head,root,ball);
        if(continuous&&wasPossessing&&!possessing)releaseLook=.65f;
        else if(continuous)releaseLook=std::max(0.f,releaseLook-dt);
        else releaseLook=0.f;
        if(!possessing&&releaseLook>0.f){
            target.pitch=clamp(head.pitch*.28f+.06f,-.14f,.20f);
            axes(target);
        }
        if(possessing&&finite){
            // Keep the chosen lens stable. Frame a close ball with the gaze,
            // rather than widening and deforming the perspective on possession.
            const float close=clamp((240.f-distance)/160.f,0.f,1.f);
            target=head;
            target.pitch=clamp(head.pitch*.28f+.06f,-.14f,.26f);
            target.roll=clamp(head.roll,-.35f,.35f);
            const float front=delta.x*std::cos(head.heading)-delta.z*std::sin(head.heading);
            if(ball.y-root.y<120.f&&ball.y-root.y>-30.f&&front>-25.f&&distance<360.f){
                float lateral=0.f;
                if(continuous&&wasPossessing){
                    const Vec velocity=(relative-previousBall)*(1.f/dt);
                    lateral=std::fabs(velocity.x*std::sin(head.heading)+velocity.z*std::cos(head.heading));
                }
                // Geometric control cue, not recognition of a dribble animation.
                const float control=std::max(closeControl?1.f:0.f,clamp((lateral-35.f)/180.f,0.f,1.f))*close;
                const float angle=std::atan2(head.eye.y-ball.y,std::max(distance,25.f));
                const float safeLowerEdge=targetLens*.5f-.07f;
                const float look=clamp(std::max(angle-.70f+control*.06f,angle-safeLowerEdge),.08f,.85f);
                const float weight=clamp((360.f-distance)/160.f,0.f,1.f);
                target.pitch+=std::max(0.f,look-target.pitch)*weight;
            }
            axes(target);
        }
        lens=continuous?lens+(targetLens-lens)*response(dt,.24f):targetLens;
        ready=true;wasPossessing=possessing&&finite;previousBall=relative;
        return {target,lens};
    }
};
inline Pose personalizeLook(Pose pose,int lookBias){
    pose.pitch=clamp(pose.pitch+clamp(static_cast<float>(lookBias),-10.f,20.f)*.01745329252f,-1.2f,1.2f);
    axes(pose);return pose;
}
}
