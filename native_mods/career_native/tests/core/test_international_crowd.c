#include "../../src/features/crowd/international_competition.h"
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if(!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while(0)

int main(void)
{
    FceCompNode nodes[] = {
        {0,-1,0,-1,0}, {10,0,1,-1,0}, {11,10,2,-1,0},
        {100,10,3,1003,0}, {101,100,4,-1,2}, {102,101,5,-1,0},
        {200,11,3,201,0}, {201,200,4,-1,2},
        {300,11,3,202,0}, {400,0,1,-1,0}, {401,400,2,-1,0},
        {402,401,3,820,0}, {500,0,3,990,0}
    };
    FceFixture fixtures[] = {
        {1,102,101,20260408,2200,1043,100,-1,-1,0,1},
        {2,201,201,20260410,2200,1043,200,-1,-1,0,1},
        {3,100,101,20260407,2200,1043,100,2,0,1,1},
        {4,100,101,20260407,2200,1043,0,-1,-1,0,1}
    };
    FceModel model;
    const FceFixture *next;
    memset(&model,0,sizeof(model));
    model.nodes=nodes; model.node_count=sizeof(nodes)/sizeof(nodes[0]);
    model.fixtures=fixtures; model.fixture_count=sizeof(fixtures)/sizeof(fixtures[0]);
    model.date=20260407;
    next=crowd_next_actual_fixture(&model,1043);
    CHECK(next==fixtures && crowd_fixture_is_international(&model,next));
    CHECK(!crowd_fixture_is_international(&model,fixtures+1));
    fixtures[0].competition_object=300;
    CHECK(!crowd_fixture_is_international(&model,fixtures)); /* domestic cup */
    fixtures[0].competition_object=402;
    CHECK(!crowd_fixture_is_international(&model,fixtures)); /* preseason */
    fixtures[0].competition_object=500;
    CHECK(crowd_fixture_is_international(&model,fixtures)); /* FIFA world competition */
    fixtures[0].competition_object=65535;
    CHECK(!crowd_fixture_is_international(&model,fixtures)); /* unknown */
    fixtures[0].played_raw=1;
    CHECK(crowd_next_actual_fixture(&model,1043)==fixtures+1);
    fixtures[0].played_raw=0; fixtures[0].date_raw=20260410;
    fixtures[0].time_raw=2300;
    CHECK(crowd_next_actual_fixture(&model,1043)==fixtures+1);
    fixtures[0].time_raw=2200;
    CHECK(crowd_next_actual_fixture(&model,1043)==fixtures);
    CHECK(!crowd_next_actual_fixture(&model,999));
    model.date=20261410;
    CHECK(!crowd_next_actual_fixture(&model,1043));
    puts("PASS: actual next fixture, continental and FIFA world competitions, domestic cup/league, preseason, unknown, played/unresolved fixtures and date/time order");
    return 0;
}
