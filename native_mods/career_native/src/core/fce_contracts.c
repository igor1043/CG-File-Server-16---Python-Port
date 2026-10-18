#include "fce_contracts.h"
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(FceStatsCriteria) == 0x3c, "Stats criteria ABI");
_Static_assert(offsetof(FceStatsCriteria, sort) == 0x14, "Stats sort ABI");
_Static_assert(sizeof(FceFixturesCriteria) == 0x24, "Fixture criteria ABI");
_Static_assert(offsetof(FceFixturesCriteria, played_filter) == 0x20, "Status ABI");
_Static_assert(sizeof(int32_t) == 4, "32-bit fields required");

static int32_t i32(const uint8_t *p, size_t off) {
    int32_t v;
    memcpy(&v, p + off, sizeof(v));
    return v;
}
static unsigned u16(const uint8_t *p, size_t off) {
    return (unsigned)p[off] | ((unsigned)p[off + 1] << 8);
}
static int signed16(const uint8_t *p, size_t off) {
    unsigned v = u16(p, off);
    return v < 0x8000 ? (int)v : (int)v - 0x10000;
}
static int stage_kind_from_name(const uint8_t *p, size_t size) {
    size_t pos = 0x1c;
    if (!p || size <= pos) return FCE_STAGE_UNKNOWN;
    if (size - pos >= sizeof("FCE_Setup_Stage") - 1 &&
        memcmp(p + pos, "FCE_Setup_Stage",
               sizeof("FCE_Setup_Stage") - 1) == 0)
        return FCE_STAGE_SETUP;
    if (size - pos >= sizeof("FCE_Group_Stage") - 1 &&
        memcmp(p + pos, "FCE_Group_Stage",
               sizeof("FCE_Group_Stage") - 1) == 0)
        return FCE_STAGE_GROUP;
    if (size - pos >= sizeof("FCE_Round_1") - 1 &&
        memcmp(p + pos, "FCE_Round_1", sizeof("FCE_Round_1") - 1) == 0)
        return FCE_STAGE_ROUND_1;
    if (size - pos >= sizeof("FCE_Round_2") - 1 &&
        memcmp(p + pos, "FCE_Round_2", sizeof("FCE_Round_2") - 1) == 0)
        return FCE_STAGE_ROUND_2;
    if (size - pos >= sizeof("FCE_Round_of_32") - 1 &&
        memcmp(p + pos, "FCE_Round_of_32",
               sizeof("FCE_Round_of_32") - 1) == 0)
        return FCE_STAGE_ROUND_32;
    if (size - pos >= sizeof("FCE_Round_of_16") - 1 &&
        memcmp(p + pos, "FCE_Round_of_16",
               sizeof("FCE_Round_of_16") - 1) == 0)
        return FCE_STAGE_ROUND_16;
    if (size - pos >= sizeof("FCE_Quarter_Finals") - 1 &&
        memcmp(p + pos, "FCE_Quarter_Finals",
               sizeof("FCE_Quarter_Finals") - 1) == 0)
        return FCE_STAGE_QUARTER_FINAL;
    if (size - pos >= sizeof("FCE_Semi_Finals") - 1 &&
        memcmp(p + pos, "FCE_Semi_Finals",
               sizeof("FCE_Semi_Finals") - 1) == 0)
        return FCE_STAGE_SEMI_FINAL;
    if (size - pos >= sizeof("FCE_Third_Place") - 1 &&
        memcmp(p + pos, "FCE_Third_Place",
               sizeof("FCE_Third_Place") - 1) == 0)
        return FCE_STAGE_THIRD_PLACE;
    if (size - pos >= sizeof("FCE_Final") - 1 &&
        memcmp(p + pos, "FCE_Final", sizeof("FCE_Final") - 1) == 0)
        return FCE_STAGE_FINAL;
    return FCE_STAGE_UNKNOWN;
}

FceResult fce_stats_criteria(FceStatsCriteria *q, int32_t competition,
                            int32_t team, int32_t limit, FceStatSort field) {
    if (!q) return FCE_INVALID;
    /* Native default constructor RVA 0x7fb00, comparator RVA 0x19550. */
    memset(q, 0xff, sizeof(*q));
    if (competition < 0 || team < -1 || limit < -1 ||
        (field != FCE_SORT_GOALS && field != FCE_SORT_ASSISTS)) return FCE_INVALID;
    q->competition_object = competition;
    q->team = team;
    q->limit = limit;
    q->sort[0].field = field;
    q->sort[0].direction = 1; /* descending; native ascending is 0 */
    return FCE_OK;
}

FceResult fce_fixtures_criteria(FceFixturesCriteria *q, int32_t team,
                               int32_t now, FceFixtureFilter filter) {
    if (!q) return FCE_INVALID;
    memset(q, 0, sizeof(*q));
    q->competition_object = q->team = q->opponent = -1;
    q->date_from = q->date_to = q->limit = -1;
    q->played_filter = FCE_ANY;
    if (team < 0 || now < 0 || filter < FCE_PLAYED || filter > FCE_ANY)
        return FCE_INVALID;
    q->team = team;
    q->played_filter = filter;
    /* All competitions; no native limit, because the direction of its
     * fixture sort is not assumed. The view selector chooses the nearest 10. */
    if (filter == FCE_UNPLAYED) q->date_from = now;
    if (filter == FCE_PLAYED) q->date_to = now;
    return FCE_OK;
}

FceResult fce_decode_stat(const void *data, size_t size, FceStat *out) {
    FceStat v;
    const uint8_t *p = data;
    if (!out) return FCE_INVALID;
    memset(out, 0, sizeof(*out));
    if (!p || size != FCE_STAT_VIEW_BYTES) return FCE_INVALID;
    memset(&v, 0, sizeof(v));
    v.stats_id = i32(p, 0); v.competition = i32(p, 4);
    v.team = i32(p, 8); v.player = i32(p, 12);
    v.appearances = i32(p, 0x10); v.minutes = i32(p, 0x14);
    v.goals = i32(p, 0x18); v.assists = i32(p, 0x20);
    v.yellow_cards = i32(p, 0x2c); v.red_cards = i32(p, 0x30);
    /* FCE exporter 0x74fbd (RSI=view+8): CleanSheets +0x3c,
     * MatchRatings +0x28. Keep validity separate from a real zero. */
    v.clean_sheets=i32(p,0x3c); v.rating_sum=i32(p,0x28);
    if(v.clean_sheets>=0 && v.clean_sheets<=v.appearances) v.profile_valid|=1;
    if(v.appearances>0 && v.rating_sum>0 && (int64_t)v.rating_sum<=(int64_t)v.appearances*100) v.profile_valid|=2;
    /* Native query can synthesize zero rows with stats_id/competition=-1.
     * They are not evidence of a played match; zero-value list entries must
     * be filtered by the caller, never replaced with another save's rows. */
    if (v.team < 0 || v.player < 0 || v.goals < 0 || v.assists < 0 ||
        v.appearances < 0 || v.minutes < 0 || v.yellow_cards < 0 || v.red_cards < 0)
        return FCE_INVALID;
    *out = v;
    return FCE_OK;
}

static int valid_fixture(const FceFixture *v) {
    return v->id >= 0 && v->competition_object >= 0 && v->date_raw >= 0 &&
           v->home >= 0 && v->away >= 0 && v->home != v->away &&
           (!v->played_raw || (v->home_score >= 0 && v->away_score >= 0));
}
FceResult fce_decode_fixture(const void *data, size_t size, FceFixture *out) {
    FceFixture v;
    const uint8_t *p = data;
    if (!out) return FCE_INVALID;
    memset(out, 0, sizeof(*out));
    if (!p || size != FCE_FIXTURE_VIEW_BYTES) return FCE_INVALID;
    v.id = i32(p, 0x30); v.competition_object = i32(p, 0x28);
    v.stage = i32(p, 0x2c); v.date_raw = i32(p, 0x34);
    v.time_raw = i32(p, 0x38); v.home = i32(p, 0x114); v.away = i32(p, 0x118);
    v.home_score = i32(p, 0x0c); v.away_score = i32(p, 0x18);
    v.played_raw = i32(p, 0x20); v.round = i32(p, 0);
    if (!valid_fixture(&v)) return FCE_INVALID;
    *out = v;
    return FCE_OK;
}

FceResult fce_decode_comp_raw(const void *data, size_t size, FceCompNode *out) {
    const uint8_t *p = data;
    FceCompNode v;
    int32_t asset = 0;
    size_t i;
    if (!out) return FCE_INVALID;
    memset(out, 0, sizeof(*out));
    if (!p || size < 0x1c) return FCE_INVALID;
    if (p[0x0a] != 1) return FCE_UNKNOWN;
    v.id = (int32_t)u16(p, 0x10); v.type = p[0x12];
    v.parent = signed16(p, 0x14); v.asset = -1;
    v.stage_kind = v.type == 4 ? stage_kind_from_name(p, size) :
        FCE_STAGE_UNKNOWN;
    if (v.type == 3 && p[0x16] == 'C') {
        int numeric_asset = 1;
        size_t digits = 0;
        asset = 0;
        for (i = 1; i < 6 && p[0x16 + i]; ++i) {
            if (p[0x16 + i] < '0' || p[0x16 + i] > '9') {
                numeric_asset = 0;
                break;
            }
            asset = asset * 10 + p[0x16 + i] - '0';
            ++digits;
        }
        /* Type-3 objects may carry non-logo identities such as CRTR.
         * Preserve the competition; an unrecognized key only hides its icon. */
        if (numeric_asset && digits) v.asset = (int32_t)asset;
    }
    /* The live object contains its display key at +0x1c. Some installed
     * databases reuse C100 while explicitly naming TrophyName_Abbr15_1009.
     * Use the bounded display identity, never a save-specific object alias. */
    if (v.type == 3 && size > 0x1c) {
        static const char prefix[] = "TrophyName_Abbr15_";
        size_t pos = 0x1c + sizeof(prefix) - 1;
        if (size > pos && memcmp(p + 0x1c, prefix, sizeof(prefix) - 1) == 0) {
            int display_asset = 0;
            size_t first = pos;
            while (pos < size && pos - first < 6 && p[pos] >= '0' && p[pos] <= '9') {
                display_asset = display_asset * 10 + p[pos++] - '0';
            }
            if (pos > first && pos < size && p[pos] == 0 && display_asset > 0)
                v.asset = display_asset;
        }
    }
    *out = v;
    return FCE_OK;
}

FceResult fce_decode_standing_raw(const void *data, size_t size, FceStanding *out) {
    const uint8_t *p = data;
    FceStanding v;
    if (!out) return FCE_INVALID;
    memset(out, 0, sizeof(*out));
    if (!p || size < 0x24) return FCE_INVALID;
    if (p[0x0a] != 1) return FCE_UNKNOWN;
    v.standing_id = (int32_t)u16(p, 8);
    v.competition_object = (int32_t)u16(p, 0x10); v.team = i32(p, 0x14);
    v.home_wins = p[0x19]; v.home_draws = p[0x1a]; v.home_losses = p[0x1b];
    v.away_wins = p[0x1e]; v.away_draws = p[0x1f]; v.away_losses = p[0x20];
    v.played = v.home_wins + v.home_draws + v.home_losses +
               v.away_wins + v.away_draws + v.away_losses;
    /* Native draws reserve ACTIVE standings slots before assigning a team.
     * team=-1 is a legitimate unresolved berth, not a corrupt snapshot.
     * Observed in live career tables; do not discard unrelated competitions. */
    if (v.team == -1) return FCE_UNKNOWN;
    if (v.team < -1) return FCE_INVALID;
    *out = v;
    return FCE_OK;
}

FceResult fce_validate_comp_index(const FceCompNode *nodes, size_t count) {
    size_t i;
    if (!nodes && count) return FCE_INVALID;
    for (i = 0; i < count; ++i)
        if (nodes[i].id < 0 || (i && nodes[i-1].id >= nodes[i].id)) return FCE_INVALID;
    return FCE_OK;
}
static const FceCompNode *find_comp(const FceCompNode *nodes, size_t count, int32_t id) {
    size_t lo = 0, hi = count;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        if (nodes[mid].id < id) lo = mid + 1; else hi = mid;
    }
    return lo < count && nodes[lo].id == id ? nodes + lo : NULL;
}
FceResult fce_resolve_competition(const FceCompNode *nodes, size_t count, int32_t id,
                                 FceCompetition *out) {
    size_t hop;
    if (!out) return FCE_INVALID;
    out->competition = out->asset = -1;
    if (!nodes && count) return FCE_INVALID;
    for (hop = 0; hop < count && id >= 0; ++hop) {
        const FceCompNode *n = find_comp(nodes, count, id);
        if (!n) return FCE_UNKNOWN;
        if (n->type == 3) {
            out->competition = n->id; out->asset = n->asset;
            return FCE_OK; /* asset=-1 means hide the icon, not a fallback logo */
        }
        id = n->parent;
    }
    return FCE_UNKNOWN; /* missing ancestor or cycle */
}

static int cmp_int(int32_t a, int32_t b) { return (a > b) - (a < b); }
static int by_id(const void *a, const void *b) {
    return cmp_int(((const FceFixture *)a)->id, ((const FceFixture *)b)->id);
}
static int by_date(const void *a, const void *b) {
    const FceFixture *x = a, *y = b;
    int d = cmp_int(x->date_raw, y->date_raw);
    if (!d) d = cmp_int(x->time_raw, y->time_raw);
    return d ? d : cmp_int(x->id, y->id);
}
static int same_fixture(const FceFixture *a, const FceFixture *b) {
    return a->id == b->id && a->competition_object == b->competition_object &&
        a->stage == b->stage && a->date_raw == b->date_raw && a->time_raw == b->time_raw &&
        a->home == b->home && a->away == b->away && a->home_score == b->home_score &&
        a->away_score == b->away_score && a->played_raw == b->played_raw && a->round == b->round;
}
FceResult fce_select_club_fixtures(const FceFixture *in, size_t count, int32_t team,
                                  int32_t now, FceFixtureFilter filter,
                                  FceFixture *out, size_t capacity, size_t *out_count) {
    FceFixture *copy;
    size_t i, unique = 0, selected = 0, n;
    if (!out_count) return FCE_INVALID;
    *out_count = 0;
    if ((!in && count) || (!out && capacity) || team < 0 || now < 0 ||
        filter < FCE_PLAYED || filter > FCE_ANY || count > SIZE_MAX / sizeof(*copy))
        return FCE_INVALID;
    if (!count) return FCE_OK;
    copy = malloc(count * sizeof(*copy));
    if (!copy) return FCE_NO_MEMORY;
    for (i = 0; i < count; ++i) {
        if (!valid_fixture(&in[i])) { free(copy); return FCE_INVALID; }
        copy[i] = in[i];
    }
    qsort(copy, count, sizeof(*copy), by_id);
    for (i = 0; i < count; ++i) {
        if (unique && copy[i].id == copy[unique - 1].id) {
            if (!same_fixture(&copy[i], &copy[unique - 1])) {
                free(copy); return FCE_CONFLICT;
            }
        } else copy[unique++] = copy[i];
    }
    for (i = 0; i < unique; ++i) {
        const FceFixture *v = &copy[i];
        if (v->home != team && v->away != team) continue;
        if (filter == FCE_UNPLAYED && (v->played_raw || v->date_raw < now)) continue;
        if (filter == FCE_PLAYED && (!v->played_raw || v->date_raw > now)) continue;
        copy[selected++] = *v;
    }
    qsort(copy, selected, sizeof(*copy), by_date);
    n = selected < capacity ? selected : capacity;
    for (i = 0; i < n; ++i) out[i] = copy[filter == FCE_PLAYED ? selected - 1 - i : i];
    free(copy);
    *out_count = n;
    return FCE_OK;
}
size_t fce_form_dot_limit(size_t available, unsigned played) {
    size_t n = available < played ? available : played;
    return n < 5 ? n : 5;
}

static int by_player_team(const void *a, const void *b) {
    const FceStat *x = a, *y = b;
    int d = cmp_int(x->player, y->player);
    return d ? d : cmp_int(x->team, y->team);
}
static int by_assists(const void *a, const void *b) {
    int d = cmp_int(((const FceStat *)b)->assists, ((const FceStat *)a)->assists);
    return d ? d : by_player_team(a, b);
}
static int by_goals(const void *a, const void *b) {
    int d = cmp_int(((const FceStat *)b)->goals, ((const FceStat *)a)->goals);
    return d ? d : by_player_team(a, b);
}
static int same_stat(const FceStat *a, const FceStat *b) {
    return a->stats_id == b->stats_id && a->competition == b->competition &&
           a->player == b->player && a->team == b->team &&
           a->appearances == b->appearances && a->minutes == b->minutes &&
           a->goals == b->goals && a->assists == b->assists &&
           a->yellow_cards == b->yellow_cards && a->red_cards == b->red_cards;
}
FceResult fce_select_stat_leaders(const FceStat *in, size_t count, int32_t competition,
                                 FceStatSort field, FceStat *out, size_t capacity, size_t *out_count) {
    FceStat *copy;
    size_t i, selected = 0, unique = 0, n;
    if (!out_count) return FCE_INVALID;
    *out_count = 0;
    if ((!in && count) || (!out && capacity) || competition < 0 ||
        (field != FCE_SORT_ASSISTS && field != FCE_SORT_GOALS) ||
        count > SIZE_MAX / sizeof(*copy)) return FCE_INVALID;
    if (!count) return FCE_OK;
    copy = malloc(count * sizeof(*copy));
    if (!copy) return FCE_NO_MEMORY;
    for (i = 0; i < count; ++i) {
        const FceStat *v = in + i;
        if (v->team < 0 || v->player < 0 || v->goals < 0 || v->assists < 0 ||
            v->appearances < 0 || v->minutes < 0 || v->yellow_cards < 0 || v->red_cards < 0) {
            free(copy); return FCE_INVALID;
        }
        /* Native filler for a player with no record in this competition. */
        if (v->stats_id == -1 && v->competition == -1 && !v->goals && !v->assists &&
            !v->appearances && !v->minutes && !v->yellow_cards && !v->red_cards) continue;
        if (v->competition != competition) { free(copy); return FCE_CONFLICT; }
        copy[selected++] = *v;
    }
    qsort(copy, selected, sizeof(*copy), by_player_team);
    for (i = 0; i < selected; ++i) {
        if (unique && by_player_team(&copy[i], &copy[unique - 1]) == 0) {
            if (!same_stat(&copy[i], &copy[unique - 1])) { free(copy); return FCE_CONFLICT; }
        } else copy[unique++] = copy[i];
    }
    selected = 0;
    for (i = 0; i < unique; ++i)
        if ((field == FCE_SORT_ASSISTS ? copy[i].assists : copy[i].goals) > 0)
            copy[selected++] = copy[i];
    qsort(copy, selected, sizeof(*copy), field == FCE_SORT_ASSISTS ? by_assists : by_goals);
    n = selected < capacity ? selected : capacity;
    for (i = 0; i < n; ++i) out[i] = copy[i];
    free(copy); *out_count = n;
    return FCE_OK;
}
