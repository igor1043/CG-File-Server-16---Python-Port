/* Explicit requests only. Use the game's own UPDATE query against the active
 * database on its existing career/UI owner. Never edit DATA or base DB files. */
#include "career_retirement_live.h"
#include <bcrypt.h>
/* FIFA 16 gameplay ratings only. Potential, traits, skills, weak foot,
 * reputation, position and physical appearance are deliberately not written. */
static const char *retirement_live_attributes[RETIREMENT_LIVE_ATTRIBUTES]={
    "acceleration","aggression","agility","balance","ballcontrol","crossing","curve",
    "dribbling","finishing","freekickaccuracy","gkdiving","gkhandling","gkkicking",
    "gkpositioning","gkreflexes","headingaccuracy","interceptions","jumping","longpassing",
    "longshots","marking","penalties","positioning","reactions","shortpassing","shotpower",
    "slidingtackle","sprintspeed","stamina","standingtackle","strength","vision","volleys"
};
typedef struct RetirementLiveScope {
    CareerContextRead captured;uintptr_t context;unsigned club;int today;void *backend;
} RetirementLiveScope;
static int retirement_live_page(void) {
    static const unsigned offsets[]={232,192,136,472};uintptr_t node=0;unsigned i;char page[96];
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,8))return 0;
    for(i=0;i<4;++i)if(!node || !read_card_scope(node+offsets[i],&node,8))return 0;
    return node && read_card_scope(node,page,sizeof(page)) && memchr(page,0,sizeof(page))
        && !strcmp(page,"game/screens/career/server16/CareerRetirement");
}
static int retirement_live_scope(void *user) {
    RetirementLiveScope *s=(RetirementLiveScope *)user;
    return retirement_live_page() && market_read_same_context(&s->captured,(int)s->club,s->today);
}
static int retirement_live_query_rows(RetirementLiveScope *s,int id,RetirementLiveRow **rows,int *count) {
    unsigned __int64 query[7]={0},result=0;int q=0,r=0,i,j,n,ok=0;
    RetirementLiveRow *values=NULL;*rows=NULL;*count=0;
    __try {
        __try {
            unsigned char (*execute)(void *,void *,void *)=(unsigned char (*)(void *,void *,void *))(*(void ***)s->backend)[1];
            native_name_db.query_init(query,1,"players");q=1;
            native_name_db.where_int(query,id?"playerid":"isretiring",0,id?id:1);
            native_name_db.result_init(&result);r=1;
            if(!execute(s->backend,query,&result))__leave;
            n=native_name_db.count(&result);if(n<0 || n>50000 || (id && n!=1))__leave;
            values=(RetirementLiveRow *)calloc(n?n:1,sizeof(*values));if(!values)__leave;
            for(i=0;i<n;++i){values[i].id=native_name_db.integer(&result,i,"playerid");
                values[i].retiring=native_name_db.integer(&result,i,"isretiring");
                values[i].birthdate=native_name_db.integer(&result,i,"birthdate");
                values[i].overall=native_name_db.integer(&result,i,"overallrating");
                values[i].potential=native_name_db.integer(&result,i,"potential");
                for(j=0;j<RETIREMENT_LIVE_ATTRIBUTES;++j)
                    values[i].attributes[j]=native_name_db.integer(&result,i,retirement_live_attributes[j]);}
            *rows=values;*count=n;values=NULL;ok=1;
        } __finally {
            if(r)native_name_db.result_free(&result);if(q)native_name_db.query_free(query);free(values);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    return ok;
}
static int retirement_live_read(void *user,int id,RetirementLiveRow *out) {
    RetirementLiveRow *rows=NULL;int n=0,ok=retirement_live_query_rows((RetirementLiveScope *)user,id,&rows,&n);
    if(ok && n==1)*out=rows[0];else ok=0;free(rows);return ok;
}
static int retirement_live_write(void *user,const RetirementLiveRow *before,const RetirementLiveRow *after) {
    RetirementLiveScope *s=(RetirementLiveScope *)user;unsigned __int64 query[7]={0},result=0;
    int q=0,r=0,i,ok=0;
    void (*set_int)(void *,const char *,int)=(void (*)(void *,const char *,int))(g_module_base+0x4462640);
    __try {
        __try {
            unsigned char (*execute)(void *,void *,void *)=(unsigned char (*)(void *,void *,void *))(*(void ***)s->backend)[1];
            native_name_db.query_init(query,3,"players");q=1;
            set_int(query,"isretiring",after->retiring);
            if(after->birthdate!=before->birthdate)set_int(query,"birthdate",after->birthdate);
            if(after->overall!=before->overall)set_int(query,"overallrating",after->overall);
            for(i=0;i<RETIREMENT_LIVE_ATTRIBUTES;++i)if(after->attributes[i]!=before->attributes[i])
                set_int(query,retirement_live_attributes[i],after->attributes[i]);
            native_name_db.where_int(query,"playerid",0,before->id);
            native_name_db.where_int(query,"isretiring",0,before->retiring);
            native_name_db.where_int(query,"birthdate",0,before->birthdate);
            native_name_db.where_int(query,"overallrating",0,before->overall);
            native_name_db.where_int(query,"potential",0,before->potential);
            native_name_db.result_init(&result);r=1;ok=execute(s->backend,query,&result)!=0;
        } __finally {if(r)native_name_db.result_free(&result);if(q)native_name_db.query_free(query);}
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    return ok;
}
static int retirement_live_random_rating(void *unused,int *out) {
    ULONG value;int attempts;(void)unused;
    /* Reject the four surplus values rather than biasing one end of 60..65.
     * Do not seed or consume FIFA's RNG, or use the process-wide C rand(). */
    for(attempts=0;attempts<8;++attempts){
        if(BCryptGenRandom(NULL,(PUCHAR)&value,sizeof(value),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)return 0;
        if(value<4294967292UL){*out=60+(int)(value%6);return 1;}
    }
    return 0;
}
static int retirement_live_publish(const char *name,const char *text) {
    char path[MAX_PATH],temp[MAX_PATH];FILE *file;int ok;
    snprintf(path,sizeof(path),"%s\\runtime\\career_options\\%s",g_mod_dir,name);
    snprintf(temp,sizeof(temp),"%s.new",path);file=fopen(temp,"wb");if(!file)return 0;
    ok=fputs(text,file)>=0;if(fclose(file))ok=0;
    if(ok)ok=MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    if(!ok)DeleteFileA(temp);return ok;
}
static int retirement_live_prepare_scope(RetirementLiveScope *s,ULONGLONG *created) {
    unsigned char *names;FILETIME ct,et,kt,ut;ULARGE_INTEGER identity;
    if(!bank_input_context(&s->captured,&s->context,&s->club,&s->today)
        || s->captured.owner_thread!=GetCurrentThreadId() || !retirement_live_scope(s)
        || !native_name_db.query_init || !native_name_db.where_int || !native_name_db.result_init
        || !native_name_db.count || !native_name_db.integer || !native_name_db.result_free || !native_name_db.query_free
        || memcmp(g_module_base+0x4462640,"\x48\x89\x5c\x24\x08",5)
        || !GetProcessTimes(GetCurrentProcess(),&ct,&et,&kt,&ut))return 0;
    names=bank_mail_service(s->captured.registry,0x4456560,8);if(!names)return 0;
    s->backend=*(void **)names;if(!is_readable_range(s->backend,16)
        || *(uintptr_t *)s->backend!=(uintptr_t)g_module_base+0x21b5770)return 0;
    identity.LowPart=ct.dwLowDateTime;identity.HighPart=ct.dwHighDateTime;*created=identity.QuadPart;return 1;
}
static void drain_retirement_live(void) {
    static ULONGLONG next,cap_next;static char last_id[33],last_response[2048];
    ULONGLONG tick=GetTickCount64(),created,request_created,context,registry,sent;
    RetirementLiveScope s;RetirementLiveRow *rows=NULL;RetirementLiveResult applied={1,0,0,0};
    unsigned schema,pid,epoch,club;int today,mode,age,n=0,used=0;char path[MAX_PATH],wire[512],id[33],text[2048];
    FILE *file;
    if(Fifa16CareerContextRead.owner_thread!=GetCurrentThreadId()
        || Fifa16CareerContextRead.sequence&1 || Fifa16CareerContextRead.epoch!=fce_runtime_context_epoch()
        || g_current_stats_provider_owner || tick<next)return;next=tick+100;
    if(!retirement_live_page())return;
    memset(&s,0,sizeof(s));if(!retirement_live_prepare_scope(&s,&created))return;
    if(tick>=cap_next){
        snprintf(text,sizeof(text),"schema=1\npid=%lu\ncreated=%llu\nepoch=%lu\ncontext=%llx\nregistry=%llx\nclub=%u\ndate=%d\ntick=%llu\n",
            GetCurrentProcessId(),created,s.captured.epoch,(unsigned long long)s.context,
            (unsigned long long)s.captured.registry,s.club,s.today,tick);
        if(retirement_live_publish("retirement_ready.tsv",text))cap_next=tick+1000;
    }
    snprintf(path,sizeof(path),"%s\\runtime\\career_options\\retirement_request.tsv",g_mod_dir);
    file=fopen(path,"rb");if(!file)return;
    n=(int)fread(wire,1,sizeof(wire)-1,file);wire[n]=0;fclose(file);
    if(sscanf(wire,"%u %u %llu %u %llx %llx %u %d %32s %d %d %llu %n",
        &schema,&pid,&request_created,&epoch,&context,&registry,&club,&today,id,&mode,&age,&sent,&used)!=12
        || !used || wire[used] || schema!=1 || strlen(id)!=32 || strspn(id,"0123456789abcdef")!=32)return;
    if(!strcmp(last_id,id)){
        if(retirement_live_publish("retirement_response.tsv",last_response))DeleteFileA(path);return;
    }
    if(pid!=GetCurrentProcessId() || request_created!=created || epoch!=s.captured.epoch
        || context!=s.context || registry!=s.captured.registry || club!=s.club || today!=s.today
        || sent>tick || tick-sent>15000 || (mode!=0 && mode!=1) || age<12 || age>50)applied.status=1;
    else if(retirement_live_query_rows(&s,0,&rows,&n)){
        RetirementLiveOps ops={&s,retirement_live_scope,retirement_live_read,retirement_live_write,retirement_live_random_rating};
        applied=retirement_live_apply(ops,rows,n,mode,today,age);
    }
    free(rows);
    snprintf(last_response,sizeof(last_response),"schema=1\nid=%s\npid=%u\ncreated=%llu\nepoch=%u\ncontext=%llx\nclub=%u\nstatus=%d\neligible=%d\nchanged=%d\nrestored=%d\nnative_save_pending=1\n",
        id,pid,request_created,epoch,context,club,applied.status,applied.eligible,applied.changed,applied.restored);
    lstrcpynA(last_id,id,sizeof(last_id));
    if(retirement_live_publish("retirement_response.tsv",last_response))DeleteFileA(path);
    append_loader_log(applied.status==0?"career_retirement_live_verified":applied.status==3?
        "career_retirement_live_restore_failed":"career_retirement_live_rejected_or_restored");
}
