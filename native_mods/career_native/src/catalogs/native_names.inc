/* Current database service, not disk tables. Verified x64 query ABI:
 * query ctor 445a2f0, where 44629b0,
 * backend vtable+8, result count/int/string, result/query destructors.
 * The scorer name resolver 5c38130 expects a NAME key, not a player ID. */
typedef struct NativeNameDbApi {
    void *(*query_init)(void *,int,const char *);
    void (*where_int)(void *,const char *,int,int);
    void *(*result_init)(void *);
    int (*count)(void *);
    int (*integer)(void *,int,const char *);
    const char *(*string)(void *,int,const char *);
    void (*result_free)(void *);
    void (*query_free)(void *);
} NativeNameDbApi;
static NativeNameDbApi native_name_db;
typedef struct NativeNameCache { int player; char text[128]; } NativeNameCache;
static NativeNameCache native_name_cache[128];
static size_t native_name_cache_count;
typedef struct NativeTeamNameCache { int team; char text[128]; } NativeTeamNameCache;
static NativeTeamNameCache native_team_name_cache[512];
static size_t native_team_name_cache_count;

static void native_name_db_bind(void) {
    native_name_db.query_init=(void *(*)(void *,int,const char *))(g_module_base+0x445a2f0);
    native_name_db.where_int=(void (*)(void *,const char *,int,int))(g_module_base+0x44629b0);
    native_name_db.result_init=(void *(*)(void *))(g_module_base+0x5cc32f0);
    native_name_db.count=(int (*)(void *))(g_module_base+0x4468cf0);
    native_name_db.integer=(int (*)(void *,int,const char *))(g_module_base+0x4462ab0);
    native_name_db.string=(const char *(*)(void *,int,const char *))(g_module_base+0x511b070);
    native_name_db.result_free=(void (*)(void *))(g_module_base+0x445e130);
    native_name_db.query_free=(void (*)(void *))(g_module_base+0x445e020);
}
static int native_name_query(int player,int edited,char *out,size_t size,int keys[4]) {
    /* Query is 0x38 bytes; result is one ref-counted pointer. */
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,found=0; size_t i;
    const char *text_fields[]={"commonname","playerjerseyname","surname","firstname"};
    const char *key_fields[]={"commonnameid","playerjerseynameid","lastnameid","firstnameid"};
    if(!native_names || !native_name_db.query_init || player<=0 || !size) return 0;
    __try {
        __try {
            void *backend=*(void **)native_names;
            void (*execute)(void *,void *,void *)=(void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,edited?"editedplayernames":"players"); query_ready=1;
            native_name_db.where_int(query,"playerid",0,player);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            if(native_name_db.count(&result)==1) {
                found=1;
                for(i=0;i<4;++i) {
                    if(edited) {
                        const char *text=native_name_db.string(&result,0,text_fields[i]);
                        if(text && text[0]) { lstrcpynA(out,text,(int)size);break; }
                    } else keys[i]=native_name_db.integer(&result,0,key_fields[i]);
                }
            }
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { found=0; out[0]=0; }
    return found;
}
static int native_team_name_query(int team,char *out,size_t size) {
    /* Use teams.teamid directly: the similarly shaped resolver at 5b8e430
     * reads nations.nationid and can return a plausible but unrelated name.
     * This in-process service respects the current database and mod clubs. */
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,found=0;
    size_t i;
    if(!size) return 0;
    out[0]=0;
    for(i=0;i<native_team_name_cache_count;++i) {
        if(native_team_name_cache[i].team==team) {
            lstrcpynA(out,native_team_name_cache[i].text,(int)size);
            return out[0]!=0;
        }
    }
    if(!native_names || !native_name_db.query_init || !native_name_db.where_int ||
       !native_name_db.result_init || !native_name_db.count || !native_name_db.string ||
       !native_name_db.result_free || !native_name_db.query_free || team<=0) return 0;
    __try {
        __try {
            void *backend=*(void **)native_names;
            void (*execute)(void *,void *,void *)=(void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,"teams"); query_ready=1;
            native_name_db.where_int(query,"teamid",0,team);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            if(native_name_db.count(&result)>0) {
                const char *name=native_name_db.string(&result,0,"teamname");
                if(name && name[0]) {
                    lstrcpynA(out,name,(int)size);
                    found=out[0]!=0;
                    if(found && native_team_name_cache_count<
                        sizeof(native_team_name_cache)/sizeof(native_team_name_cache[0])) {
                        NativeTeamNameCache *entry=
                            native_team_name_cache+native_team_name_cache_count++;
                        entry->team=team;
                        lstrcpynA(entry->text,out,sizeof(entry->text));
                    }
                }
            }
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { found=0; out[0]=0; }
    return found;
}
static void native_player_label(int player,char *out,size_t size) {
    size_t i; int keys[4]={0};
    if(!size) return; out[0]=0;
    for(i=0;i<native_name_cache_count;++i) if(native_name_cache[i].player==player) {
        lstrcpynA(out,native_name_cache[i].text,(int)size);return;
    }
    /* Edited/generated names take priority, including unsaved edits. */
    native_name_query(player,1,out,size,keys);
    if(!out[0] && native_name_query(player,0,out,size,keys)) {
        for(i=0;i<4 && !out[0];++i) if(keys[i]>0) {
            int item[2]={0,keys[i]};
            __try { g_resolve_player_name(item,native_names,out,(int)size); }
            __except(EXCEPTION_EXECUTE_HANDLER) { out[0]=0; }
            out[size-1]=0;
        }
    }
    if(native_name_cache_count<128) {
        NativeNameCache *entry=native_name_cache+native_name_cache_count++;
        entry->player=player;lstrcpynA(entry->text,out,sizeof(entry->text));
    }
}
