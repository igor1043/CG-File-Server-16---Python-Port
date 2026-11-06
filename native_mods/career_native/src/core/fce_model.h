#ifndef FIFA16_FCE_MODEL_H
#define FIFA16_FCE_MODEL_H
#include "fce_contracts.h"
/* All table buffers are OWNED copies, never pointers to a running engine. */
typedef struct { const uint8_t *bytes; size_t count, stride; } FceRawTable;
typedef struct {
    FceCompNode *nodes; size_t node_count;
    FceStanding *standings; size_t standing_count;
    FceStat *stats; size_t stat_count;
    FceFixture *fixtures; size_t fixture_count;
    int date;
    size_t unresolved_fixtures;
} FceModel;
typedef enum {
    FCE_CAREER_GOALS = 0,
    FCE_CAREER_ASSISTS = 1,
    FCE_CAREER_YELLOW_CARDS = 2,
    FCE_CAREER_RED_CARDS = 3,
    FCE_CAREER_MINUTES = 4
} FceCareerMetric;
int fce_date_valid(int date);
int fce_date_pack(int day, int month, int year);
int fce_format_date(int date, char *out, size_t capacity);
int fce_format_time(int time, char *out, size_t capacity);
FceResult fce_model_build(const FceRawTable tables[4], int date, FceModel *out);
void fce_model_free(FceModel *);
int fce_model_ancestor(const FceModel *, int object, int type);
int fce_model_stage_kind(const FceModel *, int stage);
FceResult fce_model_round(const FceModel *, int competition, int club,
                          int previous, FceFixture *, size_t capacity, size_t *count);
FceResult fce_model_leaders(const FceModel *, int competition, int club,
                            FceStatSort, FceStat *, size_t capacity, size_t *count);
/* Team-wide totals across top-level competitions in one career snapshot.
 * Root competition rows take precedence over child-stage rows to avoid
 * counting a competition total and its phase records twice. */
FceResult fce_model_career_leaders(const FceModel *, int club, FceCareerMetric,
                                   FceStat *, size_t capacity, size_t *count);
#endif
