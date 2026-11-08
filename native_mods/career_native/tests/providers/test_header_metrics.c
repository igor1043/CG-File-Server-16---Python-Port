#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif
#include "../../src/host/dinput8_wrapper.c"
#include <assert.h>

typedef struct HeaderQuery { const char *table; int club; } HeaderQuery;
static int queries, query_frees, result_frees, domestic=20, international=14;
static char field[96], efficiency[32], prestige[32];
static int published_club;

static void *query_init(void *raw,int mode,const char *table) {
    HeaderQuery *query=(HeaderQuery *)raw;
    assert(mode==1 && !strcmp(table,"teams"));
    memset(raw,0,56); query->table=table; ++queries; return raw;
}
static void where_int(void *raw,const char *key,int op,int club) {
    assert(!strcmp(key,"teamid") && op==0); ((HeaderQuery *)raw)->club=club;
}
static void *result_init(void *raw) { *(int *)raw=0; return raw; }
static void execute(void *backend,void *raw,void *result) {
    (void)backend; assert(((HeaderQuery *)raw)->club==native_club); *(int *)result=1;
}
static int count(void *raw) { return *(int *)raw; }
static int integer(void *raw,int row,const char *key) {
    assert(*(int *)raw==1 && row==0);
    if(!strcmp(key,"domesticprestige")) return domestic;
    assert(!strcmp(key,"internationalprestige")); return international;
}
static void result_free(void *raw) { (void)raw; ++result_frees; }
static void query_free(void *raw) { (void)raw; ++query_frees; }
static void prepare(void *provider) { (void)provider; field[0]=0; }
static void set_string(void *provider,const char *key,const char *value) {
    (void)provider;
    if(!strcmp(key,"ID")) lstrcpynA(field,value,sizeof(field));
    else if(!strcmp(key,"PARAM")) {
        if(!strcmp(field,"CAREER_HEADER_EFFICIENCY")) lstrcpynA(efficiency,value,sizeof(efficiency));
        if(!strcmp(field,"CAREER_HEADER_PRESTIGE")) lstrcpynA(prestige,value,sizeof(prestige));
    }
}
static void set_int(void *provider,const char *key,int value) {
    (void)provider;
    if(!strcmp(key,"PARAM") && !strcmp(field,"CAREER_HEADER_CLUB_ID")) published_club=value;
}
int main(void) {
    FceFixture fixtures[7]={0};
    void *vtable[2]={NULL,(void *)execute}; void **backend=vtable; void *service=&backend;
    int i;
    assert(native_header_efficiency(14,19)==45);
    assert(native_header_efficiency(0,0)==-1 && native_header_efficiency(1,4)==-1);
    assert(native_header_efficiency(1,0)==0 && native_header_efficiency(1,3)==100);
    assert(native_header_efficiency(INT_MAX,INT_MAX)==33);
    assert(native_header_prestige_value(20,20)==50);
    assert(native_header_prestige_value(20,14)==43);
    assert(native_header_prestige_value(0,0)==-1 && native_header_prestige_value(21,10)==-1);
    native_club=1043; native_view.date=20261107;
    for(i=0;i<7;++i) {
        fixtures[i].id=i+1; fixtures[i].date_raw=20260101+i;
        fixtures[i].home=1043; fixtures[i].away=241;
        fixtures[i].played_raw=1; fixtures[i].home_score=0; fixtures[i].away_score=1;
        fixtures[i].competition_object=100+i;
    }
    fixtures[0].home_score=2; /* A win in one competition. */
    fixtures[1].home_score=1; /* A draw in a different competition. */
    fixtures[3].played_raw=0;
    fixtures[4].date_raw=20270101; /* Future results cannot affect the header. */
    fixtures[5]=fixtures[0]; /* Duplicate snapshot of an already counted fixture. */
    fixtures[6].home=598; /* Another club's result. */
    native_view.fixtures=fixtures; native_view.fixture_count=7;
    native_coach_record(native_club);
    assert(g_coach_record.games==3 && g_coach_record.points==4);
    assert(native_header_efficiency(g_coach_record.games,g_coach_record.points)==44);
    assert(g_coach_record.percent==33); /* Existing win-rate consumers retain their definition. */
    native_names=&service;
    native_name_db.query_init=query_init; native_name_db.where_int=where_int;
    native_name_db.result_init=result_init; native_name_db.count=count;
    native_name_db.integer=integer; native_name_db.result_free=result_free; native_name_db.query_free=query_free;
    g_prepare_field=prepare; g_set_string=set_string; g_set_int=set_int;
    publish_header_metrics(&i);
    assert(published_club==1043 && !strcmp(efficiency,"44%") && !strcmp(prestige,"4,3/5"));
    native_club=112893; domestic=12; international=8;
    memset(&g_coach_record,0,sizeof(g_coach_record)); publish_header_metrics(&i);
    assert(published_club==112893 && !efficiency[0] && !strcmp(prestige,"2,5/5"));
    assert(queries==query_frees && queries==result_frees);
    puts("PASS career header: all competitions, duplicate/future/unplayed fixtures, points efficiency, current-club prestige, empty career and balanced read-only queries");
    return 0;
}
