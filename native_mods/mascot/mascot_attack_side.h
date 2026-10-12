#pragma once
// Reads engine-owned data only. No changes to halves, teams, score or direction.
static int mascot_home_native_orientation(int home)
{
    const unsigned char getter[15]={0x83,0xfa,1,0x77,0x0b,0x48,0x63,0xc2,0x8b,0x84,0x81,0x48,0x0a,0,0};
    if (!readable(image+0x4e47bc0,sizeof(getter)) || memcmp((void*)(image+0x4e47bc0),getter,sizeof(getter))) return 0;
    uintptr_t manager,world,game,registry,vt,items,pitch=0,again;
    int count,key;
    if (!get(image+0x3517420,manager) || !get(manager,vt) || vt!=image+0x2226730 ||
        !get(manager+8,world) || !get(world,vt) || vt!=image+0x2225d90 ||
        !get(world+0x10,game) || !get(game,vt) || vt!=image+0x2309370 ||
        !get(game+0x20,registry) || !registry ||
        !get(registry+8+15*32,key) || key!=15 ||
        !get(registry+8+15*32+16,count) || count!=2 ||
        !get(registry+8+15*32+24,items) || !readable(items,32)) return 0;
    bool seen[2]={false,false};
    for (int i=0;i<2;++i) {
        uintptr_t team,owner,stats,teamPitch;int side,club;
        if (!get(items+i*16+8,team) || !get(team,vt) || vt!=image+0x22fe9f0 ||
            !get(team+0x30,owner) || owner!=registry || !get(team+0x58,side) || side<0 || side>1 || seen[side] ||
            !get(team+0x50,stats) || !get(stats+0x80,club) || club<=0 || club>1000000 ||
            !get(team+0x48,teamPitch) || !get(teamPitch,vt) || vt!=image+0x22fc840) return 0;
        if (side==0 && club!=home) return 0;
        if (pitch && teamPitch!=pitch) return 0;pitch=teamPitch;seen[side]=true;
    }
    int directions[2],confirmed[2];
    if (!seen[0] || !seen[1] || !get(pitch+0xa48,directions[0]) || !get(pitch+0xa4c,directions[1]) || !get(pitch+0xa48,confirmed[0]) || !get(pitch+0xa4c,confirmed[1]) ||
        memcmp(directions,confirmed,sizeof(directions)) ||
        (directions[0]!=1 && directions[0]!=-1) || directions[1]!=-directions[0] ||
        !get(image+0x3517420,again) || again!=manager || !get(manager+8,again) || again!=world ||
        !get(world+0x10,again) || again!=game || !get(game+0x20,again) || again!=registry) return 0;
    return directions[0];
}

// Native orientation is opposite to the attacked goal's world-X sign.
// User observed second-half home orientation -1 while home attacks +X.
static float mascot_attack_goal_x(int nativeOrientation)
{
    return -mascotGoalLineBackX*(float)nativeOrientation;
}
