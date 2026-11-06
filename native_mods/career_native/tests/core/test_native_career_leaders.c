#include "../../src/core/fce_model.h"
#include <stdio.h>
#include <string.h>

#define CHECK(test) do { if(!(test)) { \
    fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#test); return 1; \
} } while(0)

int main(void) {
    FceCompNode nodes[]={
        {100,-1,3,0},{101,100,4,0},{200,-1,3,0},{201,200,4,0}
    };
    FceStat stats[]={
        {1,100,7,10,10,800,2,1,2,0},
        {1,100,7,10,10,800,2,1,2,0}, /* repeated native row */
        {2,101,7,10,10,800,8,7,5,1}, /* child phase, suppressed by root */
        {3,200,7,10,10,700,3,2,1,0},
        {4,201,7,10,10,700,9,8,4,2}, /* child phase, suppressed by root */
        {5,100,7,20,9,750,3,2,3,0},
        {6,200,7,20,9,500,1,0,1,1},
        {7,101,7,30,5,300,4,3,0,2}, /* child-only tournament row */
        {8,100,7,40,8,640,1,5,2,0},
        {9,200,7,40,8,520,4,1,0,0},
        {10,100,8,99,10,900,99,99,99,99} /* other team */
    };
    FceModel model; FceStat out[5]; size_t count=0;
    memset(&model,0,sizeof(model));
    model.nodes=nodes;model.node_count=sizeof(nodes)/sizeof(nodes[0]);
    model.stats=stats;model.stat_count=sizeof(stats)/sizeof(stats[0]);

    CHECK(fce_model_career_leaders(&model,7,FCE_CAREER_GOALS,out,5,&count)==FCE_OK);
    CHECK(count==4);
    CHECK(out[0].player==10 && out[0].goals==5);
    CHECK(out[1].player==40 && out[1].goals==5);
    CHECK(out[2].player==20 && out[2].goals==4);
    CHECK(out[3].player==30 && out[3].goals==4);

    CHECK(fce_model_career_leaders(&model,7,FCE_CAREER_ASSISTS,out,5,&count)==FCE_OK);
    CHECK(count==4);
    CHECK(out[0].player==40 && out[0].assists==6);
    CHECK(out[1].player==10 && out[1].assists==3);
    CHECK(out[2].player==30 && out[2].assists==3);
    CHECK(out[3].player==20 && out[3].assists==2);

    CHECK(fce_model_career_leaders(&model,7,FCE_CAREER_YELLOW_CARDS,out,5,&count)==FCE_OK);
    CHECK(count==3);
    CHECK(out[0].player==20 && out[0].yellow_cards==4);
    CHECK(out[1].player==10 && out[1].yellow_cards==3);
    CHECK(out[2].player==40 && out[2].yellow_cards==2);

    CHECK(fce_model_career_leaders(&model,7,FCE_CAREER_RED_CARDS,out,5,&count)==FCE_OK);
    CHECK(count==2);
    CHECK(out[0].player==30 && out[0].red_cards==2);
    CHECK(out[1].player==20 && out[1].red_cards==1);

    CHECK(fce_model_career_leaders(&model,7,FCE_CAREER_MINUTES,out,5,&count)==FCE_OK);
    CHECK(count==4);
    CHECK(out[0].player==10 && out[0].minutes==1500);
    CHECK(out[1].player==20 && out[1].minutes==1250);
    CHECK(out[2].player==40 && out[2].minutes==1160);
    CHECK(out[3].player==30 && out[3].minutes==300);
    puts("PASS: career leaders aggregate all roots, suppress duplicate stage totals, and return only populated rows.");
    return 0;
}
