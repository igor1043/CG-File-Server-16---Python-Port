#define _CRT_SECURE_NO_WARNINGS
#include "../../src/host/dinput8_wrapper.c"
#include <assert.h>
typedef struct TestQuery {const char *table;int club;} TestQuery;
static int queries,query_frees,result_frees,rows=1;
static const char *first="Senhor",*last="Manager";
static char field[96],home[256],away[256];
static void *query_init(void *raw,int mode,const char *table){TestQuery *q=(TestQuery *)raw;assert(mode==1);memset(raw,0,56);q->table=table;++queries;return raw;}
static void where_int(void *raw,const char *key,int op,int club){TestQuery *q=(TestQuery *)raw;if(!strcmp(q->table,"career_users")){assert(!strcmp(key,"clubteamid")&&op==0);q->club=club;}}
static void *result_init(void *raw){*(int *)raw=0;return raw;}
static void execute(void *backend,void *raw,void *out){TestQuery *q=(TestQuery *)raw;(void)backend;*(int *)out=!strcmp(q->table,"career_users")&&q->club==native_club?rows:0;}
static int count(void *raw){return *(int *)raw;}
static const char *string(void *raw,int row,const char *key){assert(*(int *)raw==1&&row==0);if(!strcmp(key,"firstname"))return first;assert(!strcmp(key,"surname"));return last;}
static void result_free(void *raw){(void)raw;++result_frees;}
static void query_free(void *raw){(void)raw;++query_frees;}
static void prepare(void *provider){(void)provider;field[0]=0;}
static void set_string(void *provider,const char *key,const char *value){(void)provider;if(!strcmp(key,"ID"))lstrcpynA(field,value,sizeof(field));else if(!strcmp(key,"PARAM")){if(!strcmp(field,"MYTEAM_NEXT_HOME_MANAGER"))lstrcpynA(home,value,sizeof(home));if(!strcmp(field,"MYTEAM_NEXT_AWAY_MANAGER"))lstrcpynA(away,value,sizeof(away));}}
static void set_int(void *provider,const char *key,int value){(void)provider;(void)key;(void)value;}
int main(void){
 unsigned char context[0x318]={0};void *vtable[2]={0,(void *)execute};void **backend=vtable;void *service=&backend;
 char path[MAX_PATH],temp[MAX_PATH],data[MAX_PATH],catalogs[MAX_PATH],catalog[MAX_PATH],out[128];FILE *file;
 int role=1,before;
 native_club=112893;g_career_context_identity=context;memcpy(context+0x18c,&role,4);native_names=&service;
 native_name_db.query_init=query_init;native_name_db.where_int=where_int;native_name_db.result_init=result_init;
 native_name_db.count=count;native_name_db.string=string;native_name_db.result_free=result_free;native_name_db.query_free=query_free;
 assert(GetTempPathA(sizeof(temp),temp)&&GetTempFileNameA(temp,"nmm",0,path));assert(DeleteFileA(path)&&CreateDirectoryA(path,NULL));
 snprintf(data,sizeof(data),"%s\\data",path);assert(CreateDirectoryA(data,NULL));snprintf(catalogs,sizeof(catalogs),"%s\\catalogs",data);assert(CreateDirectoryA(catalogs,NULL));
 snprintf(catalog,sizeof(catalog),"%s\\club_manager_fallback.tsv",catalogs);file=fopen(catalog,"wb");assert(file);fputs("112893|Javier Mascherano\n241|Hansi Flick\n1043|Filipe Luis\n",file);fclose(file);
 lstrcpynA(g_mod_dir,path,sizeof(g_mod_dir));lstrcpynA(g_game_dir,path,sizeof(g_game_dir));
 assert(native_next_match_manager_name(112893,out,sizeof(out))&&!strcmp(out,"Senhor Manager"));
 before=queries;assert(native_next_match_manager_name(241,out,sizeof(out))&&!strcmp(out,"Hansi Flick")&&queries==before);
 g_prepare_field=prepare;g_set_string=set_string;g_set_int=set_int;g_next_match_fixture_valid=1;g_upcoming_count=1;
 g_next_match_fixture.home=112893;g_next_match_fixture.away=241;g_next_match_fixture.date_raw=20261107;g_next_match_fixture.time_raw=1600;
 publish_next_match_card(&role);assert(!strcmp(home,"TECNICO: Senhor Manager")&&!strcmp(away,"TECNICO: Hansi Flick"));
 g_next_match_fixture.home=241;g_next_match_fixture.away=112893;publish_next_match_card(&role);
 assert(!strcmp(home,"TECNICO: Hansi Flick")&&!strcmp(away,"TECNICO: Senhor Manager"));
 rows=2;assert(!native_next_match_manager_name(112893,out,sizeof(out))&&!out[0]);rows=1;
 first="  ";last=" Manager ";assert(native_next_match_manager_name(112893,out,sizeof(out))&&!strcmp(out,"Manager"));
 role=0;memcpy(context+0x18c,&role,4);assert(native_next_match_manager_name(112893,out,sizeof(out))&&!strcmp(out,"Javier Mascherano"));
 role=1;memcpy(context+0x18c,&role,4);native_club=1043;first="Outro";last="Treinador";
 assert(native_next_match_manager_name(1043,out,sizeof(out))&&!strcmp(out,"Outro Treinador"));
 assert(native_next_match_manager_name(112893,out,sizeof(out))&&!strcmp(out,"Javier Mascherano"));
 assert(queries==query_frees&&queries==result_frees);
 assert(DeleteFileA(catalog)&&RemoveDirectoryA(catalogs)&&RemoveDirectoryA(data)&&RemoveDirectoryA(path));
 puts("PASS next-match manager: current career name, home/away, other clubs, player career, ambiguous data and save/club changes; read-only balanced queries");return 0;
}
