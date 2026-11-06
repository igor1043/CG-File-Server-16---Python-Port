#ifndef RETIREMENT_ENGINE_H
#define RETIREMENT_ENGINE_H

#include <windows.h>

typedef struct RetirementApplyResult {
    int status;
    unsigned int players_seen;
    unsigned int players_retiring;
    unsigned int players_changed;
    unsigned int transfer_budget_before;
    unsigned int transfer_budget_after;
    unsigned int transfer_budget_added;
    unsigned int crc_before;
    unsigned int crc_after;
    char message[256];
    char backup_data[1024];
    char backup_index[1024];
} RetirementApplyResult;

/* The engine is inert unless career_retirement_background.ini contains
 * enabled=1.  It is intentionally independent from the UI/NAV layer. */
#ifdef __cplusplus
extern "C" {
#endif
int retirement_engine_apply_file(const char *data_path, const char *mode,
    int target_age, RetirementApplyResult *result);
int retirement_engine_apply_buffer(void *buffer, SIZE_T size,
    const char *mode, int target_age, RetirementApplyResult *result);
/* New selection UI: NULL/0 selects all active players; otherwise only the
 * explicitly listed IDs. reset_age affects the selected players, even when
 * they were not yet retiring. Atomic in memory; not the legacy global action. */
int retirement_engine_apply_selection(void *buffer, SIZE_T size,
    const unsigned int *player_ids, SIZE_T count, int reset_age, int target_age,
    RetirementApplyResult *result);
int retirement_engine_apply_buffer_from_config(void *buffer, SIZE_T size,
    RetirementApplyResult *result);
/* Read the two recurring transfer-window closing days (MMDD) from a career
 * save. Read-only: it never repacks, writes, or backs up DATA. */
int retirement_engine_get_transfer_window_ends(const char *data_path,
    unsigned int *first_mmdd, unsigned int *second_mmdd);
int retirement_engine_patch_write_buffer(void *buffer, SIZE_T size,
    const char *data_path, RetirementApplyResult *result);
int retirement_engine_backup_before_write(const char *data_path);
void retirement_engine_set_mod_dir(const char *mod_dir);
int retirement_engine_local_logging_enabled(const char *mod_dir);
int retirement_engine_start(const char *mod_dir);
void retirement_engine_note_ui_signal(const char *path);
void retirement_engine_note_buffer_write(const char *data_path,
    const RetirementApplyResult *result);
void retirement_engine_note_write(const char *data_path);
/* Shared non-modal feedback surface used by other career features.  A zero
 * beep_type keeps the notification visual-only. */
void retirement_engine_show_feedback(const char *text, UINT beep_type);
#ifdef __cplusplus
}
#endif

#endif
