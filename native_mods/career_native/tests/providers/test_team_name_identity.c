#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif
/* Keep a test-only trap for the obsolete nation resolver. With the old host
 * its compatible tentative declaration binds the spy below; the corrected
 * host never references it. No FIFA process or game database is accessed. */
static void (*g_resolve_team)(void *,int,void *);
#include "../../src/host/dinput8_wrapper.c"

typedef struct TestTeam { int id; const char *name; } TestTeam;
typedef struct TestQuery { const char *table; int team; } TestQuery;
typedef struct TestBackend { void **vtable; } TestBackend;
static const TestTeam teams[] = {
    {1,"Arsenal"}, {9,"Liverpool"}, {1043,"Flamengo"},
    {598,"S\xc3\xa3o Paulo"}, {123456,"Clube criado pelo mod"}
};
static int failures,queries,nation_calls,query_frees,result_frees;
static char observed_field[96],home_name[256],away_name[256];
static int home_crest,away_crest;

static void check(int ok,const char *label) {
    if(!ok) { ++failures;printf("FAIL: %s\n",label); }
}
static void nation_trap(void *service,int id,void *out) {
    (void)service; ++nation_calls; memset(out,0,256);
    lstrcpynA((char *)out+4,id==1?"Albania":"Bulgaria",96);
}
static void *query_init(void *query,int mode,const char *table) {
    TestQuery *q=(TestQuery *)query;
    check(mode==1 && !strcmp(table,"teams"),"query the teams table, never nations");
    memset(query,0,56); q->table=table; ++queries; return query;
}
static void where_int(void *query,const char *field,int op,int id) {
    check(!strcmp(field,"teamid") && op==0,"filter by the fixture teamid");
    ((TestQuery *)query)->team=id;
}
static void *result_init(void *result) { *(const TestTeam **)result=NULL;return result; }
static void execute(void *backend,void *query,void *result) {
    TestQuery *q=(TestQuery *)query;size_t i;(void)backend;
    for(i=0;i<sizeof(teams)/sizeof(teams[0]);++i)
        if(teams[i].id==q->team) { *(const TestTeam **)result=teams+i;break; }
}
static int result_count(void *result) { return *(const TestTeam **)result?1:0; }
static const char *result_string(void *result,int row,const char *field) {
    const TestTeam *team=*(const TestTeam **)result;
    check(row==0 && !strcmp(field,"teamname"),"read the teamname field");
    return team?team->name:NULL;
}
static void result_free(void *result) { ++result_frees;*(const TestTeam **)result=NULL; }
static void query_free(void *query) { (void)query;++query_frees; }
static void observe_prepare(void *provider) { (void)provider;observed_field[0]=0; }
static void observe_string(void *provider,const char *key,const char *value) {
    (void)provider;
    if(!strcmp(key,"ID")) lstrcpynA(observed_field,value,sizeof(observed_field));
    if(strcmp(key,"PARAM")) return;
    if(!strcmp(observed_field,"MYTEAM_NEXT_HOME_NAME")) lstrcpynA(home_name,value,sizeof(home_name));
    if(!strcmp(observed_field,"MYTEAM_NEXT_AWAY_NAME")) lstrcpynA(away_name,value,sizeof(away_name));
}
static void observe_int(void *provider,const char *key,int value) {
    (void)provider;
    if(strcmp(key,"PARAM")) return;
    if(!strcmp(observed_field,"MYTEAM_NEXT_HOME_CREST")) home_crest=value;
    if(!strcmp(observed_field,"MYTEAM_NEXT_AWAY_CREST")) away_crest=value;
}
int main(void) {
    void *vtable[2]={NULL,(void *)execute};
    TestBackend backend={vtable};void *service=&backend;
    char value[128],guard='!';char temporary[MAX_PATH],fixture[MAX_PATH];
    FixtureRow row;FceFixture match={0};size_t i;int previous;
    setvbuf(stdout,NULL,_IONBF,0);
    g_resolve_team=nation_trap;
    native_names=&service;
    native_name_db.query_init=query_init;native_name_db.where_int=where_int;
    native_name_db.result_init=result_init;native_name_db.count=result_count;
    native_name_db.string=result_string;native_name_db.result_free=result_free;
    native_name_db.query_free=query_free;
    native_team_name_cache_count=0;
    for(i=0;i<sizeof(teams)/sizeof(teams[0]);++i) {
        native_team_name(teams[i].id,value,sizeof(value));
        check(!strcmp(value,teams[i].name),"resolve every club by identity, including mod IDs and UTF-8");
    }
    previous=queries;native_team_name(9,value,sizeof(value));
    check(!strcmp(value,"Liverpool") && queries==previous,"repeat lookup preserves the correct cached club");
    match.home=9;match.away=1;native_fixture(&match,&row);
    check(!strcmp(row.home,"Liverpool") && !strcmp(row.away,"Arsenal") &&
          row.home_logo==9 && row.away_logo==1,"fixture row keeps names paired with crests when sides swap");

    check(GetTempPathA(sizeof(temporary),temporary)!=0 &&
          GetTempFileNameA(temporary,"tnm",0,fixture)!=0,"create isolated fixture path");
    DeleteFileA(fixture);check(CreateDirectoryA(fixture,NULL),"create isolated fixture directory");
    lstrcpynA(g_game_dir,fixture,sizeof(g_game_dir));lstrcpynA(g_mod_dir,fixture,sizeof(g_mod_dir));
    g_prepare_field=observe_prepare;g_set_string=observe_string;g_set_int=observe_int;
    g_next_match_fixture_valid=1;g_upcoming_count=1;
    memset(&g_next_match_fixture,0,sizeof(g_next_match_fixture));
    g_next_match_fixture.home=1;g_next_match_fixture.away=9;
    g_next_match_fixture.date_raw=20260718;g_next_match_fixture.time_raw=1730;
    publish_next_match_card(&failures);
    check(!strcmp(home_name,"Arsenal") && !strcmp(away_name,"Liverpool") &&
          home_crest==1 && away_crest==9,"actual next-match publisher uses Arsenal/Liverpool with matching crests");
    g_next_match_fixture.home=123456;g_next_match_fixture.away=598;
    publish_next_match_card(&failures);
    check(!strcmp(home_name,teams[4].name) && !strcmp(away_name,teams[3].name) &&
          home_crest==123456 && away_crest==598,"actual publisher handles mod clubs and accented names generically");
    check(RemoveDirectoryA(fixture),"remove isolated empty fixture directory");

    lstrcpynA(value,"old value",sizeof(value));native_team_name(777777,value,sizeof(value));
    check(!value[0],"missing team never borrows an unrelated country name");
    previous=queries;native_team_name(0,value,sizeof(value));native_team_name(-1,value,sizeof(value));
    native_team_name(1,&guard,0);native_team_name(1,NULL,10);
    check(!value[0] && guard=='!' && queries==previous,"invalid IDs and empty destinations are safe");
    native_names=NULL;native_team_name(1,value,sizeof(value));
    check(!strcmp(value,"Arsenal"),"known club survives a temporary service gap");
    native_team_name(888888,value,sizeof(value));check(!value[0],"unavailable service cannot invent a team name");
    check(nation_calls==0,"nation resolver is never used for a club ID");
    check(query_frees==queries && result_frees==queries,"native query/result lifetimes are balanced");
    if(failures) return 1;
    puts("PASS: club identity in team lookups, fixture rows and next-match cards; mod IDs, UTF-8, cache, missing rows; no nation resolver");
    return 0;
}
