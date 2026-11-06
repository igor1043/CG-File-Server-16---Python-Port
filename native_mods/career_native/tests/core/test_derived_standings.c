#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "../../src/core/fce_runtime.h"
struct FceLiveSnapshot {FceModel model;};
static struct FceLiveSnapshot fixture;
static unsigned char *module;
static char runtime_log_dir[MAX_PATH];
static char log_path[MAX_PATH];
static volatile LONG generation=1;
static unsigned char fixture_iface[64],fixture_hub[64],fixture_connector[64],fixture_manager[16],clock_data[80],fixture_list[32];
static void *clocks[1];static unsigned simulations,refreshes;
static unsigned phases=2;
static FceRuntimeDateCallback date_callback;
FceLiveSnapshot *fce_runtime_cached_acquire(void){return &fixture;}
FceLiveSnapshot *fce_runtime_calendar_acquire(void){return &fixture;}
void fce_runtime_release(FceLiveSnapshot *s){(void)s;}
int fce_runtime_is_stable(void){return 1;}
void fce_runtime_request_refresh(void){++refreshes;}
static void report(const char *s,int ok,const FceModel *m,ULONGLONG time){(void)s;(void)ok;(void)m;(void)time;assert(0);}
static int copy_table(void *m,size_t offset,FceRawTable *t) {
    size_t i;unsigned char *p=calloc(phases,64);assert(m==fixture_manager && offset==0x48);
    t->bytes=p;t->count=phases;t->stride=64;
    for(i=0;i<phases;++i){p[i*64+10]=1;p[i*64+0x12]=4;p[i*64+0x10]=(unsigned char)(12+i*10);p[i*64+0x11]=(unsigned char)((12+i*10)>>8);memcpy(p+i*64+0x1c,"FCE_League_Stage",16);}return 1;
}
static void native_free(void *a,void *p,size_t n){(void)a;(void)n;free(p);}
static void *allocator_methods[4]={0,0,0,(void *)native_free};
static void **allocator=allocator_methods;
static void gather(void *c,int stage,void *out);
static void calculate(void *w,int stage,int date,void *out);
#define DERIVED_ALLOCATOR() (&allocator)
#define DERIVED_GATHER(c,s,v) gather(c,s,v)
#define DERIVED_CALCULATE(w,s,d,v) calculate(w,s,d,v)
#define DERIVED_PHASE_IS_LEAGUE(s) ((s)>=12 && ((s)-12)%10==0)
#define DERIVED_INTERFACE_READY(i) (((unsigned char *)(i))[0x30])
#include "../../src/core/derived_standings.inc"
static void set(unsigned char *p,size_t offset,int v){memcpy(p+offset,&v,4);}
static void gather(void *c,int stage,void *out) {
    DerivedNativeVector *v=out;size_t i;assert(c==fixture_connector);
    v->begin=calloc(2,0x9c);v->end=v->capacity=v->begin+2*0x9c;
    for(i=0;i<2;++i){set(v->begin+i*0x9c,0,stage*10+(int)i);set(v->begin+i*0x9c,4,stage*100+(int)i);}
}
static void calculate(void *w,int stage,int date,void *out) {
    void **wr=w;DerivedNativeVector *v=out;size_t i;
    assert(wr[0]==fixture_connector && wr[1]==clock_data && wr[2]==fixture_hub);assert(date==fixture.model.date);++simulations;
    for(i=0;i<2;++i){set(v->begin+i*0x9c,0x74,stage==12?3:1);set(v->begin+i*0x9c,0x88,2);set(v->begin+i*0x9c,0x80,9);set(v->begin+i*0x9c,0x94,4);}
}
static void run(void){int i;for(i=0;i<4;++i){derived_next=0;derived_tick(fixture_iface);}}
int main(void) {
    FceCompNode nodes[]={{11,-1,3,100,0},{12,11,4,-1,0},{13,12,5,-1,0},{21,-1,3,200,0},{22,21,4,-1,0},{23,22,5,-1,0}};
    FceStanding standings[]={{120,13,1200,0,0,0,0,0,0,0},{121,13,1201,0,0,0,0,0,0,0},{220,23,2200,0,0,0,0,0,0,0},{221,23,2201,0,0,0,0,0,0,0}};
    FceDerivedStanding out[4];
    fixture_iface[0x30]=1;*(void **)(fixture_iface+0x18)=fixture_hub;*(void **)(fixture_hub+0x28)=fixture_connector;*(void **)(fixture_hub+0x20)=fixture_list;*(void **)(fixture_connector+0x18)=fixture_manager;
    clocks[0]=clock_data;*(void ***)(fixture_list+8)=clocks;*(void ***)(fixture_list+0x10)=clocks+1;*(int *)(clock_data+0x20)=5;
    fixture.model.nodes=nodes;fixture.model.node_count=6;fixture.model.standings=standings;fixture.model.standing_count=4;fixture.model.date=20260810;
    derived_next=0;derived_tick(fixture_iface);assert(derived_complete);assert(simulations==2 && refreshes==1);assert(fce_runtime_derived_copy(out,4,20260810)==4);assert(out[0].standing.played==5 && out[2].standing.played==3);assert(out[0].home_gf+out[0].away_gf==13);
    run();assert(simulations==2);++generation;assert(fce_runtime_derived_copy(out,4,20260810)==0);
    fixture.model.date=20260811;run();assert(simulations==4 && fce_runtime_derived_copy(out,4,20260810)==0);
    /* Reordering raw rows is not a new campaign. */
    {FceStanding tmp=standings[0];standings[0]=standings[3];standings[3]=tmp;run();assert(simulations==4);tmp=standings[0];standings[0]=standings[3];standings[3]=tmp;}
    /* Only the changed root is recalculated. Unrelated data cannot flush it. */
    nodes[5].stage_kind=9;run();assert(simulations==5 && derived_reused==0); /* final unchanged run resets counters */
    {FceFixture game={1,13,12,20260811,1600,1200,1201,1,0,1,1};
     fixture.model.fixtures=&game;fixture.model.fixture_count=1;run();assert(simulations==6);game.home_score=2;run();assert(simulations==7);fixture.model.fixture_count=0;fixture.model.fixtures=NULL;run();assert(simulations==8);}
    standings[0].home_wins=standings[0].played=1;run();assert(simulations==8 && fce_runtime_derived_copy(out,4,20260811)==2);
    fixture_iface[0x30]=0;++fixture.model.date;run();assert(simulations==8);
    {
        FceCompNode world_nodes[435];FceStanding world_standings[290];unsigned j;
        phases=145;fixture_iface[0x30]=1;
        memset(world_nodes,0,sizeof(world_nodes));memset(world_standings,0,sizeof(world_standings));
        for(j=0;j<phases;++j) {
            int stage=12+j*10;FceCompNode *n=world_nodes+j*3;
            n[0]=(FceCompNode){stage-1,-1,3,100+(int)j,0};n[1]=(FceCompNode){stage,stage-1,4,-1,0};n[2]=(FceCompNode){stage+1,stage,5,-1,0};
            world_standings[j*2]=(FceStanding){stage*10,stage+1,stage*100,0,0,0,0,0,0,0};
            world_standings[j*2+1]=(FceStanding){stage*10+1,stage+1,stage*100+1,0,0,0,0,0,0,0};
        }
        fixture.model.nodes=world_nodes;fixture.model.node_count=435;fixture.model.standings=world_standings;fixture.model.standing_count=290;
        for(j=0;j<3;++j){fixture.model.date=20260901+j;derived_next=0;derived_tick(fixture_iface);assert(derived_complete);assert(derived_cursor==145);assert(fce_runtime_derived_copy(NULL,0,fixture.model.date)==290);}
        assert(simulations==8+145*3);
        {
            FceDerivedStanding golden[290],actual[290];unsigned previous=simulations;size_t k;
            assert(fce_runtime_derived_copy(golden,290,fixture.model.date)==290);
            for(k=0;k<145;++k){FceStanding t=world_standings[k];world_standings[k]=world_standings[289-k];world_standings[289-k]=t;}
            derived_next=0;derived_tick(fixture_iface);assert(simulations==previous);assert(fce_runtime_derived_copy(actual,290,fixture.model.date)==290);assert(!memcmp(golden,actual,sizeof(golden)));
            /* A counter in one root must leave the other 144 cached roots intact. */
            world_nodes[1].stage_kind=10;derived_next=0;derived_tick(fixture_iface);
            assert(derived_complete&&simulations==previous+1&&derived_reused==144);assert(fce_runtime_derived_copy(actual,290,fixture.model.date)==290);assert(!memcmp(golden,actual,sizeof(golden)));
            ++generation;derived_next=0;derived_tick(fixture_iface);assert(simulations==previous+146);assert(fce_runtime_derived_copy(actual,290,fixture.model.date)==290);assert(!memcmp(golden,actual,sizeof(golden)));
        }
    }
    {size_t k;for(k=0;k<65536;++k)free(derived_cache[k].rows);free(derived_cache);}
    free(derived_rows);puts("PASS: date/epoch-scoped campaign reuse, semantic invalidation, order stability and 145-phase daily capture");return 0;
}
