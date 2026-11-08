/* Career header presentation only. All queries use the current FIFA service;
 * no database rows, save buffers or existing dashboard definitions change. */
static int native_header_efficiency(int games,int points) {
    if(games<=0 || points<0 || (__int64)points>(__int64)games*3) return -1;
    return (int)((__int64)points*100/((__int64)games*3));
}
static int native_header_prestige_value(int domestic,int international) {
    if(domestic<0 || domestic>20 || international<0 || international>20
        || (domestic==0 && international==0)) return -1;
    /* FIFA club prestige is on a 0..20 scale. Publish tenths of a star. */
    return ((domestic+international)*10+4)/8;
}
static int native_header_prestige(int club) {
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,value=-1,domestic=0,international=0;
    void *backend=NULL;
    if(club<=0) return -1;
    if(native_names && is_readable_range(native_names,sizeof(void *))) backend=*(void **)native_names;
    if(backend && is_readable_range(backend,sizeof(void *)) && native_name_db.query_init
        && native_name_db.where_int && native_name_db.result_init && native_name_db.count
        && native_name_db.integer && native_name_db.result_free && native_name_db.query_free) {
        __try {
            __try {
                void (*execute)(void *,void *,void *)=(void (*)(void *,void *,void *))(*(void ***)backend)[1];
                native_name_db.query_init(query,1,"teams");query_ready=1;
                native_name_db.where_int(query,"teamid",0,club);
                native_name_db.result_init(&result);result_ready=1;execute(backend,query,&result);
                if(native_name_db.count(&result)==1) {
                    domestic=native_name_db.integer(&result,0,"domesticprestige");
                    international=native_name_db.integer(&result,0,"internationalprestige");
                    value=native_header_prestige_value(domestic,international);
                }
            } __finally {
                if(result_ready) native_name_db.result_free(&result);
                if(query_ready) native_name_db.query_free(query);
            }
        } __except(EXCEPTION_EXECUTE_HANDLER) {value=-1;}
    }
    if(value<0) {
        char name[256],image[256];int capacity=0;
        if(native_game_stadium_fallback(club,name,sizeof(name),&capacity,image,sizeof(image),&domestic,&international))
            value=native_header_prestige_value(domestic,international);
    }
    return value;
}
static void publish_header_metrics(void *provider) {
    int efficiency=native_header_efficiency(g_coach_record.games,g_coach_record.points);
    int prestige=native_header_prestige(native_club);
    char value[32];
    publish_int_field(provider,"CAREER_HEADER_CLUB_ID",native_club);
    if(efficiency>=0) snprintf(value,sizeof(value),"%d%%",efficiency);else value[0]=0;
    publish_string_field(provider,"CAREER_HEADER_EFFICIENCY",value);
    if(prestige>=0) snprintf(value,sizeof(value),"%d,%d/5",prestige/10,prestige%10);else value[0]=0;
    publish_string_field(provider,"CAREER_HEADER_PRESTIGE",value);
}
