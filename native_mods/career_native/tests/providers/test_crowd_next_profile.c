/* Real card calculation, synthetic owned FCE data; no game process access. */
#include "../../src/host/dinput8_wrapper.c"
#define CHECK(x) do {if(!(x)){printf("FAIL %d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void)
{
    FceCompNode nodes[]={{0,-1,0,-1,0},{10,0,1,-1,0},{20,10,2,-1,0},
        {100,10,3,1003,0},{101,100,4,-1,FCE_STAGE_GROUP},{102,101,5,-1,0},
        {200,20,3,7,0},{201,200,4,-1,0}};
    FceStanding standings[]={{1,201,1043,0,0,0,0,0,0,0},{2,201,100,0,0,0,0,0,0,0}};
    FceFixture fixtures[]={{1,102,101,20260408,2200,1043,100,-1,-1,0,1},
                          {2,201,201,20260410,2200,1043,100,-1,-1,0,1}};
    FceModel model;
    memset(&model,0,sizeof(model));
    model.nodes=nodes;model.node_count=sizeof(nodes)/sizeof(nodes[0]);
    model.standings=standings;model.standing_count=2;
    model.fixtures=fixtures;model.fixture_count=2;model.date=20260407;
    native_update_crowd(&model,200,1043);
    CHECK(crowd_runtime_attendance_percent()>=75);
    nodes[4].stage_kind=FCE_STAGE_SEMI_FINAL;
    native_update_crowd(&model,200,1043);
    CHECK(crowd_runtime_attendance_percent()>=83);
    nodes[4].stage_kind=FCE_STAGE_FINAL;
    native_update_crowd(&model,200,1043);
    CHECK(crowd_runtime_attendance_percent()==90);
    fixtures[0].played_raw=1;
    native_update_crowd(&model,200,1043);
    CHECK(crowd_runtime_attendance_percent()>=68);
    crowd_runtime_disable();CHECK(crowd_runtime_attendance_percent()==-1);
    puts("PASS: real card and runtime attendance share next-fixture Libertadores/semifinal/final and domestic profiles");
    return 0;
}
