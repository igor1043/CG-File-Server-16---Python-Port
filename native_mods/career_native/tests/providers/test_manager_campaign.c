#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../../src/core/fce_runtime.h"
typedef struct PreparedViewRecord {unsigned schema,pid,club,epoch;unsigned long long created,context,registry,captured;int date;} PreparedViewRecord;
typedef struct CareerContextRead {int unused;} CareerContextRead;
struct FceLiveSnapshot {FceModel model;};
static struct FceLiveSnapshot fixture_snapshot;
static FceDerivedStanding fixture_derived;
static unsigned fixture_revision=1,releases,refreshes;
static int valid=1;
static char g_mod_dir[MAX_PATH];
FceLiveSnapshot *fce_runtime_calendar_acquire(void){return &fixture_snapshot;}
const FceModel *fce_runtime_model(const FceLiveSnapshot *s){return &s->model;}
unsigned long fce_runtime_generation(const FceLiveSnapshot *s){(void)s;return fixture_revision;}
unsigned long fce_runtime_derived_revision(void){return 1;}
void fce_runtime_request_refresh(void){++refreshes;}
void fce_runtime_release(FceLiveSnapshot *s){(void)s;++releases;}
size_t fce_runtime_derived_copy(FceDerivedStanding *out,size_t capacity,int date){assert(date==20260301);if(out&&capacity)*out=fixture_derived;return 1;}
static int prepared_view_scope(const PreparedViewRecord *r,CareerContextRead *c){(void)r;(void)c;return valid;}
#include "../../src/host/career_manager_campaign.inc"
int main(void){
 char temp[MAX_PATH],folder[MAX_PATH],path[MAX_PATH],body[8192];FILE *f;size_t n;
 FceCompNode nodes[]={{1,-1,3,100,0},{2,1,4,10,0}};
 FceStanding standings[]={{1,2,10,0,0,0,0,0,0,0},{2,2,20,0,0,0,0,0,0,0}};
 PreparedViewRecord request={1,0,1043,2,123,456,789,0,20260301};request.pid=GetCurrentProcessId();
 assert(GetTempPathA(sizeof(temp),temp));assert(GetTempFileNameA(temp,"mcd",0,g_mod_dir));DeleteFileA(g_mod_dir);assert(CreateDirectoryA(g_mod_dir,NULL));
 snprintf(folder,sizeof(folder),"%s\\runtime",g_mod_dir);assert(CreateDirectoryA(folder,NULL));strcat(folder,"\\manager_market");assert(CreateDirectoryA(folder,NULL));strcat(folder,"\\league_days");assert(CreateDirectoryA(folder,NULL));
 snprintf(path,sizeof(path),"%s\\%lu-123-2-1c8",folder,GetCurrentProcessId());assert(CreateDirectoryA(path,NULL));strcpy(folder,path);strcat(path,"\\20260301.campaign.json");
 fixture_snapshot.model.date=20260301;fixture_snapshot.model.nodes=nodes;fixture_snapshot.model.node_count=2;fixture_snapshot.model.standings=standings;fixture_snapshot.model.standing_count=2;
 fixture_derived.standing=standings[0];fixture_derived.standing.home_wins=3;fixture_derived.standing.played=3;
 manager_archive_campaign(&request);f=fopen(path,"rb");assert(f);n=fread(body,1,sizeof(body)-1,f);fclose(f);body[n]=0;
 assert(strstr(body,"\"date\":20260301")&&strstr(body,"\"complete\":1")&&strstr(body,"\"derivedStandings\":[[1,2,10,3"));
 assert(DeleteFileA(path));request.date=20260302;manager_archive_campaign(&request);assert(refreshes==0 && GetFileAttributesA(path)==INVALID_FILE_ATTRIBUTES);
 request.date=20260301;++fixture_revision;valid=0;manager_archive_campaign(&request);assert(GetFileAttributesA(path)==INVALID_FILE_ATTRIBUTES);assert(releases==3);
 assert(RemoveDirectoryA(folder));*strrchr(folder,'\\')=0;assert(RemoveDirectoryA(folder));*strrchr(folder,'\\')=0;assert(RemoveDirectoryA(folder));*strrchr(folder,'\\')=0;assert(RemoveDirectoryA(folder));assert(RemoveDirectoryA(g_mod_dir));
 puts("PASS: daily competition archive includes native/fixture_derived standings, rejects wrong date/load and releases fixture_snapshot references");return 0;
}
