#pragma once

static int check_pitch_gaze(const MascotStandingClip& clip,bool goal,
    const MascotSkinBinding& binding,const float rendererInverse[31][16],float& worstBefore,float& worstAfter) {
    for(float x:{-5850.f,5850.f})for(float z:{-3150.f,3150.f})
    for(unsigned int frame=0;frame<clip.count;++frame) {
        float before[31][16],pose[31][16];
        mascot_retarget_baked_pose(clip.frames+frame*217,before);
        mascotWalkRuntime={};
        mascotWalkRuntime.position[0]=x;mascotWalkRuntime.position[2]=z;
        const float desired=mascot_pitch_heading(x,z);
        mascot_orient_pose(before,desired);memcpy(pose,before,sizeof(pose));
        mascotWalkRuntime.gazeBlend=1;
        float forward[3];mascot_head_forward(before,forward);
        const float error=fabsf(mascot_wrap_heading(desired-atan2f(forward[0],forward[2])));
        worstBefore=fmaxf(worstBefore,error);
        mascot_focus_pitch(pose,1.f/60,true,goal);
        for(unsigned int bone=0;bone<31;++bone) {
            if(bone!=14&&bone!=15&&memcmp(before[bone],pose[bone],sizeof(pose[bone])))return 70;
            for(float value:pose[bone])if(!isfinite(value))return 71;
        }
        for(unsigned int axis=0;axis<3;++axis)if(before[14][12+axis]!=pose[14][12+axis])return 72;
        if(fabsf(mascot_joint_distance(before,14,15)-mascot_joint_distance(pose,14,15))>.002f)return 73;
        mascot_head_forward(pose,forward);
        const float after=fabsf(mascot_wrap_heading(desired-atan2f(forward[0],forward[2])));
        worstAfter=fmaxf(worstAfter,after);
        const float freedom=goal?.20f:.12f;
        if(after>fmaxf(freedom,error-1.05f)+.002f)return 74;
        const float elevation=atan2f(forward[1],sqrtf(forward[0]*forward[0]+forward[2]*forward[2]));
        const float target=-atan2f(fmaxf(0,pose[14][13]),sqrtf(x*x+z*z));
        float original[3];mascot_head_forward(before,original);
        const float oldPitch=fabsf(atan2f(original[1],sqrtf(original[0]*original[0]+original[2]*original[2]))-target);
        if(fabsf(elevation-target)>fmaxf(goal?.28f:.14f,oldPitch-.70f)+.002f)return 75;
        // The renderer's shared inverse bind must not undo the gaze correction.
        float palette[31][16],gpu[31][16],restored[31][16];
        if(!mascot_skin_palette(binding,pose,palette))return 76;
        for(unsigned int bone=0;bone<31;++bone) {
            mascot_skin_multiply(palette[bone],rendererInverse[bone],gpu[bone]);
            mascot_skin_multiply(gpu[bone],binding.modelBind[bone],restored[bone]);
        }
        mascot_head_forward(restored,original);
        for(unsigned int axis=0;axis<3;++axis)if(fabsf(original[axis]-forward[axis])>.0002f)return 77;
        float paused[31][16];memcpy(paused,pose,sizeof(paused));
        const float weight=mascotWalkRuntime.gazeBlend;
        mascot_focus_pitch(pose,0,false,false);
        if(memcmp(paused,pose,sizeof(paused))||weight!=mascotWalkRuntime.gazeBlend)return 78;
        for(unsigned int i=0;i<16;++i){memcpy(pose,before,sizeof(pose));mascot_focus_pitch(pose,1.f/60,false,false);}
        if(mascotWalkRuntime.gazeBlend>.0001f||memcmp(pose,before,sizeof(pose)))return 79;
    }
    return 0;
}
