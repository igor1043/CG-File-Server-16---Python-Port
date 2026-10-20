#include "../native_mods/first_person/game_framing.h"
#include "../native_mods/first_person/career_camera.h"
#include "../native_mods/first_person/camera_bootstrap.h"
#include <cassert>
#include <cstdio>
#include <limits>
int main(){
    int calls=0,headBone=-1,rootBone=-1;
    const auto lookup=[&](int bone){++calls;return bone==3?12:0;};
    const unsigned char notReady[]={0,2,255};
    for(auto ready:notReady){
        assert(!fp::initializedBones(ready,lookup,headBone,rootBone));
        assert(calls==0&&headBone==-1&&rootBone==-1);
    }
    assert(fp::initializedBones(1,lookup,headBone,rootBone));
    assert(calls==2&&headBone==12&&rootBone==0);
    assert(!fp::initializedBones(1,[](int){return -1;},headBone,rootBone));
    assert(!fp::initializedBones(1,[](int){return 256;},headBone,rootBone));
    assert(headBone==12&&rootBone==0);
    std::puts("PASS: saved activation never calls bone resolver before native initialization");
    assert(fp::settings(0).heading==.13f&&fp::settings(0).rollGain==.10f);
    float priorShake=100.f;
    for(int profile=0;profile<4;++profile){
        fp::Stabilizer smoothing;
        fp::Pose p{};p.eye={0,175,0};fp::axes(p);
        smoothing.update(p,{0,0,0},0,profile);
        p.eye.x=100;p.heading=.3f;p.pitch=.2f;p.roll=.2f;
        const auto filtered=smoothing.update(p,{100,0,0},1.f/60,profile);
        assert(filtered.eye.x==100.f); // Whole-body travel never lags.
        assert(filtered.heading>0&&filtered.heading<priorShake);
        priorShake=filtered.heading;
        p.eye.y=190;
        const auto acquired=smoothing.update(p,{100,0,0},1.f/60,profile,true);
        assert(acquired.eye.y==190); // Every profile attaches immediately at kickoff.
        assert(acquired.heading<.3f); // Immediate anchor retains angular smoothing.
        for(int frame=0;frame<600;++frame)smoothing.update(p,{100,0,0},1.f/60,profile);
        const auto settled=smoothing.update(p,{100,0,0},1.f/60,profile);
        assert(std::fabs(settled.heading-.3f)<.001f);
    }
    std::puts("PASS: four progressively stronger head filters, unchanged medium baseline, instant body translation and restart anchor");
    fp::Pose head{};head.eye={14,175,0};fp::axes(head);
    const auto near=fp::gameFraming(head,{0,0,0},{90,10,0});
    const auto far=fp::gameFraming(head,{0,0,0},{3000,10,0});
    assert(near.pitch>far.pitch&&near.pitch<=.78f);
    assert(near.heading==head.heading);
    const auto behind=fp::gameFraming(head,{0,0,0},{-100,10,0});assert(behind.pitch==far.pitch);
    const auto high=fp::gameFraming(head,{0,0,0},{90,500,0});assert(high.pitch==far.pitch);
    const auto invalid=fp::gameFraming(head,{0,0,0},{std::numeric_limits<float>::quiet_NaN(),0,0});assert(std::isfinite(invalid.pitch));
    fp::Stabilizer filter;filter.update(head,{0,0,0},0);
    fp::Pose out{};
    for(int i=0;i<240;++i)out=filter.update(near,{0,0,0},1.f/120.f);
    assert(std::fabs(out.pitch-near.pitch)<.002f);
    filter.reset();head.eye.x=5014;head.heading=2;out=filter.update(head,{5000,0,0},1.f/60.f);
    assert(out.eye.x==5014&&out.heading==2);
    fp::PossessionFraming view;
    head.eye={14,175,0};head.heading=0;head.pitch=.1f;head.roll=0;fp::axes(head);
    const fp::Vec ball{90,10,0};
    auto off=view.update(head,{0,0,0},ball,false,0);
    auto legacy=fp::gameFraming(head,{0,0,0},ball);
    assert(off.pose.pitch==legacy.pitch&&off.pose.heading==legacy.heading);
    auto on=view.update(head,{0,0,0},ball,true,1.f/60.f);
    for(int i=0;i<120;++i)on=view.update(head,{0,0,0},ball,true,1.f/120.f);
    assert(on.pose.pitch<off.pose.pitch-.15f); // More field while owning ball.
    assert(on.pose.heading==head.heading&&on.pose.eye.x==head.eye.x);
    assert(std::fabs(on.fov-90*.01745329252f)<.001f);
    float ballAngle=std::atan2(165.f,76.f);
    assert(ballAngle-on.pose.pitch<on.fov*.5f);
    view.reset();auto feet=view.update(head,{0,0,0},{14,10,0},true,0);
    assert(std::atan2(165.f,25.f)-feet.pose.pitch<feet.fov*.5f);
    const auto before=view.update(head,{0,0,0},ball,true,1.f/60.f);
    auto after=view.update(head,{0,0,0},ball,false,1.f/60.f);
    assert(after.fov==before.fov); // Possession and passes preserve the chosen lens.
    assert(after.pose.pitch<.21f); // Look back up after releasing the ball.
    for(int i=0;i<120;++i)after=view.update(head,{0,0,0},ball,false,1.f/120.f);
    assert(std::fabs(after.fov-1.5707963f)<.004f);
    assert(fp::playerCameraPhase(2)&&fp::playerCameraPhase(14)&&fp::playerCameraPhase(15));
    for(int phase:{0,1,3,5,16})assert(!fp::playerCameraPhase(phase));
    fp::PossessionFraming plain,precision;
    auto normal=plain.update(head,{0,0,0},ball,true,0);
    auto controlled=precision.update(head,{0,0,0},ball,true,0,true);
    assert(controlled.pose.pitch>normal.pose.pitch);
    auto clear=head;fp::headClearance(clear,head);
    assert(std::fabs(clear.eye.x-(head.eye.x+head.forward.x*7.f))<.001f);
    assert(std::fabs(clear.eye.y-(head.eye.y+head.forward.y*7.f))<.001f);
    assert(clear.heading==head.heading&&clear.pitch==head.pitch);
    auto turn=head;turn.forward={0,0,1};turn.eye={0,175,14};
    fp::headClearance(clear,turn);
    assert(fp::dot(clear.eye-(turn.eye-turn.forward*14.f-turn.up*5.f),turn.forward)>=20.99f);
    fp::PossessionFraming custom;
    auto wide=custom.update(head,{0,0,0},ball,true,0,false,110);
    assert(wide.fov>normal.fov&&wide.fov<=120*.01745329252f);
    assert(wide.pose.pitch<=normal.pose.pitch); // Wider lens preserves more field.
    for(float requested:{125.f,145.f,150.f,200.f}){
        const float expected=std::min(requested,150.f)*.01745329252f;
        for(bool possession:{false,true}){
            custom.reset();
            const auto panoramic=custom.update(head,{0,0,0},ball,possession,0,false,requested);
            assert(std::fabs(panoramic.fov-expected)<.001f);
            assert(std::isfinite(panoramic.pose.pitch)&&std::isfinite(std::tan(panoramic.fov*.5f)));
        }
    }
    auto tilted=fp::personalizeLook(head,10);
    assert(std::fabs(tilted.pitch-head.pitch-.1745329252f)<.001f);
    assert(tilted.heading==head.heading&&tilted.eye.x==head.eye.x);
    fp::Stabilizer acquisition;
    acquisition.update(head,{0,0,0},0);
    auto corrected=head;corrected.eye.y+=20;
    auto immediate=acquisition.update(corrected,{0,0,0},1.f/60,2,true);
    assert(immediate.eye.y==corrected.eye.y); // No kickoff crawl despite strong smoothing.
    corrected.eye.y+=60;
    immediate=acquisition.update(corrected,{0,0,0},1.f/60,2);
    assert(immediate.eye.y==corrected.eye.y); // Corrected skeleton/root pose reacquired.
    fp::CareerCamera career;
    head.heading=0;head.pitch=.8f;head.roll=.7f;fp::axes(head);
    auto third=career.update(head,{0,0,0},{900,10,0},0,85);
    assert(third.pose.eye.x==-480.f&&third.pose.eye.y==230.f); // Behind the whole player.
    assert(std::fabs(third.fov-85*.01745329252f)<.001f);
    assert(third.pose.roll==0&&third.pose.pitch<.15f); // Keep the field visible.
    const float feetAngle=std::atan2(230.f,480.f);
    const float headAngle=std::atan2(230.f-175.f,480.f);
    assert(feetAngle-third.pose.pitch<third.fov*.5f);
    assert(std::fabs(headAngle-third.pose.pitch)<third.fov*.5f); // Entire body fits.
    head.eye.y+=20;head.pitch=-.5f;head.roll=-.6f;
    auto steady=career.update(head,{0,0,0},{900,10,0},1.f/60,75);
    assert(steady.pose.eye.y==third.pose.eye.y&&steady.pose.pitch==third.pose.pitch);
    assert(steady.pose.roll==0); // Animated nod/tilt does not shake this mode.
    auto translated=career.update(head,{100,0,0},{1000,10,0},1.f/60,75);
    assert(translated.pose.eye.x>third.pose.eye.x&&translated.pose.eye.x<third.pose.eye.x+10.f);
    for(int i=0;i<180;++i)translated=career.update(head,{100,0,0},{1000,10,0},1.f/60,75);
    assert(std::fabs(translated.pose.eye.x-third.pose.eye.x-100.f)<.01f);
    head.heading=1.f;
    auto orbit=career.update(head,{100,0,0},{1000,10,0},1.f/60,75);
    assert(orbit.pose.heading>0&&orbit.pose.heading<.1f); // Strong orbit smoothing.
    float priorHeading=orbit.pose.heading,priorSpeed=priorHeading*60.f;
    for(int i=0;i<180;++i){
        orbit=career.update(head,{100,0,0},{100.f+900.f*std::cos(1.f),10.f,-900.f*std::sin(1.f)},1.f/60,75);
        const float speed=fp::wrap(orbit.pose.heading-priorHeading)*60.f;
        assert(std::fabs(speed)<=1.501f);
        assert(std::fabs(speed-priorSpeed)<=4.f/60.f+.001f);
        priorHeading=orbit.pose.heading;priorSpeed=speed;
    }
    assert(std::fabs(orbit.pose.heading-1.f)<.005f);
    career.reset();
    auto reset=career.update(head,{2000,0,0},{2900,10,0},1.f/60,75);
    assert(reset.pose.heading>.5f); // New selected player/context acquires immediately.
    auto tight=career.update(head,{2000,0,0},{2900,10,0},0,60);
    assert(feetAngle-tight.pose.pitch<tight.fov*.5f); // Feet remain visible at the tightest lens.
    fp::CareerCamera presets;
    head.heading=0;fp::axes(head);
    auto closePreset=presets.update(head,{0,0,0},{900,10,0},0,85,0);
    auto midPreset=presets.update(head,{0,0,0},{900,10,0},1.f/60,85,1);
    assert(midPreset.pose.eye.x<closePreset.pose.eye.x&&midPreset.pose.eye.x>-750.f);
    for(int i=0;i<240;++i)midPreset=presets.update(head,{0,0,0},{900,10,0},1.f/120,85,1);
    assert(std::fabs(midPreset.pose.eye.x+750.f)<1.f);
    auto farPreset=presets.update(head,{0,0,0},{900,10,0},0,85,2);
    assert(farPreset.pose.eye.x==-1150.f&&farPreset.pose.eye.y==450.f);
    assert(closePreset.fov==midPreset.fov&&midPreset.fov==farPreset.fov);
    fp::CareerCamera handoff;
    const auto oldPlayer=handoff.update(head,{0,0,0},{900,10,0},0,85);
    auto newPlayer=handoff.update(head,{1000,0,0},{1900,10,0},1.f/60,85,0,true);
    assert(newPlayer.pose.eye.x>oldPlayer.pose.eye.x&&newPlayer.pose.eye.x<oldPlayer.pose.eye.x+50.f);
    for(int i=0;i<180;++i)newPlayer=handoff.update(head,{1000,0,0},{1900,10,0},1.f/60,85);
    assert(std::fabs(newPlayer.pose.eye.x-520.f)<.01f);
    const auto remote=handoff.update(head,{9000,0,0},{9900,10,0},1.f/60,85,0,true);
    assert(remote.pose.eye.x==8520.f); // No long sweep across the stadium.
    fp::CareerCamera fps60,fps120;
    head.heading=0;fps60.update(head,{0,0,0},{900,10,0},0,85);fps120.update(head,{0,0,0},{900,10,0},0,85);
    head.heading=1.f;
    fp::FramedView at60{},at120{};
    for(int i=0;i<120;++i)at60=fps60.update(head,{100,0,0},{1000,10,0},1.f/60,85);
    for(int i=0;i<240;++i)at120=fps120.update(head,{100,0,0},{1000,10,0},1.f/120,85);
    assert(std::fabs(at60.pose.heading-at120.pose.heading)<.01f);
    assert(std::fabs(at60.pose.eye.x-at120.pose.eye.x)<5.f);
    fp::PossessionFraming defaultWide;
    head.heading=0;head.pitch=.1f;fp::axes(head);
    auto defaultOff=defaultWide.update(head,{0,0,0},ball,false,0,false,85);
    auto defaultOn=defaultWide.update(head,{0,0,0},ball,true,0,false,85);
    assert(std::fabs(defaultOff.fov-85*.01745329252f)<.001f);
    assert(defaultOn.fov==defaultOff.fov);
    auto defaultFeet=defaultWide.update(head,{0,0,0},{14,10,0},true,0,false,85);
    assert(std::atan2(head.eye.y-10.f,25.f)-defaultFeet.pose.pitch<defaultFeet.fov*.5f);
    std::puts("PASS: ball/field balance, FOV/tilt personalization, hair clearance, immediate kickoff anchor and pose reacquisition");
    std::puts("PASS: career third person, whole-body framing, stable height/roll, root tracking and smooth orbit");
}
