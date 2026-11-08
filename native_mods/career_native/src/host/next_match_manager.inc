/* Read the manager name from the current in-memory career database. Never
 * edit the manager catalogue: it remains the default for other clubs/modes. */
static int native_manager_career_role(void) {
    int role=-1;
    if(!g_career_context_identity || !is_readable_range(g_career_context_identity,0x190)) return -1;
    __try { memcpy(&role,(unsigned char *)g_career_context_identity+0x18c,sizeof(role)); }
    __except(EXCEPTION_EXECUTE_HANDLER) { role=-1; }
    return role;
}
static int native_career_manager_name(int club,char *out,size_t size) {
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,found=0;
    void *backend;
    char first[128],last[128];const char *text;
    if(!out || !size) return 0;
    out[0]=0;first[0]=last[0]=0;
    if(club<=0 || club!=native_club || native_manager_career_role()!=1 || !native_names
        || !native_name_db.query_init || !native_name_db.where_int || !native_name_db.result_init
        || !native_name_db.count || !native_name_db.string || !native_name_db.result_free
        || !native_name_db.query_free || !is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=(void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,"career_users");query_ready=1;
            native_name_db.where_int(query,"clubteamid",0,club);
            native_name_db.result_init(&result);result_ready=1;execute(backend,query,&result);
            if(native_name_db.count(&result)==1) {
                text=native_name_db.string(&result,0,"firstname");if(text) lstrcpynA(first,text,sizeof(first));
                text=native_name_db.string(&result,0,"surname");if(text) lstrcpynA(last,text,sizeof(last));
                native_trim_token(first);native_trim_token(last);
                snprintf(out,size,"%s%s%s",first,first[0]&&last[0]?" ":"",last);
                found=out[0]!=0;
            }
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {out[0]=0;found=0;}
    return found;
}
static int native_next_match_manager_name(int team,char *out,size_t size) {
    if(team==native_club && native_manager_career_role()==1)
        return native_career_manager_name(team,out,size);
    return native_game_manager_fallback(team,out,size);
}
