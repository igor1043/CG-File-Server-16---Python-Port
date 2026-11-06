#ifndef FIFA16_CROWD_RUNTIME_H
#define FIFA16_CROWD_RUNTIME_H

/* Runtime-only controller for the already verified AttribDB crowd field.
 * It never edits the disk VLT.  The worker changes only a validated copy
 * loaded by the running FIFA process and restores 0.90 outside Career. */
typedef struct CrowdDecision
{
    int enabled;
    int club_id;
    int competition_id;
    int rank;
    int team_count;
    int played;
    int next_opponent;
    int next_is_home;
    int next_date;
    int next_round;
    int last_result;
    int last_margin;
    int streak;
    int streak_sign;
    int points_gap_to_safety;
    float form;
    float reputation;
    float league_reputation;
    float rivalry;
    float position_score;
    float season_progress;
    float danger;
    float momentum;
    float escape_opportunity;
    float importance;
    float phase;
    float international_bonus;
    float factor;
} CrowdDecision;

void crowd_runtime_start(const char *log_dir);
void crowd_runtime_disable(void);
void crowd_runtime_set_decision(const CrowdDecision *decision);
float crowd_runtime_team_reputation(int team_id);
int crowd_runtime_team_reputation_available(int team_id);
float crowd_runtime_league_reputation(int team_id);
float crowd_runtime_rivalry(int team_id, int opponent_id);
float crowd_runtime_international_bonus(void);
/* Configurable competition profile, expressed in percentage points. */
int crowd_runtime_competition_setting(const char *key, const char *suffix,
    int fallback, int maximum);
int crowd_runtime_attendance_percent(void);

#endif
