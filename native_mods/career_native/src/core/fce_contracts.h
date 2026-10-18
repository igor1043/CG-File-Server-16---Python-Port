/* Offline-verified FCE data contracts. Not EA source, not a game hook.
 * These functions consume OWNED COPIES from an identified native response.
 * Never pass arbitrary heap candidates or another provider's row layout.
 * Evidence: reports/FCE-NATIVO-CONTRATOS.md. Target: little-endian FIFA16 x64.
 */
#ifndef FIFA16_FCE_CONTRACTS_H
#define FIFA16_FCE_CONTRACTS_H
#include <stddef.h>
#include <stdint.h>

enum { FCE_STAT_VIEW_BYTES = 0x78, FCE_FIXTURE_VIEW_BYTES = 0x11c };
typedef enum {
    FCE_OK = 0, FCE_INVALID = -1, FCE_UNKNOWN = -2,
    FCE_CONFLICT = -3, FCE_NO_MEMORY = -4
} FceResult;
typedef enum { FCE_PLAYED = 0, FCE_UNPLAYED = 1, FCE_ANY = 2 } FceFixtureFilter;
typedef enum { FCE_SORT_GOALS = 2, FCE_SORT_ASSISTS = 4 } FceStatSort;
typedef enum {
    FCE_STAGE_UNKNOWN = 0,
    FCE_STAGE_SETUP = 1,
    FCE_STAGE_GROUP = 2,
    FCE_STAGE_ROUND_1 = 3,
    FCE_STAGE_ROUND_2 = 4,
    FCE_STAGE_ROUND_32 = 5,
    FCE_STAGE_ROUND_16 = 6,
    FCE_STAGE_QUARTER_FINAL = 7,
    FCE_STAGE_SEMI_FINAL = 8,
    FCE_STAGE_THIRD_PLACE = 9,
    FCE_STAGE_FINAL = 10
} FceStageKind;

/* Payload only, NOT a request object. Native requests also need their own
 * vtable, lifetime, allocator, correlation token and scheduling flags. */
typedef struct { int32_t field, direction; } FceSortKey;
typedef struct {
    int32_t competition_object, team, player, limit, roster_filter_unknown;
    FceSortKey sort[5];
} FceStatsCriteria;
typedef struct {
    int32_t competition_object, team, opponent, date_from, date_to, limit;
    uint8_t active_teams_only, padding[3];
    int32_t enrichment_unknown, played_filter;
} FceFixturesCriteria;

typedef struct {
    int32_t stats_id, competition, team, player, appearances, minutes;
    int32_t goals, assists, yellow_cards, red_cards;
    /* Optional fields in owned data, NOT an FCEI/native struct overlay. */
    int32_t clean_sheets, rating_sum;
    unsigned profile_valid; /* bit 0 clean sheets, bit 1 rating sum (tenths). */
} FceStat;
typedef struct {
    int32_t id, competition_object, stage, date_raw, time_raw;
    int32_t home, away, home_score, away_score, played_raw;
    int32_t round;
} FceFixture;
typedef struct {
    int32_t id, parent, type, asset, stage_kind;
} FceCompNode;
typedef struct { int32_t competition, asset; } FceCompetition;
typedef struct {
    int32_t standing_id, competition_object, team;
    unsigned home_wins, home_draws, home_losses;
    unsigned away_wins, away_draws, away_losses, played;
} FceStanding;

FceResult fce_stats_criteria(FceStatsCriteria *, int32_t competition,
                            int32_t team, int32_t limit, FceStatSort);
FceResult fce_fixtures_criteria(FceFixturesCriteria *, int32_t team,
                               int32_t current_date_raw, FceFixtureFilter);
FceResult fce_decode_stat(const void *, size_t, FceStat *);
FceResult fce_decode_fixture(const void *, size_t, FceFixture *);
/* Raw table rows differ from public FCEI views. Explicitly separate APIs. */
FceResult fce_decode_comp_raw(const void *, size_t, FceCompNode *);
FceResult fce_decode_standing_raw(const void *, size_t, FceStanding *);
FceResult fce_validate_comp_index(const FceCompNode *, size_t);
/* Index must be sorted by id and validated once per metadata snapshot. */
FceResult fce_resolve_competition(const FceCompNode *, size_t, int32_t object,
                                 FceCompetition *);
/* Every input array must belong to ONE coherent career-state snapshot.
 * Result owns no game pointers; conflicting duplicate ids fail closed.
 * On failure *out_count=0; callers must not publish the output buffer. */
FceResult fce_select_club_fixtures(const FceFixture *, size_t, int32_t team,
                                  int32_t current_date_raw, FceFixtureFilter,
                                  FceFixture *, size_t capacity, size_t *out_count);
FceResult fce_select_stat_leaders(const FceStat *, size_t, int32_t competition,
                                 FceStatSort, FceStat *, size_t capacity, size_t *out_count);
size_t fce_form_dot_limit(size_t available_valid_results, unsigned native_played);
#endif
