/* Internal UI adapter. Included after the original field publishers.
 * The game's providers still build and order the original standings/scorers.
 * No game object is retained beyond its provider callback. */
static FceLiveSnapshot *native_snapshot;
static void *native_ui_asset_owner;
static FceModel native_view;
static unsigned long native_epoch;
static unsigned long native_generation(void) { return native_epoch; }
static int native_requested_competition;
static void *native_names;
static int native_date_source;
static GetServiceDescriptorFn native_calendar_descriptor;
typedef struct NativeTrophySummary {
    int available;
    int league_titles;
    int domestic_titles;
    int continental_titles;
    int trophy_count;
    int history_count;
    int history_league_ids[64];
    int history_league_titles[64];
} NativeTrophySummary;
static NativeTrophySummary g_trophy_summary;
typedef struct NativeCompetitionStatSummary {
    int root;
    int logo;
    int title_asset;
    int goals;
    int assists;
    char title_key[64];
} NativeCompetitionStatSummary;
static NativeCompetitionStatSummary g_competition_stat_rows[8];
static SIZE_T g_competition_stat_count;
static RankedPlayer g_club_overall_rows[5];
static SIZE_T g_club_overall_count;
static RankedPlayer g_club_oldest_rows[5];
static SIZE_T g_club_oldest_count;
static RankedPlayer g_club_minutes_rows[5];
static SIZE_T g_club_minutes_count;
static FceFixture g_next_match_fixture;
static int g_next_match_fixture_valid;
static int g_next_match_date_fallback;
static int g_next_match_selection_result = FCE_UNKNOWN;

#define NATIVE_STARTING_XI_CAPACITY 11
typedef struct NativeStartingXI
{
    int players[NATIVE_STARTING_XI_CAPACITY];
    char names[NATIVE_STARTING_XI_CAPACITY][128];
    int overall[NATIVE_STARTING_XI_CAPACITY];
    int condition[NATIVE_STARTING_XI_CAPACITY];
    SIZE_T count;
    int source;
} NativeStartingXI;
static NativeStartingXI g_starting_xi;
#include "../catalogs/native_names.inc"

static int native_squad_leap_year(int year) {
    return (year%4==0 && (year%100!=0 || year%400==0));
}

static int native_squad_days_in_month(int year,int month) {
    static const int days[12]={31,28,31,30,31,30,31,31,30,31,30,31};
    if(month<1 || month>12) return 0;
    return days[month-1]+(month==2 && native_squad_leap_year(year));
}

/* FIFA's DBOFIELDTYPE_DATE stores the number of days since 1582-10-14.
 * Convert only the small range used by player birth dates; this keeps the
 * age calculation independent of the Windows locale and system clock. */
static int native_squad_birth_ymd(int raw,int *year,int *month,int *day) {
    int y=1582,m=10,d=14,left=raw;
    if(raw<0 || raw>1048575 || !year || !month || !day) return 0;
    while(left>=146097) { y+=400; left-=146097; }
    while(left>0) {
        ++d; --left;
        if(d>native_squad_days_in_month(y,m)) {
            d=1; ++m;
            if(m>12) { m=1; ++y; }
        }
    }
    *year=y; *month=m; *day=d;
    return 1;
}

static int native_squad_player_age(int birthdate,int today) {
    int birth_year,birth_month,birth_day;
    int today_year,today_month,today_day,age;
    if(!fce_date_valid(today) ||
       !native_squad_birth_ymd(birthdate,&birth_year,&birth_month,&birth_day))
        return -1;
    today_year=today/10000;
    today_month=(today/100)%100;
    today_day=today%100;
    age=today_year-birth_year;
    if(today_month<birth_month ||
       (today_month==birth_month && today_day<birth_day)) --age;
    return age>=0 && age<=100 ? age : -1;
}

static int native_query_player_profile(
    int player,int *birthdate,int *position,int *overall,int *stamina)
{
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,found=0;
    void *backend;
    if(birthdate) *birthdate=0;
    if(position) *position=-1;
    if(overall) *overall=-1;
    if(stamina) *stamina=-1;
    if(!native_names || !native_name_db.query_init || !native_name_db.where_int ||
       !native_name_db.result_init || !native_name_db.count ||
       !native_name_db.integer || !native_name_db.result_free ||
       !native_name_db.query_free || player<=0) return 0;
    if(!is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=
                (void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,"players"); query_ready=1;
            native_name_db.where_int(query,"playerid",0,player);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            if(native_name_db.count(&result)>0) {
                if(birthdate) *birthdate=native_name_db.integer(&result,0,"birthdate");
                if(position) *position=native_name_db.integer(&result,0,"preferredposition1");
                if(overall) *overall=native_name_db.integer(&result,0,"overallrating");
                if(stamina) *stamina=native_name_db.integer(&result,0,"stamina");
                found=1;
            }
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { found=0; }
    return found;
}

static SIZE_T native_query_roster_links(
    const char *table,
    int club,
    int *out,
    SIZE_T capacity,
    int *query_valid)
{
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,ok=0,row_count=0;
    SIZE_T found=0,i,j;
    void *backend;
    if(query_valid) *query_valid=0;
    if(!table || !out || !capacity || !native_names || club<=0 ||
       !native_name_db.query_init || !native_name_db.where_int ||
       !native_name_db.result_init || !native_name_db.count ||
       !native_name_db.integer || !native_name_db.result_free ||
       !native_name_db.query_free) return 0;
    memset(out,0,sizeof(*out)*capacity);
    if(!is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=
                (void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,table); query_ready=1;
            native_name_db.where_int(query,"teamid",0,club);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            row_count=native_name_db.count(&result);
            if(row_count<0) row_count=0;
            if(row_count>512) row_count=512;
            for(i=0;i<(SIZE_T)row_count && found<capacity;++i) {
                int player=native_name_db.integer(&result,(int)i,"playerid");
                if(player<=0) continue;
                for(j=0;j<found && out[j]!=player;++j) {}
                if(j==found) out[found++]=player;
            }
            ok=1;
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { ok=0; found=0; }
    if(query_valid) *query_valid=ok;
    return found;
}

static SIZE_T native_query_starting_xi(int club, int *out, int *source)
{
    int roster_valid=0;
    int roster[100]={0};
    SIZE_T roster_count;
    if(source) *source=0;
    if(!out || club<=0) return 0;
    /* Do not call the undocumented teamsheets table from the hub refresh
     * thread. On some career builds that table is owned by Team Management
     * and querying it while the hub is being created can crash FIFA. The
     * roster-link service is already used successfully by the squad summary;
     * keep this first implementation on that stable service and isolate the
     * future StartingXIDP capture from the dashboard provider. */
    roster_count=native_query_roster_links(
        "teamplayerlinks",club,roster,
        sizeof(roster)/sizeof(roster[0]),&roster_valid);
    if(roster_count==0 && g_roster_club_id==club) {
        SIZE_T i;
        for(i=0;i<g_roster_player_count && roster_count<
            sizeof(roster)/sizeof(roster[0]);++i)
            if(g_roster_player_ids[i]>0)
                roster[roster_count++]=g_roster_player_ids[i];
        roster_valid=roster_count>0;
    }
    if(roster_count>NATIVE_STARTING_XI_CAPACITY)
        roster_count=NATIVE_STARTING_XI_CAPACITY;
    if(roster_count>0) {
        memcpy(out,roster,sizeof(int)*roster_count);
        if(source) *source=roster_valid?3:0;
    }
    return roster_count;
}

static void native_starting_xi_refresh(void)
{
    SIZE_T i;
    memset(&g_starting_xi,0,sizeof(g_starting_xi));
    if(native_club<=0 || !native_names) return;
    g_starting_xi.count=native_query_starting_xi(
        native_club,g_starting_xi.players,&g_starting_xi.source);
    if(g_starting_xi.count>NATIVE_STARTING_XI_CAPACITY)
        g_starting_xi.count=NATIVE_STARTING_XI_CAPACITY;
    for(i=0;i<g_starting_xi.count;++i) {
        int birthdate=0,position=-1,overall=-1,stamina=-1;
        native_player_label(
            g_starting_xi.players[i],g_starting_xi.names[i],
            sizeof(g_starting_xi.names[i]));
        if(native_query_player_profile(g_starting_xi.players[i],&birthdate,
            &position,&overall,&stamina)) {
            g_starting_xi.overall[i]=overall;
            g_starting_xi.condition[i]=stamina;
        }
    }
}

static void native_squad_refresh(void) {
    int players[100],query_valid=0,age_sum=0,overall_sum=0,position;
    SIZE_T count=0,i,j;
    int today=native_view.date;
    memset(&g_squad_summary,0,sizeof(g_squad_summary));
    if(native_club<=0) return;
    count=native_query_roster_links("teamplayerlinks",native_club,
        players,sizeof(players)/sizeof(players[0]),&query_valid);
    if(count>0) g_squad_summary.source=1;
    /* Contracts capture is retained as a fallback for save variants whose
     * runtime link table is not exposed to the career query service. */
    if(count==0 && g_roster_club_id==native_club) {
        for(i=0;i<g_roster_player_count && count<sizeof(players)/sizeof(players[0]);++i) {
            int player=g_roster_player_ids[i];
            if(player<=0) continue;
            for(j=0;j<count && players[j]!=player;++j) {}
            if(j==count) players[count++]=player;
        }
        if(count>0) g_squad_summary.source=2;
    }
    if(count==0) return;
    g_squad_summary.available=1;
    g_squad_summary.total=(int)count;
    for(i=0;i<count;++i) {
        int birthdate=0,overall=-1;
        position=-1;
        if(!native_query_player_profile(players[i],&birthdate,&position,&overall,NULL)) continue;
        j=(SIZE_T)-1;
        if(position==0) { g_squad_summary.goalkeepers++; j=0; }
        else if(position>=1 && position<=8) { g_squad_summary.defenders++; j=1; }
        else if(position>=9 && position<=19) { g_squad_summary.midfielders++; j=2; }
        else if(position>=20 && position<=31) { g_squad_summary.attackers++; j=3; }
        if(j!=(SIZE_T)-1) ++g_squad_summary.position_count;
        position=native_squad_player_age(birthdate,today);
        if(position>=0) { age_sum+=position; ++g_squad_summary.age_count; }
        if(overall>0) { overall_sum+=overall; ++g_squad_summary.overall_count; }
    }
    if(g_squad_summary.age_count>0)
        g_squad_summary.average_age=(age_sum+g_squad_summary.age_count/2)/g_squad_summary.age_count;
    if(g_squad_summary.overall_count>0)
        g_squad_summary.average_overall=(overall_sum+g_squad_summary.overall_count/2)/
            g_squad_summary.overall_count;
}

static void native_end(void) {
    native_ui_asset_owner=NULL;
    fce_runtime_release(native_snapshot); native_snapshot=NULL;
    memset(&native_view,0,sizeof(native_view)); native_names=NULL;
    native_name_cache_count=0;
}
static void native_context_reset(void) {
    crowd_runtime_disable();
    clear_pending_stats_refresh();
    InterlockedExchange(&g_last_requested_calendar_date, 0);
    native_end();
    memset(g_assist_rows,0,sizeof(g_assist_rows)); g_assist_count=0;
    memset(g_club_goal_rows,0,sizeof(g_club_goal_rows)); g_club_goal_count=0;
    memset(g_club_assist_rows,0,sizeof(g_club_assist_rows)); g_club_assist_count=0;
    memset(g_upcoming_rows,0,sizeof(g_upcoming_rows)); g_upcoming_count=0;
    g_next_match_date_fallback=0;
    g_next_match_selection_result=FCE_UNKNOWN;
    memset(g_club_previous_rows,0,sizeof(g_club_previous_rows)); g_club_previous_count=0;
    memset(g_round_previous_rows,0,sizeof(g_round_previous_rows)); g_round_previous_count=0;
    memset(g_round_next_rows,0,sizeof(g_round_next_rows)); g_round_next_count=0;
    memset(g_standing_rows,0,sizeof(g_standing_rows));
    memset(g_standing_logos,0,sizeof(g_standing_logos));
    memset(g_form_matches,0,sizeof(g_form_matches)); g_form_match_count=0;
    memset(g_competition_rows,0,sizeof(g_competition_rows)); g_competition_count=0;
    memset(g_competition_league_rows,0,sizeof(g_competition_league_rows));
    memset(g_competition_tab_rows,0,sizeof(g_competition_tab_rows));
    memset(g_competition_tab_row_counts,0,sizeof(g_competition_tab_row_counts));
    memset(g_competition_tab_knockout,0,sizeof(g_competition_tab_knockout));
    memset(g_competition_tab_knockout_history,0,sizeof(g_competition_tab_knockout_history));
    memset(g_competition_tab_knockout_history_counts,0,sizeof(g_competition_tab_knockout_history_counts));
    memset(&g_coach_record,0,sizeof(g_coach_record));
    memset(&g_trophy_summary,0,sizeof(g_trophy_summary));
    memset(g_competition_stat_rows,0,sizeof(g_competition_stat_rows));
    g_competition_stat_count=0;
     memset(&g_squad_summary,0,sizeof(g_squad_summary));
     memset(g_club_overall_rows,0,sizeof(g_club_overall_rows)); g_club_overall_count=0;
     memset(g_club_oldest_rows,0,sizeof(g_club_oldest_rows)); g_club_oldest_count=0;
     memset(g_club_minutes_rows,0,sizeof(g_club_minutes_rows)); g_club_minutes_count=0;
     memset(&g_starting_xi,0,sizeof(g_starting_xi));
     g_injury_count=0; g_injury_club_id=0;
    memset(g_injury_rows,0,sizeof(g_injury_rows));
    memset(&g_injury_current,0,sizeof(g_injury_current));
    g_injury_capture_provider=NULL; g_injury_last_tick=0;
    g_injury_current_committed=FALSE;
    InterlockedExchange(&g_injury_refresh_busy,0);
    g_injury_snapshot_loaded_club=0;
    InterlockedExchange(&g_standing_competition_id,0);
    InterlockedExchange(&g_display_competition_id,0);
    native_epoch=0; native_club=0; native_requested_competition=0;
}
static int native_league_logo_asset_exists(int asset);

static int native_logo(int object) {
    FceCompetition competition;int asset;
    if(fce_resolve_competition(native_view.nodes,native_view.node_count,object,&competition)==FCE_OK){
        if(competition.asset>0)return career_competition_icon_from_live_asset(competition.asset);
        return career_competition_icon_from_live_asset(career_ui_competition_asset(competition.competition,native_ui_asset_owner));
    }
    /* Do not reinterpret an old career object as an installed competition or
     * a league artwork ID. The CRTR registry is the only temporary-root path. */
    asset=career_ui_competition_asset(object,native_ui_asset_owner);
    return career_competition_icon_from_live_asset(asset);
}

/* Pre-season fixtures can be backed by a temporary competition object which
 * is not present in the compact FCE competition index.  A resolved root is
 * still preferred, but the fixture object is a safe local root when the
 * fixture itself proves that the managed club participates in it. */
static int native_fixture_root(const FceFixture *fixture) {
    int root;
    if(!fixture || fixture->competition_object<=0) return 0;
    root=fce_model_ancestor(&native_view,fixture->competition_object,3);
    return root>0?root:fixture->competition_object;
}

static int native_fixture_stage_matches(const FceFixture *fixture,int stage) {
    if(!fixture || stage<0) return 0;
    if(stage==0 || fixture->stage<=0) return 1;
    return fixture->stage==stage || fixture->competition_object==stage;
}

static int native_fixture_object_for_club(int object,int club) {
    size_t i;
    if(object<=0 || club<=0) return 0;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *fixture=native_view.fixtures+i;
        if(fixture->competition_object==object &&
           (fixture->home==club || fixture->away==club)) return 1;
    }
    return 0;
}

static int native_history_league_logo(int league_id) {
    return career_competition_icon_from_live_asset(league_id);
}
static int native_root_contains_club(int root,int club) {
    size_t i;
    if(root<0 || club<=0) return 0;
    for(i=0;i<native_view.standing_count;++i)
        if(native_view.standings[i].team==club &&
           fce_model_ancestor(&native_view,native_view.standings[i].competition_object,3)==root)
            return 1;
    return 0;
}
static int native_root_profile(int root,int club,int *overlap) {
    int teams[64],count=0,matched=0; size_t i,j;
    if(overlap) *overlap=0;
    if(root<0) return 0;
    for(i=0;i<native_view.standing_count;++i) {
        const FceStanding *s=native_view.standings+i;
        if(s->team<=0 || fce_model_ancestor(&native_view,s->competition_object,3)!=root) continue;
        for(j=0;j<(size_t)count;++j) if(teams[j]==s->team) break;
        if(j==(size_t)count && count<(int)(sizeof(teams)/sizeof(teams[0]))) teams[count++]=s->team;
    }
    for(i=0;i<20;++i) {
        int team=g_standing_rows[i].club_id;
        if(team<=0) continue;
        for(j=0;j<(size_t)count;++j) if(teams[j]==team) { ++matched; break; }
    }
    if(club>0) {
        for(j=0;j<(size_t)count;++j) if(teams[j]==club) break;
        if(j==(size_t)count) return 0;
    }
    if(overlap) *overlap=matched;
    return count;
}
static int native_best_competition(int club,int require_overlap) {
    int best=-1,best_overlap=-1,best_teams=-1; size_t i;
    for(i=0;i<native_view.node_count;++i) {
        const FceCompNode *n=native_view.nodes+i; int overlap=0,teams;
        if(n->type!=3) continue;
        teams=native_root_profile(n->id,club,&overlap);
        if(!teams || (require_overlap && overlap<2)) continue;
        if(overlap>best_overlap || (overlap==best_overlap && teams>best_teams)) {
            best=n->id;best_overlap=overlap;best_teams=teams;
        }
    }
    return best;
}
static int native_competition_from_asset(int asset,int club,int hint) {
    int hinted=fce_model_ancestor(&native_view,hint,3),best=-1,best_overlap=-1,best_teams=-1;
    size_t i;
    if(asset<=0) return -1;
    for(i=0;i<native_view.node_count;++i) {
        const FceCompNode *n=native_view.nodes+i; int overlap=0,teams;
        if(n->type!=3 || n->asset!=asset) continue;
        teams=native_root_profile(n->id,club,&overlap); if(!teams) continue;
        if(n->id==hinted) return n->id;
        if(overlap>best_overlap || (overlap==best_overlap && teams>best_teams)) {
            best=n->id;best_overlap=overlap;best_teams=teams;
        }
    }
    return best;
}
static int native_display_context_competition(int requested,int club) {
    int requested_root=fce_model_ancestor(&native_view,requested,3);
    int standing=(int)InterlockedCompareExchange(&g_standing_competition_id,0,0);
    int standing_root=fce_model_ancestor(&native_view,standing,3);
    int inferred=native_best_competition(club,1);
    int inferred_overlap=0,requested_overlap=0;
    int inferred_teams=native_root_profile(inferred,club,&inferred_overlap);
    int requested_teams=native_root_profile(requested_root,club,&requested_overlap);
    int prefer_inferred=inferred>0 && inferred!=requested_root &&
        inferred_overlap>=10 && inferred_teams>=10 &&
        requested_teams>0 && requested_teams<10;
    /* The Statistics/Standings provider field is the screen's live request.
     * Prefer it whenever the current FCE snapshot confirms participation.
     * The exception is a small transient cup query while FIFA has already
     * built a complete league table (10+ matching visible rows). */
    if(requested_root>0 && native_root_contains_club(requested_root,club) && !prefer_inferred)
        return requested_root;
    if(g_standing_knockout_mode && requested_root>0 && native_root_contains_club(requested_root,club))
        return requested_root;
    if(prefer_inferred) return inferred;
    if(standing_root>0 && native_root_contains_club(standing_root,club)) return standing_root;
    if(inferred>0) return inferred;
    return native_best_competition(club,0);
}
static void native_team_name(int team,char *out,size_t size) {
    unsigned char result[256]={0};
    if(!size) return; out[0]=0;
    __try {
        if(native_names && team>0) g_resolve_team(native_names,team,result);
        result[0x63]=0;
        if(result[4] && result[4]!='#') lstrcpynA(out,(const char *)result+4,(int)size);
    } __except(EXCEPTION_EXECUTE_HANDLER) { out[0]=0; }
    if(!out[0]) native_team_name_query(team,out,size);
}
static void native_player(const FceStat *s,FceStatSort field,RankedPlayer *out) {
    memset(out,0,sizeof(*out)); out->head=s->player; out->logo=s->team;
    out->value=field==FCE_SORT_ASSISTS?s->assists:s->goals;
    native_player_label(s->player,out->name,sizeof(out->name));
    if(!out->name[0]) snprintf(out->name,sizeof(out->name),"#%d",s->player);
}
static void native_fixture(const FceFixture *f,FixtureRow *out) {
    memset(out,0,sizeof(*out));
    out->home_logo=f->home; out->away_logo=f->away;
    out->competition_id=f->competition_object; out->stage_id=f->stage;
    fce_format_date(f->date_raw,out->date,sizeof(out->date));
    fce_format_time(f->time_raw,out->time,sizeof(out->time));
    native_team_name(f->home,out->home,sizeof(out->home));
    native_team_name(f->away,out->away,sizeof(out->away));
    if(f->played_raw) snprintf(out->score,sizeof(out->score),"%d-%d",f->home_score,f->away_score);
    else lstrcpynA(out->score,"-",sizeof(out->score));
}
static void native_fsw_settings_path(char *out,size_t size) {
    if(!out || !size) return;
    snprintf(out,size,"%s\\FSW\\settings.ini",g_game_dir);
}
static int native_ini_integer_token(const char *value) {
    const unsigned char *p=(const unsigned char *)value;
    if(!p || !*p) return 0;
    while(*p) { if(*p<'0' || *p>'9') return 0; ++p; }
    return 1;
}
static void native_trim_token(char *value) {
    char *start=value,*end;
    if(!value) return;
    while(*start==' ' || *start=='\t') ++start;
    if(start!=value) memmove(value,start,strlen(start)+1);
    end=value+strlen(value);
    while(end>value && (end[-1]==' ' || end[-1]=='\t')) --end;
    *end=0;
}
static void native_stadium_text(const char *source,char *out,size_t size,int strip_location) {
    char text[1024];
    wchar_t wide[512];
    char *p,*last=NULL,*previous=NULL;
    size_t length;
    int count;
    if(!out || !size) return;
    out[0]=0;
    if(!source || !source[0]) return;
    /* The native text fields consume UTF-8. FSW packs also exist in Windows
     * 1252; convert those without double-encoding an already UTF-8 name. */
    count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,source,-1,wide,512);
    if(!count) count=MultiByteToWideChar(1252,0,source,-1,wide,512);
    if(!count || !WideCharToMultiByte(CP_UTF8,0,wide,-1,text,sizeof(text),NULL,NULL)) return;
    if(strip_location) {
        /* Scoreboard names end in city + state/country. Keep stadium aliases
         * such as "Santa Cruz - Arena NicNet", removing only the last two
         * location components. Both separators occur in the installed FSW. */
        for(p=text;*p;++p) {
            if(!strncmp(p," - ",3) || !strncmp(p," \xE2\x80\x93 ",5) ||
               !strncmp(p," \xE2\x80\x94 ",5)) { previous=last; last=p; }
        }
        if(previous) *previous=0;
    }
    native_trim_token(text);
    length=strlen(text);
    if(length>=size) {
        length=size-1;
        // Never cut an accented character in the middle of its UTF-8 bytes.
        while(length && ((unsigned char)text[length]&0xC0)==0x80) --length;
    }
    memcpy(out,text,length); out[length]=0;
}
static int native_stadium_display_name(const char *config_name,char *out,size_t size) {
    char path[MAX_PATH],display[256],key[256];
    size_t key_length;
    if(!config_name || !config_name[0] || !out || !size) return 0;
    native_fsw_settings_path(path,sizeof(path));
    lstrcpynA(key,config_name,(int)sizeof(key));
    native_trim_token(key);
    display[0]=0;
    GetPrivateProfileStringA("scoreboardstdname",key,"",display,
        (DWORD)sizeof(display),path);
    /* A few [comp] pool lines omit the comma before their trailing numeric
     * parameters (e.g. a stadium key ending in "Brasil5,3,0"). If the full
     * key is unknown, remove only trailing digits until a real display-name
     * mapping is found. Exact keys always win, including stadiums named with
     * a number. */
    key_length=strlen(key);
    while(!display[0] && key_length>0 && key[key_length-1]>='0' && key[key_length-1]<='9') {
        key[--key_length]=0;
        GetPrivateProfileStringA("scoreboardstdname",key,"",display,
            (DWORD)sizeof(display),path);
    }
    if(display[0]) {
        char *comma=strchr(display,',');
        if(comma) *comma=0;
        native_trim_token(display);
        if(display[0]) { native_stadium_text(display,out,size,1); return out[0]!=0; }
    }
    native_stadium_text(config_name,out,size,0);
    return out[0]!=0;
}
static int native_stadium_location(const char *config_name,char *out,size_t size) {
    char path[MAX_PATH],display[256],key[256],*comma;size_t key_length;
    if(!config_name||!config_name[0]||!out||!size)return 0;out[0]=0;
    native_fsw_settings_path(path,sizeof(path));lstrcpynA(key,config_name,(int)sizeof(key));native_trim_token(key);
    GetPrivateProfileStringA("scoreboardstdname",key,"",display,(DWORD)sizeof(display),path);
    key_length=strlen(key);
    while(!display[0]&&key_length>0&&key[key_length-1]>='0'&&key[key_length-1]<='9') {
        key[--key_length]=0;GetPrivateProfileStringA("scoreboardstdname",key,"",display,(DWORD)sizeof(display),path);
    }
    comma=strchr(display,',');if(!comma)return 0;++comma;native_trim_token(comma);
    if(!comma[0])return 0;lstrcpynA(out,comma,(int)size);return out[0]!=0;
}
static int native_competition_stadiums(int competition_id,char *out,size_t size,
    char *label,size_t label_size,char *detail,size_t detail_size) {
    char path[MAX_PATH],key[24],pool[3072];
    char *cursor,*comma;
    char names[8][192];
    int count=0,total=0;
    if(!out || !size || competition_id<=0) return 0;
    out[0]=0; pool[0]=0;
    native_fsw_settings_path(path,sizeof(path));
    snprintf(key,sizeof(key),"%d",competition_id);
    GetPrivateProfileStringA("comp",key,"",pool,(DWORD)sizeof(pool),path);
    if(!pool[0]) return 0;
    cursor=pool;
    while(cursor && *cursor) {
        char config_name[192],display[192];
        comma=strchr(cursor,',');
        if(comma) { *comma=0; }
        lstrcpynA(config_name,cursor,(int)sizeof(config_name));
        native_trim_token(config_name);
        if(!config_name[0] || native_ini_integer_token(config_name)) break;
        ++total;
        if(count<(int)(sizeof(names)/sizeof(names[0])) &&
           native_stadium_display_name(config_name,display,sizeof(display))) {
            lstrcpynA(names[count],display,(int)sizeof(names[count]));
            ++count;
        }
        if(!comma) break;
        cursor=comma+1;
    }
    if(!total || !count) return 0;
    if(total==1) {
        lstrcpynA(out,names[0],(int)size);
        if(label && label_size) lstrcpynA(label,"ESTADIO DA COMPETICAO",(int)label_size);
        if(detail && detail_size) detail[0]=0;
        return 1;
    }
    if(count>=2)
        snprintf(out,size,"%s - %s%s",names[0],names[1],
            total>2?" + outras opcoes":"");
    else
        snprintf(out,size,"%s + %d opcoes",names[0],total-1);
    if(label && label_size) lstrcpynA(label,"ESTADIOS POSSIVEIS",(int)label_size);
    if(detail && detail_size)
        lstrcpynA(detail,"O FSW seleciona o local ao iniciar a partida.",(int)detail_size);
    return 1;
}
static int native_team_stadium(int team_id,char *out,size_t size,
    char *label,size_t label_size,char *detail,size_t detail_size) {
    char path[MAX_PATH],key[24],mapping[512],*comma;
    if(!out || !size || team_id<=0) return 0;
    out[0]=0; mapping[0]=0;
    native_fsw_settings_path(path,sizeof(path));
    snprintf(key,sizeof(key),"%d",team_id);
    GetPrivateProfileStringA("stadium",key,"",mapping,(DWORD)sizeof(mapping),path);
    if(!mapping[0]) return 0;
    comma=strchr(mapping,','); if(comma) *comma=0;
    native_trim_token(mapping);
    if(!native_stadium_display_name(mapping,out,size)) return 0;
    if(label && label_size) lstrcpynA(label,"ESTADIO DO MANDANTE",(int)label_size);
    if(detail && detail_size) detail[0]=0;
    return 1;
}
static int native_competition_stadium_config(int competition_id,
    char *out,size_t size) {
    char path[MAX_PATH],key[24],pool[3072],*comma;
    if(!out || !size || competition_id<=0) return 0;
    out[0]=0; pool[0]=0;
    native_fsw_settings_path(path,sizeof(path));
    snprintf(key,sizeof(key),"%d",competition_id);
    GetPrivateProfileStringA("comp",key,"",pool,(DWORD)sizeof(pool),path);
    if(!pool[0]) return 0;
    comma=strchr(pool,','); if(comma) *comma=0;
    native_trim_token(pool);
    if(!pool[0] || native_ini_integer_token(pool)) return 0;
    lstrcpynA(out,pool,(int)size);
    return out[0]!=0;
}
static int native_team_stadium_config(int team_id,char *out,size_t size) {
    char path[MAX_PATH],key[24],mapping[512],*comma;
    if(!out || !size || team_id<=0) return 0;
    out[0]=0; mapping[0]=0;
    native_fsw_settings_path(path,sizeof(path));
    snprintf(key,sizeof(key),"%d",team_id);
    GetPrivateProfileStringA("stadium",key,"",mapping,
        (DWORD)sizeof(mapping),path);
    if(!mapping[0]) return 0;
    comma=strchr(mapping,','); if(comma) *comma=0;
    native_trim_token(mapping);
    lstrcpynA(out,mapping,(int)size);
    return out[0]!=0;
}
static int native_next_match_stadium_config(const FceFixture *fixture,
    int competition_id,char *out,size_t size) {
    if(!fixture || !out || !size) return 0;
    /* Keep the same precedence as the text provider. For a multi-venue
     * competition the first entry is only a representative thumbnail. */
    if(native_competition_stadium_config(competition_id,out,size)) return 1;
    return native_team_stadium_config(fixture->home,out,size);
}
static void native_stadium_log_image_lookup(const char *key,const char *result,
    const char *source,const char *destination) {
    char path[MAX_PATH];
    FILE *log;
    if(!fce_runtime_log_verbose() || !g_mod_dir[0]) return;
    if(snprintf(path,sizeof(path),"%s\\logs\\career_stadium_images.log",g_mod_dir)<0)
        return;
    log=fopen(path,"ab");
    if(!log) return;
    fprintf(log,"stadium_image pid=%lu key=%s result=%s source=%s target=%s\n",
        GetCurrentProcessId(),key?key:"",result?result:"",source?source:"",
        destination?destination:"");
    fclose(log);
}
static int native_stadium_image_key(const char *config_name,
    char *out,size_t size) {
    char candidate[256],original[256],source[MAX_PATH],destination[MAX_PATH];
    char destination_dir[MAX_PATH],art_directory[MAX_PATH],asset[40],package[MAX_PATH];
    size_t length;
    int written,sync_result;
    size_t extension;
    static const char *extensions[]={"dds","jpg","jpeg","png","bmp"};
    DWORD attributes;
    if(!config_name || !config_name[0] || !out || !size || !g_game_dir[0])
        return 0;
    out[0]=0;
    lstrcpynA(candidate,config_name,(int)sizeof(candidate));
    native_trim_token(candidate);
    if(!candidate[0] || !strcmp(candidate,".") || !strcmp(candidate,"..") ||
       strchr(candidate,'\\') || strchr(candidate,'/') || strchr(candidate,':'))
        return 0;
    lstrcpynA(original,candidate,(int)sizeof(original));
    written=snprintf(destination_dir,sizeof(destination_dir),
        "%s\\data\\ui\\imgAssets\\stadium",g_game_dir);
    if(written<0 || written>=(int)sizeof(destination_dir)) return 0;
    written=snprintf(art_directory,sizeof(art_directory),
        "%s\\data\\ui\\artAssets\\stadium",g_game_dir);
    if(written<0 || written>=(int)sizeof(art_directory)) return 0;
    attributes=GetFileAttributesA(destination_dir);
    if(attributes==INVALID_FILE_ATTRIBUTES) {
        if(!CreateDirectoryA(destination_dir,NULL) &&
           GetLastError()!=ERROR_ALREADY_EXISTS) return 0;
    } else if(!(attributes&FILE_ATTRIBUTE_DIRECTORY)) return 0;
    length=strlen(candidate);
    /* Built-in DB venues already have a native APT movie. Use that key
     * directly, without requiring a StadiumGBD thumbnail. */
    if(native_ini_integer_token(candidate) &&
       stadium_thumbnail_native(art_directory,atoi(candidate),asset,sizeof(asset))){
        if(strlen(asset)>=size)return 0;
        lstrcpynA(out,asset,(int)size);
        native_stadium_log_image_lookup(original,"native-movie",art_directory,asset);
        return 1;
    }
    while(candidate[0] && length>0) {
        written=snprintf(destination,sizeof(destination),
            "%s\\stadium_%s.dds",destination_dir,candidate);
        if(written<0 || written>=(int)sizeof(destination)) return 0;
        for(extension=0;extension<sizeof(extensions)/sizeof(extensions[0]);++extension) {
            written=snprintf(source,sizeof(source),
                "%s\\StadiumGBD\\render\\thumbnail\\stadium\\%s.%s",
                g_game_dir,candidate,extensions[extension]);
            if(written<0 || written>=(int)sizeof(source)) return 0;
            sync_result=stadium_thumbnail_sync(source,destination);
            if(sync_result) {
                int package_result=stadium_thumbnail_package(destination,art_directory,asset,sizeof(asset));
                if(!package_result) {
                    native_stadium_log_image_lookup(original,"package-failed",source,destination);
                    return 0;
                }
                native_stadium_log_image_lookup(original,
                    sync_result==STADIUM_IMAGE_CONVERTED?"converted":
                    sync_result==STADIUM_IMAGE_COPIED?"copied":"current",source,destination);
                written=snprintf(package,sizeof(package),"%s\\stadium_%s.big",art_directory,asset);
                if(written<0 || written>=(int)sizeof(package)) return 0;
                native_stadium_log_image_lookup(original,"movie-ready",destination,package);
                if(strlen(asset)>=size) return 0;
                lstrcpynA(out,asset,(int)size);
                return out[0]!=0;
            }
        }
        /* FSW sometimes appends render digits to a key without a comma. */
        if(candidate[length-1]<'0' || candidate[length-1]>'9') break;
        candidate[--length]=0;
        native_trim_token(candidate);
    }
    native_stadium_log_image_lookup(original,"missing",source,destination);
    return 0;
}

/* The career database keeps the authoritative team->stadium link, while
 * FSW/settings.ini is only an optional visual override.  The fallback file is
 * generated from fifa_ng_db.db at build time and is read as plain data here;
 * this avoids calling the live career DB service from the card refresh path. */
static int native_game_stadium_fallback(int team_id,char *name,size_t name_size,
    int *capacity,char *image,size_t image_size,int *domestic,int *international) {
    char path[MAX_PATH],line[768];
    FILE *file;
    if(name && name_size) name[0]=0;
    if(image && image_size) image[0]=0;
    if(capacity) *capacity=0;
    if(domestic) *domestic=0;
    if(international) *international=0;
    if(team_id<=0 || !g_mod_dir[0]) return 0;
    career_path_read(path,sizeof(path),g_mod_dir,"data\\catalogs","club_stadium_fallback.tsv");
    file=fopen(path,"rb");
    if(!file) return 0;
    while(fgets(line,sizeof(line),file)) {
        char *field[7],*cursor=line,*separator;
        int count=0,parsed_team;
        while(cursor && count<(int)(sizeof(field)/sizeof(field[0]))) {
            field[count++]=cursor;
            separator=strchr(cursor,'|');
            if(!separator) { cursor=NULL; break; }
            *separator=0; cursor=separator+1;
        }
        if(count<5) continue;
        parsed_team=atoi(field[0]);
        if(parsed_team!=team_id) continue;
        if(name && name_size) native_stadium_text(field[3],name,name_size,0);
        if(image && image_size) lstrcpynA(image,field[4],(int)image_size);
        if(image && image_size && !image[0] && atoi(field[1])>0)
            snprintf(image,image_size,"%d",atoi(field[1]));
        if(capacity) *capacity=atoi(field[2]);
        if(domestic && count>5) *domestic=atoi(field[5]);
        if(international && count>6) *international=atoi(field[6]);
        fclose(file);
        return 1;
    }
    fclose(file);
    return 0;
}
#define NATIVE_REPUTATION_ASSET_BASE 9900
static int native_reputation_star_count(int domestic,int international) {
    int average,stars;
    if(domestic<=0 && international<=0) return 0;
    average=(domestic+international+1)/2;
    stars=(average+4)/5;
    if(stars<1) stars=1;
    if(stars>5) stars=5;
    return stars;
}
static int native_game_manager_fallback(int team_id,char *name,size_t size) {
    char path[MAX_PATH],line[512],*separator;
    FILE *file;
    int parsed_team;
    if(name && size) name[0]=0;
    if(team_id<=0 || !name || !size || !g_mod_dir[0]) return 0;
    career_path_read(path,sizeof(path),g_mod_dir,"data\\catalogs","club_manager_fallback.tsv");
    file=fopen(path,"rb");
    if(!file) return 0;
    while(fgets(line,sizeof(line),file)) {
        separator=strchr(line,'|');
        if(!separator) continue;
        *separator=0;
        parsed_team=atoi(line);
        if(parsed_team!=team_id) continue;
        ++separator;
        {
            char *endline=strpbrk(separator,"\r\n");
            if(endline) *endline=0;
        }
        native_trim_token(separator);
        lstrcpynA(name,separator,(int)size);
        fclose(file);
        return name[0]!=0;
    }
    fclose(file);
    return 0;
}
static int native_next_match_stadium(const FceFixture *fixture,int competition_id,
    char *out,size_t size,char *label,size_t label_size,
    char *detail,size_t detail_size) {
    /* FSW's [comp] pool takes precedence over a club's default [stadium]
     * mapping. A pool with multiple venues is shown as possibilities, never
     * as a falsely certain single ground before the match is launched. */
    if(!fixture || !out || !size) return 0;
    if(native_competition_stadiums(competition_id,out,size,label,label_size,
        detail,detail_size)) return 1;
    return native_team_stadium(fixture->home,out,size,label,label_size,
        detail,detail_size);
}
static int native_match_kit_key(int team,int kit_type,char *out,size_t size) {
    char path[MAX_PATH],filename[48];
    if(!out || !size) return 0;
    out[0]=0;
    /* The static availability catalogue can lag behind custom leagues and
     * newly added clubs. The game's thumbnail filename is the authoritative
     * key, so publish a kit whenever that exact image is installed. */
    if(team<=0 || kit_type<0 || kit_type>2) return 0;
    snprintf(filename,sizeof(filename),"%d_%d_0",kit_type,team);
    snprintf(path,sizeof(path),"%s\\data\\ui\\imgAssets\\kits\\j%s.dds",
        g_game_dir,filename);
    if(GetFileAttributesA(path)==INVALID_FILE_ATTRIBUTES) return 0;
    lstrcpynA(out,filename,(int)size);
    return out[0]!=0;
}

static void publish_next_match_card(void *provider) {
    char value[256],date[32],time[16],home_kit[48],away_kit[48];
    char stadium_label[64],stadium_detail[128],stadium_config[256],stadium_image[256];
    char fallback_name[256];
    char fallback_image[256];
    char home_manager[128],away_manager[128];
    int fallback_capacity=0,fallback_domestic=0,fallback_international=0;
    int expected_percent;
    int fallback_ok=0;
    FceCompetition competition;
    int valid=g_next_match_fixture_valid && g_upcoming_count>0;
    int home_crest=FORM_ASSET_EMPTY,away_crest=FORM_ASSET_EMPTY;
    int competition_icon=FORM_ASSET_EMPTY;
    int competition_asset=0,competition_id=0;
    if(!provider) return;
    publish_visibility_field(provider,"MYTEAM_NEXT_STATUS",!valid);
    publish_string_field(provider,"MYTEAM_NEXT_STATUS",valid?"":"CM_PA_NoMatch");
    publish_visibility_field(provider,"MYTEAM_NEXT_STATUS_DETAIL",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_STATUS_DETAIL","");
    publish_visibility_field(provider,"MYTEAM_NEXT_COMP_ICON",FALSE);
    publish_int_field(provider,"MYTEAM_NEXT_COMP_ICON",FORM_ASSET_EMPTY);
    publish_visibility_field(provider,"MYTEAM_NEXT_COMP_TITLE",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_COMP_TITLE","");
    publish_visibility_field(provider,"MYTEAM_NEXT_DATE",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_DATE","");
    publish_visibility_field(provider,"MYTEAM_NEXT_TIME",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_TIME","");
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM","");
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_LABEL","Stadium_mixedcase");
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY_LABEL",FALSE);
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY_LABEL","");
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY","");
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE_LABEL",FALSE);
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE_LABEL","");
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE","");
    publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_IMAGE",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_STADIUM_IMAGE","");
    publish_visibility_field(provider,"MYTEAM_NEXT_INFO_DIVIDER0",FALSE);
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_CREST",FALSE);
    publish_int_field(provider,"MYTEAM_NEXT_HOME_CREST",FORM_ASSET_EMPTY);
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_NAME",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_HOME_NAME","");
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_MANAGER",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_HOME_MANAGER","");
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_KIT",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_HOME_KIT","");
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_CREST",FALSE);
    publish_int_field(provider,"MYTEAM_NEXT_AWAY_CREST",FORM_ASSET_EMPTY);
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_NAME",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_AWAY_NAME","");
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_MANAGER",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_AWAY_MANAGER","");
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_KIT",FALSE);
    publish_string_field(provider,"MYTEAM_NEXT_AWAY_KIT","");
    if(!valid) return;

    native_team_name(g_next_match_fixture.home,value,sizeof(value));
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_NAME",value[0]!=0);
    publish_string_field(provider,"MYTEAM_NEXT_HOME_NAME",value);
    native_team_name(g_next_match_fixture.away,value,sizeof(value));
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_NAME",value[0]!=0);
    publish_string_field(provider,"MYTEAM_NEXT_AWAY_NAME",value);
    home_manager[0]=0; away_manager[0]=0;
    native_game_manager_fallback(g_next_match_fixture.home,home_manager,sizeof(home_manager));
    native_game_manager_fallback(g_next_match_fixture.away,away_manager,sizeof(away_manager));
    if(home_manager[0]) {
        snprintf(value,sizeof(value),"TECNICO: %s",home_manager);
        lstrcpynA(home_manager,value,(int)sizeof(home_manager));
    }
    if(away_manager[0]) {
        snprintf(value,sizeof(value),"TECNICO: %s",away_manager);
        lstrcpynA(away_manager,value,(int)sizeof(away_manager));
    }
    publish_string_field(provider,"MYTEAM_NEXT_HOME_MANAGER",home_manager);
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_MANAGER",home_manager[0]!=0);
    publish_string_field(provider,"MYTEAM_NEXT_AWAY_MANAGER",away_manager);
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_MANAGER",away_manager[0]!=0);
    home_crest=g_next_match_fixture.home>0?g_next_match_fixture.home:FORM_ASSET_EMPTY;
    away_crest=g_next_match_fixture.away>0?g_next_match_fixture.away:FORM_ASSET_EMPTY;
    publish_int_field(provider,"MYTEAM_NEXT_HOME_CREST",home_crest);
    publish_visibility_field(provider,"MYTEAM_NEXT_HOME_CREST",home_crest>0);
    publish_int_field(provider,"MYTEAM_NEXT_AWAY_CREST",away_crest);
    publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_CREST",away_crest>0);

    snprintf(date,sizeof(date),"%02d/%02d/%04d",
        g_next_match_fixture.date_raw%100,
        (g_next_match_fixture.date_raw/100)%100,
        g_next_match_fixture.date_raw/10000);
    publish_string_field(provider,"MYTEAM_NEXT_DATE",date);
    publish_visibility_field(provider,"MYTEAM_NEXT_DATE",date[0]!=0);
    if(fce_format_time(g_next_match_fixture.time_raw,time,sizeof(time))) {
        publish_string_field(provider,"MYTEAM_NEXT_TIME",time);
        publish_visibility_field(provider,"MYTEAM_NEXT_TIME",TRUE);
    }
    if(fce_resolve_competition(native_view.nodes,native_view.node_count,
        g_next_match_fixture.competition_object,&competition)==FCE_OK) {
        competition_id=competition.competition;
        if(competition.asset>0) {
            competition_asset=competition.asset;
            competition_icon=native_logo(g_next_match_fixture.competition_object);
            if(competition_icon>0) {
                publish_int_field(provider,"MYTEAM_NEXT_COMP_ICON",competition_icon);
                publish_visibility_field(provider,"MYTEAM_NEXT_COMP_ICON",TRUE);
            }
            snprintf(value,sizeof(value),"TrophyName_%d",competition_asset);
            publish_string_field(provider,"MYTEAM_NEXT_COMP_TITLE",value);
            publish_visibility_field(provider,"MYTEAM_NEXT_COMP_TITLE",TRUE);
        }
    }
    if(native_match_kit_key(g_next_match_fixture.home,0,home_kit,sizeof(home_kit))) {
        publish_string_field(provider,"MYTEAM_NEXT_HOME_KIT",home_kit);
        publish_visibility_field(provider,"MYTEAM_NEXT_HOME_KIT",TRUE);
    }
    if(native_match_kit_key(g_next_match_fixture.away,1,away_kit,sizeof(away_kit))) {
        publish_string_field(provider,"MYTEAM_NEXT_AWAY_KIT",away_kit);
        publish_visibility_field(provider,"MYTEAM_NEXT_AWAY_KIT",TRUE);
    }
    stadium_label[0]=0; stadium_detail[0]=0;
    stadium_config[0]=0; stadium_image[0]=0;
    fallback_name[0]=0; fallback_image[0]=0;
    /* The fallback is read-only game data. Keep the stadium title resolved by
     * the existing fixture/competition logic; use the club-id row only for
     * the thumbnail when that image exists. This changes the image source
     * without breaking the title publisher. */
    fallback_ok=native_game_stadium_fallback(g_next_match_fixture.home,
        fallback_name,sizeof(fallback_name),&fallback_capacity,
        fallback_image,sizeof(fallback_image),&fallback_domestic,
        &fallback_international);
    /* Capacity comes from the read-only club/stadium fallback table. Keep it
     * separate from the crowd percentage: the first value is the stadium's
     * total capacity, while the second is the expected attendance for this
     * match. */
    if(fallback_ok && fallback_capacity>0) {
        snprintf(value,sizeof(value),"%d",fallback_capacity);
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY_LABEL",
            "Capacity");
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY",value);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY_LABEL",
            TRUE);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_CAPACITY",TRUE);
    }
    expected_percent=crowd_runtime_attendance_percent();
    if(expected_percent>0 && expected_percent<=100) {
        snprintf(value,sizeof(value),"%d%%",expected_percent);
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE_LABEL",
            "Público estimado");
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE",value);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE_LABEL",
            TRUE);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_ATTENDANCE",TRUE);
    }
    if(native_next_match_stadium(&g_next_match_fixture,competition_id,
        value,sizeof(value),stadium_label,sizeof(stadium_label),
        stadium_detail,sizeof(stadium_detail))) {
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM",value);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM",TRUE);
        /* Keep the label short; the value field reserves enough height for a
         * long stadium name to wrap without colliding with attendance data. */
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_LABEL","Stadium_mixedcase");
        if(stadium_detail[0]) {
            publish_string_field(provider,"MYTEAM_NEXT_STATUS_DETAIL",stadium_detail);
            publish_visibility_field(provider,"MYTEAM_NEXT_STATUS_DETAIL",TRUE);
        }
    } else {
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_LABEL","Stadium_mixedcase");
        if(fallback_ok && fallback_name[0]) {
            publish_string_field(provider,"MYTEAM_NEXT_STADIUM",fallback_name);
            publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM",TRUE);
        }
    }
    /* Resolve the picture independently of display-name availability. Use
     * the DB host venue only when FSW has not selected another venue. */
    if(native_next_match_stadium_config(&g_next_match_fixture,competition_id,
        stadium_config,sizeof(stadium_config))) {
        native_stadium_image_key(stadium_config,stadium_image,sizeof(stadium_image));
    } else if(fallback_ok && fallback_image[0]) {
        /* An explicit FSW venue without a photo must not borrow a picture
         * of the club's different default stadium. */
        native_stadium_image_key(fallback_image,stadium_image,sizeof(stadium_image));
    }
    if(stadium_image[0]) {
        publish_string_field(provider,"MYTEAM_NEXT_STADIUM_IMAGE",stadium_image);
        publish_visibility_field(provider,"MYTEAM_NEXT_STADIUM_IMAGE",TRUE);
        publish_visibility_field(provider,"MYTEAM_NEXT_INFO_DIVIDER0",TRUE);
    }
}
static void native_coach_record(int club) {
    size_t i,j;
    memset(&g_coach_record,0,sizeof(g_coach_record));
    if(club<=0) return;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        int scored,conceded;
        if(!f->played_raw || (f->home!=club && f->away!=club)) continue;
        if(fce_date_valid(native_view.date) && f->date_raw>native_view.date) continue;
        if(f->home_score<0 || f->away_score<0) continue;
        /* A few career snapshots expose the same fixture through more than
         * one live service. Count the match once, by its stable fixture id. */
        if(f->id>0) {
            for(j=0;j<i;++j) {
                const FceFixture *previous=native_view.fixtures+j;
                if(previous->id==f->id) break;
            }
            if(j<i) continue;
        }
        if(f->home==club) {
            scored=f->home_score; conceded=f->away_score;
        } else {
            scored=f->away_score; conceded=f->home_score;
        }
        ++g_coach_record.games;
        if(f->home==club) ++g_coach_record.home_games;
        else ++g_coach_record.away_games;
        if(scored>conceded) {
            ++g_coach_record.wins;
            g_coach_record.points+=3;
            if(f->home==club) {
                ++g_coach_record.home_wins;
                g_coach_record.home_points+=3;
            } else {
                ++g_coach_record.away_wins;
                g_coach_record.away_points+=3;
            }
        } else if(scored==conceded) {
            ++g_coach_record.draws;
            ++g_coach_record.points;
            if(f->home==club) ++g_coach_record.home_points;
            else ++g_coach_record.away_points;
        } else {
            ++g_coach_record.losses;
        }
    }
    /* The dashboard percentage is the match win rate. Points efficiency is a
     * different metric and was producing confusing values such as 45% for a
     * 5-4-5 record. Keep the definition aligned with the visible W/D/L row. */
    if(g_coach_record.games>0)
        g_coach_record.percent=(g_coach_record.wins*100)/g_coach_record.games;
    if(g_coach_record.home_games>0)
        g_coach_record.home_percent=(g_coach_record.home_wins*100)/
            g_coach_record.home_games;
    if(g_coach_record.away_games>0)
        g_coach_record.away_percent=(g_coach_record.away_wins*100)/
            g_coach_record.away_games;
}
static SIZE_T native_leaders(int comp,int club,FceStatSort field,RankedPlayer *rows) {
    FceStat leaders[5]; size_t count=0,i;
    memset(rows,0,5*sizeof(*rows));
    if(fce_model_leaders(&native_view,comp,club,field,leaders,5,&count)!=FCE_OK) return 0;
    for(i=0;i<count;++i) native_player(leaders+i,field,rows+i);
    return count;
}
static SIZE_T native_club_career_leaders(int club,FceCareerMetric metric,RankedPlayer *rows) {
    FceStat leaders[5]; size_t count=0,i;
    memset(rows,0,5*sizeof(*rows));
    if(fce_model_career_leaders(&native_view,club,metric,leaders,5,&count)!=FCE_OK) return 0;
    for(i=0;i<count;++i) {
        RankedPlayer *item=rows+i;
        memset(item,0,sizeof(*item));
        item->head=leaders[i].player;item->logo=leaders[i].team;
        switch(metric) {
        case FCE_CAREER_GOALS: item->value=leaders[i].goals;break;
        case FCE_CAREER_ASSISTS: item->value=leaders[i].assists;break;
        case FCE_CAREER_YELLOW_CARDS: item->value=leaders[i].yellow_cards;break;
        case FCE_CAREER_RED_CARDS: item->value=leaders[i].red_cards;break;
        case FCE_CAREER_MINUTES: item->value=leaders[i].minutes;break;
        default: item->value=0;break;
        }
        native_player_label(item->head,item->name,sizeof(item->name));
        if(!item->name[0]) snprintf(item->name,sizeof(item->name),"#%d",item->head);
    }
    return count;
}
static SIZE_T native_club_overall_leaders(int club,RankedPlayer *rows) {
    int roster_ids[100],roster_valid=0;
    SIZE_T count=0,roster_count=0,i,j;
    if(!rows) return 0;
    memset(rows,0,5*sizeof(*rows));
    if(club<=0) return 0;

    /* Use the same live roster source as the Elenco card. The contracts
     * capture can be stale or absent in some career saves, which previously
     * made the Pontuacao Geral page publish no rows even though the squad
     * summary had players available. */
    roster_count=native_query_roster_links("teamplayerlinks",club,roster_ids,
        sizeof(roster_ids)/sizeof(roster_ids[0]),&roster_valid);
    /* A few career saves expose the active squad through the temporary link
     * table during hub refresh. Use it only when the normal table is empty,
     * so the card still sees the complete squad when both are available. */
    if(roster_count==0)
        roster_count=native_query_roster_links("temp_teamplayerlinks",club,
            roster_ids,sizeof(roster_ids)/sizeof(roster_ids[0]),&roster_valid);
    if(roster_count==0 && g_roster_club_id==club) {
        for(i=0;i<g_roster_player_count &&
            roster_count<sizeof(roster_ids)/sizeof(roster_ids[0]);++i) {
            int player=g_roster_player_ids[i];
            if(player<=0) continue;
            for(j=0;j<roster_count && roster_ids[j]!=player;++j) {}
            if(j==roster_count) roster_ids[roster_count++]=player;
        }
    }
    if(roster_count==0) return 0;
    for(i=0;i<roster_count;++i) {
        RankedPlayer candidate;
        int birthdate=0,position=-1,overall=-1;
        memset(&candidate,0,sizeof(candidate));
        if(roster_ids[i]<=0 ||
           !native_query_player_profile(roster_ids[i],&birthdate,
               &position,&overall,NULL) || overall<=0)
            continue;
        candidate.head=roster_ids[i];
        candidate.logo=club;
        candidate.value=overall;
        native_player_label(candidate.head,candidate.name,sizeof(candidate.name));
        if(!candidate.name[0] && g_roster_player_names[i][0])
            lstrcpynA(candidate.name,g_roster_player_names[i],
                (int)sizeof(candidate.name));
        if(!candidate.name[0])
            snprintf(candidate.name,sizeof(candidate.name),"#%d",candidate.head);
        if(count>=5 && candidate.value<=rows[4].value) continue;
        if(count<5) ++count;
        j=count-1;
        while(j>0 && candidate.value>rows[j-1].value) {
            rows[j]=rows[j-1]; --j;
        }
        rows[j]=candidate;
    }
    return count;
}
static SIZE_T native_club_oldest_players(int club,RankedPlayer *rows) {
    int roster_ids[100],roster_valid=0;
    int today=native_view.date;
    SIZE_T count=0,roster_count=0,i,j;
    if(!rows || club<=0) return 0;
    memset(rows,0,5*sizeof(*rows));

    /* Reuse the same live roster source as the Elenco card. This keeps the
     * new carousel page tied to the currently managed club instead of a
     * static global roster. */
    roster_count=native_query_roster_links("teamplayerlinks",club,roster_ids,
        sizeof(roster_ids)/sizeof(roster_ids[0]),&roster_valid);
    /* Keep the oldest-player carousel alive on saves where the active squad
     * is exposed through the temporary link table during a hub refresh. */
    if(roster_count==0)
        roster_count=native_query_roster_links("temp_teamplayerlinks",club,
            roster_ids,sizeof(roster_ids)/sizeof(roster_ids[0]),&roster_valid);
    if(roster_count==0 && g_roster_club_id==club) {
        for(i=0;i<g_roster_player_count &&
            roster_count<sizeof(roster_ids)/sizeof(roster_ids[0]);++i) {
            int player=g_roster_player_ids[i];
            if(player<=0) continue;
            for(j=0;j<roster_count && roster_ids[j]!=player;++j) {}
            if(j==roster_count) roster_ids[roster_count++]=player;
        }
    }
    if(roster_count==0) return 0;
    for(i=0;i<roster_count;++i) {
        RankedPlayer candidate;
        int birthdate=0,position=-1,overall=-1,age;
        memset(&candidate,0,sizeof(candidate));
        if(roster_ids[i]<=0 ||
           !native_query_player_profile(roster_ids[i],&birthdate,
               &position,&overall,NULL)) continue;
        age=native_squad_player_age(birthdate,today);
        if(age<0) continue;
        candidate.head=roster_ids[i];
        candidate.logo=club;
        candidate.value=age;
        native_player_label(candidate.head,candidate.name,sizeof(candidate.name));
        if(!candidate.name[0] && g_roster_player_names[i][0])
            lstrcpynA(candidate.name,g_roster_player_names[i],
                (int)sizeof(candidate.name));
        if(!candidate.name[0])
            snprintf(candidate.name,sizeof(candidate.name),"#%d",candidate.head);

        /* Keep five rows, ordered from oldest to youngest. Player ID makes
         * equal-age ordering deterministic and keeps refreshes stable. */
        if(count>=5 && (candidate.value<rows[4].value ||
           (candidate.value==rows[4].value && candidate.head>=rows[4].head)))
            continue;
        if(count<5) ++count;
        j=count-1;
        while(j>0 && (candidate.value>rows[j-1].value ||
               (candidate.value==rows[j-1].value &&
                candidate.head<rows[j-1].head))) {
            rows[j]=rows[j-1]; --j;
        }
        rows[j]=candidate;
    }
    return count;
}
static int native_calendar_date(void *owner) {
    /* CalendarManager service descriptor RVA 0x44563f0. Its +0x34 date
     * highlights TODAY; +0x4c is the selected day (must NOT be used).
     * Evidence: saved code 0x5be11eb..0x5be1229, ctor 0x44e5590. */
    void *calendar; int date=-1;
    __try {
        calendar=owner_service(owner,native_calendar_descriptor ? native_calendar_descriptor :
            (GetServiceDescriptorFn)(g_module_base+0x44563f0),NULL);
        if(calendar) {
            int *p=(int *)((unsigned char *)calendar+0x34);
            date=fce_date_pack(p[0],p[1],p[2]);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { date=-1; }
    return date;
}

static int native_read_active_save_path(char *path, size_t capacity)
{
    char bridge[MAX_PATH];
    char line[1200];
    FILE *file;
    if (!path || !capacity || !g_mod_dir[0])
        return 0;
    path[0] = '\0';
    snprintf(bridge, sizeof(bridge), "%s\\runtime\\career_save_source.tsv",
        g_mod_dir);
    file = fopen(bridge, "rb");
    if (!file) {
        snprintf(bridge, sizeof(bridge), "%s\\runtime\\career_active_save.tsv",
            g_mod_dir);
        file = fopen(bridge, "rb");
    }
    if (!file)
        return 0;
    while (fgets(line, sizeof(line), file)) {
        char *value;
        size_t length;
        if (strncmp(line, "path=", 5) != 0)
            continue;
        value = line + 5;
        length = strcspn(value, "\r\n");
        if (!length || length >= capacity)
            break;
        memcpy(path, value, length);
        path[length] = '\0';
        fclose(file);
        if (!is_fifa_save_data_path(path)) {
            path[0] = '\0';
            return 0;
        }
        return 1;
    }
    fclose(file);
    return 0;
}

static unsigned long native_fce_snapshot_generation;
static unsigned long long native_fce_snapshot_size;
static unsigned long long native_fce_snapshot_write_time;
static unsigned long long native_fce_snapshot_fingerprint;
static unsigned long long native_fce_hash_value(unsigned long long hash,
    unsigned int value)
{
    int byte;
    for (byte = 0; byte < 4; ++byte) {
        hash ^= (unsigned char)(value >> (byte * 8));
        hash *= 1099511628211ULL;
    }
    return hash;
}
static unsigned long long native_fce_model_fingerprint(const FceModel *model)
{
    unsigned long long hash = 1469598103934665603ULL;
    size_t i;
    hash = native_fce_hash_value(hash, (unsigned int)model->date);
    hash = native_fce_hash_value(hash, (unsigned int)model->unresolved_fixtures);
    hash = native_fce_hash_value(hash, (unsigned int)model->node_count);
    hash = native_fce_hash_value(hash, (unsigned int)model->standing_count);
    hash = native_fce_hash_value(hash, (unsigned int)model->fixture_count);
    hash = native_fce_hash_value(hash, (unsigned int)model->stat_count);
    for (i = 0; i < model->node_count; ++i) {
        const FceCompNode *row = model->nodes + i;
        hash = native_fce_hash_value(hash, (unsigned int)row->id);
        hash = native_fce_hash_value(hash, (unsigned int)row->parent);
        hash = native_fce_hash_value(hash, (unsigned int)row->type);
        hash = native_fce_hash_value(hash, (unsigned int)row->asset);
        hash = native_fce_hash_value(hash, (unsigned int)row->stage_kind);
    }
    for (i = 0; i < model->standing_count; ++i) {
        const FceStanding *row = model->standings + i;
        hash = native_fce_hash_value(hash, (unsigned int)row->standing_id);
        hash = native_fce_hash_value(hash, (unsigned int)row->competition_object);
        hash = native_fce_hash_value(hash, (unsigned int)row->team);
        hash = native_fce_hash_value(hash, row->home_wins);
        hash = native_fce_hash_value(hash, row->home_draws);
        hash = native_fce_hash_value(hash, row->home_losses);
        hash = native_fce_hash_value(hash, row->away_wins);
        hash = native_fce_hash_value(hash, row->away_draws);
        hash = native_fce_hash_value(hash, row->away_losses);
        hash = native_fce_hash_value(hash, row->played);
    }
    for (i = 0; i < model->fixture_count; ++i) {
        const FceFixture *row = model->fixtures + i;
        hash = native_fce_hash_value(hash, (unsigned int)row->id);
        hash = native_fce_hash_value(hash, (unsigned int)row->competition_object);
        hash = native_fce_hash_value(hash, (unsigned int)row->stage);
        hash = native_fce_hash_value(hash, (unsigned int)row->date_raw);
        hash = native_fce_hash_value(hash, (unsigned int)row->time_raw);
        hash = native_fce_hash_value(hash, (unsigned int)row->home);
        hash = native_fce_hash_value(hash, (unsigned int)row->away);
        hash = native_fce_hash_value(hash, (unsigned int)row->home_score);
        hash = native_fce_hash_value(hash, (unsigned int)row->away_score);
        hash = native_fce_hash_value(hash, (unsigned int)row->played_raw);
        hash = native_fce_hash_value(hash, (unsigned int)row->round);
    }
    for (i = 0; i < model->stat_count; ++i) {
        const FceStat *row = model->stats + i;
        hash = native_fce_hash_value(hash, (unsigned int)row->stats_id);
        hash = native_fce_hash_value(hash, (unsigned int)row->competition);
        hash = native_fce_hash_value(hash, (unsigned int)row->team);
        hash = native_fce_hash_value(hash, (unsigned int)row->player);
        hash = native_fce_hash_value(hash, (unsigned int)row->appearances);
        hash = native_fce_hash_value(hash, (unsigned int)row->minutes);
        hash = native_fce_hash_value(hash, (unsigned int)row->goals);
        hash = native_fce_hash_value(hash, (unsigned int)row->assists);
        hash = native_fce_hash_value(hash, (unsigned int)row->yellow_cards);
        hash = native_fce_hash_value(hash, (unsigned int)row->red_cards);
        hash = native_fce_hash_value(hash, (unsigned int)row->clean_sheets);
        hash = native_fce_hash_value(hash, (unsigned int)row->rating_sum);
        hash = native_fce_hash_value(hash, row->profile_valid);
    }
    return hash;
}
static int native_fce_snapshot_json_string(FILE *file, const char *value)
{
    const unsigned char *cursor = (const unsigned char *)value;
    if (fputc('"', file) == EOF) return 0;
    while (*cursor) {
        if (*cursor == '"' || *cursor == '\\') {
            if (fputc('\\', file) == EOF || fputc(*cursor, file) == EOF) return 0;
        } else if (*cursor == '\r') {
            if (fputs("\\r", file) == EOF) return 0;
        } else if (*cursor == '\n') {
            if (fputs("\\n", file) == EOF) return 0;
        } else if (*cursor == '\t') {
            if (fputs("\\t", file) == EOF) return 0;
        } else if (*cursor >= 0x20) {
            if (fputc(*cursor, file) == EOF) return 0;
        }
        ++cursor;
    }
    return fputc('"', file) != EOF;
}

/* Keep a career-owned copy of the live FCE model. The browser only reads this
 * atomic snapshot; it never inspects FIFA process memory. */
static int native_fce_snapshot_write(void)
{
    const FceModel *model = &native_view;
    char runtime_dir[MAX_PATH], snapshot_path[MAX_PATH], temporary_path[MAX_PATH];
    char save_path[1024];
    wchar_t save_path_w[2048];
    FILE *file;
    FILETIME created, exited, kernel, user;
    WIN32_FILE_ATTRIBUTE_DATA save_attributes;
    ULARGE_INTEGER created_value, saved_write_time, save_size;
    DWORD pid = GetCurrentProcessId();
    size_t i;
    int ok = 1;
    unsigned long generation = native_epoch;
    unsigned long long fingerprint;
    int converted;
    if (!g_mod_dir[0] || !generation ||
        model->node_count > 65536 || model->standing_count > 65536 ||
        model->fixture_count > 65536 || model->stat_count > 65536 ||
        (model->node_count && !model->nodes) ||
        (model->standing_count && !model->standings) ||
        (model->fixture_count && !model->fixtures) ||
        (model->stat_count && !model->stats) ||
        !native_read_active_save_path(save_path, sizeof(save_path)) ||
        !GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user))
        return 0;
    converted = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, save_path, -1,
        save_path_w, (int)(sizeof(save_path_w) / sizeof(save_path_w[0])));
    if (!converted || !GetFileAttributesExW(save_path_w, GetFileExInfoStandard,
        &save_attributes)) return 0;
    created_value.LowPart = created.dwLowDateTime;
    created_value.HighPart = created.dwHighDateTime;
    saved_write_time.LowPart = save_attributes.ftLastWriteTime.dwLowDateTime;
    saved_write_time.HighPart = save_attributes.ftLastWriteTime.dwHighDateTime;
    save_size.LowPart = save_attributes.nFileSizeLow;
    save_size.HighPart = save_attributes.nFileSizeHigh;
    fingerprint = native_fce_model_fingerprint(model);
    if (fingerprint == native_fce_snapshot_fingerprint &&
        save_size.QuadPart == native_fce_snapshot_size &&
        saved_write_time.QuadPart == native_fce_snapshot_write_time) return 0;
    snprintf(runtime_dir, sizeof(runtime_dir), "%s\\runtime", g_mod_dir);
    if (!CreateDirectoryA(runtime_dir, NULL) &&
        GetLastError() != ERROR_ALREADY_EXISTS) return 0;
    snprintf(snapshot_path, sizeof(snapshot_path),
        "%s\\career_fce_snapshot.json", runtime_dir);
    snprintf(temporary_path, sizeof(temporary_path),
        "%s\\career_fce_snapshot.%lu.tmp", runtime_dir, (unsigned long)pid);
    file = fopen(temporary_path, "wb");
    if (!file) return 0;
    if (fprintf(file,
        "{\"schema\":3,\"pid\":%lu,\"processCreated100ns\":%llu,"
        "\"generation\":%lu,\"saveSize\":%llu,\"saveWriteTime100ns\":%llu,"
        "\"savePath\":",
        (unsigned long)pid, (unsigned long long)created_value.QuadPart,
        generation, (unsigned long long)save_size.QuadPart,
        (unsigned long long)saved_write_time.QuadPart) < 0) ok = 0;
    if (ok && !native_fce_snapshot_json_string(file, save_path)) ok = 0;
    if (ok && fprintf(file, ",\"club\":%d,\"date\":%d,\"unresolvedFixtures\":%llu,\"nodes\":[",
        native_club, model->date,
        (unsigned long long)model->unresolved_fixtures) < 0) ok = 0;
    for (i = 0; ok && i < model->node_count; ++i) {
        const FceCompNode *n = model->nodes + i;
        if (fprintf(file, "%s[%d,%d,%d,%d,%d]", i ? "," : "",
            (int)n->id, (int)n->parent, (int)n->type, (int)n->asset,
            (int)n->stage_kind) < 0) ok = 0;
    }
    if (ok && fputs("],\"standings\":[", file) == EOF) ok = 0;
    for (i = 0; ok && i < model->standing_count; ++i) {
        const FceStanding *standing = model->standings + i;
        if (fprintf(file, "%s[%d,%d,%d,%u,%u,%u,%u,%u,%u,%u]",
            i ? "," : "", (int)standing->standing_id,
            (int)standing->competition_object, (int)standing->team,
            standing->home_wins, standing->home_draws, standing->home_losses,
            standing->away_wins, standing->away_draws, standing->away_losses,
            standing->played) < 0) ok = 0;
    }
    if (ok && fputs("],\"fixtures\":[", file) == EOF) ok = 0;
    for (i = 0; ok && i < model->fixture_count; ++i) {
        const FceFixture *fixture = model->fixtures + i;
        if (fprintf(file, "%s[%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d]",
            i ? "," : "", (int)fixture->id,
            (int)fixture->competition_object, (int)fixture->stage,
            (int)fixture->date_raw, (int)fixture->time_raw,
            (int)fixture->home, (int)fixture->away,
            (int)fixture->home_score, (int)fixture->away_score,
            (int)fixture->played_raw, (int)fixture->round) < 0) ok = 0;
    }
    if (ok && fputs("],\"stats\":[", file) == EOF) ok = 0;
    for (i = 0; ok && i < model->stat_count; ++i) {
        const FceStat *stat = model->stats + i;
        if (fprintf(file, "%s[%d,%d,%d,%d,%d,%d,%d,%d]", i ? "," : "",
            (int)stat->stats_id, (int)stat->competition, (int)stat->team,
            (int)stat->player, (int)stat->appearances, (int)stat->minutes,
            (int)stat->goals, (int)stat->assists) < 0) ok = 0;
    }
    if (ok && fputs("]}\n", file) == EOF) ok = 0;
    if (fflush(file) != 0) ok = 0;
    if (fclose(file) != 0) ok = 0;
    if (!ok) {
        DeleteFileA(temporary_path);
        return 0;
    }
    if (!MoveFileExA(temporary_path, snapshot_path,
        MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileA(temporary_path);
        return 0;
    }
    native_fce_snapshot_generation = generation;
    native_fce_snapshot_size = save_size.QuadPart;
    native_fce_snapshot_write_time = saved_write_time.QuadPart;
    native_fce_snapshot_fingerprint = fingerprint;
    return 1;
}

static unsigned int native_find_layout_id_offsets(const void *object,
    unsigned int expected, char *output, size_t capacity)
{
    const unsigned char *bytes = (const unsigned char *)object;
    size_t offset;
    unsigned int count = 0;
    size_t used = 0;
    if (!output || !capacity)
        return 0;
    output[0] = '\0';
    if (!object || !is_readable_range(object, 0x400))
        return 0;
    for (offset = 0; offset + sizeof(unsigned int) <= 0x400;
         offset += sizeof(unsigned int)) {
        unsigned int value;
        memcpy(&value, bytes + offset, sizeof(value));
        if (value != expected)
            continue;
        if (count < 8) {
            int written = snprintf(output + used, capacity - used,
                "%s0x%03X", used ? "," : "", (unsigned int)offset);
            if (written > 0 && (size_t)written < capacity - used)
                used += (size_t)written;
        }
        ++count;
    }
    return count;
}

static int native_is_competition_round_provider(void *owner, void *provider)
{
    static const unsigned int layout_ids[] = { 656, 657, 658, 660 };
    size_t i;
    char offsets[32];
    for (i = 0; i < sizeof(layout_ids) / sizeof(layout_ids[0]); ++i) {
        if (native_find_layout_id_offsets(owner, layout_ids[i], offsets,
                sizeof(offsets))
            || native_find_layout_id_offsets(provider, layout_ids[i], offsets,
                sizeof(offsets)))
            return 1;
    }
    return 0;
}

/* Diagnostic-only probe for the stats-provider owner and the active transfer
 * window. The IDs are recorded from live objects when verbose logging is on;
 * the probe itself does not make assumptions about which slide is active. */
static void native_log_transfer_card_context(void *provider)
{
    char log_path[MAX_PATH];
    char save_path[1024];
    char owner_725[96], owner_728[96], owner_729[96];
    char provider_725[96], provider_728[96], provider_729[96];
    unsigned int end1 = 0, end2 = 0;
    int calendar_ok = 0;
    int today = native_calendar_date(g_current_stats_provider_owner);
    FILE *log;
    if (!fce_runtime_log_verbose() || !g_mod_dir[0])
        return;
    save_path[0] = '\0';
    if (native_read_active_save_path(save_path, sizeof(save_path)))
        calendar_ok = retirement_engine_get_transfer_window_ends(save_path,
            &end1, &end2);
    snprintf(log_path, sizeof(log_path), "%s\\logs\\transfer_card_gate_probe.log",
        g_mod_dir);
    log = fopen(log_path, "ab");
    if (!log)
        return;
    fprintf(log,
        "owner=%p provider=%p date=%d calendar=%d end1=%04u end2=%04u "
        "owner725=%u[%s] owner728=%u[%s] owner729=%u[%s] "
        "provider725=%u[%s] provider728=%u[%s] provider729=%u[%s]\n",
        g_current_stats_provider_owner, provider, today, calendar_ok, end1, end2,
        native_find_layout_id_offsets(g_current_stats_provider_owner, 725,
            owner_725, sizeof(owner_725)), owner_725,
        native_find_layout_id_offsets(g_current_stats_provider_owner, 728,
            owner_728, sizeof(owner_728)), owner_728,
        native_find_layout_id_offsets(g_current_stats_provider_owner, 729,
            owner_729, sizeof(owner_729)), owner_729,
        native_find_layout_id_offsets(provider, 725,
            provider_725, sizeof(provider_725)), provider_725,
        native_find_layout_id_offsets(provider, 728,
            provider_728, sizeof(provider_728)), provider_728,
        native_find_layout_id_offsets(provider, 729,
            provider_729, sizeof(provider_729)), provider_729);
    fclose(log);
}

#include "../features/crowd/international_competition.h"

typedef struct NativeCrowdMetric {
    int team;
    int played;
    int wins;
    int draws;
    int losses;
    int points;
} NativeCrowdMetric;

static float native_crowd_clamp(float value) {
    if(value<0.0f) return 0.0f;
    if(value>1.0f) return 1.0f;
    return value;
}

static int native_crowd_metric_index(
    NativeCrowdMetric *metrics,
    int count,
    int team) {
    int i;
    for(i=0;i<count;++i) if(metrics[i].team==team) return i;
    return -1;
}

static int native_crowd_rank_for_metric(
    NativeCrowdMetric *metrics,
    int count,
    int target) {
    int rank=1,i;
    if(target<0 || target>=count) return 0;
    for(i=0;i<count;++i) {
        if(i==target) continue;
        if(metrics[i].points>metrics[target].points ||
           (metrics[i].points==metrics[target].points &&
            metrics[i].wins>metrics[target].wins))
            ++rank;
    }
    return rank;
}

#include "../features/crowd/competition_attendance.h"
static void native_update_crowd(const FceModel *model,int competition,int club) {
    CrowdDecision decision;
    NativeCrowdMetric metrics[64];
    const FceFixture *recent[5]={0};
    const FceFixture *next=NULL;
    const FceFixture *actual_next;
    int root,count=0,my_index=-1,rank=1,team_count,expected_matches;
    int current_points=0,recent_points=0;
    int i,k,recent_count=0;
    int danger_slots,danger_start,danger_pressure_start;
    int safety_index=-1,opponent_index=-1,opponent_rank=0;
    int last_result=0,last_margin=0,streak=0,streak_sign=0;
    int points_gap_to_safety=0;
    float performance,form,reputation,league_reputation,rivalry;
    float position_score,season_progress,danger;
    float importance,phase,factor,round_progress,momentum,escape_opportunity;
    memset(&decision,0,sizeof(decision));
    decision.factor=0.90f;
    if(!model || club<=0 || competition<=0 || !fce_date_valid(model->date)) {
        crowd_runtime_disable();
        return;
    }
    root=fce_model_ancestor(model,competition,3);
    if(root<0) root=competition;
    memset(metrics,0,sizeof(metrics));
    for(i=0;i<(int)model->standing_count;++i) {
        const FceStanding *standing=model->standings+i;
        NativeCrowdMetric *metric;
        int index=native_crowd_metric_index(metrics,count,standing->team);
        if(standing->team<=0 ||
           fce_model_ancestor(model,standing->competition_object,3)!=root)
            continue;
        if(index<0) {
            if(count>=(int)(sizeof(metrics)/sizeof(metrics[0]))) continue;
            index=count++;
            metrics[index].team=standing->team;
        } else if(metrics[index].played >= (int)standing->played) {
            continue;
        }
        metric=metrics+index;
        metric->played=(int)standing->played;
        metric->wins=(int)standing->home_wins+(int)standing->away_wins;
        metric->draws=(int)standing->home_draws+(int)standing->away_draws;
        metric->losses=(int)standing->home_losses+(int)standing->away_losses;
        metric->points=metric->wins*3+metric->draws;
    }
    team_count=count;
    my_index=native_crowd_metric_index(metrics,count,club);
    if(my_index<0 || team_count<2) {
        crowd_runtime_disable();
        return;
    }
    current_points=metrics[my_index].points;
    rank=native_crowd_rank_for_metric(metrics,count,my_index);
    for(i=0;i<(int)model->fixture_count;++i) {
        const FceFixture *fixture=model->fixtures+i;
        if(fixture->home!=club && fixture->away!=club) continue;
        if(fce_model_ancestor(model,fixture->competition_object,3)!=root) continue;
        if(fixture->played_raw) {
            int position=0;
            if(fixture->date_raw>model->date) continue;
            while(position<recent_count &&
                  (recent[position]->date_raw>fixture->date_raw ||
                   (recent[position]->date_raw==fixture->date_raw &&
                    recent[position]->id>fixture->id))) ++position;
            if(position>=5) continue;
            if(recent_count<5) ++recent_count;
            for(k=recent_count-1;k>position;--k) recent[k]=recent[k-1];
            recent[position]=fixture;
        } else if(fixture->date_raw>=model->date &&
                  (!next || fixture->date_raw<next->date_raw ||
                   (fixture->date_raw==next->date_raw && fixture->time_raw<next->time_raw) ||
                   (fixture->date_raw==next->date_raw && fixture->time_raw==next->time_raw &&
                    fixture->id<next->id))) {
            next=fixture;
        }
    }
    recent_points=0;
    for(i=0;i<recent_count;++i) {
        int scored=recent[i]->home==club?recent[i]->home_score:recent[i]->away_score;
        int conceded=recent[i]->home==club?recent[i]->away_score:recent[i]->home_score;
        recent_points += scored>conceded?3:(scored==conceded?1:0);
    }
    form=recent_count>0?(float)recent_points/(float)(recent_count*3):0.50f;

    /* Recent momentum is intentionally separate from the table form.  A
     * heavy result affects the next attendance, while a draw breaks a
     * win/loss streak. */
    if(recent_count>0) {
        int scored=recent[0]->home==club?recent[0]->home_score:recent[0]->away_score;
        int conceded=recent[0]->home==club?recent[0]->away_score:recent[0]->home_score;
        int result=scored>conceded?1:(scored<conceded?-1:0);
        last_result=result;
        last_margin=scored>conceded?scored-conceded:conceded-scored;
        if(result!=0) {
            streak_sign=result;
            for(i=0;i<recent_count;++i) {
                int recent_scored=recent[i]->home==club?
                    recent[i]->home_score:recent[i]->away_score;
                int recent_conceded=recent[i]->home==club?
                    recent[i]->away_score:recent[i]->home_score;
                int recent_result=recent_scored>recent_conceded?1:
                    (recent_scored<recent_conceded?-1:0);
                if(recent_result!=streak_sign) break;
                ++streak;
            }
        }
    }
    momentum=0.50f;
    if(last_result!=0) {
        momentum += 0.12f*(float)last_result;
        if(last_margin>=3) momentum += 0.10f*(float)last_result;
        else if(last_margin==2) momentum += 0.05f*(float)last_result;
    }
    if(streak>=2) {
        float streak_effect=(float)streak*0.06f;
        if(streak_effect>0.18f) streak_effect=0.18f;
        momentum += (float)streak_sign*streak_effect;
    }
    momentum=native_crowd_clamp(momentum);

    reputation=crowd_runtime_team_reputation(club);
    league_reputation=crowd_runtime_league_reputation(club);
    rivalry=next ? crowd_runtime_rivalry(club,
        next->home==club?next->away:next->home) : 0.0f;
    performance=team_count>1
        ? 1.0f-(float)(rank-1)/(float)(team_count-1)
        : 0.50f;
    position_score=native_crowd_clamp(performance);
    expected_matches=(team_count-1)*2;
    if(expected_matches<1) expected_matches=1;
    season_progress=native_crowd_clamp(
        (float)metrics[my_index].played/(float)expected_matches);
    if(next && next->round>0) {
        round_progress=native_crowd_clamp(
            (float)(next->round-1)/(float)expected_matches);
        if(round_progress>season_progress) season_progress=round_progress;
    }
    phase=season_progress;
    danger=0.0f;
    danger_slots=team_count>8?4:2;
    danger_start=team_count-danger_slots+1;
    danger_pressure_start=team_count-(danger_slots+2)+1;
    if(rank>=danger_pressure_start)
        danger=native_crowd_clamp(
            (float)(rank-(danger_pressure_start-1))/(float)(danger_slots+2));

    /* A club inside the relegation places gets an opportunity score when it
     * is close to the safety line, especially late in the season. A direct
     * fixture against the safety line adds a small extra push. */
    if(rank>=danger_start) {
        for(i=0;i<team_count;++i) {
            int candidate_rank=native_crowd_rank_for_metric(metrics,count,i);
            if(candidate_rank==danger_start-1 && metrics[i].points>=current_points &&
               (safety_index<0 || metrics[i].points<metrics[safety_index].points))
                safety_index=i;
        }
        if(safety_index>=0) {
            float gap_score;
            points_gap_to_safety=metrics[safety_index].points-current_points;
            if(points_gap_to_safety<0) points_gap_to_safety=0;
            gap_score=1.0f-native_crowd_clamp((float)points_gap_to_safety/6.0f);
            escape_opportunity=gap_score*native_crowd_clamp(
                (season_progress-0.35f)/0.65f);
            if(next) {
                opponent_index=native_crowd_metric_index(metrics,count,
                    next->home==club?next->away:next->home);
                if(opponent_index>=0) {
                    opponent_rank=native_crowd_rank_for_metric(
                        metrics,count,opponent_index);
                    if(opponent_rank==danger_start-1)
                        escape_opportunity+=0.20f;
                    else if(opponent_rank<danger_start &&
                            opponent_rank>=danger_start-2)
                        escape_opportunity+=0.10f;
                }
            }
            escape_opportunity=native_crowd_clamp(escape_opportunity);
        } else {
            escape_opportunity=0.0f;
        }
    } else {
        escape_opportunity=0.0f;
    }
    /* League tier and a verified derby/rival entry are attendance drivers in
     * their own right. Type 1 database rivalries are the strongest classics. */
    importance=0.20f+0.15f*native_crowd_clamp(league_reputation)+
        0.25f*native_crowd_clamp(rivalry);
    if((rank<=3 || danger>0.0f) && season_progress>0.0f)
        importance+=0.35f*season_progress;
    importance+=0.20f*escape_opportunity;
    if(next) {
        if(next->stage!=next->competition_object) importance+=0.10f;
    }
    importance=native_crowd_clamp(importance);
    factor=0.08f+0.38f*native_crowd_clamp(reputation)+
        0.22f*season_progress*position_score+
        0.08f*season_progress*native_crowd_clamp(form)+
        0.10f*momentum+
        0.08f*importance+
        0.04f*native_crowd_clamp(league_reputation)+
        0.08f*native_crowd_clamp(rivalry)+
        0.10f*native_crowd_clamp(reputation)*escape_opportunity-
        0.12f*(1.0f-native_crowd_clamp(reputation))*danger*season_progress;
    actual_next=crowd_next_actual_fixture(model,club);
    if(actual_next) {
        CrowdCompetitionProfile profile=crowd_competition_profile(model,actual_next);
        profile.bonus_percent=crowd_runtime_competition_setting(profile.key,"bonus",profile.bonus_percent,40);
        profile.minimum_percent=crowd_runtime_competition_setting(profile.key,"minimum",profile.minimum_percent,90);
        profile.maximum_percent=crowd_runtime_competition_setting(profile.key,"maximum",profile.maximum_percent,90);
        /* Includes the former international bonus once, not on top of it. */
        if(crowd_fixture_is_international(model,actual_next))
            decision.international_bonus=(float)profile.bonus_percent/100.0f;
        factor=crowd_competition_apply(factor,&profile);
    }
    decision.enabled=1;
    decision.club_id=club;
    decision.competition_id=competition;
    decision.rank=rank;
    decision.team_count=team_count;
    decision.played=metrics[my_index].played;
    decision.form=form;
    decision.reputation=reputation;
    decision.league_reputation=league_reputation;
    decision.rivalry=rivalry;
    decision.position_score=position_score;
    decision.season_progress=season_progress;
    decision.danger=danger;
    decision.last_result=last_result;
    decision.last_margin=last_margin;
    decision.streak=streak;
    decision.streak_sign=streak_sign;
    decision.points_gap_to_safety=points_gap_to_safety;
    decision.momentum=momentum;
    decision.escape_opportunity=escape_opportunity;
    decision.importance=importance;
    decision.phase=phase;
    decision.factor=factor;
    if(actual_next) {
        decision.next_opponent=actual_next->home==club?actual_next->away:actual_next->home;
        decision.next_is_home=actual_next->home==club;
        decision.next_date=actual_next->date_raw;
        decision.next_round=actual_next->round;
    }
    crowd_runtime_set_decision(&decision);
}

static void native_movement_history(int comp) {
    size_t i,j; int root=fce_model_ancestor(&native_view,comp,3);
    g_form_match_count=0;
    if(root<0 || !fce_date_valid(native_view.date)) return;
    /* Only the latest completed fixture per participating team is needed
     * by the existing previous-position display. Never mix cup matches. */
    for(i=0;i<native_view.standing_count && g_form_match_count<FORM_MATCH_CAPACITY;++i) {
        const FceStanding *s=native_view.standings+i; const FceFixture *best=NULL;
        FormMatch *out;
        if(s->team<=0 || fce_model_ancestor(&native_view,s->competition_object,3)!=root) continue;
        for(j=0;j<native_view.fixture_count;++j) {
            const FceFixture *f=native_view.fixtures+j;
            if(!f->played_raw || f->date_raw>native_view.date || (f->home!=s->team && f->away!=s->team) ||
                native_fixture_root(f)!=root) continue;
            if(!best || f->date_raw>best->date_raw || (f->date_raw==best->date_raw && f->id>best->id)) best=f;
        }
        if(!best) continue;
        out=g_form_matches+g_form_match_count++;
        memset(out,0,sizeof(*out));out->home_logo=best->home;out->away_logo=best->away;
        out->home_score=best->home_score;out->away_score=best->away_score;out->date_key=best->date_raw;
    }
}

static int native_competition_has_club(int root,int club) {
    size_t i;
    if(root<=0 || club<=0) return 0;
    for(i=0;i<native_view.standing_count;++i) {
        const FceStanding *s=native_view.standings+i;
        if(s->team==club && fce_model_ancestor(&native_view,s->competition_object,3)==root)
            return 1;
    }
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        if((f->home==club || f->away==club) && native_fixture_root(f)==root)
            return 1;
    }
    return 0;
}

static size_t native_stage_team_count(int stage,int club,int *contains_club) {
    int teams[64]; size_t count=0,i,j;
    if(contains_club) *contains_club=0;
    if(stage<=0) return 0;
    for(i=0;i<native_view.standing_count;++i) {
        const FceStanding *s=native_view.standings+i;
        if(s->team<=0 || s->competition_object!=stage) continue;
        if(contains_club && s->team==club) *contains_club=1;
        for(j=0;j<count;++j) if(teams[j]==s->team) break;
        if(j==count && count<sizeof(teams)/sizeof(teams[0])) teams[count++]=s->team;
    }
    return count;
}

static size_t native_stage_fixture_team_count(int stage) {
    int teams[64]; size_t count=0,i,j;
    if(stage<=0) return 0;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i; int pair[2],p;
        if(f->stage!=stage) continue;
        pair[0]=f->home;pair[1]=f->away;
        for(p=0;p<2;++p) {
            if(pair[p]<=0) continue;
            for(j=0;j<count;++j) if(teams[j]==pair[p]) break;
            if(j==count && count<sizeof(teams)/sizeof(teams[0])) teams[count++]=pair[p];
        }
    }
    return count;
}

static void native_knockout_stage_label(int stage,int round,char *out,size_t size) {
    size_t teams=native_stage_fixture_team_count(stage);
    if(!out || !size) return;
    if(teams==2) lstrcpynA(out,"FINAL",(int)size);
    else if(teams==4) lstrcpynA(out,"SEMIFINAL",(int)size);
    else if(teams==8) lstrcpynA(out,"QUARTAS DE FINAL",(int)size);
    else if(teams==16) lstrcpynA(out,"OITAVAS DE FINAL",(int)size);
    else if(teams==32) lstrcpynA(out,"FASE DE 32",(int)size);
    else if(round>0) snprintf(out,size,"MATA-MATA  -  RODADA %d",round);
    else lstrcpynA(out,"MATA-MATA ATUAL",(int)size);
}

static int native_fixture_precedes(const FceFixture *a,const FceFixture *b) {
    if(a->date_raw!=b->date_raw) return a->date_raw<b->date_raw;
    if(a->time_raw!=b->time_raw) return a->time_raw<b->time_raw;
    return a->id<b->id;
}

/* Pick the phase from the club's own calendar. Old group standings remain
 * alive after qualification, so "most games played" cannot identify the
 * current phase. The next unresolved fixture wins; after the tournament has
 * ended, the latest completed fixture wins. */
static int native_current_stage(int root,int club,int fallback) {
    const FceFixture *next=NULL,*previous=NULL; size_t i;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        if((f->home!=club && f->away!=club) || native_fixture_root(f)!=root) continue;
        if(!f->played_raw && (!fce_date_valid(native_view.date) || f->date_raw>=native_view.date)) {
            if(!next || native_fixture_precedes(f,next)) next=f;
        } else if(f->played_raw && (!fce_date_valid(native_view.date) || f->date_raw<=native_view.date)) {
            if(!previous || native_fixture_precedes(previous,f)) previous=f;
        }
    }
    if(next) return next->stage>0?next->stage:next->competition_object;
    if(previous) return previous->stage>0?previous->stage:previous->competition_object;
    return fallback>0?fallback:root;
}

/* A carousel page needs positive participation evidence. Resolved fixtures
 * are definitive. A table/group with at least three assigned clubs is also
 * definitive and covers competitions whose first fixture has not been drawn.
 * Two-team placeholder standings alone are deliberately rejected. */
static int native_competition_is_active_for_club(int root,int club,int current_root) {
    size_t i;
    if(root<=0 || club<=0) return 0;
    if(root==current_root && native_competition_has_club(root,club)) return 1;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        if((f->home==club || f->away==club) && native_fixture_root(f)==root) return 1;
    }
    for(i=0;i<native_view.standing_count;++i) {
        const FceStanding *s=native_view.standings+i; int contains=0;
        if(s->team!=club || fce_model_ancestor(&native_view,s->competition_object,3)!=root) continue;
        if(native_stage_team_count(s->competition_object,club,&contains)>=3 && contains) return 1;
    }
    return 0;
}

static void native_add_club_competition(int object,int club,int standing_stage) {
    FceCompetition resolved; size_t i; int displayed_root,resolved_ok;
    displayed_root=fce_model_ancestor(&native_view,(int)InterlockedCompareExchange(
        &g_active_competition_id,0,0),3);
    resolved_ok=fce_resolve_competition(native_view.nodes,native_view.node_count,
        object,&resolved)==FCE_OK;
    /* A pre-season tour can use a temporary object which is absent from the
     * compact competition index. Keep it only when this exact object owns a
     * fixture for the managed club; never invent pages from a random object. */
    if(!resolved_ok) {
        if(!native_fixture_object_for_club(object,club)) return;
        memset(&resolved,0,sizeof(resolved));
        resolved.competition=object;
        resolved.asset=native_logo(object);
    }
    if(g_competition_count>=COMPETITION_TAB_CAPACITY ||
       resolved.competition<=0 || (!native_competition_has_club(resolved.competition,club) &&
       resolved.competition!=displayed_root)) return;
    for(i=0;i<g_competition_count;++i) {
        if(g_competition_rows[i].competition_id!=resolved.competition) continue;
        if(standing_stage>0) {
            unsigned current_played=0,incoming_played=0; size_t s;
            for(s=0;s<native_view.standing_count;++s) {
                const FceStanding *row=native_view.standings+s;
                if(row->team!=club) continue;
                if(row->competition_object==g_competition_rows[i].stage) current_played=row->played;
                if(row->competition_object==standing_stage) incoming_played=row->played;
            }
            if(g_competition_rows[i].stage<=0 || incoming_played>=current_played)
                g_competition_rows[i].stage=standing_stage;
        }
        return;
    }
    memset(g_competition_rows+g_competition_count,0,sizeof(g_competition_rows[0]));
    g_competition_rows[g_competition_count].competition_id=resolved.competition;
    g_competition_rows[g_competition_count].league_id=resolved.asset;
    g_competition_rows[g_competition_count].stage=standing_stage>0?standing_stage:object;
    snprintf(g_competition_rows[g_competition_count].title_key,
        sizeof(g_competition_rows[g_competition_count].title_key),
        "TrophyName_%d",resolved.asset>0?resolved.asset:resolved.competition);
    ++g_competition_count;
}

/* Add fixture-backed competitions by earliest participation date. Raw FCE
 * order is grouped by internal service, so using it can fill all five slots
 * before a pre-season tour is reached. */
static void native_add_club_fixture_competitions(int club) {
    const FceFixture *candidates[128]; int roots[128];
    size_t candidate_count=0,i,j;
    memset(roots,0,sizeof(roots));
    for(i=0;i<native_view.fixture_count && candidate_count<sizeof(candidates)/sizeof(candidates[0]);++i) {
        const FceFixture *fixture=native_view.fixtures+i;
        int root;
        if(fixture->home!=club && fixture->away!=club) continue;
        root=native_fixture_root(fixture);
        if(root<=0) continue;
        for(j=0;j<candidate_count && roots[j]!=root;++j) {}
        if(j==candidate_count) {
            roots[candidate_count]=root;
            candidates[candidate_count++]=fixture;
        } else if(native_fixture_precedes(fixture,candidates[j])) {
            candidates[j]=fixture;
        }
    }
    for(i=0;i<candidate_count;++i) for(j=i+1;j<candidate_count;++j) {
        if(native_fixture_precedes(candidates[j],candidates[i])) {
            const FceFixture *fixture=candidates[i]; int root=roots[i];
            candidates[i]=candidates[j]; roots[i]=roots[j];
            candidates[j]=fixture; roots[j]=root;
        }
    }
    for(i=0;i<candidate_count && g_competition_count<COMPETITION_TAB_CAPACITY;++i)
        native_add_club_competition(candidates[i]->competition_object,club,0);
}

static int native_tab_row_precedes(const CompetitionTabRow *a,const CompetitionTabRow *b) {
    int gd_a=a->goals_for-a->goals_against,gd_b=b->goals_for-b->goals_against;
    if(a->points!=b->points) return a->points>b->points;
    if(a->won!=b->won) return a->won>b->won;
    if(gd_a!=gd_b) return gd_a>gd_b;
    if(a->goals_for!=b->goals_for) return a->goals_for>b->goals_for;
    return a->team_id<b->team_id;
}

static void native_build_competition_tab(size_t page,int club) {
    CompetitionSummary *summary=g_competition_rows+page;
    CompetitionTabRow *rows=g_competition_tab_rows[page];
    size_t i,j,count=0,exact_count=0; int root=summary->competition_id,contains_club=0;
    const FceFixture *next=NULL,*previous=NULL;
    memset(rows,0,sizeof(g_competition_tab_rows[page]));
    memset(g_competition_tab_knockout+page,0,sizeof(g_competition_tab_knockout[page]));
    memset(g_competition_tab_knockout_history[page],0,
        sizeof(g_competition_tab_knockout_history[page]));
    g_competition_tab_knockout_history_counts[page]=0;
    summary->stage=native_current_stage(root,club,summary->stage);
    exact_count=native_stage_team_count(summary->stage,club,&contains_club);
    for(i=0;i<native_view.standing_count && count<COMPETITION_TAB_ROW_CAPACITY;++i) {
        const FceStanding *s=native_view.standings+i; CompetitionTabRow row; size_t row_index;
        if(s->team<=0 || fce_model_ancestor(&native_view,s->competition_object,3)!=root ||
           exact_count<3 || !contains_club || s->competition_object!=summary->stage) continue;
        for(row_index=0;row_index<count;++row_index) if(rows[row_index].team_id==s->team) break;
        if(row_index<count && rows[row_index].played>=(int)s->played) continue;
        memset(&row,0,sizeof(row));
        row.team_id=s->team; row.played=(int)s->played;
        row.won=(int)(s->home_wins+s->away_wins);
        row.drawn=(int)(s->home_draws+s->away_draws);
        row.lost=(int)(s->home_losses+s->away_losses);
        row.points=row.won*3+row.drawn;
        for(j=0;j<native_view.fixture_count;++j) {
            const FceFixture *f=native_view.fixtures+j;
            if(!f->played_raw || (fce_date_valid(native_view.date) && f->date_raw>native_view.date) ||
               !native_fixture_stage_matches(f,summary->stage) ||
               native_fixture_root(f)!=root ||
               (f->home!=row.team_id && f->away!=row.team_id)) continue;
            if(f->home==row.team_id) { row.goals_for+=f->home_score;row.goals_against+=f->away_score; }
            else { row.goals_for+=f->away_score;row.goals_against+=f->home_score; }
        }
        if(row_index<count) rows[row_index]=row; else rows[count++]=row;
    }
    for(i=0;i<count;++i) for(j=i+1;j<count;++j) {
        if(native_tab_row_precedes(rows+j,rows+i)) {
            CompetitionTabRow temporary=rows[i];rows[i]=rows[j];rows[j]=temporary;
        }
    }
    for(i=0;i<count;++i) {
        rows[i].rank=(int)i+1;
        if(rows[i].team_id==club) {
            summary->rank=rows[i].rank;summary->played=rows[i].played;
            summary->points=rows[i].points;
        }
    }
    summary->kind=count>=3?1:0;
    g_competition_tab_row_counts[page]=count;
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        if((f->home!=club && f->away!=club) ||
           native_fixture_root(f)!=root ||
           !native_fixture_stage_matches(f,summary->stage)) continue;
        if(!f->played_raw && (!next || f->date_raw<next->date_raw ||
           (f->date_raw==next->date_raw && f->time_raw<next->time_raw))) next=f;
        if(f->played_raw && (!previous || f->date_raw>previous->date_raw ||
           (f->date_raw==previous->date_raw && f->time_raw>previous->time_raw))) previous=f;
    }
    {
        const FceFixture *shown=next?next:previous;
        if(shown) {
            CompetitionTabKnockout *ko=g_competition_tab_knockout+page;
            ko->visible=count<3;ko->stage=shown->stage;ko->round=shown->round;
            ko->home_team=shown->home;ko->away_team=shown->away;
            ko->date=shown->date_raw;ko->time=shown->time_raw;ko->played=shown->played_raw;
            ko->home_score=shown->home_score;ko->away_score=shown->away_score;
            if(next) { summary->next_home_logo=next->home;summary->next_away_logo=next->away;
                summary->next_date=next->date_raw;summary->next_time=next->time_raw; }
        }
    }
    if(count<3) {
        const FceFixture *history[COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY]={0};
        size_t history_count=0;
        for(i=0;i<native_view.fixture_count;++i) {
            const FceFixture *f=native_view.fixtures+i; size_t k; int stage_contains=0;
            if(!f->played_raw || (f->home!=club && f->away!=club) ||
               native_fixture_root(f)!=root ||
               (fce_date_valid(native_view.date) && f->date_raw>native_view.date)) continue;
            if(native_stage_team_count(f->stage,club,&stage_contains)>=3) continue;
            for(k=0;k<history_count;++k) if(native_fixture_precedes(history[k],f)) break;
            if(k<COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY) {
                size_t move=history_count<COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY?
                    history_count:COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY-1;
                while(move>k) { history[move]=history[move-1]; --move; }
                history[k]=f;
                if(history_count<COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY) ++history_count;
            }
        }
        for(i=0;i<history_count;++i) {
            CompetitionTabKnockout *item=&g_competition_tab_knockout_history[page][i];
            const FceFixture *f=history[i];
            item->visible=1;item->stage=f->stage;item->round=f->round;
            item->home_team=f->home;item->away_team=f->away;
            item->date=f->date_raw;item->time=f->time_raw;item->played=1;
            item->home_score=f->home_score;item->away_score=f->away_score;
        }
        g_competition_tab_knockout_history_counts[page]=history_count;
    }
}
static void native_prepare(void *owner) {
    const FceModel *model; unsigned long epoch; int club,comp,date,requested,selection_date; size_t i,count=0;
    FceFixture fixtures[10];
    native_end();
    requested=(int)g_active_competition_id; comp=requested;
    native_ui_asset_owner=owner;
    club=resolve_user_club_id(owner,NULL);
    native_requested_competition=requested;
    native_snapshot=fce_runtime_acquire(); model=fce_runtime_model(native_snapshot);
    epoch=fce_runtime_generation(native_snapshot);
    if(native_epoch!=epoch || native_club!=club) {
        g_salary_count=g_roster_player_count=0;
        memset(g_salary_rows,0,sizeof(g_salary_rows));
    }
    /* Fixture/stat snapshots refresh during normal play. Preserve the
     * separately captured InjuryList rows for this club across those refreshes. */
    if(native_club!=club) {
        g_injury_count=0;
        memset(g_injury_rows,0,sizeof(g_injury_rows));
        memset(&g_injury_current,0,sizeof(g_injury_current));
        g_injury_club_id=0;
        g_injury_capture_provider=NULL;
        g_injury_last_tick=0;
        g_injury_current_committed=FALSE;
        g_injury_snapshot_loaded_club=0;
    }
     native_epoch=epoch; native_club=club;
     native_names=owner_service(owner,g_get_name_service_descriptor,NULL);
     native_starting_xi_refresh();
     if(g_injury_count==0)
        injury_load_snapshot(club);
    g_assist_count=g_club_goal_count=g_club_assist_count=g_club_minutes_count=0;
    g_club_oldest_count=0;
    g_club_yellow_count=g_club_red_count=0;
    g_upcoming_count=g_club_previous_count=g_round_previous_count=g_round_next_count=0;
    g_next_match_fixture_valid=0;
    g_next_match_date_fallback=0;
    g_next_match_selection_result=FCE_UNKNOWN;
    memset(&g_next_match_fixture,0,sizeof(g_next_match_fixture));
    g_form_match_count=0; g_competition_count=0;
    g_upcoming_club_id=g_club_previous_club_id=g_round_club_id=g_competition_club_id=club;
    memset(g_competition_rows,0,sizeof(g_competition_rows));
    memset(g_competition_league_rows,0,sizeof(g_competition_league_rows));
    memset(g_competition_tab_rows,0,sizeof(g_competition_tab_rows));
    memset(g_competition_tab_row_counts,0,sizeof(g_competition_tab_row_counts));
    memset(g_competition_tab_knockout,0,sizeof(g_competition_tab_knockout));
    memset(g_competition_tab_knockout_history,0,sizeof(g_competition_tab_knockout_history));
    memset(g_competition_tab_knockout_history_counts,0,sizeof(g_competition_tab_knockout_history_counts));
    memset(g_upcoming_rows,0,sizeof(g_upcoming_rows));
    memset(g_club_previous_rows,0,sizeof(g_club_previous_rows));
    memset(g_round_previous_rows,0,sizeof(g_round_previous_rows));
    memset(g_round_next_rows,0,sizeof(g_round_next_rows));
    if(!model) return;
    native_view=*model;
    comp=native_display_context_competition(requested,club);
    if(comp<=0) comp=requested;
    InterlockedExchange(&g_active_competition_id,comp);
    InterlockedExchange(&g_display_competition_id,comp);
    g_stats_tile_query_competition=comp;
    g_assist_competition_id=comp; g_round_competition_id=comp;
    date=native_calendar_date(owner);
    native_date_source=0;
    /* The CalendarManager TODAY field is the current career date, not the
     * month selected in its UI; the SimManager date is a native fallback. */
    if(fce_date_valid(date)) { native_view.date=date; native_date_source=1; }
    native_coach_record(club);
    native_movement_history(comp);
    native_update_crowd(&native_view,comp,club);
    g_assist_count=native_leaders(comp,-1,FCE_SORT_ASSISTS,g_assist_rows);
    if(club<=0) return;
    g_club_goal_count=native_club_career_leaders(club,FCE_CAREER_GOALS,g_club_goal_rows);
    g_club_assist_count=native_club_career_leaders(club,FCE_CAREER_ASSISTS,g_club_assist_rows);
    g_club_minutes_count=native_club_career_leaders(club,FCE_CAREER_MINUTES,g_club_minutes_rows);
    g_club_yellow_count=native_club_career_leaders(club,FCE_CAREER_YELLOW_CARDS,g_club_yellow_rows);
    g_club_red_count=native_club_career_leaders(club,FCE_CAREER_RED_CARDS,g_club_red_rows);
    g_next_match_selection_result=FCE_OK;
    if(native_view.fixture_count>0) {
        selection_date=native_view.date;
        if(!fce_date_valid(selection_date)) {
            /* Pre-season can publish its fixtures before CalendarManager's
             * current date is ready. The snapshot itself is already scoped
             * to this career, so choose its earliest unplayed club fixture. */
            selection_date=0;
            g_next_match_date_fallback=1;
        }
        g_next_match_selection_result=fce_select_club_fixtures(
            native_view.fixtures,native_view.fixture_count,club,selection_date,
            FCE_UNPLAYED,fixtures,10,&count);
        if(g_next_match_selection_result==FCE_OK) {
            g_upcoming_count=count;
            if(count>0) {
                g_next_match_fixture=fixtures[0];
                g_next_match_fixture_valid=1;
            }
            for(i=0;i<count;++i) native_fixture(fixtures+i,g_upcoming_rows+i);
        }
    }
    if(fce_date_valid(native_view.date)) {
        if(fce_select_club_fixtures(native_view.fixtures,native_view.fixture_count,club,native_view.date,
              FCE_PLAYED,fixtures,10,&count)==FCE_OK) {
            g_club_previous_count=count;
            for(i=0;i<count;++i) native_fixture(fixtures+i,g_club_previous_rows+i);
        }
        /* "Rodada anterior" belongs to the competition displayed in the
         * centre table. A more recent cup match must not switch this card to
         * another tournament. */
        if(fce_model_round(&native_view,comp,club,1,fixtures,10,&count)==FCE_OK) {
            g_round_previous_count=count;
            for(i=0;i<count;++i) native_fixture(fixtures+i,g_round_previous_rows+i);
        }
        if(fce_model_round(&native_view,comp,club,0,fixtures,10,&count)==FCE_OK) {
            g_round_next_count=count;
            for(i=0;i<count;++i) native_fixture(fixtures+i,g_round_next_rows+i);
        }
    }
    /* Keep the native competition currently displayed as the first page.
     * Additional pages are discovered only when this club appears in the
     * standings or fixtures. This also includes knockout cups that do not
     * expose a league table yet. */
    /* The page selected by FIFA is always slot zero, even during the short
     * startup window before its draw/standings rows are materialized. */
    native_add_club_competition(comp,club,0);
    /* Fixtures are the strongest participation evidence. Use the earliest
     * fixture of each root so a pre-season tour cannot lose its page merely
     * because the native service returned competitions in another order. */
    native_add_club_fixture_competitions(club);
    for(i=0;i<native_view.standing_count && g_competition_count<COMPETITION_TAB_CAPACITY;++i) {
        const FceStanding *st=native_view.standings+i;
        int root=fce_model_ancestor(&native_view,st->competition_object,3);
        if(st->team==club && native_competition_is_active_for_club(root,club,comp))
            native_add_club_competition(st->competition_object,club,st->competition_object);
    }
    for(i=0;i<g_competition_count;++i) native_build_competition_tab(i,club);
    (void)native_fce_snapshot_write();
    if(g_competition_count>0) {
        size_t row_count=g_competition_tab_row_counts[0];
        size_t j;
        for(j=0;j<row_count && j<20;++j) {
            g_competition_league_rows[j].rank=g_competition_tab_rows[0][j].rank;
            g_competition_league_rows[j].team_id=g_competition_tab_rows[0][j].team_id;
            g_competition_league_rows[j].played=g_competition_tab_rows[0][j].played;
            g_competition_league_rows[j].points=g_competition_tab_rows[0][j].points;
        }
    }
}
static void native_form(void *provider,int row,int club) {
    const FceFixture *best[5]={0}; size_t count=0,i,j,limit=0;
    int standing=(int)InterlockedCompareExchange(&g_standing_competition_id,0,0);
    int comp=fce_model_ancestor(&native_view,(int)g_active_competition_id,3);
    if(comp<0) comp=fce_model_ancestor(&native_view,standing,3);
    if(row>=0 && row<20 && g_standing_rows[row].metrics_ready)
        limit=fce_form_dot_limit(5,(unsigned)g_standing_rows[row].played);
    if(comp>=0 && limit) for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *f=native_view.fixtures+i;
        if(!f->played_raw || (f->home!=club && f->away!=club) ||
           native_fixture_root(f)!=comp ||
           (fce_date_valid(native_view.date) && f->date_raw>native_view.date)) continue;
        for(j=0;j<count;++j) if(f->date_raw>best[j]->date_raw ||
            (f->date_raw==best[j]->date_raw && f->id>best[j]->id)) break;
        if(j<limit) {
            size_t k=count<limit?count:limit-1;
            while(k>j) { best[k]=best[k-1]; --k; }
            best[j]=f; if(count<limit) ++count;
        }
    }
    for(i=0;i<5;++i) {
        char key[48]; int asset=FORM_ASSET_EMPTY;
        if(i>=5-count) {
            const FceFixture *f=best[4-i];
            int gf=f->home==club?f->home_score:f->away_score;
            int ga=f->home==club?f->away_score:f->home_score;
            asset=gf>ga?FORM_ASSET_WIN:gf<ga?FORM_ASSET_LOSS:FORM_ASSET_DRAW;
        }
        snprintf(key,sizeof(key),"FORM_%d_%u",row,(unsigned)i);
        publish_int_field(provider,key,asset);
        publish_visibility_field(provider,key,asset!=FORM_ASSET_EMPTY);
    }
}

static void native_publish_competition_tabs(void *provider) {
    size_t page,row;
    for(page=1;page<g_competition_count && page<COMPETITION_TAB_CAPACITY;++page) {
        CompetitionSummary *summary=g_competition_rows+page;
        CompetitionTabKnockout *ko=g_competition_tab_knockout+page;
        size_t row_count=g_competition_tab_row_counts[page];
        char key[64],value[256],name[128];
        snprintf(key,sizeof(key),"CT%u_TITLE",(unsigned)page);
        publish_string_field(provider,key,summary->title_key);
        snprintf(key,sizeof(key),"CT%u_LOGO",(unsigned)page);
        publish_int_field(provider,key,summary->league_id>0?summary->league_id:FORM_ASSET_EMPTY);
        {
            const char *headers[]={"HEADER","PLAYEDLABEL","WDL_LABEL","GOALS_LABEL","POINTSLABEL"};
            size_t k;
            for(k=0;k<sizeof(headers)/sizeof(headers[0]);++k) {
                snprintf(key,sizeof(key),"CT%u_%s",(unsigned)page,headers[k]);
                publish_visibility_field(provider,key,row_count>0);
            }
        }
        for(row=0;row<COMPETITION_TAB_ROW_CAPACITY;++row) {
            CompetitionTabRow empty,*item; BOOL visible=row<row_count;
            memset(&empty,0,sizeof(empty));item=visible?&g_competition_tab_rows[page][row]:&empty;
            {
                const char *suffixes[]={"ROW","RANK","LOGO","NAME","PLAYED","WDL","GOALS","POINTS"};
                size_t k;
                for(k=0;k<sizeof(suffixes)/sizeof(suffixes[0]);++k) {
                    snprintf(key,sizeof(key),"CT%u_%s%u",(unsigned)page,suffixes[k],(unsigned)row);
                    publish_visibility_field(provider,key,visible);
                }
            }
            snprintf(key,sizeof(key),"CT%u_RANK%u",(unsigned)page,(unsigned)row);
            publish_int_field(provider,key,item->rank);
            snprintf(key,sizeof(key),"CT%u_LOGO%u",(unsigned)page,(unsigned)row);
            publish_int_field(provider,key,item->team_id>0?item->team_id:FORM_ASSET_EMPTY);
            native_team_name(item->team_id,name,sizeof(name));
            snprintf(key,sizeof(key),"CT%u_NAME%u",(unsigned)page,(unsigned)row);
            publish_string_field(provider,key,name);
            snprintf(key,sizeof(key),"CT%u_PLAYED%u",(unsigned)page,(unsigned)row);
            publish_int_field(provider,key,item->played);
            snprintf(value,sizeof(value),"%2d    %2d    %2d",item->won,item->drawn,item->lost);
            snprintf(key,sizeof(key),"CT%u_WDL%u",(unsigned)page,(unsigned)row);
            publish_string_field(provider,key,value);
            snprintf(value,sizeof(value),"%3d   %3d   %3d",item->goals_for,item->goals_against,
                item->goals_for-item->goals_against);
            snprintf(key,sizeof(key),"CT%u_GOALS%u",(unsigned)page,(unsigned)row);
            publish_string_field(provider,key,value);
            snprintf(key,sizeof(key),"CT%u_POINTS%u",(unsigned)page,(unsigned)row);
            publish_int_field(provider,key,item->points);
        }
        {
            const char *suffixes[]={"KO_BACKGROUND","KO_HOME_LOGO","KO_AWAY_LOGO","KO_HOME_NAME",
                "KO_AWAY_NAME","KO_INFO","KO_SCORE"}; size_t k;
            for(k=0;k<sizeof(suffixes)/sizeof(suffixes[0]);++k) {
                snprintf(key,sizeof(key),"CT%u_%s",(unsigned)page,suffixes[k]);
                publish_visibility_field(provider,key,ko->visible!=0);
            }
        }
        snprintf(key,sizeof(key),"CT%u_KO_HOME_LOGO",(unsigned)page);
        publish_int_field(provider,key,ko->home_team>0?ko->home_team:FORM_ASSET_EMPTY);
        snprintf(key,sizeof(key),"CT%u_KO_AWAY_LOGO",(unsigned)page);
        publish_int_field(provider,key,ko->away_team>0?ko->away_team:FORM_ASSET_EMPTY);
        native_team_name(ko->home_team,name,sizeof(name));
        snprintf(key,sizeof(key),"CT%u_KO_HOME_NAME",(unsigned)page);
        publish_string_field(provider,key,name);
        native_team_name(ko->away_team,name,sizeof(name));
        snprintf(key,sizeof(key),"CT%u_KO_AWAY_NAME",(unsigned)page);
        publish_string_field(provider,key,name);
        {
            char stage_name[64];
            native_knockout_stage_label(ko->stage,ko->round,stage_name,sizeof(stage_name));
            if(ko->date>0) snprintf(value,sizeof(value),"%s  |  %02d/%02d  %02d:%02d",
                stage_name,ko->date%100,(ko->date/100)%100,ko->time/100,ko->time%100);
            else lstrcpynA(value,stage_name,sizeof(value));
        }
        snprintf(key,sizeof(key),"CT%u_KO_INFO",(unsigned)page);
        publish_string_field(provider,key,value);
        if(ko->visible && ko->played) snprintf(value,sizeof(value),"%d - %d",ko->home_score,ko->away_score);
        else lstrcpynA(value,"-",sizeof(value));
        snprintf(key,sizeof(key),"CT%u_KO_SCORE",(unsigned)page);
        publish_string_field(provider,key,value);
        for(row=0;row<COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY;++row) {
            CompetitionTabKnockout empty_history,*history;
            BOOL history_visible=row<g_competition_tab_knockout_history_counts[page];
            char home_name[128],away_name[128];
            memset(&empty_history,0,sizeof(empty_history));
            history=history_visible?&g_competition_tab_knockout_history[page][row]:&empty_history;
            native_team_name(history->home_team,home_name,sizeof(home_name));
            native_team_name(history->away_team,away_name,sizeof(away_name));
            if(history_visible) snprintf(value,sizeof(value),"%s%02d/%02d   %s   %d - %d   %s",
                row==0?"ULTIMOS:  ":"",history->date%100,(history->date/100)%100,
                home_name,history->home_score,history->away_score,away_name);
            else value[0]=0;
            snprintf(key,sizeof(key),"CT%u_KO_HISTORY%u",(unsigned)page,(unsigned)row);
            publish_string_field(provider,key,value);
            publish_visibility_field(provider,key,history_visible);
        }
    }
}
static void publish_coach_record(void *provider) {
    char record[160], efficiency[96], home_efficiency[32], away_efficiency[32];
    int total, wins_slots, draws_slots, losses_slots, i;
    char key[64];
    publish_int_field(provider,"COACH_GAMES",g_coach_record.games);
    publish_int_field(provider,"COACH_WINS",g_coach_record.wins);
    publish_int_field(provider,"COACH_DRAWS",g_coach_record.draws);
    publish_int_field(provider,"COACH_LOSSES",g_coach_record.losses);
    publish_int_field(provider,"COACH_POINTS",g_coach_record.points);
    publish_int_field(provider,"COACH_PERCENT",g_coach_record.percent);
    snprintf(record,sizeof(record),"JOGOS %d     VITORIAS %d     EMPATES %d     DERROTAS %d",
        g_coach_record.games,g_coach_record.wins,g_coach_record.draws,g_coach_record.losses);
    /* Keep this binding to one short value. The label and points used to wrap
     * inside the 418px tile and collide with the W/D/L captions. */
    snprintf(efficiency,sizeof(efficiency),"%d%%",g_coach_record.percent);
    snprintf(home_efficiency,sizeof(home_efficiency),"%d%%",g_coach_record.home_percent);
    snprintf(away_efficiency,sizeof(away_efficiency),"%d%%",g_coach_record.away_percent);
    publish_string_field(provider,"COACH_RECORD",record);
    publish_string_field(provider,"COACH_EFFICIENCY",efficiency);
    publish_string_field(provider,"COACH_HOME_EFFICIENCY",home_efficiency);
    publish_visibility_field(provider,"COACH_HOME_EFFICIENCY",g_coach_record.home_games>0);
    publish_string_field(provider,"COACH_AWAY_EFFICIENCY",away_efficiency);
    publish_visibility_field(provider,"COACH_AWAY_EFFICIENCY",g_coach_record.away_games>0);

    /* The scout summary uses a native donut. The career hub layout cannot
     * import that screen's internal shape directly, so it uses 16 transparent
     * sector layers. Allocate the sectors in W/D/L order, preserving the same
     * proportions as the record shown beside the chart. */
    total=g_coach_record.wins+g_coach_record.draws+g_coach_record.losses;
    wins_slots=total>0?(g_coach_record.wins*16+total/2)/total:0;
    draws_slots=total>0?(g_coach_record.draws*16+total/2)/total:0;
    if(wins_slots>16) wins_slots=16;
    if(draws_slots>16-wins_slots) draws_slots=16-wins_slots;
    losses_slots=16-wins_slots-draws_slots;
    for(i=0;i<16;++i) {
        snprintf(key,sizeof(key),"MYTEAM_DONUT_W%02d",i);
        publish_visibility_field(provider,key,total>0 && i<wins_slots);
        snprintf(key,sizeof(key),"MYTEAM_DONUT_D%02d",i);
        publish_visibility_field(provider,key,total>0 && i>=wins_slots && i<wins_slots+draws_slots);
        snprintf(key,sizeof(key),"MYTEAM_DONUT_L%02d",i);
        publish_visibility_field(provider,key,total>0 && i>=wins_slots+draws_slots && i<wins_slots+draws_slots+losses_slots);
    }
}

static void native_publish_club_profile(void *provider) {
    char stadium_name[160],stadium_config[256],stadium_image[256];
    char fallback_name[160],fallback_image[256],capacity_text[64],key[64];
    char stadium_location[128];
    int fallback_capacity=0,domestic=0,international=0,fallback_ok;
    int reputation_stars=0,i;
    if(!provider) return;
    publish_string_field(provider,"MYTEAM_CLUB_PRESTIGE","");
    publish_visibility_field(provider,"MYTEAM_CLUB_PRESTIGE",FALSE);
    for(i=0;i<5;++i) {
        snprintf(key,sizeof(key),"MYTEAM_CLUB_PRESTIGE_STAR%d_ACTIVE",i);
        publish_visibility_field(provider,key,FALSE);
        snprintf(key,sizeof(key),"MYTEAM_CLUB_PRESTIGE_STAR%d_INACTIVE",i);
        publish_visibility_field(provider,key,FALSE);
    }
    publish_string_field(provider,"MYTEAM_SQUAD_VALUE","");
    publish_visibility_field(provider,"MYTEAM_SQUAD_VALUE",FALSE);
    publish_string_field(provider,"MYTEAM_STADIUM_NAME","");
    publish_visibility_field(provider,"MYTEAM_STADIUM_NAME",FALSE);
    publish_string_field(provider,"MYTEAM_STADIUM_CAPACITY","");
    publish_visibility_field(provider,"MYTEAM_STADIUM_CAPACITY",FALSE);
    publish_string_field(provider,"MYTEAM_STADIUM_IMAGE","");
    publish_visibility_field(provider,"MYTEAM_STADIUM_IMAGE",FALSE);

    stadium_name[0]=0; stadium_config[0]=0; stadium_image[0]=0;
    stadium_location[0]=0;
    fallback_name[0]=0; fallback_image[0]=0;
    fallback_ok=native_game_stadium_fallback(native_club,fallback_name,
        sizeof(fallback_name),&fallback_capacity,fallback_image,
        sizeof(fallback_image),&domestic,&international);
    if(native_team_stadium(native_club,stadium_name,sizeof(stadium_name),
        NULL,0,NULL,0)) {
        publish_string_field(provider,"MYTEAM_STADIUM_NAME",stadium_name);
        publish_visibility_field(provider,"MYTEAM_STADIUM_NAME",TRUE);
    } else if(fallback_ok && fallback_name[0]) {
        publish_string_field(provider,"MYTEAM_STADIUM_NAME",fallback_name);
        publish_visibility_field(provider,"MYTEAM_STADIUM_NAME",TRUE);
    }
    if(native_team_stadium_config(native_club,stadium_config,sizeof(stadium_config))) {
        native_stadium_location(stadium_config,stadium_location,sizeof(stadium_location));
        native_stadium_image_key(stadium_config,stadium_image,sizeof(stadium_image));
    }
    if(!stadium_image[0] && fallback_ok && fallback_image[0])
        native_stadium_image_key(fallback_image,stadium_image,sizeof(stadium_image));
    if(stadium_image[0]) {
        publish_string_field(provider,"MYTEAM_STADIUM_IMAGE",stadium_image);
        publish_visibility_field(provider,"MYTEAM_STADIUM_IMAGE",TRUE);
    }
    if(fallback_ok && fallback_capacity>0) {
        snprintf(capacity_text,sizeof(capacity_text),"%d",fallback_capacity);
        publish_string_field(provider,"MYTEAM_STADIUM_CAPACITY",capacity_text);
        publish_visibility_field(provider,"MYTEAM_STADIUM_CAPACITY",TRUE);
    }
    if(fallback_ok && (domestic>0 || international>0)) {
        reputation_stars=native_reputation_star_count(domestic,international);
        publish_int_field(provider,"MYTEAM_CLUB_PRESTIGE",
            NATIVE_REPUTATION_ASSET_BASE+reputation_stars);
        publish_visibility_field(provider,"MYTEAM_CLUB_PRESTIGE",TRUE);
        for(i=0;i<5;++i) {
            snprintf(key,sizeof(key),"MYTEAM_CLUB_PRESTIGE_STAR%d_ACTIVE",i);
            publish_visibility_field(provider,key,i<reputation_stars);
            snprintf(key,sizeof(key),"MYTEAM_CLUB_PRESTIGE_STAR%d_INACTIVE",i);
            publish_visibility_field(provider,key,i>=reputation_stars);
        }
    }
}

typedef struct NativeInjuryCandidate {
    int player;
    int weeks;
} NativeInjuryCandidate;

/* Query both runtime roster tables. Some career saves expose injury weeks on
 * teamplayerlinks while temp_teamplayerlinks is a valid but empty table. The
 * stock InjuryList capture remains the authoritative fallback for localized
 * status and return-time strings. */
static SIZE_T native_query_injury_table(
    const char *table,
    int club,
    NativeInjuryCandidate *out,
    SIZE_T capacity,
    int *query_valid)
{
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,ok=0,row_count=0;
    SIZE_T found=0,i;
    void *backend;
    if(query_valid) *query_valid=0;
    if(!table || !out || !capacity || !native_names
        || !native_name_db.query_init || !native_name_db.where_int
        || !native_name_db.result_init || !native_name_db.count
        || !native_name_db.integer || !native_name_db.result_free
        || !native_name_db.query_free || club<=0)
        return 0;
    memset(out,0,sizeof(*out)*capacity);
    if(!is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=
                (void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,table);
            query_ready=1;
            native_name_db.where_int(query,"teamid",0,club);
            native_name_db.result_init(&result);
            result_ready=1;
            execute(backend,query,&result);
            row_count=native_name_db.count(&result);
            if(row_count<0) row_count=0;
            if(row_count>512) row_count=512;
            for(i=0;i<(SIZE_T)row_count && found<capacity;++i) {
                int player=native_name_db.integer(&result,(int)i,"playerid");
                int weeks=native_name_db.integer(&result,(int)i,"injury");
                if(player>0 && weeks>0 && weeks<=35) {
                    out[found].player=player;
                    out[found].weeks=weeks;
                    ++found;
                }
            }
            ok=1;
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        ok=0;
        found=0;
    }
    if(query_valid) *query_valid=ok;
    return found;
}

static SIZE_T native_live_injury_rows(
    int club,
    InjuryRow *out,
    SIZE_T capacity,
    int *query_valid,
    int *query_source)
{
    NativeInjuryCandidate candidates[128];
    int temp_valid=0,roster_valid=0;
    SIZE_T found=0,i,j;
    if(query_valid) *query_valid=0;
    if(query_source) *query_source=0;
    if(!out || !capacity) return 0;
    memset(candidates,0,sizeof(candidates));
    found=native_query_injury_table("temp_teamplayerlinks",club,
        candidates,sizeof(candidates)/sizeof(candidates[0]),&temp_valid);
    if(found>0) {
        if(query_source) *query_source=2;
    } else {
        found=native_query_injury_table("teamplayerlinks",club,
            candidates,sizeof(candidates)/sizeof(candidates[0]),&roster_valid);
        if(found>0 && query_source) *query_source=3;
    }
    if(query_valid) *query_valid=temp_valid || roster_valid;
    if(!found) return 0;
    /* Show the longest absences first, capped to the five visible rows. */
    for(i=0;i<found;++i) for(j=i+1;j<found;++j) {
        if(candidates[j].weeks>candidates[i].weeks) {
            NativeInjuryCandidate swap=candidates[i];
            candidates[i]=candidates[j];
            candidates[j]=swap;
        }
    }
    if(found>capacity) found=capacity;
    memset(out,0,sizeof(InjuryRow)*capacity);
    for(i=0;i<found;++i) {
        out[i].head=candidates[i].player;
        native_player_label(candidates[i].player,out[i].name,sizeof(out[i].name));
        if(!out[i].name[0])
            snprintf(out[i].name,sizeof(out[i].name),"#%d",candidates[i].player);
        snprintf(out[i].length,sizeof(out[i].length),"%d SEM.",candidates[i].weeks);
        lstrcpynA(out[i].injury,"LESIONADO",sizeof(out[i].injury));
    }
    return found;
}

static int native_career_user_exists(int club,int *query_valid) {
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,exists=0,ok=0;
    void *backend;
    if(query_valid) *query_valid=0;
    if(!native_names || !native_name_db.query_init || !native_name_db.where_int
        || !native_name_db.result_init || !native_name_db.count
        || !native_name_db.result_free || !native_name_db.query_free || club<=0)
        return 0;
    if(!is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=
                (void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,"career_users"); query_ready=1;
            native_name_db.where_int(query,"clubteamid",0,club);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            exists=native_name_db.count(&result)>0;
            ok=1;
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { ok=0; exists=0; }
    if(query_valid) *query_valid=ok;
    return exists;
}

static int native_league_trophy_asset(int league_id) {
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,asset=0;
    void *backend;
    if(league_id<=0 || !native_names || !native_name_db.query_init
        || !native_name_db.where_int || !native_name_db.result_init
        || !native_name_db.count || !native_name_db.integer
        || !native_name_db.result_free || !native_name_db.query_free)
        return 0;
    if(!is_readable_range(native_names,sizeof(void *))) return 0;
    backend=*(void **)native_names;
    if(!backend || !is_readable_range(backend,sizeof(void *))) return 0;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=
                (void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,"cz_leagues"); query_ready=1;
            native_name_db.where_int(query,"leagueid",0,league_id);
            native_name_db.result_init(&result); result_ready=1;
            execute(backend,query,&result);
            if(native_name_db.count(&result)>0)
                asset=native_name_db.integer(&result,0,"trophyid");
        } __finally {
            if(result_ready) native_name_db.result_free(&result);
            if(query_ready) native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { asset=0; }
    if(asset>0 && asset<=65535) {
        char path[MAX_PATH];
        snprintf(path,sizeof(path),"%s\\data\\ui\\imgAssets\\trophy\\t%d.dds",
            g_game_dir,asset);
        if(GetFileAttributesA(path)!=INVALID_FILE_ATTRIBUTES) return asset;
    }
    /* This install has an empty cz_leagues table, but the extracted game
     * assets pair competition IDs with t<ID>.dds (including the active
     * competition visual IDs). Use that exact, file-verified key as fallback. */
    if(league_id>0 && league_id<=65535) {
        char path[MAX_PATH];
        snprintf(path,sizeof(path),"%s\\data\\ui\\imgAssets\\trophy\\t%d.dds",
            g_game_dir,league_id);
        if(GetFileAttributesA(path)!=INVALID_FILE_ATTRIBUTES) return league_id;
    }
    return 0;
}

typedef struct NativeActiveCompetition {
    int root;
    int logo;
    int title_asset;
    int trophy_asset;
    int next_date;
    int next_time;
} NativeActiveCompetition;

static int native_active_competition_trophy(int competition_id,int title_asset) {
    int trophy=native_league_trophy_asset(competition_id);
    /* Some FCE competition roots are wrapper IDs while the visual asset ID
     * is the installed compdata key. Resolve cz_leagues.trophyid first; when
     * that table has no row, native_league_trophy_asset accepts the exact
     * visual ID only if its t<ID>.dds is present. */
    if(trophy<=0 && title_asset>0 && title_asset!=competition_id)
        trophy=native_league_trophy_asset(title_asset);
    return trophy;
}

static int native_league_logo_asset_exists(int asset) {
    return calendar_competition_asset_exists(asset);
}
static int native_active_competition_logo(int root,int visual_asset) {
    int logo=native_logo(root);
    (void)visual_asset;
    return native_league_logo_asset_exists(logo)?logo:0;
}

static void native_active_competition_add(NativeActiveCompetition *rows,
    SIZE_T *count,SIZE_T capacity,int root,int visual_asset,int date,int time) {
    SIZE_T i;
    int logo;
    if(!rows || !count || root<=0) return;
    logo=native_active_competition_logo(root,visual_asset);
    for(i=0;i<*count && rows[i].root!=root;++i) {}
    if(i==*count) {
        if(*count>=capacity) return;
        memset(rows+i,0,sizeof(rows[i]));
        rows[i].root=root;
        rows[i].title_asset=visual_asset;
        rows[i].logo=logo;
        rows[i].trophy_asset=native_active_competition_trophy(root,visual_asset);
        rows[i].next_date=date;
        rows[i].next_time=time;
        ++*count;
        return;
    }
    if(rows[i].logo<=0 && logo>0) rows[i].logo=logo;
    if(rows[i].title_asset<=0 && visual_asset>0) rows[i].title_asset=visual_asset;
    if(rows[i].trophy_asset<=0)
        rows[i].trophy_asset=native_active_competition_trophy(root,visual_asset);
    if(date>rows[i].next_date ||
       (date==rows[i].next_date && time>rows[i].next_time)) {
        rows[i].next_date=date;
        rows[i].next_time=time;
    }
}

static int native_history_title_count_for_competition(
    const NativeActiveCompetition *competition,int *known) {
    int best=0;
    SIZE_T i;
    if(known) *known=0;
    if(!competition || !g_trophy_summary.available) return 0;
    for(i=0;i<(SIZE_T)g_trophy_summary.history_count;++i) {
        int league_id=g_trophy_summary.history_league_ids[i];
        int matches=league_id==competition->root || league_id==competition->title_asset;
        if(!matches && competition->logo>0)
            matches=native_history_league_logo(league_id)==competition->logo;
        if(matches) {
            int count=g_trophy_summary.history_league_titles[i];
            if(count>best) best=count;
            if(known) *known=1;
        }
    }
    return best;
}

static SIZE_T native_collect_active_competitions(NativeActiveCompetition *out,
    SIZE_T capacity) {
    NativeActiveCompetition all[48];
    SIZE_T count=0,i;
    memset(all,0,sizeof(all));
    if(!out || !capacity || !native_club) return 0;
    /* The competition tabs are built only from competitions in which the
     * managed club actually participates. Seed this room from that same
     * authoritative list so a current cup/league appears even before its
     * first fixture, without showing unrelated future competitions. */
    for(i=0;i<g_competition_count;++i) {
        const CompetitionSummary *summary=g_competition_rows+i;
        if(summary->competition_id<=0) continue;
        native_active_competition_add(all,&count,
            sizeof(all)/sizeof(all[0]),summary->competition_id,
            summary->league_id,0,0);
    }
    /* The competition carousel is intentionally capped at five pages, but
     * the My Team summaries may show more than five tournaments. Seed the
     * same de-duplicated list from the club's stat roots as well, so a cup
     * that is present in the career data is not silently omitted here. */
    for(i=0;i<native_view.stat_count;++i) {
        const FceStat *stat=native_view.stats+i;
        FceCompetition resolved;
        int root,asset;
        if(stat->team!=native_club || stat->competition<0) continue;
        root=fce_model_ancestor(&native_view,stat->competition,3);
        if(root<=0) continue;
        asset=native_logo(root);
        if(fce_resolve_competition(native_view.nodes,native_view.node_count,
            root,&resolved)==FCE_OK && resolved.asset>0) asset=resolved.asset;
        native_active_competition_add(all,&count,
            sizeof(all)/sizeof(all[0]),root,asset,0,0);
    }
    /* Keep a recently completed competition visible too when it no longer
     * owns an active tab (for example, a finished knockout cup). */
    for(i=0;i<native_view.fixture_count;++i) {
        const FceFixture *fixture=native_view.fixtures+i;
        FceCompetition resolved;
        if(!fixture->played_raw ||
           (fixture->home!=native_club && fixture->away!=native_club)) continue;
        if(fce_resolve_competition(native_view.nodes,native_view.node_count,
            fixture->competition_object,&resolved)!=FCE_OK || resolved.competition<=0)
            continue;
        native_active_competition_add(all,&count,
            sizeof(all)/sizeof(all[0]),resolved.competition,resolved.asset,
            fixture->date_raw,fixture->time_raw);
    }
    if(count>capacity) count=capacity;
    memcpy(out,all,count*sizeof(*out));
    return count;
}

typedef struct NativeCompetitionStatRaw {
    int player;
    int root;
    int competition;
    int goals;
    int assists;
} NativeCompetitionStatRaw;

static int native_competition_stat_order(const void *a,const void *b) {
    const NativeCompetitionStatRaw *x=a,*y=b;
    if(x->player!=y->player) return (x->player>y->player)-(x->player<y->player);
    if(x->root!=y->root) return (x->root>y->root)-(x->root<y->root);
    if(x->competition!=y->competition)
        return (x->competition>y->competition)-(x->competition<y->competition);
    if(x->goals!=y->goals) return (x->goals>y->goals)-(x->goals<y->goals);
    return (x->assists>y->assists)-(x->assists<y->assists);
}

static int native_competition_stat_add(int current,int value) {
    if(value>0 && current>INT32_MAX-value) return INT32_MAX;
    return current+value;
}

/* Build one row per competition root. The raw career snapshot can expose a
 * root total together with its phase/stage rows, and it can repeat a row
 * through more than one service. Collapse exact duplicates by maximum first;
 * then trust the root total when it exists, otherwise sum the child phases.
 * This mirrors fce_model_career_leaders, but keeps the result grouped by
 * competition instead of by player. */
static void native_competition_stats_refresh(void) {
    NativeActiveCompetition active[8];
    NativeCompetitionStatRaw *raw=NULL;
    SIZE_T active_count,count,i,raw_count,unique_count;
    memset(g_competition_stat_rows,0,sizeof(g_competition_stat_rows));
    g_competition_stat_count=0;
    active_count=native_collect_active_competitions(active,
        sizeof(active)/sizeof(active[0]));
    count=active_count<sizeof(g_competition_stat_rows)/sizeof(g_competition_stat_rows[0])
        ?active_count:sizeof(g_competition_stat_rows)/sizeof(g_competition_stat_rows[0]);
    for(i=0;i<count;++i) {
        g_competition_stat_rows[i].root=active[i].root;
        g_competition_stat_rows[i].logo=active[i].logo;
        g_competition_stat_rows[i].title_asset=active[i].title_asset;
        snprintf(g_competition_stat_rows[i].title_key,
            sizeof(g_competition_stat_rows[i].title_key),"TrophyName_%d",
            active[i].title_asset>0?active[i].title_asset:active[i].root);
    }
    g_competition_stat_count=count;
    if(!native_club || !native_view.stat_count || !count) return;
    if(native_view.stat_count>SIZE_MAX/sizeof(*raw)) return;
    raw=malloc(native_view.stat_count*sizeof(*raw));
    if(!raw) return;
    for(i=0,raw_count=0;i<native_view.stat_count;++i) {
        const FceStat *stat=native_view.stats+i;
        int root;
        if(stat->team!=native_club || stat->player<0 || stat->competition<0) continue;
        root=fce_model_ancestor(&native_view,stat->competition,3);
        if(root<=0) continue;
        raw[raw_count].player=stat->player;
        raw[raw_count].root=root;
        raw[raw_count].competition=stat->competition;
        raw[raw_count].goals=stat->goals;
        raw[raw_count].assists=stat->assists;
        ++raw_count;
    }
    if(!raw_count) { free(raw); return; }
    qsort(raw,raw_count,sizeof(*raw),native_competition_stat_order);
    for(i=0,unique_count=0;i<raw_count;) {
        NativeCompetitionStatRaw selected=raw[i];
        SIZE_T j=i+1;
        while(j<raw_count && raw[j].player==selected.player &&
              raw[j].root==selected.root &&
              raw[j].competition==selected.competition) {
            if(raw[j].goals>selected.goals) selected.goals=raw[j].goals;
            if(raw[j].assists>selected.assists) selected.assists=raw[j].assists;
            ++j;
        }
        raw[unique_count++]=selected;
        i=j;
    }
    for(i=0;i<unique_count;) {
        SIZE_T end=i,k;
        int player=raw[i].player,root=raw[i].root;
        int root_goals=0,root_assists=0,child_goals=0,child_assists=0;
        int has_root=0,summary_index=-1;
        while(end<unique_count && raw[end].player==player && raw[end].root==root) {
            if(raw[end].competition==root) {
                if(!has_root || raw[end].goals>root_goals) root_goals=raw[end].goals;
                if(!has_root || raw[end].assists>root_assists) root_assists=raw[end].assists;
                has_root=1;
            } else {
                child_goals=native_competition_stat_add(child_goals,raw[end].goals);
                child_assists=native_competition_stat_add(child_assists,raw[end].assists);
            }
            ++end;
        }
        for(k=0;k<count && g_competition_stat_rows[k].root!=root;++k) {}
        if(k<count) summary_index=(int)k;
        if(summary_index>=0) {
            g_competition_stat_rows[summary_index].goals=native_competition_stat_add(
                g_competition_stat_rows[summary_index].goals,has_root?root_goals:child_goals);
            g_competition_stat_rows[summary_index].assists=native_competition_stat_add(
                g_competition_stat_rows[summary_index].assists,has_root?root_assists:child_assists);
        }
        i=end;
    }
    /* Do not leave empty competition slots between populated rows. A
     * competition with no goals and no assists has no useful line for this
     * page, so compact the remaining rows before publishing them. */
    {
        SIZE_T kept=0;
        for(i=0;i<g_competition_stat_count;++i) {
            if(g_competition_stat_rows[i].goals<=0 &&
               g_competition_stat_rows[i].assists<=0) continue;
            if(kept!=i) g_competition_stat_rows[kept]=g_competition_stat_rows[i];
            ++kept;
        }
        for(i=kept;i<g_competition_stat_count;++i)
            memset(g_competition_stat_rows+i,0,sizeof(g_competition_stat_rows[i]));
        g_competition_stat_count=kept;
    }
    free(raw);
}

static void native_publish_competition_stats(void *provider) {
    SIZE_T i;
    char key[64],value[32];
    native_competition_stats_refresh();
    for(i=0;i<8;++i) {
        int visible=i<g_competition_stat_count;
        const NativeCompetitionStatSummary *row=visible?g_competition_stat_rows+i:NULL;
        snprintf(key,sizeof(key),"MYTEAM_COMP_STATS_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,visible);
        snprintf(key,sizeof(key),"MYTEAM_COMP_STATS_ICON%u",(unsigned)i);
        publish_int_field(provider,key,visible && row->logo>0?row->logo:FORM_ASSET_EMPTY);
        publish_visibility_field(provider,key,visible && row->logo>0);
        snprintf(key,sizeof(key),"MYTEAM_COMP_STATS_NAME%u",(unsigned)i);
        publish_string_field(provider, key, visible?row->title_key:"");
        publish_visibility_field(provider,key,visible);
        snprintf(key,sizeof(key),"MYTEAM_COMP_STATS_GOALS%u",(unsigned)i);
        if(visible && row->goals>0) snprintf(value,sizeof(value),"%d",row->goals);
        else value[0]=0;
        publish_string_field(provider,key,value);
        publish_visibility_field(provider,key,value[0]!=0);
        snprintf(key,sizeof(key),"MYTEAM_COMP_STATS_ASSISTS%u",(unsigned)i);
        if(visible && row->assists>0) snprintf(value,sizeof(value),"%d",row->assists);
        else value[0]=0;
        publish_string_field(provider,key,value);
        publish_visibility_field(provider,key,value[0]!=0);
    }
}

static void publish_active_competitions(void *provider) {
    NativeActiveCompetition rows[8];
    SIZE_T count,i;
    char key[64],value[32];
    count=native_collect_active_competitions(rows,
        sizeof(rows)/sizeof(rows[0]));
    /* This is a permanent section label, not an empty-state message. */
    publish_visibility_field(provider,"MYTEAM_ACTIVE_COMP_TITLE",TRUE);
    for(i=0;i<8;++i) {
        int visible=i<count;
        int logo=visible?rows[i].logo:0;
        int trophy=visible?rows[i].trophy_asset:0;
        int title_count=0,count_known=0;
        snprintf(key,sizeof(key),"MYTEAM_ACTIVE_COMP_ICON%u",(unsigned)i);
        publish_int_field(provider,key,logo>0?logo:FORM_ASSET_EMPTY);
        publish_visibility_field(provider,key,visible && logo>0);
        snprintf(key,sizeof(key),"MYTEAM_ACTIVE_COMP_TROPHY%u",(unsigned)i);
        publish_int_field(provider,key,trophy>0?trophy:FORM_ASSET_EMPTY);
        publish_visibility_field(provider,key,visible && trophy>0);
        snprintf(key,sizeof(key),"MYTEAM_ACTIVE_COMP_COUNT%u",(unsigned)i);
        if(visible) title_count=native_history_title_count_for_competition(
            rows+i,&count_known);
        if(visible && !count_known && g_trophy_summary.available &&
           g_trophy_summary.domestic_titles==0 &&
           g_trophy_summary.continental_titles==0) {
            title_count=0;
            count_known=1;
        }
        if(!visible) value[0]=0;
        else if(count_known) snprintf(value,sizeof(value),"%d",title_count);
        else lstrcpynA(value,"-",sizeof(value));
        publish_string_field(provider,key,value);
        publish_visibility_field(provider,key,visible);
    }
}

static void native_publish_starting_xi(void *provider)
{
    SIZE_T slot;
    int segment,condition,bucket;
    char key[64];
    char kit_asset[64];
    BOOL visible;
    int kit_available=native_match_kit_key(
        native_club,0,kit_asset,sizeof(kit_asset));
    for(slot=0;slot<NATIVE_STARTING_XI_CAPACITY;++slot) {
        visible=slot<g_starting_xi.count &&
            g_starting_xi.players[slot]>0;
        snprintf(key,sizeof(key),"MYTEAM_XI_HEAD%u",(unsigned)slot);
        publish_visibility_field(provider,key,visible);
        publish_int_field(provider,key,
            visible?g_starting_xi.players[slot]:FORM_ASSET_EMPTY);
        snprintf(key,sizeof(key),"MYTEAM_XI_NAME%u",(unsigned)slot);
        publish_visibility_field(provider,key,visible);
        publish_string_field(provider,key,
            visible?g_starting_xi.names[slot]:"");
        snprintf(key,sizeof(key),"MYTEAM_XI_KIT%u",(unsigned)slot);
        publish_visibility_field(provider,key,visible && kit_available);
        publish_string_field(provider,key,
            visible && kit_available?kit_asset:"");
        snprintf(key,sizeof(key),"MYTEAM_XI_OVR%u",(unsigned)slot);
        publish_visibility_field(provider,key,
            visible && g_starting_xi.overall[slot]>0);
        publish_int_field(provider,key,
            visible && g_starting_xi.overall[slot]>0?
                g_starting_xi.overall[slot]:0);
        condition=g_starting_xi.condition[slot];
        bucket=condition>0?(condition+19)/20:0;
        if(bucket>5) bucket=5;
        snprintf(key,sizeof(key),"MYTEAM_XI_COND_BG%u",(unsigned)slot);
        publish_visibility_field(provider,key,visible);
        for(segment=0;segment<5;++segment) {
            snprintf(key,sizeof(key),"MYTEAM_XI_COND%u_%d",
                (unsigned)slot,segment);
            publish_visibility_field(provider,key,
                visible && segment<bucket);
        }
    }
    publish_visibility_field(provider,"MYTEAM_XI_STATUS",
        g_starting_xi.count==0);
    publish_string_field(provider,"MYTEAM_XI_STATUS",
        g_starting_xi.count>0?"":"ESCALACAO NAO DISPONIVEL");
}

static void publish_trophy_room(void *provider) {
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,user_query_valid=0,career_user;
    int row_count=0,query_ok=0;
    int league_ids[64],league_counts[64];
    SIZE_T history_count=0,i;
    void *backend;
    char text[128];
    memset(&g_trophy_summary,0,sizeof(g_trophy_summary));
    memset(league_ids,0,sizeof(league_ids));
    memset(league_counts,0,sizeof(league_counts));
    career_user=native_career_user_exists(native_club,&user_query_valid);
    backend=NULL;
    if(native_names && is_readable_range(native_names,sizeof(void *)))
        backend=*(void **)native_names;
    if(user_query_valid && career_user && backend && is_readable_range(backend,sizeof(void *))
        && native_name_db.query_init && native_name_db.where_int
        && native_name_db.result_init && native_name_db.count
        && native_name_db.integer && native_name_db.result_free && native_name_db.query_free) {
        __try {
            __try {
                void (*execute)(void *,void *,void *)=
                    (void (*)(void *,void *,void *))(*(void ***)backend)[1];
                native_name_db.query_init(query,1,"career_managerhistory"); query_ready=1;
                native_name_db.where_int(query,"teamid",0,native_club);
                native_name_db.result_init(&result); result_ready=1;
                execute(backend,query,&result);
                row_count=native_name_db.count(&result);
                if(row_count<0) row_count=0;
                if(row_count>256) row_count=256;
                for(i=0;i<(SIZE_T)row_count;++i) {
                    int league_count=native_name_db.integer(&result,(int)i,"leaguetrophies");
                    int domestic_count=native_name_db.integer(&result,(int)i,"domesticcuptrophies");
                    int continental_count=native_name_db.integer(&result,(int)i,"continentalcuptrophies");
                    int league=native_name_db.integer(&result,(int)i,"leagueid");
                    if(league_count>0)
                        g_trophy_summary.league_titles+=league_count;
                    if(league>0) {
                        SIZE_T j;
                        for(j=0;j<history_count && league_ids[j]!=league;++j) {}
                        if(j<history_count) {
                            if(league_count>0) league_counts[j]+=league_count;
                        } else if(history_count<64) {
                            league_ids[history_count]=league;
                            league_counts[history_count]=league_count>0?league_count:0;
                            ++history_count;
                        }
                    }
                    if(domestic_count>0) g_trophy_summary.domestic_titles+=domestic_count;
                    if(continental_count>0) g_trophy_summary.continental_titles+=continental_count;
                }
                query_ok=1;
            } __finally {
                if(result_ready) native_name_db.result_free(&result);
                if(query_ready) native_name_db.query_free(query);
            }
        } __except(EXCEPTION_EXECUTE_HANDLER) { query_ok=0; }
    }
    g_trophy_summary.available=query_ok;
    g_trophy_summary.history_count=(int)history_count;
    for(i=0;i<history_count;++i) {
        g_trophy_summary.history_league_ids[i]=league_ids[i];
        g_trophy_summary.history_league_titles[i]=league_counts[i];
    }
    g_trophy_summary.trophy_count=g_trophy_summary.league_titles
        +g_trophy_summary.domestic_titles+g_trophy_summary.continental_titles;
    publish_int_field(provider,"MYTEAM_TROPHY_TOTAL",g_trophy_summary.trophy_count);
    publish_visibility_field(provider,"MYTEAM_TROPHY_TOTALS",g_trophy_summary.available);
    if(!g_trophy_summary.available)
        lstrcpynA(text,"HISTORICO NAO DISPONIVEL",sizeof(text));
    else if(g_trophy_summary.trophy_count==0)
        text[0]=0;
    else
        snprintf(text,sizeof(text),"%d TITULOS CONQUISTADOS",g_trophy_summary.trophy_count);
    publish_string_field(provider,"MYTEAM_TROPHY_STATUS",text);
    publish_visibility_field(provider,"MYTEAM_TROPHY_STATUS",text[0]!=0);
    publish_active_competitions(provider);
}


static void native_publish(void *provider) {
    char path[MAX_PATH],club_name[128]; FILE *log; size_t i;
    size_t club_stat_rows=0,club_stat_roots=0,club_stat_unmapped=0;
    SIZE_T goal_display_count,assist_display_count,minutes_display_count;
    SIZE_T yellow_display_count,red_display_count;
    SIZE_T injury_display_count=0;
    NativeActiveCompetition trophy_log_rows[8];
    SIZE_T trophy_log_count;
    int injury_source=0;
    int seen_roots[128];
    char kit_asset_ids[3][32];
    int kit_available[3];
    if(!provider) return;
    native_team_name(native_club,club_name,sizeof(club_name));
    native_squad_refresh();
    g_club_overall_count=native_club_overall_leaders(native_club,g_club_overall_rows);
    g_club_oldest_count=native_club_oldest_players(native_club,g_club_oldest_rows);
    native_publish_club_profile(provider);
    native_publish_starting_xi(provider);
    publish_int_field(provider,"TEAMLOGO",native_club>0?native_club:FORM_ASSET_EMPTY);
    /* The stock getArtAssetPath("kits", assetID) prepends "j" and appends
     * ".dds" without adding a kit suffix. Therefore assetID must be the
     * complete middle part of the real filename: <type>_<teamtechid>_0.
     * Example: 0_1043_0 -> imgAssets/kits/j0_1043_0.dds. teamkitid is only
     * the DB row ID and is not the thumbnail filename key. */
    kit_available[0]=native_match_kit_key(native_club,0,kit_asset_ids[0],sizeof(kit_asset_ids[0]));
    kit_available[1]=native_match_kit_key(native_club,1,kit_asset_ids[1],sizeof(kit_asset_ids[1]));
    kit_available[2]=native_match_kit_key(native_club,2,kit_asset_ids[2],sizeof(kit_asset_ids[2]));
    publish_string_field(provider,"TEAMKIT1",kit_available[0]?kit_asset_ids[0]:"");
    publish_visibility_field(provider,"TEAMKIT1",kit_available[0]);
    publish_string_field(provider,"TEAMKIT2",kit_available[1]?kit_asset_ids[1]:"");
    publish_visibility_field(provider,"TEAMKIT2",kit_available[1]);
    publish_string_field(provider,"TEAMKIT3",kit_available[2]?kit_asset_ids[2]:"");
    publish_visibility_field(provider,"TEAMKIT3",kit_available[2]);
    publish_string_field(provider,"TEAMNAME",club_name);
    publish_int_field(provider,"MYTEAM_SQUAD_TOTAL",g_squad_summary.total);
    publish_visibility_field(provider,"MYTEAM_SQUAD_TOTAL",g_squad_summary.available);
    publish_int_field(provider,"MYTEAM_SQUAD_AVERAGE_AGE",g_squad_summary.average_age);
    publish_visibility_field(provider,"MYTEAM_SQUAD_AVERAGE_AGE",g_squad_summary.age_count>0);
    publish_int_field(provider,"MYTEAM_SQUAD_AVERAGE_OVERALL",g_squad_summary.average_overall);
    publish_visibility_field(provider,"MYTEAM_SQUAD_AVERAGE_OVERALL",g_squad_summary.overall_count>0);
    publish_int_field(provider,"MYTEAM_SQUAD_GK",g_squad_summary.goalkeepers);
    publish_int_field(provider,"MYTEAM_SQUAD_DEF",g_squad_summary.defenders);
    publish_int_field(provider,"MYTEAM_SQUAD_MID",g_squad_summary.midfielders);
    publish_int_field(provider,"MYTEAM_SQUAD_ATT",g_squad_summary.attackers);
    /* The position counters are valid even when one position has zero
     * players. Publish each field while the roster query is available so the
     * layout renders 0 instead of leaving the four counters invisible. */
    publish_visibility_field(provider,"MYTEAM_SQUAD_GK",g_squad_summary.available);
    publish_visibility_field(provider,"MYTEAM_SQUAD_DEF",g_squad_summary.available);
    publish_visibility_field(provider,"MYTEAM_SQUAD_MID",g_squad_summary.available);
    publish_visibility_field(provider,"MYTEAM_SQUAD_ATT",g_squad_summary.available);
    publish_visibility_field(provider,"MYTEAM_SQUAD_POSITIONS",g_squad_summary.position_count>0);
    publish_competition_leader_states(provider,publish_top_assists(provider));
    publish_ranked_rows(provider,"CLUB_GOAL_",g_club_goal_rows,g_club_goal_count);
    publish_ranked_rows(provider,"CLUB_ASSIST_",g_club_assist_rows,g_club_assist_count);
    publish_ranked_rows(provider,"CLUB_OVERALL_",g_club_overall_rows,g_club_overall_count);
    publish_ranked_rows(provider,"CLUB_OLDEST_",g_club_oldest_rows,g_club_oldest_count);
    publish_ranked_rows(provider,"CLUB_MINUTES_",g_club_minutes_rows,g_club_minutes_count);
    publish_ranked_rows(provider,"CLUB_YELLOW_",g_club_yellow_rows,g_club_yellow_count);
    publish_ranked_rows(provider,"CLUB_RED_",g_club_red_rows,g_club_red_count);
    goal_display_count=g_club_goal_count>stock_stat_count_for_prefix("CLUB_GOAL_")
        ? g_club_goal_count : stock_stat_count_for_prefix("CLUB_GOAL_");
    assist_display_count=g_club_assist_count>stock_stat_count_for_prefix("CLUB_ASSIST_")
        ? g_club_assist_count : stock_stat_count_for_prefix("CLUB_ASSIST_");
    minutes_display_count=g_club_minutes_count>stock_stat_count_for_prefix("CLUB_MINUTES_")
        ? g_club_minutes_count : stock_stat_count_for_prefix("CLUB_MINUTES_");
    yellow_display_count=g_club_yellow_count>stock_stat_count_for_prefix("CLUB_YELLOW_")
        ? g_club_yellow_count : stock_stat_count_for_prefix("CLUB_YELLOW_");
    red_display_count=g_club_red_count>stock_stat_count_for_prefix("CLUB_RED_")
        ? g_club_red_count : stock_stat_count_for_prefix("CLUB_RED_");
    /* Each statistic has its own empty state. A populated card must clear
     * the old PARAM as well as hiding the field; otherwise a stale stock
     * message can remain painted over the player rows after a refresh. */
    publish_ranked_empty_state(provider,"MYTEAM_GOALS_EMPTY",goal_display_count);
    publish_ranked_empty_state(provider,"MYTEAM_ASSISTS_EMPTY",assist_display_count);
    publish_ranked_empty_state(provider,"MYTEAM_MINUTES_EMPTY",minutes_display_count);
    publish_ranked_empty_state(provider,"MYTEAM_YELLOW_EMPTY",yellow_display_count);
    publish_ranked_empty_state(provider,"MYTEAM_RED_EMPTY",red_display_count);
    for(i=0;i<5;++i) {
        char key[48];
        snprintf(key,sizeof(key),"MYTEAM_GOALS_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,i<goal_display_count);
        snprintf(key,sizeof(key),"MYTEAM_ASSISTS_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,i<assist_display_count);
        snprintf(key,sizeof(key),"MYTEAM_YELLOW_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,i<yellow_display_count);
        snprintf(key,sizeof(key),"MYTEAM_RED_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,i<red_display_count);
        snprintf(key,sizeof(key),"MYTEAM_OLDEST_ROW%u",(unsigned)i);
        publish_visibility_field(provider,key,i<g_club_oldest_count);
    }
    /* An empty/invalid-age banner is misleading here: the managed squad is
     * available and the carousel should simply render the rows it can obtain.
     * Keep the field permanently hidden so it never replaces the player list
     * with "DADOS DE IDADE INDISPONIVEIS" during a transient refresh. */
    publish_string_field(provider,"MYTEAM_OLDEST_EMPTY","");
    publish_visibility_field(provider,"MYTEAM_OLDEST_EMPTY",FALSE);
    publish_ranked_rows(provider,"SALARY_",g_salary_rows,g_salary_count);
    injury_display_count=publish_injury_rows(provider,&injury_source);
    publish_trophy_room(provider);
    native_publish_competition_stats(provider);
    publish_coach_record(provider);
    publish_upcoming_rows(provider); publish_next_match_card(provider);
    publish_club_previous_rows(provider); publish_round_rows(provider);
    publish_competitions(provider); native_publish_competition_tabs(provider); publish_bridge_status(provider);
    trophy_log_count=native_collect_active_competitions(trophy_log_rows,
        sizeof(trophy_log_rows)/sizeof(trophy_log_rows[0]));
    for(i=0;i<5;++i) {
        char key[48];
        snprintf(key,sizeof(key),"MYCOMP%u_RANK",(unsigned)i);
        publish_visibility_field(provider,key,i<g_competition_count && g_competition_rows[i].rank>0);
        snprintf(key,sizeof(key),"MYCOMP%u_POINTS",(unsigned)i);
        publish_visibility_field(provider,key,i<g_competition_count && g_competition_rows[i].rank>0);
    }
    for(i=0;i<20;++i) {
        char key[48],name[128]; int team=g_competition_league_rows[i].team_id;
        native_team_name(team,name,sizeof(name));
        snprintf(key,sizeof(key),"MYCOMP_LEAGUE_NAME%u",(unsigned)i);
        publish_string_field(provider,key,name);
    }
    /* The card log is a development artifact. All card fields have already
     * been published above, so production can return here without changing
     * the UI payload or its timing-sensitive behavior. */
    if(!fce_runtime_log_verbose()) return;
    snprintf(path,sizeof(path),"%s\\logs\\career_native_cards.log",g_mod_dir);
    log=fopen(path,"ab"); if(!log) return;
    fprintf(log,"kit_binding club=%d asset_teamtechid=%d available=%d/%d/%d TEAMKIT1_asset_id=%s TEAMKIT2_asset_id=%s TEAMKIT3_asset_id=%s\n",
        native_club,native_club,kit_available[0],kit_available[1],kit_available[2],
        kit_available[0]?kit_asset_ids[0]:"",
        kit_available[1]?kit_asset_ids[1]:"",
        kit_available[2]?kit_asset_ids[2]:"");
    fprintf(log,"squad_summary total=%d average_age=%d age_count=%d positions=%d/%d/%d/%d position_count=%d source=%d available=%d\n",
        g_squad_summary.total,g_squad_summary.average_age,g_squad_summary.age_count,
        g_squad_summary.goalkeepers,g_squad_summary.defenders,
        g_squad_summary.midfielders,g_squad_summary.attackers,
        g_squad_summary.position_count,g_squad_summary.source,
        g_squad_summary.available);
    fprintf(log,"starting_xi club=%d count=%llu source=%d players=",
        native_club,(unsigned long long)g_starting_xi.count,
        g_starting_xi.source);
    for(i=0;i<g_starting_xi.count;++i)
        fprintf(log,"%s%d",i?",":"",g_starting_xi.players[i]);
    fputc('\n',log);
    memset(seen_roots,0,sizeof(seen_roots));
    for(i=0;i<native_view.stat_count;++i) {
        const FceStat *stat=native_view.stats+i;
        int root; size_t j;
        if(stat->team!=native_club) continue;
        ++club_stat_rows;
        root=fce_model_ancestor(&native_view,stat->competition,3);
        if(root<0) { ++club_stat_unmapped; continue; }
        for(j=0;j<club_stat_roots && seen_roots[j]!=root;++j) {}
        if(j==club_stat_roots && club_stat_roots<sizeof(seen_roots)/sizeof(seen_roots[0]))
            seen_roots[club_stat_roots++]=root;
    }
    fprintf(log,"generation=%lu provider=%p club=%d club_name=%s injuries=%llu captured=%llu injury_source=%s requested=%ld competition=%ld standing=%ld date=%d date_source=%s assists=%llu upcoming=%llu club_results=%llu previous_round=%llu\n",
        native_epoch,provider,native_club,club_name,(unsigned long long)injury_display_count,
        (unsigned long long)g_injury_count,
        injury_source==3?"teamplayerlinks":(injury_source==2?"temp_teamplayerlinks":(injury_source==1?"stock_InjuryList":"none")),
        native_requested_competition,g_active_competition_id,g_standing_competition_id,native_view.date,
        native_date_source?"CalendarManager.today":"SimManager.current",
        (unsigned long long)g_assist_count,(unsigned long long)g_upcoming_count,
        (unsigned long long)g_club_previous_count,(unsigned long long)g_round_previous_count);
    if(injury_source==1) for(i=0;i<injury_display_count && i<5;++i)
        fprintf(log,"injury_card_row[%llu] player=%d name=%s return=%s\n",
            (unsigned long long)i,g_injury_rows[i].head,
            g_injury_rows[i].name,g_injury_rows[i].length);
    fprintf(log,"coach_record games=%d wins=%d draws=%d losses=%d points=%d percent=%d\n",
        g_coach_record.games,g_coach_record.wins,g_coach_record.draws,
        g_coach_record.losses,g_coach_record.points,g_coach_record.percent);
    fprintf(log,"club_trophies available=%d total=%d league=%d domestic=%d continental=%d history_leagues=%d\n",
        g_trophy_summary.available,g_trophy_summary.trophy_count,
        g_trophy_summary.league_titles,g_trophy_summary.domestic_titles,
        g_trophy_summary.continental_titles,g_trophy_summary.history_count);
    for(i=0;i<trophy_log_count;++i) {
        int known=0;
        int titles=native_history_title_count_for_competition(trophy_log_rows+i,&known);
        fprintf(log,"trophy_comp[%llu] root=%d asset=%d logo=%d trophy=%d count_known=%d titles=%d\n",
            (unsigned long long)i,trophy_log_rows[i].root,trophy_log_rows[i].title_asset,
            trophy_log_rows[i].logo,trophy_log_rows[i].trophy_asset,known,titles);
    }
    fprintf(log,"my_team_scope=all_competition_roots stat_rows=%llu roots=%llu unmapped=%llu goals_players=%llu assists_players=%llu yellow_players=%llu red_players=%llu\n",
        (unsigned long long)club_stat_rows,(unsigned long long)club_stat_roots,
        (unsigned long long)club_stat_unmapped,(unsigned long long)g_club_goal_count,
        (unsigned long long)g_club_assist_count,(unsigned long long)g_club_yellow_count,
        (unsigned long long)g_club_red_count);
    fprintf(log,"competition_tabs=%llu\n",(unsigned long long)g_competition_count);
    fprintf(log,"next_match_probe result=%d club=%d date=%d date_source=%s date_fallback=%d fixtures=%llu unresolved=%llu selected=%llu valid=%d fixture_id=%d competition_object=%d stage=%d fixture_date=%d time=%d home=%d away=%d played=%d\n",
        g_next_match_selection_result,native_club,native_view.date,
        native_date_source?"CalendarManager.today":"SimManager.current",
        g_next_match_date_fallback,(unsigned long long)native_view.fixture_count,
        (unsigned long long)native_view.unresolved_fixtures,
        (unsigned long long)g_upcoming_count,g_next_match_fixture_valid,
        g_next_match_fixture.id,g_next_match_fixture.competition_object,
        g_next_match_fixture.stage,g_next_match_fixture.date_raw,
        g_next_match_fixture.time_raw,g_next_match_fixture.home,
        g_next_match_fixture.away,g_next_match_fixture.played_raw);
    for(i=0;i<g_competition_count;++i) fprintf(log,
        "competition_tab[%llu] root=%d stage=%d asset=%d rows=%llu kind=%s\n",
        (unsigned long long)i,g_competition_rows[i].competition_id,g_competition_rows[i].stage,
        g_competition_rows[i].league_id,(unsigned long long)g_competition_tab_row_counts[i],
        g_competition_rows[i].kind?"table":"knockout");
    for(i=0;i<g_assist_count;++i) fprintf(log,"assist player=%d club=%d value=%d name=%s\n",g_assist_rows[i].head,g_assist_rows[i].logo,g_assist_rows[i].value,g_assist_rows[i].name);
    for(i=0;i<g_upcoming_count;++i) fprintf(log,"next home=%d away=%d date=%s time=%s object=%d logo=%d\n",g_upcoming_rows[i].home_logo,g_upcoming_rows[i].away_logo,g_upcoming_rows[i].date,g_upcoming_rows[i].time,g_upcoming_rows[i].competition_id,native_logo(g_upcoming_rows[i].competition_id));
    for(i=0;i<g_club_previous_count;++i) fprintf(log,"club_result home=%d away=%d score=%s date=%s object=%d logo=%d\n",g_club_previous_rows[i].home_logo,g_club_previous_rows[i].away_logo,g_club_previous_rows[i].score,g_club_previous_rows[i].date,g_club_previous_rows[i].competition_id,native_logo(g_club_previous_rows[i].competition_id));
    for(i=0;i<g_round_previous_count;++i) fprintf(log,"previous_round home=%d away=%d score=%s date=%s object=%d logo=%d\n",g_round_previous_rows[i].home_logo,g_round_previous_rows[i].away_logo,g_round_previous_rows[i].score,g_round_previous_rows[i].date,g_round_previous_rows[i].competition_id,native_logo(g_round_previous_rows[i].competition_id));
    fclose(log);
}
