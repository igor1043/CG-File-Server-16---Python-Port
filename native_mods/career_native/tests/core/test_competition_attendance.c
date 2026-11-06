#include "../../src/features/crowd/competition_attendance.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
#define CHECK(x) do {if(!(x)){printf("FAIL %d: %s\n",__LINE__,#x);return 1;}}while(0)

int main(void)
{
    FceCompNode nodes[]={{0,-1,0,-1,0},{10,0,1,-1,0},{20,10,2,-1,0},
        {100,10,3,1003,0},{101,100,4,-1,2},{102,101,5,-1,0},
        {200,20,3,7,0},{201,200,4,-1,0},{300,20,3,229,0},
        {301,300,4,-1,7},{400,20,3,820,0},{401,400,4,-1,2}};
    FceFixture fixtures[]={{1,102,101,20260408,2200,1043,100,-1,-1,0,1},
                          {2,201,201,20260410,2200,1043,200,-1,-1,0,1}};
    FceModel model;
    CrowdCompetitionProfile profile;
    float value;
    memset(&model,0,sizeof(model));model.nodes=nodes;model.node_count=sizeof(nodes)/sizeof(nodes[0]);
    model.fixtures=fixtures;model.fixture_count=2;model.date=20260407;
    profile=crowd_competition_profile(&model,crowd_next_actual_fixture(&model,1043));
    CHECK(!strcmp(profile.key,"libertadores"));
    /* Former 56% included 6 points. New profile replaces that old bonus. */
    value=crowd_competition_apply(0.50f,&profile);CHECK(fabsf(value-0.75f)<0.001f);
    CHECK(crowd_competition_apply(0.95f,&profile)<=0.881f);
    nodes[4].stage_kind=FCE_STAGE_QUARTER_FINAL;
    profile=crowd_competition_profile(&model,fixtures);CHECK(crowd_competition_apply(0.50f,&profile)>=0.789f);
    nodes[4].stage_kind=FCE_STAGE_SEMI_FINAL;
    profile=crowd_competition_profile(&model,fixtures);CHECK(crowd_competition_apply(0.50f,&profile)>=0.829f);
    nodes[4].stage_kind=FCE_STAGE_FINAL;
    profile=crowd_competition_profile(&model,fixtures);CHECK(fabsf(crowd_competition_apply(0.5f,&profile)-0.90f)<0.001f);
    nodes[4].stage_kind=FCE_STAGE_GROUP;nodes[3].asset=1007;
    profile=crowd_competition_profile(&model,fixtures);CHECK(!strcmp(profile.key,"sudamericana"));
    CHECK(crowd_competition_apply(0.50f,&profile)>=0.699f);
    profile=crowd_competition_profile(&model,fixtures+1);CHECK(!strcmp(profile.key,"brasileirao_a"));
    CHECK(crowd_competition_apply(0.50f,&profile)>=0.679f);
    nodes[6].asset=83;profile=crowd_competition_profile(&model,fixtures+1);
    CHECK(crowd_competition_apply(0.40f,&profile)>=0.599f);
    nodes[6].asset=350;profile=crowd_competition_profile(&model,fixtures+1);
    CHECK(crowd_competition_apply(0.40f,&profile)>=0.499f);
    nodes[6].asset=351;profile=crowd_competition_profile(&model,fixtures+1);
    CHECK(crowd_competition_apply(0.30f,&profile)>=0.419f);
    fixtures[1].competition_object=301;fixtures[1].stage=301;
    profile=crowd_competition_profile(&model,fixtures+1);CHECK(!strcmp(profile.key,"copa_brasil"));
    CHECK(crowd_competition_apply(0.50f,&profile)>=0.739f);
    fixtures[1].competition_object=401;fixtures[1].stage=401;
    profile=crowd_competition_profile(&model,fixtures+1);CHECK(!strcmp(profile.key,"preseason"));
    CHECK(fabsf(crowd_competition_apply(0.50f,&profile)-0.50f)<0.001f);
    nodes[11].stage_kind=FCE_STAGE_FINAL;
    profile=crowd_competition_profile(&model,fixtures+1);
    CHECK(fabsf(crowd_competition_apply(0.50f,&profile)-0.50f)<0.001f);
    CHECK(fabsf(crowd_competition_apply(0.89f,&profile)-0.89f)<0.001f);
    fixtures[1].competition_object=65535;profile=crowd_competition_profile(&model,fixtures+1);
    CHECK(profile.bonus_percent==0 && profile.minimum_percent==0);
    CHECK(fabsf(crowd_competition_apply(0.50f,&profile)-0.50f)<0.001f);
    CHECK(crowd_competition_profile(&model,NULL).bonus_percent==0);
    puts("PASS: Libertadores 75/79/83/90, Sudamericana, Brazilian A/B/C/D and cup, actual next match, preseason and unknown");
    return 0;
}
