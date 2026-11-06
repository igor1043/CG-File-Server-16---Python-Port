#include "fce_model.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static int r32(const uint8_t *p, size_t o) { int v; memcpy(&v, p+o, 4); return v; }
static int r16(const uint8_t *p, size_t o) { return p[o] | (p[o+1] << 8); }
static int rs16(const uint8_t *p, size_t o) { int v=r16(p,o); return v < 32768 ? v : v-65536; }
static int rs8(uint8_t b) { return b < 128 ? b : b-256; }
int fce_date_valid(int d) {
    static const int days[12]={31,28,31,30,31,30,31,31,30,31,30,31};
    int y=d/10000,m=(d/100)%100,day=d%100,max;
    if(y<1900 || y>2999 || m<1 || m>12 || day<1) return 0;
    max=days[m-1]+(m==2 && y%4==0 && (y%100!=0 || y%400==0));
    return day<=max;
}
int fce_date_pack(int d,int m,int y) {
    int v;
    if (d<1 || d>31 || m<1 || m>12 || y<1900 || y>2999) return -1;
    v=y*10000+m*100+d; return fce_date_valid(v) ? v : -1;
}
int fce_format_date(int d,char *out,size_t n) {
    if(!out || !n) return 0;
    out[0]=0; if(!fce_date_valid(d) || n<6) return 0;
    snprintf(out,n,"%02d/%02d",d%100,(d/100)%100); return 1;
}
int fce_format_time(int t,char *out,size_t n) {
    if(!out || !n) return 0;
    out[0]=0; if(t<0 || t>2359 || t%100>59 || n<6) return 0;
    snprintf(out,n,"%02d:%02d",t/100,t%100); return 1;
}
static int node_cmp(const void *a,const void *b) {
    int x=((const FceCompNode*)a)->id,y=((const FceCompNode*)b)->id;
    return (x>y)-(x<y);
}
int fce_model_ancestor(const FceModel *m,int id,int type) {
    size_t hop;
    for(hop=0; hop<m->node_count && id>=0; ++hop) {
        FceCompNode key={0}; const FceCompNode *p;
        key.id=id; p=bsearch(&key,m->nodes,m->node_count,sizeof(key),node_cmp);
        if(!p) return -1;
        if(p->type==type) return p->id;
        id=p->parent;
    }
    return -1;
}
int fce_model_stage_kind(const FceModel *m, int stage) {
    FceCompNode key;
    const FceCompNode *node;
    if (!m || stage < 0) return FCE_STAGE_UNKNOWN;
    key.id = stage;
    node = bsearch(&key, m->nodes, m->node_count, sizeof(key), node_cmp);
    return node && node->type == 4 ? node->stage_kind : FCE_STAGE_UNKNOWN;
}
void fce_model_free(FceModel *m) {
    if(!m) return;
    free(m->nodes); free(m->standings); free(m->stats); free(m->fixtures);
    memset(m,0,sizeof(*m)); m->date=-1;
}
static int table_ok(const FceRawTable *t,size_t min) {
    return t->count<=65536 && t->stride>=min && t->stride<=1024 &&
        (!t->count || t->bytes);
}
FceResult fce_model_build(const FceRawTable t[4],int date,FceModel *m) {
    size_t i; int *standing_by_id=NULL,*standing_any_by_id=NULL;
    FceResult result=FCE_INVALID;
    if(!m) return FCE_INVALID;
    memset(m,0,sizeof(*m)); m->date=fce_date_valid(date) ? date : -1;
    if(!t || !table_ok(t,0x1c) || !table_ok(t+1,0x24) ||
       !table_ok(t+2,0x25) || !table_ok(t+3,0x23)) return FCE_INVALID;
    m->nodes=calloc(t[0].count+1,sizeof(*m->nodes));
    m->standings=calloc(t[1].count+1,sizeof(*m->standings));
    m->stats=calloc(t[2].count+1,sizeof(*m->stats));
    m->fixtures=calloc(t[3].count+1,sizeof(*m->fixtures));
    if(!m->nodes || !m->standings || !m->stats || !m->fixtures) {
        result=FCE_NO_MEMORY; goto fail;
    }
    /* Fixture +0x1a/+0x1e store StandingsData::standing_id, not the
     * physical slot number.  IDs happen to equal slots in several leagues,
     * which hid this bug until careers with sparse/reused IDs were loaded. */
    standing_by_id=malloc(65536*sizeof(*standing_by_id));
    standing_any_by_id=malloc(65536*sizeof(*standing_any_by_id));
    if(!standing_by_id || !standing_any_by_id) { result=FCE_NO_MEMORY; goto fail; }
    memset(standing_by_id,0xff,65536*sizeof(*standing_by_id));
    memset(standing_any_by_id,0xff,65536*sizeof(*standing_any_by_id));
    /* Friendly/pre-season draws can reference a valid team row whose
     * standing slot is not marked active. Keep a separate ID map for those
     * rows; the public standings array remains filtered to active entries. */
    for(i=0;i<t[1].count;++i) {
        const uint8_t *p=t[1].bytes+i*t[1].stride;
        unsigned id=(unsigned)r16(p,8); int team=r32(p,0x14);
        if(team<0) continue;
        if(standing_any_by_id[id]==-1) standing_any_by_id[id]=(int)i;
        else standing_any_by_id[id]=-2;
    }
    for(i=0;i<t[0].count;++i) {
        FceResult r=fce_decode_comp_raw(t[0].bytes+i*t[0].stride,t[0].stride,m->nodes+m->node_count);
        if(r==FCE_OK) ++m->node_count; else if(r!=FCE_UNKNOWN) goto fail;
    }
    qsort(m->nodes,m->node_count,sizeof(*m->nodes),node_cmp);
    if(fce_validate_comp_index(m->nodes,m->node_count)!=FCE_OK) goto fail;
    for(i=0;i<t[1].count;++i) {
        FceResult r=fce_decode_standing_raw(t[1].bytes+i*t[1].stride,t[1].stride,m->standings+m->standing_count);
        if(r==FCE_OK) {
            int id=m->standings[m->standing_count].standing_id;
            if(id<0 || id>65535) goto fail;
            if(standing_by_id[id]==-1) standing_by_id[id]=(int)i;
            else standing_by_id[id]=-2; /* ambiguous snapshots fail that fixture closed */
            ++m->standing_count;
        } else if(r!=FCE_UNKNOWN) goto fail;
    }
    for(i=0;i<t[2].count;++i) {
        const uint8_t *p=t[2].bytes+i*t[2].stride; FceStat *s=m->stats+m->stat_count;
        if(p[10]!=1) continue;
        s->stats_id=r16(p,8); s->team=r32(p,0x10); s->player=r32(p,0x14);
        s->competition=r16(p,0x18); s->minutes=r16(p,0x1a);
        s->appearances=p[0x1e]; s->goals=p[0x1f]; s->assists=p[0x21];
        s->yellow_cards=p[0x23]; s->red_cards=p[0x24];
        /* Native raw->FCEI copy 0x33365/0x33397 and debug exporter:
         * raw word +1c is accumulated MatchRatings, byte +27 CleanSheets.
         * Old/minimal fixtures have only 0x25 bytes: never read past stride. */
        s->rating_sum=r16(p,0x1c);
        if(s->appearances>0 && s->rating_sum>0 && s->rating_sum<=s->appearances*100) s->profile_valid|=2;
        if(t[2].stride>=0x28){s->clean_sheets=p[0x27];if(s->clean_sheets<=s->appearances)s->profile_valid|=1;}
        if(s->team<0 || s->player<0) goto fail;
        ++m->stat_count;
    }
    for(i=0;i<t[3].count;++i) {
        const uint8_t *p=t[3].bytes+i*t[3].stride,*h,*a;
        FceFixture *f=m->fixtures+m->fixture_count;
        int hi,ai,hslot,aslot;
        if(p[10]!=1) continue;
        hi=rs16(p,0x1a); ai=rs16(p,0x1e);
        hslot=hi>=0?standing_by_id[hi]:-1;
        aslot=ai>=0?standing_by_id[ai]:-1;
        if(hslot<0 && hi>=0) hslot=standing_any_by_id[hi];
        if(aslot<0 && ai>=0) aslot=standing_any_by_id[ai];
        if(hi<0 || ai<0 || hslot<0 || aslot<0 ||
           (size_t)hslot>=t[1].count || (size_t)aslot>=t[1].count) {
            ++m->unresolved_fixtures; continue; /* draw has not resolved a team */
        }
        h=t[1].bytes+(size_t)hslot*t[1].stride;
        a=t[1].bytes+(size_t)aslot*t[1].stride;
        f->id=(int)i; f->competition_object=r16(p,0x10); f->round=p[0x12];
        f->stage=fce_model_ancestor(m,f->competition_object,4);
        /* Real league fixtures also point directly to a type-3 competition,
         * with no type-4 ancestor. Its own native object scopes the round. */
        if(f->stage<0) f->stage=f->competition_object;
        f->date_raw=r32(p,0x14); f->time_raw=r16(p,0x18);
        f->home=r32(h,0x14); f->away=r32(a,0x14);
        f->home_score=rs8(p[0x1c]); f->away_score=rs8(p[0x20]);
        f->played_raw=rs8(p[0x22]);
        if(!fce_date_valid(f->date_raw) || f->home<0 || f->away<0 || f->home==f->away ||
           (f->played_raw && (f->home_score<0 || f->away_score<0))) {
            ++m->unresolved_fixtures; continue;
        }
        ++m->fixture_count;
    }
    free(standing_by_id); free(standing_any_by_id); return FCE_OK;
fail:
    free(standing_by_id);
    free(standing_any_by_id);
    fce_model_free(m); return result;
}
FceResult fce_model_leaders(const FceModel *m,int comp,int club,FceStatSort field,
                            FceStat *out,size_t cap,size_t *count) {
    FceStat *filtered; size_t i,n=0; FceResult r;
    if(!m || !count) return FCE_INVALID;
    *count=0; comp=fce_model_ancestor(m,comp,3);
    if(comp<0) return FCE_UNKNOWN;
    filtered=malloc((m->stat_count+1)*sizeof(*filtered));
    if(!filtered) return FCE_NO_MEMORY;
    for(i=0;i<m->stat_count;++i) {
        FceStat s=m->stats[i];
        if(s.competition!=comp || (club>=0 && s.team!=club)) continue;
        s.competition=comp; filtered[n++]=s;
    }
    r=fce_select_stat_leaders(filtered,n,comp,field,out,cap,count);
    free(filtered); return r;
}
typedef struct {
    int32_t player, team, root, competition, value;
} CareerCompetitionMetric;
typedef struct {
    int32_t player, team, value;
} CareerPlayerMetric;
static int career_metric_order(const void *a,const void *b) {
    const CareerCompetitionMetric *x=a,*y=b;
    if(x->player!=y->player) return (x->player>y->player)-(x->player<y->player);
    if(x->team!=y->team) return (x->team>y->team)-(x->team<y->team);
    if(x->root!=y->root) return (x->root>y->root)-(x->root<y->root);
    if(x->competition!=y->competition)
        return (x->competition>y->competition)-(x->competition<y->competition);
    return (x->value>y->value)-(x->value<y->value);
}
static int career_player_rank_order(const void *a,const void *b) {
    const CareerPlayerMetric *x=a,*y=b;
    if(x->value!=y->value) return x->value>y->value?-1:1;
    if(x->player!=y->player) return (x->player>y->player)-(x->player<y->player);
    return (x->team>y->team)-(x->team<y->team);
}
static int32_t career_metric_value(const FceStat *s,FceCareerMetric metric) {
    switch(metric) {
    case FCE_CAREER_GOALS: return s->goals;
    case FCE_CAREER_ASSISTS: return s->assists;
    case FCE_CAREER_YELLOW_CARDS: return s->yellow_cards;
    case FCE_CAREER_RED_CARDS: return s->red_cards;
    case FCE_CAREER_MINUTES: return s->minutes;
    default: return -1;
    }
}
static int32_t career_saturating_add(int32_t a,int32_t b) {
    return b>INT32_MAX-a?INT32_MAX:a+b;
}
FceResult fce_model_career_leaders(const FceModel *m,int club,FceCareerMetric metric,
                                   FceStat *out,size_t cap,size_t *count) {
    CareerCompetitionMetric *raw=NULL;
    CareerPlayerMetric *totals=NULL;
    size_t raw_count=0,unique_count=0,total_count=0,i,j,output_count;
    if(!count || !m || (!out && cap) || club<0 ||
       metric<FCE_CAREER_GOALS || metric>FCE_CAREER_MINUTES) return FCE_INVALID;
    *count=0;
    if(!m->stat_count || !cap) return FCE_OK;
    if(m->stat_count>SIZE_MAX/sizeof(*raw) || m->stat_count>SIZE_MAX/sizeof(*totals))
        return FCE_NO_MEMORY;
    raw=malloc(m->stat_count*sizeof(*raw));
    totals=malloc(m->stat_count*sizeof(*totals));
    if(!raw || !totals) { free(raw);free(totals);return FCE_NO_MEMORY; }
    for(i=0;i<m->stat_count;++i) {
        const FceStat *s=m->stats+i;
        int32_t root,value;
        if(s->team!=club || s->player<0 || s->competition<0) continue;
        value=career_metric_value(s,metric);
        if(value<0) continue;
        root=fce_model_ancestor(m,s->competition,3);
        if(root<0) continue;
        raw[raw_count].player=s->player;
        raw[raw_count].team=s->team;
        raw[raw_count].root=root;
        raw[raw_count].competition=s->competition;
        raw[raw_count].value=value;
        ++raw_count;
    }
    if(!raw_count) { free(raw);free(totals);return FCE_OK; }
    qsort(raw,raw_count,sizeof(*raw),career_metric_order);
    /* Collapse duplicate rows for the same player/team/competition. Keep the
     * highest value rather than summing a repeated native snapshot row. */
    for(i=0;i<raw_count;) {
        CareerCompetitionMetric selected=raw[i];
        j=i+1;
        while(j<raw_count && raw[j].player==selected.player &&
              raw[j].team==selected.team && raw[j].root==selected.root &&
              raw[j].competition==selected.competition) {
            if(raw[j].value>selected.value) selected.value=raw[j].value;
            ++j;
        }
        raw[unique_count++]=selected;
        i=j;
    }
    /* Sum independent competition roots for each player. If the same root
     * contains both a root total and child-stage rows, trust the root total;
     * only sum child rows when no root total exists for that player/root. */
    for(i=0;i<unique_count;) {
        size_t end=i;
        int32_t player=raw[i].player,team=raw[i].team,root=raw[i].root;
        int32_t root_value=0,child_sum=0; int has_root=0;
        while(end<unique_count && raw[end].player==player && raw[end].team==team &&
              raw[end].root==root) {
            if(raw[end].competition==root) {
                if(!has_root || raw[end].value>root_value) root_value=raw[end].value;
                has_root=1;
            } else child_sum=career_saturating_add(child_sum,raw[end].value);
            ++end;
        }
        {
            int32_t value=has_root?root_value:child_sum;
            if(value>0) {
                if(total_count && totals[total_count-1].player==player &&
                   totals[total_count-1].team==team)
                    totals[total_count-1].value=career_saturating_add(
                        totals[total_count-1].value,value);
                else {
                    totals[total_count].player=player;
                    totals[total_count].team=team;
                    totals[total_count].value=value;
                    ++total_count;
                }
            }
        }
        i=end;
    }
    qsort(totals,total_count,sizeof(*totals),career_player_rank_order);
    output_count=total_count<cap?total_count:cap;
    for(i=0;i<output_count;++i) {
        memset(out+i,0,sizeof(*out));
        out[i].stats_id=-1;out[i].competition=-1;
        out[i].team=totals[i].team;out[i].player=totals[i].player;
        switch(metric) {
        case FCE_CAREER_GOALS: out[i].goals=totals[i].value;break;
        case FCE_CAREER_ASSISTS: out[i].assists=totals[i].value;break;
        case FCE_CAREER_YELLOW_CARDS: out[i].yellow_cards=totals[i].value;break;
        case FCE_CAREER_RED_CARDS: out[i].red_cards=totals[i].value;break;
        case FCE_CAREER_MINUTES: out[i].minutes=totals[i].value;break;
        default: break;
        }
    }
    *count=output_count;
    free(raw);free(totals);return FCE_OK;
}
static int fixture_order(const void *a,const void *b) {
    const FceFixture *x=a,*y=b;
    if(x->date_raw!=y->date_raw) return (x->date_raw>y->date_raw)-(x->date_raw<y->date_raw);
    if(x->time_raw!=y->time_raw) return (x->time_raw>y->time_raw)-(x->time_raw<y->time_raw);
    return (x->id>y->id)-(x->id<y->id);
}
FceResult fce_model_round(const FceModel *m,int comp,int club,int previous,
                          FceFixture *out,size_t cap,size_t *count) {
    const FceFixture *anchor=NULL; FceFixture *list; size_t i,n=0;
    if(!m || !count || (!out && cap)) return FCE_INVALID;
    *count=0; comp=fce_model_ancestor(m,comp,3);
    if(comp<0 || !fce_date_valid(m->date)) return FCE_UNKNOWN;
    /* Round identity comes from schedule.raw+0x14 -> fixture.raw+0x12,
     * creation RVA 0x6f3c0 -> 0x1a1f0. Group by native round AND stage.
     * Anchor on the club's last completed / next unplayed match, so a
     * different group's advanced calendar cannot choose the club's round. */
    for(i=0;i<m->fixture_count;++i) {
        const FceFixture *f=m->fixtures+i;
        if(fce_model_ancestor(m,f->competition_object,3)!=comp ||
           (club>=0 && f->home!=club && f->away!=club) || f->stage<0) continue;
        if(previous ? (!f->played_raw || f->date_raw>m->date) :
                      (f->played_raw || f->date_raw<m->date)) continue;
        if(!anchor || (previous ? fixture_order(f,anchor)>0 : fixture_order(f,anchor)<0)) anchor=f;
    }
    if(!anchor) return FCE_OK;
    list=malloc((m->fixture_count+1)*sizeof(*list));
    if(!list) return FCE_NO_MEMORY;
    for(i=0;i<m->fixture_count;++i) {
        const FceFixture *f=m->fixtures+i;
        if(f->stage!=anchor->stage || f->round!=anchor->round ||
           fce_model_ancestor(m,f->competition_object,3)!=comp) continue;
        if(previous && (!f->played_raw || f->date_raw>m->date)) continue;
        list[n++]=*f;
    }
    qsort(list,n,sizeof(*list),fixture_order);
    if(n>cap) n=cap;
    if(n) memcpy(out,list,n*sizeof(*list));
    free(list); *count=n; return FCE_OK;
}
