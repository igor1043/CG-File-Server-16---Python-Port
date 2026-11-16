#pragma once

// Native reactions can turn the head independently of the pelvis. Correct
// only Head and HeadEnd in the owned pose, never the root, feet or crowd actor.
static void mascot_head_forward(const float pose[31][16],float forward[3]) {
    const MascotWalkQuaternion delta=mascot_wq_mul(mascot_wq_from_matrix(pose[14]),
        mascot_wq_inverse(mascot_wq_from_matrix(mascotBindPose[14])));
    const float neutral[3]={0,0,1};
    mascot_wq_rotate(delta,neutral,forward);
}

static void mascot_focus_pitch(float pose[31][16],float dt,bool standing,bool goal) {
    MascotWalkRuntime& s=mascotWalkRuntime;
    if(!isfinite(dt) || dt<=0)return;
    // Fade back to the original head movement while turning or walking.
    const float step=fminf(dt,.05f)/.25f;
    s.gazeBlend=fmaxf(0,fminf(1,s.gazeBlend+(standing?step:-step)));
    if(s.gazeBlend<=0)return;
    float forward[3];mascot_head_forward(pose,forward);
    const float horizontal=sqrtf(forward[0]*forward[0]+forward[2]*forward[2]);
    const float distance=sqrtf(s.position[0]*s.position[0]+s.position[2]*s.position[2]);
    if(!isfinite(horizontal)||horizontal<.001f||distance<1)return;
    const float heading=atan2f(forward[0],forward[2]);
    const float yawError=mascot_wrap_heading(mascot_pitch_heading(s.position[0],s.position[2])-heading);
    const float yawFreedom=goal?.20f:.12f;
    float yaw=fabsf(yawError)>yawFreedom?yawError-copysignf(yawFreedom,yawError):0;
    yaw=fmaxf(-1.05f,fminf(1.05f,yaw))*s.gazeBlend;
    const float elevation=atan2f(forward[1],horizontal);
    const float fieldElevation=-atan2f(fmaxf(0,s.position[1]+pose[14][13]),distance);
    const float pitchFreedom=goal?.28f:.14f;
    const float pitchError=elevation-fieldElevation;
    float pitch=fabsf(pitchError)>pitchFreedom?pitchError-copysignf(pitchFreedom,pitchError):0;
    pitch=fmaxf(-.70f,fminf(.70f,pitch))*s.gazeBlend;
    if(fabsf(yaw)<.000001f && fabsf(pitch)<.000001f)return;
    const MascotWalkQuaternion yawQ={0,sinf(yaw*.5f),0,cosf(yaw*.5f)};
    const float finalHeading=heading+yaw,sine=sinf(pitch*.5f);
    const MascotWalkQuaternion pitchQ={cosf(finalHeading)*sine,0,-sinf(finalHeading)*sine,cosf(pitch*.5f)};
    const MascotWalkQuaternion correction=mascot_wq_mul(pitchQ,yawQ);
    const float pivot[3]={pose[14][12],pose[14][13],pose[14][14]};
    for(unsigned int bone=14;bone<=15;++bone) {
        for(unsigned int column=0;column<3;++column) {
            const unsigned int k=column*4;
            const float v[3]={pose[bone][k],pose[bone][k+1],pose[bone][k+2]};float rotated[3];
            mascot_wq_rotate(correction,v,rotated);
            for(unsigned int axis=0;axis<3;++axis)pose[bone][k+axis]=rotated[axis];
        }
        if(bone!=14) {
            const float v[3]={pose[bone][12]-pivot[0],pose[bone][13]-pivot[1],pose[bone][14]-pivot[2]};float rotated[3];
            mascot_wq_rotate(correction,v,rotated);
            for(unsigned int axis=0;axis<3;++axis)pose[bone][12+axis]=pivot[axis]+rotated[axis];
        }
    }
}
