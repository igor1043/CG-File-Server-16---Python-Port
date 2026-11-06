/* Global league evidence for coach decisions, using the already validated
 * career DB read API on FIFA's UI owner. No DB setter or save write is used.
 * The companion requests an exact PID/session/club/day; stale requests expire.
 */
static const char *manager_league_fields[]={
    "teamid","leagueid","secondarytable","nummatchesplayed","points",
    "homewins","homedraws","homelosses","awaywins","awaydraws","awaylosses",
    "homegf","homega","awaygf","awayga","currenttableposition"};
static ULONGLONG g_manager_read_next;
static int g_manager_read_date,g_manager_journal_date;
static DWORD g_manager_read_epoch,g_manager_journal_epoch;
static uintptr_t g_manager_read_context;
static uintptr_t g_manager_journal_context;
static unsigned long long g_manager_journal_hash;

static void manager_archive_day(const char *source,const PreparedViewRecord *request,const MarketReadRows *rows)
{
    char root[MAX_PATH],folder[MAX_PATH],path[MAX_PATH],temporary[MAX_PATH];
    unsigned long long hash=1469598103934665603ULL;size_t i,total=(size_t)rows->count*rows->columns;
    for(i=0;i<total;++i){hash^=(unsigned)rows->values[i];hash*=1099511628211ULL;}
    if(g_manager_journal_date==request->date && g_manager_journal_context==(uintptr_t)request->context
        && g_manager_journal_epoch==request->epoch && g_manager_journal_hash==hash)return;
    if(snprintf(root,sizeof(root),"%s\\runtime\\manager_market\\league_days",g_mod_dir)>=(int)sizeof(root))return;
    if(!CreateDirectoryA(root,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return;
    if(snprintf(folder,sizeof(folder),"%s\\%lu-%llu-%u-%llx",root,GetCurrentProcessId(),request->created,request->epoch,request->context)>=(int)sizeof(folder))return;
    if(!CreateDirectoryA(folder,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return;
    if(snprintf(path,sizeof(path),"%s\\%d.tsv",folder,request->date)>=(int)sizeof(path))return;
    if(snprintf(temporary,sizeof(temporary),"%s.new",path)>=(int)sizeof(temporary))return;
    if(CopyFileA(source,temporary,FALSE) && MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)){
        g_manager_journal_date=request->date;g_manager_journal_epoch=request->epoch;g_manager_journal_context=(uintptr_t)request->context;g_manager_journal_hash=hash;
    }else DeleteFileA(temporary);
}

#ifndef MANAGER_ARCHIVE_CAMPAIGN
#include "career_manager_campaign.inc"
#define MANAGER_ARCHIVE_CAMPAIGN(r) manager_archive_campaign(r)
#endif

/* Archive the immutable owner-thread copy even during fast simulation.
 * Unlike drain_manager_read this does not execute a native DB query. */
static void drain_manager_calendar(void)
{
    PreparedViewRecord request;CareerContextRead captured;uintptr_t context;unsigned club;int today;
    char path[MAX_PATH];ULONGLONG tick=GetTickCount64();
    if(g_current_stats_provider_owner)return;
    snprintf(path,sizeof(path),"%s\\runtime\\manager_market\\read_request.tsv",g_mod_dir);
    if(!prepared_view_read_file(path,&request) || tick<request.captured || tick-request.captured>12000)return;
    if(!bank_input_context(&captured,&context,&club,&today))return;
    request.date=today;
    if(!prepared_view_scope(&request,&captured))return;
    MANAGER_ARCHIVE_CAMPAIGN(&request);
}

static void drain_manager_read(void)
{
    PreparedViewRecord request;CareerContextRead captured,verified;
    MarketReadRows rows={0};void *names,*backend;uintptr_t context;unsigned club;int today;
    ULONGLONG tick=GetTickCount64();int ok=0;FILE *file=NULL;
    char path[MAX_PATH],temporary[MAX_PATH],request_path[MAX_PATH];
    if(g_current_stats_provider_owner || !fce_runtime_is_stable()
        || !native_name_db.query_init || !native_name_db.where_int || !native_name_db.result_init
        || !native_name_db.count || !native_name_db.integer || !native_name_db.result_free || !native_name_db.query_free)return;
    snprintf(request_path,sizeof(request_path),"%s\\runtime\\manager_market\\read_request.tsv",g_mod_dir);
    if(!prepared_view_read_file(request_path,&request) || tick<request.captured
        || tick-request.captured>12000)return;
    /* Follow the native calendar on its owner thread even if the Python
     * request still carries yesterday's date. PID/context/epoch remain exact. */
    if(!bank_input_context(&captured,&context,&club,&today))return;
    request.date=today;
    if(!prepared_view_scope(&request,&captured))return;
    if(today==g_manager_read_date && captured.epoch==g_manager_read_epoch && context==g_manager_read_context && tick<g_manager_read_next)return;
    g_manager_read_date=today;g_manager_read_epoch=captured.epoch;g_manager_read_context=context;g_manager_read_next=tick+500;
    names=bank_mail_service(captured.registry,0x4456560,8);
    if(!names || !is_readable_range(names,sizeof(void *)))return;
    backend=*(void **)names;if(!is_readable_range(backend,16))return;
    context=(uintptr_t)request.context;
    snprintf(path,sizeof(path),"%s\\runtime\\manager_market\\live_leagues.tsv",g_mod_dir);
    snprintf(temporary,sizeof(temporary),"%s.new",path);
    __try {
        __try {
            if(!market_read_table(backend,"leagueteamlinks",manager_league_fields,
                (int)(sizeof(manager_league_fields)/sizeof(manager_league_fields[0])),"secondarytable",0,&rows)
                || rows.count<=0 || !prepared_view_scope(&request,&verified)
                || captured.sequence!=verified.sequence)__leave;
            file=fopen(temporary,"wb");if(!file)__leave;
            fprintf(file,"schema=1\npid=%lu\nprocess_created_100ns=%llu\nepoch=%lu\ncontext=%llx\nregistry=%llx\nclub=%u\ndate=%d\ncaptured_ms=%llu\n",
                GetCurrentProcessId(),request.created,captured.epoch,(unsigned long long)context,
                (unsigned long long)captured.registry,request.club,request.date,(unsigned long long)tick);
            if(!market_write_rows(file,"league",&rows) || !prepared_view_scope(&request,&verified)
                || captured.sequence!=verified.sequence)__leave;
            fputs("complete=1\n",file);ok=!ferror(file);
        } __finally {
            if(file){if(fclose(file))ok=0;file=NULL;}
            if(ok){manager_archive_day(temporary,&request,&rows);MANAGER_ARCHIVE_CAMPAIGN(&request);}
            free(rows.values);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    if(ok)MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    else DeleteFileA(temporary);
}
