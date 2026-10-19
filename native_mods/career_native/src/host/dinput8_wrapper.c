#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winternl.h>
#define DirectInput8Create DirectInput8Create_sdk_declaration
#define GetdfDIJoystick GetdfDIJoystick_sdk_declaration
#include <dinput.h>
#undef DirectInput8Create
#undef GetdfDIJoystick
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>
#include "../platform/mod_paths.h"
#include "../platform/stadium_thumbnail.h"
#include "../core/fce_runtime.h"
#include "../features/crowd/crowd_runtime.h"
#include "../features/retirement/retirement_engine.h"
#include "swiss_delta.h"
#include "card_refresh_schedule.h"
#include "../../../common/competition_identity.h"
#include "calendar_icon_identity.h"
static void native_prepare(void *owner);
static void native_publish(void *provider);
static void native_log_transfer_card_context(void *provider);
static void native_form(void *provider, int row, int club);
static int native_logo(int object);
static unsigned long native_generation(void);
static int native_calendar_date(void *owner);
static int native_competition_from_asset(int asset, int club, int hint);
static int native_display_context_competition(int requested, int club);
static int native_is_competition_round_provider(void *owner, void *provider);
static void native_end(void);
static void refresh_initial_competition_provider(unsigned long generation);
static void drain_pending_stats_refresh(void);
static void clear_pending_stats_refresh(void);
static void remember_pending_stats_refresh(void *owner);
static void stats_provider_with_diagnostics(void *provider_owner);
static void publish_coach_record(void *provider);
static void native_context_reset(void);
static int native_club;
static void append_loader_log(const char *event);


typedef HRESULT(WINAPI *DirectInput8CreateFn)(
    HINSTANCE,
    DWORD,
    REFIID,
    LPVOID *,
    LPUNKNOWN);
typedef HRESULT(WINAPI *DllCanUnloadNowFn)(void);
typedef HRESULT(WINAPI *DllGetClassObjectFn)(
    REFCLSID,
    REFIID,
    LPVOID *);
typedef HRESULT(WINAPI *DllRegisterServerFn)(void);
typedef HRESULT(WINAPI *DllUnregisterServerFn)(void);
typedef LPCDIDATAFORMAT(WINAPI *GetdfDIJoystickFn)(void);
typedef BOOL(WINAPI *Fifa16ModHostStartFn)(void);
typedef HANDLE(WINAPI *CreateFileAFn)(
    LPCSTR,
    DWORD,
    DWORD,
    LPSECURITY_ATTRIBUTES,
    DWORD,
    DWORD,
    HANDLE);
typedef HANDLE(WINAPI *CreateFileWFn)(
    LPCWSTR,
    DWORD,
    DWORD,
    LPSECURITY_ATTRIBUTES,
    DWORD,
    DWORD,
    HANDLE);
typedef BOOL(WINAPI *ReadFileFn)(HANDLE, LPVOID, DWORD, LPDWORD, LPOVERLAPPED);
typedef BOOL(WINAPI *WriteFileFn)(HANDLE, LPCVOID, DWORD, LPDWORD, LPOVERLAPPED);
typedef DWORD(WINAPI *GetFinalPathNameByHandleWFn)(
    HANDLE,
    LPWSTR,
    DWORD,
    DWORD);
typedef NTSTATUS(NTAPI *NtCreateFileFn)(
    PHANDLE,
    ACCESS_MASK,
    POBJECT_ATTRIBUTES,
    PIO_STATUS_BLOCK,
    PLARGE_INTEGER,
    ULONG,
    ULONG,
    ULONG,
    ULONG,
    PVOID,
    ULONG);

static HMODULE g_self;
/* The L9 module owns the low-level FIFA executable patches.  This wrapper
 * remains the only dinput8.dll placed in the game root, so the Career UI,
 * save workflow and optional plugins stay under this project's control. */
static HMODULE g_l9_proxy;
static DirectInput8CreateFn g_direct_input8_create;
static DllCanUnloadNowFn g_dll_can_unload_now;
static DllGetClassObjectFn g_dll_get_class_object;
static DllRegisterServerFn g_dll_register_server;
static DllUnregisterServerFn g_dll_unregister_server;
static GetdfDIJoystickFn g_getdf_di_joystick;
static char g_game_dir[MAX_PATH];
/* Runtime data belongs in one auditable mod directory.  Keep g_game_dir for
 * FIFA's executable assets (notably the legacy dinput8_v33 proxy), while
 * every cache, marker, diagnostic log and bridge script uses g_mod_dir. */
static char g_mod_dir[MAX_PATH];
static unsigned char *g_module_base;
static SIZE_T g_module_size;
/* Read by the Server through the PE export table; no remote call needed. */
const DWORD Fifa16CareerJobOfferProtocol = 1;
static CreateFileAFn g_original_create_file_a;
static CreateFileWFn g_original_create_file_w;
static ReadFileFn g_original_read_file;
static WriteFileFn g_original_write_file;
static GetFinalPathNameByHandleWFn g_get_final_path_name_by_handle_w;
static NtCreateFileFn g_original_nt_create_file;
static SRWLOCK g_save_path_lock = SRWLOCK_INIT;
static char g_candidate_save_data_path[1024];
static char g_committed_save_data_path[1024];
static volatile LONG g_save_file_hook_count;
/* Keep one bridge worker per FIFA process.  Duplicate workers race while
 * writing the shared cache and can alternate between old and live calendars. */
static HANDLE g_bridge_instance_mutex;

#include "active_save_probe.inc"


typedef int (*StandingStatFn)(void *, int, int);
typedef void (*PrepareFieldFn)(void *);
typedef void (*SetIntFn)(void *, const char *, int);
typedef void (*SetStringFn)(void *, const char *, const char *);
typedef void *(*StatsVectorFn)(void *, int, unsigned char);
typedef void (*StatsProviderFn)(void *);
typedef void (*StatsMarkDirtyFn)(void *, unsigned char);
typedef void (*StandingProviderFn)(void *);
typedef void (*GetServiceDescriptorFn)(void *);
typedef int (*GetSelectionFn)(void *);
typedef int *(*GetCompetitionRefFn)(void *, int);
typedef void (*InitStatContainerFn)(void *);
typedef void (*QueryPlayerStatsFn)(void *, int, int, int, int, void *);
typedef int (*StatContainerCountFn)(void *);
typedef void *(*StatContainerItemFn)(void *, int);
typedef int (*StatItemValueFn)(void *, int);
typedef void (*ResolvePlayerNameFn)(void *, void *, char *, int);
typedef void (*ResolveTeamFn)(void *, int, void *);
typedef int (*FullStatsCategoryFn)(void *, const char *);
typedef void *(*GetCareerContextFn)(void *);
typedef void *(*GetUserTeamFn)(void *, int);
typedef void (*ContractsProviderFn)(void *);
typedef void (*IndexedIntFn)(void *, int, const char *, int);
typedef void (*IndexedStringFn)(void *, int, const char *, const char *);
typedef int (*CalendarAssetForDateFn)(void *, const void *);
typedef void *(*ResolveCareerStartupObjectFn)(uintptr_t);

static StandingStatFn g_standing_stat;
static PrepareFieldFn g_prepare_field;
static SetIntFn g_set_int;
static SetStringFn g_set_string;
static StatsVectorFn g_stats_vector;
static StatsProviderFn g_stats_provider;
static StatsMarkDirtyFn g_stats_mark_dirty;
static StandingProviderFn g_standing_provider;
static GetServiceDescriptorFn g_get_competition_service_descriptor;
static GetServiceDescriptorFn g_get_name_service_descriptor;
static GetServiceDescriptorFn g_get_query_service_descriptor;
static GetSelectionFn g_get_selection;
static GetCompetitionRefFn g_get_competition_ref;
static InitStatContainerFn g_init_stat_container;
static QueryPlayerStatsFn g_query_player_stats;
static void *g_stats_tile_query_service;
static void *g_stats_tile_name_service;
static int g_stats_tile_query_competition;
static int g_stats_tile_team_filter = -1;
static int g_stats_tile_stat_type = -1;
static int g_stats_tile_scope_filter = -1;
static int g_last_stats_query_log_competition = -1;
static int g_last_stats_query_log_type = -999;
static StatContainerCountFn g_stat_container_count;
static StatContainerItemFn g_stat_container_item;
static StatItemValueFn g_stat_item_value;
static ResolvePlayerNameFn g_resolve_player_name;
static ResolveTeamFn g_resolve_team;
static FullStatsCategoryFn g_full_stats_category;
static GetServiceDescriptorFn g_get_career_service_descriptor;
static GetCareerContextFn g_get_career_context;
static GetUserTeamFn g_get_user_team;
static ContractsProviderFn g_contracts_provider;
static IndexedIntFn g_set_indexed_int;
static IndexedStringFn g_set_indexed_string;
static CalendarAssetForDateFn g_calendar_asset_for_date;
static ResolveCareerStartupObjectFn g_resolve_career_startup_object;

static void *g_current_standing_record;
static void *g_current_stats_object;
static void *g_current_stats_provider;
static void *g_current_stats_provider_owner;
static void *g_pending_stats_provider_owner;
static void *g_pending_stats_provider_vtable;
static void *g_pending_stats_provider_registry;
static CardRefreshSchedule g_stats_refresh_schedule;
static unsigned long g_pending_stats_context_epoch;
static DWORD g_pending_stats_thread;
static volatile LONG g_stats_ready_generation;
static volatile LONG g_stats_tick_thread_mismatch;
static unsigned long g_stats_applied_generation;
static BOOL g_stats_publication_completed;
static volatile LONG g_pending_stats_refresh_busy;
static volatile LONG g_last_requested_calendar_date;
static char g_current_standing_field[32];

typedef struct RankedPlayer
{
    int head;
    int logo;
    int value;
    char name[128];
} RankedPlayer;

static RankedPlayer g_assist_rows[5];
static SIZE_T g_assist_count;
/* Save-derived rows are independent from FIFA's screen-local statistic
 * vector, which can belong to another competition after navigation. */
static RankedPlayer g_save_assist_rows[5][5];
static SIZE_T g_save_assist_counts[5];
static int g_save_assist_competitions[5];
static SIZE_T g_save_assist_competition_count;
static int g_save_assist_club_id;
static RankedPlayer g_club_goal_rows[5];
static SIZE_T g_club_goal_count;
static RankedPlayer g_club_assist_rows[5];
static SIZE_T g_club_assist_count;
static volatile LONG g_active_competition_id;
static volatile LONG g_standing_competition_id;
static volatile LONG g_full_stats_competition_id;
static volatile LONG g_full_stats_category_id;
static volatile LONG g_last_logged_category_id = -999;
static volatile LONG g_last_logged_vector_category = -999;
static volatile LONG g_user_club_id;
static volatile LONG g_crowd_api_last_live_club;
static volatile LONG g_crowd_api_last_live_competition;
static volatile LONG g_crowd_api_fallback_logged;
static volatile LONG g_user_team_key = -1;
static void *g_career_context_identity;
static int g_career_context_club;
static int g_assist_competition_id;
static BOOL g_assist_official_capture;
static int g_club_assist_competition_id;
static int g_club_assist_club_id;
static RankedPlayer g_club_yellow_rows[5];
static SIZE_T g_club_yellow_count;
static RankedPlayer g_club_red_rows[5];
static SIZE_T g_club_red_count;
static int g_card_competition_id;
static int g_card_club_id;

typedef struct InjuryRow
{
    int head;
    char name[128];
    char injury[128];
    char length[64];
    char status[128];
} InjuryRow;

typedef struct FixtureRow
{
    int home_logo;
    int away_logo;
    int competition_id;
    int stage_id;
    char date[64];
    char home[128];
    char away[128];
    char score[32];
    char time[32];
} FixtureRow;

typedef struct CoachRecord
{
    int games;
    int wins;
    int draws;
    int losses;
    int points;
    int percent;
    int home_games;
    int home_wins;
    int home_points;
    int home_percent;
    int away_games;
    int away_wins;
    int away_points;
    int away_percent;
} CoachRecord;

/* Calculated from the live FCE fixture snapshot, including unsaved advances. */
static CoachRecord g_coach_record;

/*
 * Dynamic RAM provenance tracker.
 *
 * The game allocates Career objects on the heap, so an absolute address is
 * not a stable identifier.  The tracker records the address found during
 * the current session, its module-relative offset when applicable, the
 * semantic validation context and the source path/query that produced it.
 * This makes a relocation visible without making the renderer depend on a
 * hard-coded heap address.
 */
static uintptr_t g_ram_tracker_last_vector;
static uintptr_t g_ram_tracker_last_vector_begin;
static uintptr_t g_ram_tracker_last_vector_end;
static int g_ram_tracker_last_vector_competition;
static int g_ram_tracker_last_vector_category;
static uintptr_t g_ram_tracker_last_query_container;
static int g_ram_tracker_last_query_key;
static int g_ram_tracker_last_query_competition;
static int g_ram_tracker_last_query_count;
static SIZE_T g_ram_tracker_fixture_log_count;
static SIZE_T g_ram_tracker_raw_log_count;
static uintptr_t g_ram_tracker_last_save_image;
static unsigned long long g_ram_tracker_last_save_size;
static SIZE_T g_ram_tracker_last_save_anchors;
static DWORD g_ram_tracker_forensic_tick;

static unsigned long long ram_tracker_module_rva(const void *address);
static FILE *ram_tracker_open(void);
static void ram_tracker_log_data_path(const char *path);
static void ram_tracker_log_stats_vector(
    const void *vector,
    const void *begin,
    const void *end,
    int category,
    int selected_category,
    int competition_id,
    SIZE_T count,
    const char *source);
static void ram_tracker_log_stats_query(
    const void *container,
    int display_competition,
    int query_competition,
    int count);
static void ram_tracker_log_fixture(
    const void *record,
    const FixtureRow *fixture,
    const char *source);
static void ram_tracker_reset_fixture_log(void);
static void ram_tracker_reset_raw_log(void);
static void ram_tracker_log_raw_calendar(
    const void *club_address,
    const void *date_address,
    int raw_date,
    const void *team_address,
    int other_team,
    const void *competition_address,
    int competition_id,
    const void *stage_address,
    int stage_id);
static void ram_tracker_scan_raw_calendar(int club_id, int competition_id);
static void ram_tracker_scan_save_image(int club_id);
static BOOL ram_tracker_get_reference_data_path(char *path, SIZE_T capacity);
static BOOL form_memory_protection_is_readable(DWORD protection);
static BOOL ram_tracker_dump_save_image(
    const void *candidate,
    const char *reference_path,
    SIZE_T data_size,
    SIZE_T anchors);
static void ram_tracker_log_scan_summary(
    int club_id,
    int competition_id,
    SIZE_T upcoming_count,
    SIZE_T competition_count);


/* ram_tracker_module_rva: removed obsolete bridge/scanner path. */


/* ram_tracker_open: removed obsolete bridge/scanner path. */


/* ram_tracker_log_data_path: removed obsolete bridge/scanner path. */


/* ram_tracker_log_stats_vector: removed obsolete bridge/scanner path. */


/* ram_tracker_log_stats_query: removed obsolete bridge/scanner path. */


/* ram_tracker_log_fixture: removed obsolete bridge/scanner path. */


/* ram_tracker_reset_fixture_log: removed obsolete bridge/scanner path. */


/* ram_tracker_reset_raw_log: removed obsolete bridge/scanner path. */


/* ram_tracker_log_raw_calendar: removed obsolete bridge/scanner path. */


/* ram_tracker_log_scan_summary: removed obsolete bridge/scanner path. */


/* ram_tracker_find_bytes: removed obsolete bridge/scanner path. */

#define FIXTURE_CAPTURE_CAPACITY 512
#define FORM_MATCH_CAPACITY 512
#define FORM_ASSET_EMPTY 990000
#define FORM_ASSET_WIN 990001
#define FORM_ASSET_DRAW 990002
#define FORM_ASSET_LOSS 990003
#define POSITION_ASSET_EMPTY 990010
#define POSITION_ASSET_UP 990011
#define POSITION_ASSET_DOWN 990012
#define POSITION_ASSET_STABLE 990013

typedef struct FormMatch
{
    int home_logo;
    int away_logo;
    int home_score;
    int away_score;
    int date_key;
    char date[64];
} FormMatch;

typedef struct StandingSnapshot
{
    int club_id;
    int current_rank;
    int played;
    int won;
    int drawn;
    int lost;
    int goals_for;
    int goals_against;
    int goal_difference;
    int points;
    BOOL metrics_ready;
} StandingSnapshot;

typedef struct PreviousStanding
{
    int source_row;
    int current_rank;
    int points;
    int won;
    int goals_for;
    int goal_difference;
    BOOL removed_match;
} PreviousStanding;

static RankedPlayer g_salary_rows[5];
static SIZE_T g_salary_count;
static int g_salary_club_id;
static int g_roster_player_ids[100];
static char g_roster_player_names[100][128];
static SIZE_T g_roster_player_count;
static int g_roster_club_id;
typedef struct NativeSquadSummary
{
    int available;
    int total;
    int average_age;
    int age_count;
    int average_overall;
    int overall_count;
    int goalkeepers;
    int defenders;
    int midfielders;
    int attackers;
    int position_count;
    int source;
} NativeSquadSummary;
static NativeSquadSummary g_squad_summary;
static InjuryRow g_injury_rows[5];
static SIZE_T g_injury_count;
static int g_injury_club_id;
static InjuryRow g_injury_current;
static void *g_injury_capture_provider;
static DWORD g_injury_last_tick;
static BOOL g_injury_current_committed;
static volatile LONG g_injury_refresh_busy;
/* The game instantiates its InjuryList provider only when that native screen
 * is opened. Keep the last provider-confirmed rows per club in a tiny UI
 * snapshot so the My Team card is populated on the next hub render. This is
 * presentation data in ModCarrerMode only; no career save is edited. */
static int g_injury_snapshot_loaded_club;
static FixtureRow g_fixture_capture[FIXTURE_CAPTURE_CAPACITY];
static SIZE_T g_fixture_capture_count;
/* Indexed UI callbacks arrive one field at a time and may expose only one
 * tile.  Keep them out of the complete RAM calendar so row zero cannot erase
 * the authoritative cross-competition snapshot. */
static FixtureRow g_ui_fixture_capture[FIXTURE_CAPTURE_CAPACITY];
static SIZE_T g_ui_fixture_capture_count;
/* The competition calendar shows the next ten fixtures for the career club. */
static FixtureRow g_upcoming_rows[10];
static SIZE_T g_upcoming_count;
static int g_upcoming_club_id;
static FixtureRow g_club_previous_rows[10];
static SIZE_T g_club_previous_count;
static int g_club_previous_club_id;
static FixtureRow g_round_previous_rows[10];
static SIZE_T g_round_previous_count;
static FixtureRow g_round_next_rows[10];
static SIZE_T g_round_next_count;
static int g_round_competition_id;
static int g_round_club_id;
static volatile LONG g_display_competition_id;
static BOOL g_standing_knockout_mode;
static FixtureRow g_knockout_fixture;
static BOOL g_standing_previous_leg_visible;
static char g_standing_previous_leg_score[32];
static FormMatch g_form_matches[FORM_MATCH_CAPACITY];
static SIZE_T g_form_match_count;
static int g_form_competition_id;
static int g_standing_logos[20];
static StandingSnapshot g_standing_rows[20];
static DWORD g_form_memory_scan_tick;
static int g_form_memory_scan_competition;
static DWORD g_fixture_memory_scan_tick;
static int g_fixture_memory_scan_competition;
static int g_fixture_memory_scan_club;
static DWORD g_upcoming_memory_scan_tick;
static int g_upcoming_memory_scan_club;
static int g_bridge_generation;
static int g_bridge_club_id;
static int g_bridge_current_date;
static int g_bridge_status_state;
static int g_bridge_status_timestamp;
static BOOL g_bridge_upcoming_authoritative;
/* Sticky for the current FIFA session once RAM is newer than the DATA cache. */
static BOOL g_live_ram_priority;

typedef struct TeamNameRow
{
    int team_id;
    char name[128];
} TeamNameRow;

#define BRIDGE_TEAM_CAPACITY 2048
static TeamNameRow g_bridge_team_names[BRIDGE_TEAM_CAPACITY];
static SIZE_T g_bridge_team_name_count;

static void refresh_form_cache_from_memory(void);
static void refresh_fixture_capture_from_memory(void);
static int form_date_key(const char *date);
static void refresh_form_cache(void);
static void refresh_upcoming_rows(void);
static void refresh_club_previous_from_memory(void);
static void refresh_round_rows(void);
static void publish_round_rows(void *provider);
static void ram_tracker_mark_live_priority(SIZE_T rows);
static void publish_round_group(
    void *provider,
    const char *prefix,
    FixtureRow *rows,
    SIZE_T count);
static void load_round_cache(void);
static void load_competitions_cache(void);
static void publish_competitions(void *provider);
static int resolve_user_club_id(void *provider_owner, FILE *log);
static void *owner_service(
    void *owner,
    GetServiceDescriptorFn get_descriptor,
    int *service_index);
static SIZE_T query_top_assists(void *provider_owner, FILE *log);
static BOOL fixture_rows_equal(
    const FixtureRow *left,
    const FixtureRow *right);
static BOOL fixture_rows_same_match(
    const FixtureRow *left,
    const FixtureRow *right);
static BOOL fixture_rows_same_calendar_slot(
    const FixtureRow *left,
    const FixtureRow *right);
static BOOL fixture_belongs_to_competition(
    const FixtureRow *fixture,
    int competition_id);
static int fixture_date_sort_key(const FixtureRow *fixture);
static BOOL current_ram_differs_from_disk_snapshot(void);
static void merge_live_fixture_state(
    FixtureRow *baseline,
    const FixtureRow *live);
static BOOL merge_fixture_row_into_set(
    FixtureRow *rows,
    SIZE_T *count,
    SIZE_T capacity,
    const FixtureRow *incoming);
static int compare_fixture_rows(const void *left, const void *right);

typedef struct AssistCacheDisk
{
    uint32_t magic;
    int competition_id;
    int count;
    RankedPlayer rows[5];
} AssistCacheDisk;

#define ASSIST_CACHE_MAGIC 0x33535341u
#define ASSIST_CACHE_OFFICIAL_MAGIC 0x4F535341u

typedef struct SaveAssistCompetitionDisk
{
    int competition_id;
    int count;
    RankedPlayer rows[5];
} SaveAssistCompetitionDisk;

typedef struct SaveAssistsCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    SaveAssistCompetitionDisk competitions[5];
} SaveAssistsCacheDisk;

#define SAVE_ASSISTS_CACHE_MAGIC 0x36535341u

typedef struct ClubAssistCacheDisk
{
    uint32_t magic;
    int competition_id;
    int club_id;
    int count;
    RankedPlayer rows[5];
} ClubAssistCacheDisk;

#define CLUB_ASSIST_CACHE_MAGIC 0x424C4341u

typedef struct ClubCardsCacheDisk
{
    uint32_t magic;
    int competition_id;
    int club_id;
    int yellow_count;
    int red_count;
    RankedPlayer yellow[5];
    RankedPlayer red[5];
} ClubCardsCacheDisk;

#define CLUB_CARDS_CACHE_MAGIC 0x44524343u

typedef struct SalaryCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    RankedPlayer rows[5];
} SalaryCacheDisk;

#define SALARY_CACHE_MAGIC 0x594C4153u

typedef struct RosterCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    int player_ids[100];
} RosterCacheDisk;

#define ROSTER_CACHE_MAGIC 0x54534F52u

typedef struct UpcomingCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    FixtureRow rows[10];
} UpcomingCacheDisk;

/* Bump the format so an old five-row cache is never read as ten rows. */
#define UPCOMING_CACHE_MAGIC 0x354F5055u

typedef struct ClubPreviousCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    FixtureRow rows[10];
} ClubPreviousCacheDisk;

#define CLUB_PREVIOUS_CACHE_MAGIC 0x35525043u

typedef struct ClubStatsBridgeDisk
{
    uint32_t magic;
    int club_id;
    int goal_count;
    int assist_count;
    int generation;
    RankedPlayer goals[5];
    RankedPlayer assists[5];
} ClubStatsBridgeDisk;

#define CLUB_STATS_BRIDGE_MAGIC 0x34545343u

typedef struct BridgeCacheDisk
{
    uint32_t magic;
    int club_id;
    int generation;
    int current_date;
} BridgeCacheDisk;

#define BRIDGE_CACHE_MAGIC 0x34475242u
#define BRIDGE_STATUS_MAGIC 0x36544253u
#define TEAM_NAMES_CACHE_MAGIC 0x344D4E54u

typedef struct BridgeStatusDisk
{
    uint32_t magic;
    int state;
    int timestamp;
} BridgeStatusDisk;

typedef struct RoundCacheDisk
{
    uint32_t magic;
    int competition_id;
    int club_id;
    int previous_count;
    int next_count;
    FixtureRow previous_rows[10];
    FixtureRow next_rows[10];
} RoundCacheDisk;

#define ROUND_CACHE_MAGIC 0x34444E52u

typedef struct CompetitionSummary
{
    int competition_id;
    int kind;
    int league_id;
    int rank;
    int played;
    int points;
    int stage;
    int next_home_logo;
    int next_away_logo;
    int next_date;
    int next_time;
    char title_key[64];
} CompetitionSummary;

typedef struct CompetitionStandingRow
{
    int rank;
    int team_id;
    int played;
    int points;
} CompetitionStandingRow;

#define COMPETITION_TAB_CAPACITY 5
#define COMPETITION_TAB_ROW_CAPACITY 20
#define COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY 3

typedef struct CompetitionTabRow
{
    int team_id;
    int rank;
    int played;
    int won;
    int drawn;
    int lost;
    int goals_for;
    int goals_against;
    int points;
} CompetitionTabRow;

typedef struct CompetitionTabKnockout
{
    int visible;
    int stage;
    int round;
    int home_team;
    int away_team;
    int date;
    int time;
    int played;
    int home_score;
    int away_score;
} CompetitionTabKnockout;

typedef struct CompetitionCacheDisk
{
    uint32_t magic;
    int club_id;
    int count;
    CompetitionSummary rows[COMPETITION_TAB_CAPACITY];
    CompetitionStandingRow league_rows[20];
} CompetitionCacheDisk;

#define COMPETITIONS_CACHE_MAGIC 0x36504D43u

typedef struct FixtureCompetitionAssetRow
{
    int competition_id;
    int asset_id;
} FixtureCompetitionAssetRow;

#define FIXTURE_COMPETITION_ASSET_CAPACITY 128
#define FIXTURE_COMPETITION_ASSET_CACHE_MAGIC 0x31434146u

typedef struct FixtureCompetitionAssetCacheDisk
{
    uint32_t magic;
    int count;
    int reserved;
    FixtureCompetitionAssetRow rows[FIXTURE_COMPETITION_ASSET_CAPACITY];
} FixtureCompetitionAssetCacheDisk;

static CompetitionSummary g_competition_rows[COMPETITION_TAB_CAPACITY];
static CompetitionStandingRow g_competition_league_rows[20];
static CompetitionTabRow
    g_competition_tab_rows[COMPETITION_TAB_CAPACITY][COMPETITION_TAB_ROW_CAPACITY];
static SIZE_T g_competition_tab_row_counts[COMPETITION_TAB_CAPACITY];
static CompetitionTabKnockout
    g_competition_tab_knockout[COMPETITION_TAB_CAPACITY];
static CompetitionTabKnockout
    g_competition_tab_knockout_history
        [COMPETITION_TAB_CAPACITY][COMPETITION_TAB_KNOCKOUT_HISTORY_CAPACITY];
static SIZE_T
    g_competition_tab_knockout_history_counts[COMPETITION_TAB_CAPACITY];
static SIZE_T g_competition_count;
static int g_competition_club_id;
static FixtureCompetitionAssetRow
    g_fixture_competition_assets[FIXTURE_COMPETITION_ASSET_CAPACITY];
static SIZE_T g_fixture_competition_asset_count;


/*
 * All career match cards use the same live identity -> installed INI ID
 * resolver as CalendarCell. No raw object, fixture or artwork-existence guess.
 */
static int competition_icon_asset_id(int competition_id)
{
    return native_logo(competition_id);
}


/* The UI reuses the last valid asset when it receives id zero.  Use the
 * transparent placeholder shipped with the mod for an empty/missing match
 * instead, so an old competition crest can never leak into a blank row. */
static int fixture_competition_icon_or_blank(const FixtureRow *fixture)
{
    int asset = fixture && fixture->home_logo > 0 && fixture->away_logo > 0
        ? native_logo(fixture->competition_id) : 0;
    return asset > 0 ? asset : FORM_ASSET_EMPTY;
}

typedef struct FormCacheDisk
{
    uint32_t magic;
    int competition_id;
    int club_id;
    int count;
    FormMatch matches[FORM_MATCH_CAPACITY];
} FormCacheDisk;

#define FORM_CACHE_MAGIC 0x324D5246u


/* active_competition_path: removed obsolete bridge/scanner path. */


/* load_active_competition: removed obsolete bridge/scanner path. */


/* save_active_competition: removed obsolete bridge/scanner path. */


/* save_active_club: removed obsolete bridge/scanner path. */


/* save_fallback_competition: removed obsolete bridge/scanner path. */


/* save_standing_competition: removed obsolete bridge/scanner path. */


/* assist_cache_path: removed obsolete bridge/scanner path. */


/* load_assist_cache: removed obsolete bridge/scanner path. */


/* load_save_assists_cache: removed obsolete bridge/scanner path. */


/* competition_ids_equivalent: removed obsolete bridge/scanner path. */


/* save_assists_for_competition: removed obsolete bridge/scanner path. */


/* save_assist_cache: removed obsolete bridge/scanner path. */


/* club_assist_cache_path: removed obsolete bridge/scanner path. */


/* load_club_assist_cache: removed obsolete bridge/scanner path. */


/* save_club_assist_cache: removed obsolete bridge/scanner path. */


/* cache_file_path: removed obsolete bridge/scanner path. */


/* read_cache_file: removed obsolete bridge/scanner path. */


/* write_cache_file: removed obsolete bridge/scanner path. */


/* load_club_cards_cache: removed obsolete bridge/scanner path. */


/* save_club_cards_cache: removed obsolete bridge/scanner path. */


/* load_salary_cache: removed obsolete bridge/scanner path. */


static void save_salary_cache(void)
{
    /* Session-only native values: no persistent career cache. */
}


/* load_roster_cache: removed obsolete bridge/scanner path. */


static void save_roster_cache(void)
{
    /* Session-only native values: no persistent career cache. */
}


/* roster_contains_player: removed obsolete bridge/scanner path. */


/* load_upcoming_cache: removed obsolete bridge/scanner path. */


/* save_upcoming_cache: removed obsolete bridge/scanner path. */


/* load_club_previous_cache: removed obsolete bridge/scanner path. */


/* load_club_stats_bridge: removed obsolete bridge/scanner path. */


/* load_bridge_team_names: removed obsolete bridge/scanner path. */


static const char *bridge_team_name(int team_id)
{
    SIZE_T index;
    for (index = 0; index < g_bridge_team_name_count; index++)
        if (g_bridge_team_names[index].team_id == team_id)
            return g_bridge_team_names[index].name;
    return "";
}


/* load_competitions_cache: removed obsolete bridge/scanner path. */


/* load_fixture_competition_asset_cache: removed obsolete bridge/scanner path. */


/* reload_bridge_caches: removed obsolete bridge/scanner path. */


/* load_bridge_status: removed obsolete bridge/scanner path. */


/* load_round_cache: removed obsolete bridge/scanner path. */


/* save_round_cache: removed obsolete bridge/scanner path. */

/* form_cache_file_name: removed obsolete bridge/scanner path. */


/* load_form_cache: removed obsolete bridge/scanner path. */


/* save_form_cache: removed obsolete bridge/scanner path. */


/* query_player_stats_capture: removed obsolete bridge/scanner path. */


/* stats_tile_query_capture: removed obsolete bridge/scanner path. */


/* is_hex_save_directory: removed obsolete bridge/scanner path. */


/* capture_save_data_path: removed obsolete bridge/scanner path. */


/* create_file_a_capture: removed obsolete bridge/scanner path. */


/* create_file_w_capture: removed obsolete bridge/scanner path. */


/* nt_create_file_capture: removed obsolete bridge/scanner path. */


/* install_nt_create_file_hook: removed obsolete bridge/scanner path. */


/* replace_import_address: removed obsolete bridge/scanner path. */


/* install_save_file_hooks: removed obsolete bridge/scanner path. */


/* commit_active_save_path: removed obsolete bridge/scanner path. */


static void initialize_paths(void)
{
    char path[MAX_PATH];
    DWORD length = GetModuleFileNameA(g_self, path, MAX_PATH);
    if (length == 0 || length >= MAX_PATH)
        return;
    char *separator = strrchr(path, '\\');
    if (separator)
        *separator = '\0';
    lstrcpynA(g_game_dir, path, MAX_PATH);
    snprintf(g_mod_dir, sizeof(g_mod_dir), "%s\\ModCarrerMode", g_game_dir);
    CreateDirectoryA(g_mod_dir, NULL);
    career_path_logs(g_mod_dir);
}


/* This log deliberately records only loader state.  It is written from the
 * worker or DirectInput entry point, never under DllMain's loader lock, so a
 * failed hook can be distinguished from a UI/data failure on the first run. */
static void append_loader_log(const char *event)
{
    char path[MAX_PATH];
    FILE *log;

    if (!g_mod_dir[0])
        return;
    snprintf(path, sizeof(path), "%s\\logs\\career_loader.log", g_mod_dir);
    log = fopen(path, "ab");
    if (!log)
        return;
    fprintf(
        log,
        "%s pid=%lu module=%p game=%s\\n",
        event,
        (unsigned long)GetCurrentProcessId(),
        (void *)g_self,
        g_game_dir);
    fclose(log);
}


/* prepare_career_session_markers: removed obsolete bridge/scanner path. */


static BOOL load_l9_proxy(void)
{
    if (g_direct_input8_create)
        return TRUE;

    char path[MAX_PATH];
    /* L9.65 is stored inside this custom DLL as RCDATA resource 101.  It is
     * materialized under its own name and receives DirectInput first, so its
     * database-capacity, scouting, formation and null-getter patches start
     * from a single authoritative chain before the Career hooks are used. */
    HRSRC resource = FindResourceA(
        g_self,
        MAKEINTRESOURCEA(101),
        RT_RCDATA);
    HGLOBAL resource_handle = resource ? LoadResource(g_self, resource) : NULL;
    DWORD resource_size = resource
        ? SizeofResource(g_self, resource)
        : 0;
    const void *resource_bytes = resource_handle
        ? LockResource(resource_handle)
        : NULL;
    if (resource_size > 0 && resource_bytes)
    {
        wsprintfA(path, "%s\\dinput8_l9_chain.dll", g_game_dir);
        /* Reuse only the exact embedded L9 build. This avoids modifying
         * dinput8_orig.dll or the system DirectInput module and makes an old
         * materialized chain self-heal on the next game start. */
        HANDLE existing = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ,
            NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (existing != INVALID_HANDLE_VALUE) {
            LARGE_INTEGER size;
            DWORD offset = 0;
            BOOL matches = GetFileSizeEx(existing, &size)
                && size.QuadPart == resource_size;
            while (matches && offset < resource_size) {
                unsigned char chunk[4096]; DWORD received = 0;
                DWORD length = resource_size - offset;
                if (length > sizeof(chunk)) length = sizeof(chunk);
                matches = ReadFile(existing, chunk, length, &received, NULL)
                    && received == length
                    && memcmp(chunk, (const unsigned char *)resource_bytes + offset, length) == 0;
                offset += length;
            }
            CloseHandle(existing);
            if (matches) g_l9_proxy = LoadLibraryA(path);
        }
        if (!g_l9_proxy) {
        HANDLE file = CreateFileA(
            path,
            GENERIC_WRITE,
            0,
            NULL,
            CREATE_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            NULL);
        if (file != INVALID_HANDLE_VALUE)
        {
            DWORD written = 0;
            BOOL saved = WriteFile(
                file,
                resource_bytes,
                resource_size,
                &written,
                NULL)
                && written == resource_size;
            if (saved)
                FlushFileBuffers(file);
            CloseHandle(file);
            if (saved)
                g_l9_proxy = LoadLibraryA(path);
        }
        }
    }
    if (!g_l9_proxy) {
        append_loader_log("l9_proxy_load_failed");
        return FALSE;
    }

    g_direct_input8_create = (DirectInput8CreateFn)GetProcAddress(
        g_l9_proxy,
        "DirectInput8Create");
    g_dll_can_unload_now = (DllCanUnloadNowFn)GetProcAddress(
        g_l9_proxy,
        "DllCanUnloadNow");
    g_dll_get_class_object = (DllGetClassObjectFn)GetProcAddress(
        g_l9_proxy,
        "DllGetClassObject");
    g_dll_register_server = (DllRegisterServerFn)GetProcAddress(
        g_l9_proxy,
        "DllRegisterServer");
    g_dll_unregister_server = (DllUnregisterServerFn)GetProcAddress(
        g_l9_proxy,
        "DllUnregisterServer");
    g_getdf_di_joystick = (GetdfDIJoystickFn)GetProcAddress(
        g_l9_proxy,
        "GetdfDIJoystick");
    append_loader_log(
        g_direct_input8_create
            ? "l9_proxy_chain_ready"
            : "l9_proxy_export_missing");
    return g_direct_input8_create != NULL;
}


typedef struct PatchSpec
{
    const char *name;
    uintptr_t rva;
    unsigned char size;
    unsigned char expected[6];
    unsigned char replacement[6];
} PatchSpec;


static const PatchSpec g_patches[] = {
    {
        "standings_display_count",
        0x059CD3FE,
        6,
        {0x41, 0xBC, 0x07, 0x00, 0x00, 0x00},
        {0x41, 0xBC, 0x14, 0x00, 0x00, 0x00},
    },
    {
        "standings_empty_rows_start",
        0x059CDA2D,
        4,
        {0x41, 0x83, 0xFC, 0x07, 0x00, 0x00},
        {0x41, 0x83, 0xFC, 0x14, 0x00, 0x00},
    },
    {
        "standings_empty_rows_loop",
        0x059CDA87,
        4,
        {0x41, 0x83, 0xFC, 0x07, 0x00, 0x00},
        {0x41, 0x83, 0xFC, 0x14, 0x00, 0x00},
    },
    {
        "top_scorers_result_count",
        0x059CE279,
        5,
        {0xB8, 0x03, 0x00, 0x00, 0x00, 0x00},
        {0xB8, 0x05, 0x00, 0x00, 0x00, 0x00},
    },
    {
        "top_scorers_publish_loop",
        0x059CEA33,
        4,
        {0x41, 0x83, 0xFE, 0x06, 0x00, 0x00},
        {0x41, 0x83, 0xFE, 0x0A, 0x00, 0x00},
    },
};


static BOOL bytes_equal(
    const unsigned char *left,
    const unsigned char *right,
    SIZE_T size)
{
    SIZE_T index;
    for (index = 0; index < size; index++)
    {
        if (left[index] != right[index])
            return FALSE;
    }
    return TRUE;
}
static BOOL apply_patch(
    unsigned char *module_base,
    const PatchSpec *patch,
    FILE *log)
{
    unsigned char *address = module_base + patch->rva;
    if (bytes_equal(address, patch->replacement, patch->size))
    {
        fprintf(
            log,
            "[JA APLICADO] %s @ 0x%llX\n",
            patch->name,
            (unsigned long long)(uintptr_t)address);
        return TRUE;
    }
    if (!bytes_equal(address, patch->expected, patch->size))
    {
        fprintf(
            log,
            "[ASSINATURA DIFERENTE] %s @ 0x%llX\n",
            patch->name,
            (unsigned long long)(uintptr_t)address);
        return FALSE;
    }

    DWORD old_protection;
    if (!VirtualProtect(
        address,
        patch->size,
        PAGE_EXECUTE_READWRITE,
        &old_protection))
    {
        fprintf(
            log,
            "[ERRO VirtualProtect=%lu] %s\n",
            (unsigned long)GetLastError(),
            patch->name);
        return FALSE;
    }

    memcpy(address, patch->replacement, patch->size);
    FlushInstructionCache(GetCurrentProcess(), address, patch->size);

    DWORD ignored;
    VirtualProtect(address, patch->size, old_protection, &ignored);
    if (!bytes_equal(address, patch->replacement, patch->size))
    {
        fprintf(log, "[ERRO VERIFICACAO] %s\n", patch->name);
        return FALSE;
    }

    fprintf(
        log,
        "[OK] %s @ 0x%llX\n",
        patch->name,
        (unsigned long long)(uintptr_t)address);
    return TRUE;
}


static int standing_stat_capture(void *record, int aggregate, int selector)
{
    g_current_standing_record = record;
    return g_standing_stat(record, aggregate, selector);
}


static void publish_int_field(void *provider, const char *field, int value)
{
    g_prepare_field(provider);
    g_set_string(provider, "ID", field);
    g_set_int(provider, "PARAM", value);
}


static void publish_string_field(
    void *provider,
    const char *field,
    const char *value)
{
    g_prepare_field(provider);
    g_set_string(provider, "ID", field);
    g_set_string(provider, "PARAM", value);
}

static void publish_visibility_field(
    void *provider,
    const char *field,
    BOOL visible)
{
    g_prepare_field(provider);
    g_set_string(provider, "ID", field);
    g_set_int(provider, "VISIBLE", visible ? 1 : 0);
}


/* ascii_contains_case_insensitive: removed obsolete bridge/scanner path. */


/* competition_logo_id_from_name: removed obsolete bridge/scanner path. */


static void set_display_competition(int competition_id)
{
    InterlockedExchange(&g_display_competition_id, competition_id);
}


static void publish_league_row_visibility(
    void *provider,
    int row,
    BOOL visible)
{
    static const char *fields[] = {
        "ROW",
        "RANK",
        "POSITION_",
        "LOGO",
        "NAME",
        "PLAYED",
        "WDL",
        "GOALS",
        "POINTS",
    };
    char key[48];
    SIZE_T index;
    for (index = 0; index < sizeof(fields) / sizeof(fields[0]); index++)
    {
        snprintf(key, sizeof(key), "%s%d", fields[index], row);
        publish_visibility_field(provider, key, visible);
    }
    int slot;
    for (slot = 0; slot < 5; slot++)
    {
        snprintf(key, sizeof(key), "FORM_%d_%d", row, slot);
        publish_visibility_field(provider, key, visible);
    }
}


static void publish_knockout_leg_visibility(
    void *provider,
    BOOL visible)
{
    static const char *fields[] = {
        "CM_KO_LEG_LABEL",
        "CM_KO_LEG_DIVIDER",
        "CM_KO_LEG_SCORE",
        "CM_KO_LEG_HOME",
        "CM_KO_LEG_AWAY",
    };
    SIZE_T index;
    for (index = 0; index < sizeof(fields) / sizeof(fields[0]); index++)
        publish_visibility_field(provider, fields[index], visible);
}


/* The layout contains both the league-table and knockout fields, so merely
 * visiting KO_NAME while parsing the provider must not switch a league page
 * into cup mode. Only the active competition's current knockout fixture can
 * enable that presentation. */
static BOOL stock_standing_has_league_rows(void)
{
    int row;
    int count = 0;

    /* The native competition snapshot can be temporarily empty while FIFA's
     * stock standings provider has already populated the visible league. In
     * that window, the fixture-only fallback must not expose the cup fields
     * over the league rows. Three clubs are enough to distinguish a table
     * from a knockout fixture without changing the cup path. */
    for (row = 0; row < 20; row++)
    {
        if (g_standing_rows[row].club_id > 0)
            count++;
    }
    return count >= 3;
}


static BOOL active_standing_knockout_context(void)
{
    const CompetitionSummary *summary;
    const CompetitionTabKnockout *current;

    if (g_competition_count == 0
        || g_competition_count > COMPETITION_TAB_CAPACITY)
        return FALSE;

    if (stock_standing_has_league_rows())
        return FALSE;

    summary = &g_competition_rows[0];
    current = &g_competition_tab_knockout[0];
    return summary->competition_id > 0
        && summary->kind == 0
        && current->visible
        && current->stage > 0
        && current->round > 0
        && current->home_team > 0
        && current->away_team > 0;
}


static void clear_standing_knockout_fields(void *provider)
{
    static const char *text_fields[] = {
        "KO_NAME",
        "KO_STAGE",
        "KO_TEAM0",
        "KO_TEAM1",
    };
    SIZE_T index;

    /* Visibility alone is not enough here: Flux can retain the last cup
     * values in a reused provider. Clear the payload as well so a league
     * render cannot inherit a cup crest or label from the previous screen. */
    for (index = 0; index < sizeof(text_fields) / sizeof(text_fields[0]); index++)
        publish_string_field(provider, text_fields[index], "");
    publish_int_field(provider, "KO_LOGO0", FORM_ASSET_EMPTY);
    publish_int_field(provider, "KO_LOGO1", FORM_ASSET_EMPTY);
    publish_int_field(provider, "CM_KO_COMPETITION_ICON", FORM_ASSET_EMPTY);
    publish_int_field(provider, "TROPHYID", FORM_ASSET_EMPTY);
    publish_string_field(provider, "CM_KO_LEG_LABEL", "");
    publish_string_field(provider, "CM_KO_LEG_DIVIDER", "");
    publish_string_field(provider, "CM_KO_LEG_SCORE", "");
    publish_string_field(provider, "CM_KO_LEG_HOME", "");
    publish_string_field(provider, "CM_KO_LEG_AWAY", "");
}


static void publish_standing_mode(
    void *provider,
    BOOL knockout)
{
    static const char *league_headers[] = {
        "HEADER",
        "PLAYEDLABEL",
        "WDL_LABEL",
        "GOALS_LABEL",
        "POINTSLABEL",
    };
    static const char *knockout_fields[] = {
        "KO_RECT0",
        "KO_RECT1",
        "KO_RECT2",
        "KO_NAME",
        "KO_STAGE",
        "KO_LOGO0",
        "KO_TEAM0",
        "KO_LOGO1",
        "KO_TEAM1",
    };
    SIZE_T index;
    knockout = knockout && active_standing_knockout_context();
    g_standing_knockout_mode = knockout;
    if (!knockout)
    {
        g_standing_previous_leg_visible = FALSE;
        g_standing_previous_leg_score[0] = 0;
    }

    for (
        index = 0;
        index < sizeof(league_headers) / sizeof(league_headers[0]);
        index++)
        publish_visibility_field(
            provider,
            league_headers[index],
            !knockout);
    int row;
    for (row = 0; row < 20; row++)
        publish_league_row_visibility(provider, row, !knockout);
    for (
        index = 0;
        index < sizeof(knockout_fields) / sizeof(knockout_fields[0]);
        index++)
        publish_visibility_field(
            provider,
            knockout_fields[index],
            knockout);
    publish_visibility_field(provider, "LEAGUELOGO", !knockout);
    publish_visibility_field(provider, "CM_KO_COMPETITION_ICON", FALSE);
    publish_knockout_leg_visibility(provider, FALSE);
    publish_visibility_field(provider, "CM_KO_LEG_VISIBLE", FALSE);
    publish_visibility_field(provider, "TROPHYID", FALSE);
    if (!knockout)
        clear_standing_knockout_fields(provider);
}


/* fixture_score_is_future: removed obsolete bridge/scanner path. */


static void refresh_knockout_round(void)
{
    /* Authoritative data is supplied by the native snapshot at provider entry. */
}


static void publish_standing_knockout_details(void *provider);


/* form_result_for_match: removed obsolete bridge/scanner path. */


static const FormMatch *latest_form_match_for_club(int club_id)
{
    const FormMatch *best = NULL;
    SIZE_T index;
    for (index = 0; index < g_form_match_count; index++)
    {
        const FormMatch *match = &g_form_matches[index];
        if (
            match->home_logo != club_id
            && match->away_logo != club_id)
            continue;
        if (
            !best
            || match->date_key > best->date_key
            || (
                match->date_key == best->date_key
                && match > best))
            best = match;
    }
    return best;
}


static BOOL previous_standing_precedes(
    const PreviousStanding *left,
    const PreviousStanding *right)
{
    if (left->points != right->points)
        return left->points > right->points;
    if (left->won != right->won)
        return left->won > right->won;
    if (left->goal_difference != right->goal_difference)
        return left->goal_difference > right->goal_difference;
    if (left->goals_for != right->goals_for)
        return left->goals_for > right->goals_for;
    return left->current_rank < right->current_rank;
}


static PreviousStanding previous_standing_for_row(int row)
{
    StandingSnapshot *current = &g_standing_rows[row];
    PreviousStanding previous;
    memset(&previous, 0, sizeof(previous));
    previous.source_row = row;
    previous.current_rank = current->current_rank;
    previous.points = current->points;
    previous.won = current->won;
    previous.goals_for = current->goals_for;
    previous.goal_difference = current->goal_difference;

    const FormMatch *match =
        latest_form_match_for_club(current->club_id);
    if (!match || current->played <= 0)
        return previous;

    int scored;
    int conceded;
    if (match->home_logo == current->club_id)
    {
        scored = match->home_score;
        conceded = match->away_score;
    }
    else
    {
        scored = match->away_score;
        conceded = match->home_score;
    }

    previous.goals_for -= scored;
    previous.goal_difference -= scored - conceded;
    if (scored > conceded)
    {
        previous.points -= 3;
        previous.won--;
    }
    else if (scored == conceded)
    {
        previous.points--;
    }

    if (previous.points < 0)
        previous.points = 0;
    if (previous.won < 0)
        previous.won = 0;
    if (previous.goals_for < 0)
        previous.goals_for = 0;
    previous.removed_match = TRUE;
    return previous;
}


static void publish_standing_movements(void *provider)
{
    PreviousStanding previous[20];
    int order[20];
    int previous_rank[20];
    int count = 0;
    int row;
    memset(previous_rank, 0, sizeof(previous_rank));

    for (row = 0; row < 20; row++)
    {
        if (
            g_standing_rows[row].club_id <= 0
            || !g_standing_rows[row].metrics_ready)
            continue;
        previous[count] = previous_standing_for_row(row);
        order[count] = count;
        count++;
    }

    int left;
    for (left = 0; left < count; left++)
    {
        int right;
        for (right = left + 1; right < count; right++)
        {
            if (previous_standing_precedes(
                    &previous[order[right]],
                    &previous[order[left]]))
            {
                int temporary = order[left];
                order[left] = order[right];
                order[right] = temporary;
            }
        }
    }

    for (left = 0; left < count; left++)
        previous_rank[previous[order[left]].source_row] = left + 1;

    for (row = 0; row < 20; row++)
    {
        char key[32];
        int asset_id = POSITION_ASSET_EMPTY;
        StandingSnapshot *current = &g_standing_rows[row];
        if (
            current->club_id > 0
            && current->metrics_ready
            && current->played >= 2
            && previous_rank[row] > 0)
        {
            PreviousStanding state = previous_standing_for_row(row);
            if (state.removed_match)
            {
                if (current->current_rank < previous_rank[row])
                    asset_id = POSITION_ASSET_UP;
                else if (current->current_rank > previous_rank[row])
                    asset_id = POSITION_ASSET_DOWN;
                else
                    asset_id = POSITION_ASSET_STABLE;
            }
        }

        snprintf(key, sizeof(key), "POSITION_%d", row);
        publish_int_field(provider, key, asset_id);
        publish_visibility_field(provider, key, !g_standing_knockout_mode && asset_id != POSITION_ASSET_EMPTY);
    }
}


static void publish_standing_form(
    void *provider,
    int row,
    int club_id)
{
    native_form(provider, row, club_id);
}


static void publish_standing_summaries(
    void *provider,
    int row,
    int played)
{
    char key[32];
    char value[64];
    int won = g_standing_stat(g_current_standing_record, 2, 3);
    int drawn = g_standing_stat(g_current_standing_record, 2, 4);
    int lost = g_standing_stat(g_current_standing_record, 2, 5);
    int goals_for = g_standing_stat(g_current_standing_record, 2, 6);
    int goals_against = g_standing_stat(g_current_standing_record, 2, 7);
    int goal_difference = g_standing_stat(g_current_standing_record, 2, 8);

    snprintf(key, sizeof(key), "WDL%d", row);
    snprintf(value, sizeof(value), "%2d    %2d    %2d", won, drawn, lost);
    publish_string_field(provider, key, value);

    snprintf(key, sizeof(key), "GOALS%d", row);
    snprintf(
        value,
        sizeof(value),
        "%3d   %3d   %3d",
        goals_for,
        goals_against,
        goal_difference);
    publish_string_field(provider, key, value);

    (void)played;
}


static void standing_string_capture(
    void *provider,
    const char *attribute,
    const char *value)
{
    if (
        attribute
        && value
        && strcmp(attribute, "ID") == 0)
    {
        if (strcmp(value, "LOGO0") == 0)
            publish_standing_mode(provider, FALSE);
        else if (strcmp(value, "KO_NAME") == 0)
        {
            BOOL knockout = active_standing_knockout_context();
            memset(&g_knockout_fixture, 0, sizeof(g_knockout_fixture));
            publish_standing_mode(provider, knockout);
            if (knockout)
                publish_standing_knockout_details(provider);
        }
        lstrcpynA(
            g_current_standing_field,
            value,
            (int)sizeof(g_current_standing_field));
    }
    g_set_string(provider, attribute, value);

    if (
        !attribute
        || !value
        || strcmp(attribute, "PARAM") != 0)
        return;

    if (strcmp(g_current_standing_field, "KO_NAME") == 0)
    {
        int competition_id = (int)InterlockedCompareExchange(
            &g_active_competition_id,
            0,
            0);
        if (competition_id > 0)
            set_display_competition(competition_id);
        int logo_id = native_logo(competition_id);
        if (logo_id > 0)
        {
            publish_int_field(provider, "LEAGUELOGO", logo_id);
        }
        refresh_knockout_round();
    }
    else if (strcmp(g_current_standing_field, "KO_TEAM0") == 0)
    {
        lstrcpynA(
            g_knockout_fixture.home,
            value,
            (int)sizeof(g_knockout_fixture.home));
        refresh_knockout_round();
    }
    else if (strcmp(g_current_standing_field, "KO_TEAM1") == 0)
    {
        lstrcpynA(
            g_knockout_fixture.away,
            value,
            (int)sizeof(g_knockout_fixture.away));
        refresh_knockout_round();
    }
}


static void set_played_and_extra(
    void *provider,
    const char *attribute,
    int played)
{
    g_set_int(provider, attribute, played);

    if (strcmp(g_current_standing_field, "LEAGUELOGO") == 0)
    {
        int competition_id = (int)InterlockedCompareExchange(
            &g_active_competition_id,
            0,
            0);
        int resolved = native_competition_from_asset(
            played,
            native_club,
            competition_id);
        if (resolved > 0)
        {
            competition_id = resolved;
            InterlockedExchange(&g_active_competition_id, resolved);
            InterlockedExchange(&g_standing_competition_id, resolved);
        }
        set_display_competition(competition_id > 0 ? competition_id : played);
        return;
    }

    if (strcmp(g_current_standing_field, "KO_LOGO0") == 0)
    {
        g_knockout_fixture.home_logo = played;
        refresh_knockout_round();
        return;
    }

    if (strcmp(g_current_standing_field, "KO_LOGO1") == 0)
    {
        g_knockout_fixture.away_logo = played;
        refresh_knockout_round();
        return;
    }

    if (strncmp(g_current_standing_field, "LOGO", 4) == 0)
    {
        int row = atoi(g_current_standing_field + 4);
        if (row >= 0 && row < 20)
        {
            if (row == 0)
            {
                memset(g_standing_logos, 0, sizeof(g_standing_logos));
                memset(g_standing_rows, 0, sizeof(g_standing_rows));
            }
            g_standing_logos[row] = played;
            g_standing_rows[row].club_id = played;
            g_standing_rows[row].current_rank = row + 1;
            publish_league_row_visibility(
                provider,
                row,
                played > 0);
            if (row == 19)
            {
                int form_row;
                refresh_form_cache_from_memory();
                for (form_row = 0; form_row < 20; form_row++)
                    if (g_standing_logos[form_row] > 0)
                        publish_standing_form(
                            provider,
                            form_row,
                            g_standing_logos[form_row]);
            }
            else
            {
                publish_standing_form(provider, row, played);
            }
        }
        return;
    }

    if (
        strncmp(g_current_standing_field, "POINTS", 6) == 0
        && g_current_standing_field[6] >= '0'
        && g_current_standing_field[6] <= '9')
    {
        int row = atoi(g_current_standing_field + 6);
        if (row >= 0 && row < 20)
        {
            g_standing_rows[row].points = played;
            publish_standing_movements(provider);
        }
        return;
    }

    if (
        !g_current_standing_record
        || strcmp(g_current_standing_field, "PLAYED") == 0
        || strncmp(g_current_standing_field, "PLAYED", 6) != 0)
        return;

    int row = atoi(g_current_standing_field + 6);
    if (row < 0 || row > 99)
        return;

    if (row < 20)
    {
        StandingSnapshot *snapshot = &g_standing_rows[row];
        snapshot->current_rank = row + 1;
        snapshot->played = played;
        snapshot->won =
            g_standing_stat(g_current_standing_record, 2, 3);
        snapshot->drawn =
            g_standing_stat(g_current_standing_record, 2, 4);
        snapshot->lost =
            g_standing_stat(g_current_standing_record, 2, 5);
        snapshot->goals_for =
            g_standing_stat(g_current_standing_record, 2, 6);
        snapshot->goals_against =
            g_standing_stat(g_current_standing_record, 2, 7);
        snapshot->goal_difference =
            g_standing_stat(g_current_standing_record, 2, 8);
        /* POINTSn is captured independently from FIFA, including deductions. */
        snapshot->metrics_ready = TRUE;
    }

    publish_standing_summaries(provider, row, played);
    if (row < 20 && g_standing_logos[row] > 0)
        publish_standing_form(
            provider,
            row,
            g_standing_logos[row]);
    if (row < 20)
        publish_standing_movements(provider);
}


static void *stats_vector_capture(
    void *stats_object,
    int category,
    unsigned char enabled)
{
    void *provider;
    g_current_stats_object = stats_object;
    provider = g_stats_vector(stats_object, category, enabled);
    /* Capture the exact vector, including native queries without scorer rows. */
    if (g_current_stats_provider_owner)
        g_current_stats_provider = provider;
    return provider;
}

/* Rows written by FIFA's own StatisticsData provider. These are deliberately
 * kept separate from the FCE career query counts: the two providers can be
 * refreshed at different times during hub startup. */
static SIZE_T g_stock_goal_count;
static SIZE_T g_stock_assist_count;
static SIZE_T g_stock_minutes_count;
static SIZE_T g_stock_yellow_count;
static SIZE_T g_stock_red_count;
static BOOL g_competition_scorer_present[5];
static int g_competition_scorer_field = -1;
static void *g_competition_scorer_provider;

static void reset_stock_stat_capture(void)
{
    g_stock_goal_count = 0;
    g_stock_assist_count = 0;
    g_stock_minutes_count = 0;
    g_stock_yellow_count = 0;
    g_stock_red_count = 0;
    memset(g_competition_scorer_present, 0, sizeof(g_competition_scorer_present));
    g_competition_scorer_field = -1;
    g_competition_scorer_provider = NULL;
}

/* Observe the actual NAME<n> field ID and its following PARAM/FALSE write.
 * HEAD IDs are emitted even for empty rows, so they cannot establish that a
 * scorer exists. These two call sites are inside the native scorer loop. */
static void competition_scorer_name_capture(
    void *provider, const char *attribute, const char *value)
{
    g_set_string(provider, attribute, value);
    if (!provider || !attribute || !value) return;
    if (!strcmp(attribute, "ID")) {
        size_t length = strlen(value);
        g_competition_scorer_provider = provider;
        g_competition_scorer_field = length == 5 && !strncmp(value, "NAME", 4) &&
            value[4] >= '0' && value[4] <= '4' ? value[4] - '0' : -1;
    } else if (provider == g_competition_scorer_provider &&
        g_competition_scorer_field >= 0) {
        if (!strcmp(attribute, "PARAM"))
            g_competition_scorer_present[g_competition_scorer_field] = value[0] != 0;
        else if (!strcmp(attribute, "VISIBLE") && !_stricmp(value, "FALSE"))
            g_competition_scorer_present[g_competition_scorer_field] = FALSE;
    }
}

static SIZE_T stock_stat_count_for_prefix(const char *prefix)
{
    if (!prefix) return 0;
    if (strcmp(prefix, "CLUB_GOAL_") == 0) return g_stock_goal_count;
    if (strcmp(prefix, "CLUB_ASSIST_") == 0) return g_stock_assist_count;
    if (strcmp(prefix, "CLUB_MINUTES_") == 0) return g_stock_minutes_count;
    if (strcmp(prefix, "CLUB_YELLOW_") == 0) return g_stock_yellow_count;
    if (strcmp(prefix, "CLUB_RED_") == 0) return g_stock_red_count;
    return 0;
}


static void stats_string_capture(
    void *provider,
    const char *key,
    const char *value)
{
    const char *prefixes[] = {
        "CLUB_GOAL_NAME",
        "CLUB_ASSIST_NAME",
        "CLUB_MINUTES_NAME",
        "CLUB_YELLOW_NAME",
        "CLUB_RED_NAME"
    };
    SIZE_T i;

    g_current_stats_provider = provider;
    g_set_string(provider, key, value);

    /* The stock StatisticsData provider can repopulate these rows after the
     * native FCE query. Keep a small presence snapshot so the empty-state
     * banner never covers valid rows that FIFA has just published. */
    if (!key || !value || !value[0])
        return;
    for (i = 0; i < sizeof(prefixes) / sizeof(prefixes[0]); ++i)
    {
        SIZE_T prefix_length = strlen(prefixes[i]);
        if (strncmp(key, prefixes[i], prefix_length) == 0)
        {
            int row = atoi(key + prefix_length);
            if (row >= 0 && row < 5)
            {
                SIZE_T *count = NULL;
                switch (i)
                {
                case 0: count = &g_stock_goal_count; break;
                case 1: count = &g_stock_assist_count; break;
                case 2: count = &g_stock_minutes_count; break;
                case 3: count = &g_stock_yellow_count; break;
                case 4: count = &g_stock_red_count; break;
                default: break;
                }
                if (count && *count < (SIZE_T)(row + 1))
                    *count = (SIZE_T)(row + 1);
            }
            break;
        }
    }
}


static BOOL is_readable_range(const void *address, SIZE_T size)
{
    MEMORY_BASIC_INFORMATION info;
    if (!address || size == 0 || !VirtualQuery(address, &info, sizeof(info)))
        return FALSE;
    if (info.State != MEM_COMMIT || (info.Protect & PAGE_GUARD))
        return FALSE;
    if (
        info.Protect == PAGE_NOACCESS
        || info.Protect == PAGE_EXECUTE)
        return FALSE;
    uintptr_t start = (uintptr_t)address;
    uintptr_t end = start + size;
    uintptr_t region_end =
        (uintptr_t)info.BaseAddress + info.RegionSize;
    return end >= start && end <= region_end;
}


/* Calendar artwork has one source. Old BIG/DDS existence cannot choose an ID. */
static BOOL calendar_competition_asset_exists(int asset)
{
    char path[MAX_PATH];unsigned char header[128];FILE *file;long length;size_t got;
    int size=0,width=0,height=0;
    if(asset<=1000000 || asset>1065535)return FALSE;
    asset-=1000000;
    snprintf(path,sizeof(path),"%s/data/ui/imgAssets/careerCompetitionIcons/calendar/c%d.dds",g_game_dir,asset);
    file=fopen(path,"rb");if(!file)return FALSE;
    got=fread(header,1,sizeof(header),file);length=fseek(file,0,SEEK_END)?0:ftell(file);fclose(file);
    if(got!=sizeof(header))return FALSE;
    memcpy(&size,header+4,4);memcpy(&height,header+12,4);memcpy(&width,header+16,4);
    return length>=16512 && !memcmp(header,"DDS ",4) && size==124 && width==128 && height==128 && !memcmp(header+84,"DXT5",4);
}
static volatile LONG g_compdata_index_state;
static CompIdentityIndex g_competition_identity;
static int g_preseason_competition[65536];

typedef int (WINAPI *UiCompetitionAssetFn)(int,const void *);
static int career_ui_competition_asset(int root,const void *owner)
{
    BYTE *registry=NULL;HMODULE plugin;UiCompetitionAssetFn resolve;
    if(owner && is_readable_range((const BYTE*)owner+8,sizeof(registry)))memcpy(&registry,(const BYTE*)owner+8,sizeof(registry));
    plugin=GetModuleHandleA("career_ui_assets.dll");
    if(!plugin)return 0;
    resolve=(UiCompetitionAssetFn)GetProcAddress(plugin,"Fifa16UiAssetsResolveCompetition");
    return resolve?resolve(root,registry):0;
}

static void load_compdata_competition_index(void)
{
    char path[MAX_PATH],line[512];FILE *file;
    if(InterlockedCompareExchange(&g_compdata_index_state,1,0)!=0)return;
    snprintf(path,sizeof(path),"%s\\dlc\\dlc_FootballCompEng\\dlc\\FootballCompEng\\data\\compdata\\compobj.txt",g_game_dir);
    comp_identity_load(&g_competition_identity,path);
    snprintf(path,sizeof(path),"%s\\data\\catalogs\\career_competition_icon_map.tsv",g_mod_dir);
    file=fopen(path,"rb");
    if(file){while(fgets(line,sizeof(line),file)){
        int asset=0,root=comp_identity_mapping(&g_competition_identity,line,&asset);
        const CompIdentityNode *node=comp_identity_node(&g_competition_identity,root);
        if(root>0 && !comp_identity_visual(node) && asset>0 && asset<=65535){
            if(g_preseason_competition[asset] && g_preseason_competition[asset]!=root)g_preseason_competition[asset]=-1;
            else g_preseason_competition[asset]=root;
        }
    }fclose(file);}
    InterlockedExchange(&g_compdata_index_state,2);
}
static int career_competition_icon_from_live_asset(int asset)
{
    int id;
    if(InterlockedCompareExchange(&g_compdata_index_state,0,0)==0)load_compdata_competition_index();
    if(InterlockedCompareExchange(&g_compdata_index_state,0,0)!=2)return 0;
    id=comp_identity_live_id(&g_competition_identity,asset);
    if(!id && asset>0 && asset<=65535)id=g_preseason_competition[asset];
    /* Explicit artwork namespace avoids numeric collisions with ordinary
     * league IDs in other FIFA screens. The filename still uses the INI ID. */
    return id>0?1000000+id:0;
}
static int calendar_asset_for_date_capture(void *calendar_service,const void *competition_value)
{
    FceLiveSnapshot *snapshot;const FceModel *model;FceCompetition competition;
    FceResult identity=FCE_UNKNOWN;int reference[3],candidate=0,resolved=0;
    if(!is_readable_range(competition_value,sizeof(reference)))return 0;
    memcpy(reference,competition_value,sizeof(reference));
    snapshot=fce_runtime_cached_acquire();model=fce_runtime_model(snapshot);
    if(model)identity=calendar_icon_identity(model->nodes,model->node_count,reference,&competition);
    if(identity==FCE_OK){
        candidate=competition.asset>0?career_competition_icon_from_live_asset(competition.asset):
            career_competition_icon_from_live_asset(career_ui_competition_asset(competition.competition,calendar_service));
    }else if(identity!=FCE_CONFLICT){
        /* Temporary preseason roots are accepted only by the guarded native
         * CRTR registry. Never guess a competition from reference[2]. */
        candidate=career_competition_icon_from_live_asset(career_ui_competition_asset(reference[0],calendar_service));
    }
    fce_runtime_release(snapshot);
    if(calendar_competition_asset_exists(candidate))resolved=candidate;
    if(fce_runtime_log_verbose()){
        char path[MAX_PATH];FILE *log;
        snprintf(path,sizeof(path),"%s\\logs\\calendar_native_hook.log",g_mod_dir);
        log=fopen(path,"ab");
        if(log){fprintf(log,"calendar-cell-v2 competition=%d stage=%d fixture=%d identity=%d asset=%d\n",
            reference[0],reference[1],reference[2],identity,resolved);fclose(log);}
    }
    return resolved;
}

static void startup_object_noop(void *self, void *observer, int remove)
{
    (void)self;
    (void)observer;
    (void)remove;
}


/* FIFA's new-career cleanup path calls a resolver and immediately executes
 * virtual slot 3 without checking its return value.  The 2026-09-20 dump
 * proves that the resolver can legitimately return NULL while the career
 * services are still being created (fifa16.exe+0x5F18BDA, RAX=0).  Return a
 * local no-op implementation only for that transient missing object. */
static void *g_startup_noop_vtable[4] = {
    NULL,
    NULL,
    NULL,
    (void *)startup_object_noop,
};
static void **g_startup_noop_object = g_startup_noop_vtable;


static void *resolve_career_startup_object_guard(uintptr_t key)
{
    void *object = g_resolve_career_startup_object
        ? g_resolve_career_startup_object(key)
        : NULL;
    if (object)
        return object;

    static volatile LONG logged;
    if (InterlockedCompareExchange(&logged, 1, 0) == 0)
        append_loader_log("career_startup_null_object_guarded");
    return &g_startup_noop_object;
}


static int competition_from_statistics_provider(void *provider_owner)
{
    /*
     * CM_STATISTICS_DP owns the competition used by the native top-scorer
     * query. FIFA reads this DWORD at 0x1459CE1E6/0x1459CE217, directly
     * before validating and querying the statistics service.
     */
    const unsigned char *field =
        (const unsigned char *)provider_owner + 0x1F8;
    if (!is_readable_range(field, sizeof(int)))
        return 0;

    int competition_id = 0;
    memcpy(&competition_id, field, sizeof(competition_id));
    /* FCE object IDs are unsigned 16-bit; current Carioca is 2212. */
    if (competition_id <= 0 || competition_id > 65535)
        return 0;
    return competition_id;
}


static void standing_provider_with_context(void *provider_owner)
{
    int comp = competition_from_statistics_provider(provider_owner);
    InterlockedExchange(&g_active_competition_id, comp);
    InterlockedExchange(&g_standing_competition_id, comp);
    InterlockedExchange(&g_display_competition_id, comp);
    native_prepare(provider_owner);
    /* Start each standings provider with a clean capture. Otherwise a league
     * from the previous screen can make a new knockout provider look like a
     * league, or vice versa, while FIFA is still enumerating its fields. */
    memset(g_standing_logos, 0, sizeof(g_standing_logos));
    memset(g_standing_rows, 0, sizeof(g_standing_rows));
    g_standing_provider(provider_owner);
    /* Coach fields are published only from native_publish() after FIFA has
     * completed the live statistics query and supplied its captured UI
     * provider.  Writing those fields to provider_owner here used the wrong
     * object during career startup and caused a lifecycle crash. */
    native_end();
}


static void clear_pending_stats_refresh(void)
{
    g_pending_stats_provider_owner = NULL;
    g_pending_stats_provider_vtable = NULL;
    g_pending_stats_provider_registry = NULL;
    g_pending_stats_context_epoch = 0;
    g_pending_stats_thread = 0;
    memset(&g_stats_refresh_schedule, 0, sizeof(g_stats_refresh_schedule));
    InterlockedExchange(&g_stats_ready_generation, 0);
}


static void remember_pending_stats_refresh(void *owner)
{
    if (!is_readable_range(owner, 2 * sizeof(void *)))
        return;
    g_pending_stats_provider_owner = owner;
    g_pending_stats_provider_vtable = *(void **)owner;
    g_pending_stats_provider_registry = ((void **)owner)[1];
    g_pending_stats_context_epoch = fce_runtime_context_epoch();
    g_pending_stats_thread = GetCurrentThreadId();
    card_refresh_enter(&g_stats_refresh_schedule, GetTickCount64());
}


static void refresh_initial_competition_provider(unsigned long generation)
{
    /* Do not re-enter UI code inside snapshot capture. */
    InterlockedExchange(&g_stats_ready_generation, (LONG)generation);
}


static void log_card_refresh(const char *event, void *owner, void *provider,
    unsigned reason)
{
    char path[MAX_PATH];
    FILE *log;
    if (!g_mod_dir[0] || !fce_runtime_log_verbose()) return;
    snprintf(path, sizeof(path), "%s\\logs\\career_card_refresh.log", g_mod_dir);
    log = fopen(path, "ab");
    if (!log) return;
    fprintf(log, "event=%s owner=%p provider=%p view=%lu applied=%lu "
        "requested=%lu context=%lu thread=%lu owner_thread=%lu reason=%u completed=%d\n",
        event, owner, provider, g_stats_refresh_schedule.view_revision,
        g_stats_refresh_schedule.applied_generation,
        g_stats_refresh_schedule.requested_generation,
        fce_runtime_context_epoch(), GetCurrentThreadId(), g_pending_stats_thread, reason,
        g_stats_publication_completed != FALSE);
    fclose(log);
}


static void drain_pending_stats_refresh(void)
{
    void *owner;
    void *expected_vtable;
    unsigned reason;
    unsigned long ready_generation;
    if (!g_pending_stats_provider_owner || g_current_stats_provider_owner)
        return;
    if (GetCurrentThreadId() != g_pending_stats_thread) {
        if (!InterlockedExchange(&g_stats_tick_thread_mismatch, 1))
            log_card_refresh("owner_thread_mismatch", g_pending_stats_provider_owner, NULL, 0);
        return;
    }
    if (g_pending_stats_context_epoch != fce_runtime_context_epoch()) {
        clear_pending_stats_refresh();
        return;
    }
    if (!fce_runtime_is_stable()) return;
    ready_generation = (unsigned long)InterlockedExchange(&g_stats_ready_generation, 0);
    card_refresh_request(&g_stats_refresh_schedule, ready_generation, GetTickCount64());
    if (InterlockedCompareExchange(&g_pending_stats_refresh_busy, 1, 0)) return;
    reason = card_refresh_take_due(&g_stats_refresh_schedule, GetTickCount64());
    if (!reason) {
        InterlockedExchange(&g_pending_stats_refresh_busy, 0);
        return;
    }
    owner = g_pending_stats_provider_owner;
    expected_vtable = g_pending_stats_provider_vtable;
    if (!owner
        || !is_readable_range(owner, 2 * sizeof(void *))
        || *(void **)owner != expected_vtable
        || ((void **)owner)[1] != g_pending_stats_provider_registry)
    {
        clear_pending_stats_refresh();
        InterlockedExchange(&g_pending_stats_refresh_busy, 0);
        return;
    }

    __try
    {
        fce_runtime_suppress_refresh(1);
        stats_provider_with_diagnostics(owner);
        log_card_refresh("deferred_refresh", owner, NULL, reason);
    }
    __except(EXCEPTION_EXECUTE_HANDLER)
    {
        clear_pending_stats_refresh();
        append_loader_log("career_card_deferred_refresh_guarded");
    }
    fce_runtime_suppress_refresh(0);
    InterlockedExchange(&g_pending_stats_refresh_busy, 0);
}


/* full_stats_category_capture: removed obsolete bridge/scanner path. */


/* full_stats_vector_capture: removed obsolete bridge/scanner path. */


/* competition_ref_capture: removed obsolete bridge/scanner path. */


typedef struct ServiceDescriptor
{
    int index;
    int reserved;
    void *type;
} ServiceDescriptor;


static void *owner_service(
    void *owner,
    GetServiceDescriptorFn get_descriptor,
    int *resolved_index)
{
    ServiceDescriptor descriptor;
    memset(&descriptor, 0, sizeof(descriptor));
    descriptor.index = -1;
    if (!owner || !get_descriptor || !is_readable_range(owner, 16))
        return NULL;
    get_descriptor(&descriptor);
    int index = descriptor.index;
    if (resolved_index)
        *resolved_index = index;
    if (index < 0 || index > 4096)
        return NULL;

    unsigned char *registry = *(unsigned char **)((unsigned char *)owner + 8);
    SIZE_T entry_offset = (SIZE_T)index * 32 + 0x18;
    if (!is_readable_range(registry, entry_offset + sizeof(void *)))
        return NULL;

    void *wrapper = *(void **)(registry + entry_offset);
    if (!is_readable_range(wrapper, sizeof(void *)))
        return NULL;
    return *(void **)wrapper;
}


static int resolve_user_club_id(void *provider_owner, FILE *log)
{
    void *service = owner_service(provider_owner,g_get_career_service_descriptor,NULL);
    void *context = NULL, *team = NULL;
    int club = 0;
    (void)log;
    __try {
        if(service) context = g_get_career_context(service);
        if(context) team = g_get_user_team(context,0);
        if(team) club = *(int *)((unsigned char *)team+4);
    } __except(EXCEPTION_EXECUTE_HANDLER) { club = 0; }
    if(club < 0 || club > 2000000) club = 0;
    if (
        context
        && (
            (g_career_context_identity && context != g_career_context_identity)
            || (club > 0 && g_career_context_club > 0 && club != g_career_context_club)))
    {
        /* A provider object can survive navigation while the Career context
         * behind it is replaced.  Never let rows from that former save take
         * part in competition inference or card publication. */
        fce_runtime_invalidate();
        native_context_reset();
        /* The former snapshot was deliberately discarded. Queue the new
         * career immediately; otherwise a foreign/new club remains at
         * generation zero until a later save/load event happens. */
        fce_runtime_request_refresh();
    }
    /* A short null service window occurs during load. Preserve the last
     * non-null identity so the following valid callback can still detect the
     * save transition instead of accepting the previous snapshot. */
    if(context) g_career_context_identity = context;
    if(club > 0) g_career_context_club = club;
    InterlockedExchange(&g_user_club_id,club);
    return club;
}


static void insert_ranked_player(
    RankedPlayer *rows,
    SIZE_T *count,
    const RankedPlayer *candidate)
{
    if (!rows || !count || !candidate || candidate->value <= 0)
        return;
    SIZE_T position = 0;
    while (
        position < *count
        && rows[position].value >= candidate->value)
        position++;
    if (position >= 5)
        return;
    SIZE_T limit = *count < 5 ? *count : 4;
    while (limit > position)
    {
        rows[limit] = rows[limit - 1];
        limit--;
    }
    rows[position] = *candidate;
    if (*count < 5)
        (*count)++;
}


static void contracts_provider_capture(void *provider_owner)
{
    g_contracts_provider(provider_owner);
    if (!is_readable_range(provider_owner, 0x150))
        return;

    unsigned char *begin =
        *(unsigned char **)((unsigned char *)provider_owner + 0x140);
    unsigned char *end =
        *(unsigned char **)((unsigned char *)provider_owner + 0x148);
    if (
        !begin
        || !end
        || end < begin
        || (SIZE_T)(end - begin) % 0x98 != 0)
        return;
    SIZE_T total = (SIZE_T)(end - begin) / 0x98;
    if (total > 100)
        return;

    RankedPlayer captured[5];
    SIZE_T captured_count = 0;
    memset(captured, 0, sizeof(captured));
    int club_id = (int)InterlockedCompareExchange(
        &g_user_club_id,
        0,
        0);
    memset(g_roster_player_ids, 0, sizeof(g_roster_player_ids));
    memset(g_roster_player_names, 0, sizeof(g_roster_player_names));
    g_roster_player_count = 0;
    g_roster_club_id = club_id;
    SIZE_T index;
    for (index = 0; index < total; index++)
    {
        unsigned char *item = begin + index * 0x98;
        if (!is_readable_range(item, 0x98))
            break;
        int player_id = *(int *)(item + 0x00);
        const char *name = (const char *)(item + 0x28);
        int wage = *(int *)(item + 0x88);
        if (
            player_id > 0
            && name[0]
            && g_roster_player_count < 100)
        {
        {
            g_roster_player_ids[g_roster_player_count] = player_id;
            lstrcpynA(g_roster_player_names[g_roster_player_count], name,
                (int)sizeof(g_roster_player_names[g_roster_player_count]));
            ++g_roster_player_count;
        }
        }
        if (
            player_id <= 0
            || wage <= 0
            || !name[0])
            continue;
        RankedPlayer candidate;
        memset(&candidate, 0, sizeof(candidate));
        candidate.head = player_id;
        candidate.logo = club_id;
        candidate.value = wage;
        lstrcpynA(candidate.name, name, (int)sizeof(candidate.name));
        insert_ranked_player(
            captured,
            &captured_count,
            &candidate);
    }

    memcpy(g_salary_rows, captured, sizeof(g_salary_rows));
    g_salary_count = captured_count;
    g_salary_club_id = club_id;
    if (club_id > 0)
    {
        save_salary_cache();
        save_roster_cache();
    }

    if (fce_runtime_log_verbose())
    {
        char path[MAX_PATH];
        wsprintfA(path, "%s\\logs\\career_dashboard_hook.log", g_mod_dir);
        FILE *log = fopen(path, "ab");
        if (log)
        {
            fprintf(
                log,
                "salarios: club=%d rows=%llu top=%llu\n",
                club_id,
                (unsigned long long)total,
                (unsigned long long)captured_count);
            fprintf(
                log,
                "elenco: club=%d jogadores=%llu\n",
                club_id,
                (unsigned long long)g_roster_player_count);
            for (index = 0; index < captured_count; index++)
                fprintf(
                    log,
                    "  salario[%llu] player=%d value=%d name=\"%s\"\n",
                    (unsigned long long)index,
                    captured[index].head,
                    captured[index].value,
                    captured[index].name);
            fclose(log);
        }
    }
}


static void injury_commit_current(void *provider);
static void injury_begin_batch(void *provider, int active_club);
static int injury_match_roster_player(const char *name);
static void injury_load_snapshot(int active_club);
static void injury_save_snapshot(void);
static void injury_capture_log(
    const char *event,
    void *provider,
    const InjuryRow *row);
static SIZE_T native_live_injury_rows(
    int club,
    InjuryRow *out,
    SIZE_T capacity,
    int *query_valid,
    int *query_source);
static SIZE_T publish_injury_rows(void *provider, int *source);


static void injury_snapshot_path(char *path, size_t capacity)
{
    if (!path || capacity == 0)
        return;
    if (!g_mod_dir[0]) {
        path[0] = '\0';
        return;
    }
    /* The migration keeps this mutable snapshot separate from catalogs. */
    {
        char directory[MAX_PATH];
        snprintf(directory, sizeof(directory), "%s\\runtime", g_mod_dir);
        CreateDirectoryA(directory, NULL);
    }
    snprintf(path, capacity, "%s\\runtime\\injury_snapshot.tsv", g_mod_dir);
}


static void injury_load_snapshot(int active_club)
{
    char path[MAX_PATH], line[640], *context = NULL, *part;
    FILE *file;
    int snapshot_club = 0;
    SIZE_T count = 0;
    if (active_club <= 0 || g_injury_snapshot_loaded_club == active_club)
        return;
    g_injury_snapshot_loaded_club = active_club;
    injury_snapshot_path(path, sizeof(path));
    if (!path[0] || !(file = fopen(path, "rb")))
        return;
    if (!fgets(line, sizeof(line), file)
        || strcmp(line, "INJURY_SNAPSHOT_V1\n") != 0)
        goto done;
    if (!fgets(line, sizeof(line), file))
        goto done;
    snapshot_club = atoi(line);
    if (snapshot_club != active_club)
        goto done;
    while (count < sizeof(g_injury_rows) / sizeof(g_injury_rows[0])
        && fgets(line, sizeof(line), file))
    {
        InjuryRow row;
        memset(&row, 0, sizeof(row));
        part = strtok_s(line, "|\r\n", &context);
        if (!part)
            continue;
        row.head = atoi(part);
        part = strtok_s(NULL, "|\r\n", &context);
        if (!part)
            continue;
        lstrcpynA(row.name, part, (int)sizeof(row.name));
        part = strtok_s(NULL, "|\r\n", &context);
        if (!part)
            continue;
        lstrcpynA(row.length, part, (int)sizeof(row.length));
        if (row.head > 0 && row.name[0] && row.length[0])
            g_injury_rows[count++] = row;
    }
    if (count > 0) {
        g_injury_count = count;
        g_injury_club_id = active_club;
    }
done:
    fclose(file);
}


static void injury_save_snapshot(void)
{
    char path[MAX_PATH], temporary[MAX_PATH];
    FILE *file;
    SIZE_T index;
    if (g_injury_club_id <= 0 || g_injury_count == 0)
        return;
    injury_snapshot_path(path, sizeof(path));
    if (!path[0])
        return;
    snprintf(temporary, sizeof(temporary), "%s.tmp", path);
    file = fopen(temporary, "wb");
    if (!file)
        return;
    fprintf(file, "INJURY_SNAPSHOT_V1\n%d\n", g_injury_club_id);
    for (index = 0; index < g_injury_count; ++index)
        fprintf(file, "%d|%s|%s\n", g_injury_rows[index].head,
            g_injury_rows[index].name, g_injury_rows[index].length);
    if (fclose(file) == 0)
        (void)MoveFileExA(temporary, path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    else
        (void)DeleteFileA(temporary);
}


static void injury_set_int_capture(
    void *provider,
    const char *attribute,
    int value)
{
    DWORD now = GetTickCount();
    if (attribute && strcmp(attribute, "PLAYERID") == 0)
    {
        int active_club = (int)InterlockedCompareExchange(
            &g_user_club_id, 0, 0);
        BOOL new_batch =
            provider != g_injury_capture_provider
            || (g_injury_club_id > 0 && g_injury_club_id != active_club)
            || now - g_injury_last_tick > 5000
            || (
                g_injury_count > 0
                && g_injury_rows[0].head == value);
        /* Commit the previous row before the next PLAYERID replaces its
         * staging buffer. This makes row capture independent of which field
         * the game writes last (the UI reads POSITIONTYPE last, but the
         * native provider does not guarantee the same setter order). */
        if (!new_batch && g_injury_current.head > 0
            && g_injury_current.head != value)
            injury_commit_current(provider);
        if (new_batch)
        {
            injury_begin_batch(provider, active_club);
        }
        else if (g_injury_current.head > 0
            && g_injury_current.head != value)
            memset(&g_injury_current, 0, sizeof(g_injury_current));
        g_injury_current.head = value;
        g_injury_current_committed = FALSE;
    }
    g_injury_last_tick = now;
    g_set_int(provider, attribute, value);
}


static void injury_begin_batch(void *provider, int active_club)
{
    memset(g_injury_rows, 0, sizeof(g_injury_rows));
    memset(&g_injury_current, 0, sizeof(g_injury_current));
    g_injury_count = 0;
    g_injury_capture_provider = provider;
    g_injury_club_id = active_club;
    g_injury_current_committed = FALSE;
    injury_capture_log("batch_begin", provider, NULL);
}


static int injury_match_roster_player(const char *name)
{
    SIZE_T index;
    int active_club = (int)InterlockedCompareExchange(
        &g_user_club_id, 0, 0);
    if (!name || !name[0] || g_roster_club_id != active_club)
        return 0;
    for (index = 0; index < g_roster_player_count; ++index)
        if (g_roster_player_names[index][0]
            && _stricmp(g_roster_player_names[index], name) == 0)
            return g_roster_player_ids[index];
    return 0;
}


static void injury_capture_log(
    const char *event,
    void *provider,
    const InjuryRow *row)
{
    char path[MAX_PATH];
    FILE *log;
    if (!fce_runtime_log_verbose())
        return;
    wsprintfA(path, "%s\\logs\\career_dashboard_hook.log", g_mod_dir);
    log = fopen(path, "ab");
    if (!log)
        return;
    fprintf(log, "lesoes: %s provider=%p club=%d rows=%llu",
        event, provider, g_injury_club_id,
        (unsigned long long)g_injury_count);
    if (row)
        fprintf(log, " player=%d name=\"%s\" length=\"%s\"",
            row->head, row->name, row->length);
    fputc('\n', log);
    fclose(log);
}


/* InjuryList is populated by a different provider from CM_STATISTICS_DP.
 * Requesting an FCE snapshot alone is insufficient because the injury table
 * can change while the FCE model remains byte-for-byte identical. Re-enter
 * the remembered statistics provider immediately after a completed row, with
 * the same vtable/lifecycle guard used by generation refreshes. */
static void injury_refresh_cards_now(void)
{
    void *owner = g_pending_stats_provider_owner;
    void *expected_vtable = g_pending_stats_provider_vtable;
    if (!owner || !expected_vtable || g_current_stats_provider_owner
        || GetCurrentThreadId() != g_pending_stats_thread
        || g_pending_stats_context_epoch != fce_runtime_context_epoch()
        || !is_readable_range(owner, 2 * sizeof(void *))
        || *(void **)owner != expected_vtable
        || ((void **)owner)[1] != g_pending_stats_provider_registry
        || InterlockedCompareExchange(&g_injury_refresh_busy, 1, 0))
        return;
    if (InterlockedCompareExchange(&g_pending_stats_refresh_busy, 1, 0)) {
        InterlockedExchange(&g_injury_refresh_busy, 0);
        return;
    }
    fce_runtime_suppress_refresh(1);
    __try
    {
        stats_provider_with_diagnostics(owner);
        append_loader_log("injury_card_immediate_refresh");
    }
    __except(EXCEPTION_EXECUTE_HANDLER)
    {
        append_loader_log("injury_card_immediate_refresh_guarded");
    }
    fce_runtime_suppress_refresh(0);
    InterlockedExchange(&g_pending_stats_refresh_busy, 0);
    InterlockedExchange(&g_injury_refresh_busy, 0);
}


static void injury_commit_current(void *provider)
{
    SIZE_T index;
    int club_id;
    if (g_injury_current_committed)
        return;
    /* The stock InjuryList APT binds PLAYERNAME, LENGTH and STATUS but does
     * not bind PLAYERID. Keep a valid injury row even if the roster-name
     * fallback cannot resolve its portrait ID; otherwise all textual injury
     * data silently disappears from the My Team card. */
    if (!g_injury_current.name[0]
        || !g_injury_current.length[0])
        return;

    g_injury_current_committed = TRUE;
    for (index = 0; index < g_injury_count; ++index) {
        if ((g_injury_current.head > 0
                && g_injury_rows[index].head == g_injury_current.head)
            || _stricmp(g_injury_rows[index].name, g_injury_current.name) == 0)
            return;
    }
    if (g_injury_count >= 5)
        return;

    g_injury_rows[g_injury_count++] = g_injury_current;
    club_id = (int)InterlockedCompareExchange(&g_user_club_id, 0, 0);
    if (club_id > 0)
        g_injury_club_id = club_id;
    injury_capture_log("row", provider, &g_injury_current);
    injury_save_snapshot();
    /* InjuryList is a separate native screen: its setters can update our
     * captured rows after the Career dashboard provider has already rendered
     * the empty state. Queue a stable FCE publication so the remembered
     * CM_STATISTICS_DP owner republishes the card with the new rows. The
     * request is atomic and coalesces naturally while FCE settles. */
    fce_runtime_request_refresh();
}


static void injury_set_string_capture(
    void *provider,
    const char *attribute,
    const char *value)
{
    SIZE_T count_before = g_injury_count;
    if (attribute && value)
    {
        DWORD now = GetTickCount();
        int active_club = (int)InterlockedCompareExchange(
            &g_user_club_id, 0, 0);
        if (provider != g_injury_capture_provider
            || (g_injury_club_id > 0 && g_injury_club_id != active_club)
            || now - g_injury_last_tick > 5000)
            injury_begin_batch(provider, active_club);

        if (strcmp(attribute, "PLAYERNAME") == 0)
        {
            if (g_injury_current.name[0]
                && _stricmp(g_injury_current.name, value) != 0)
            {
                injury_commit_current(provider);
                memset(&g_injury_current, 0, sizeof(g_injury_current));
            }
            lstrcpynA(
                g_injury_current.name,
                value,
                (int)sizeof(g_injury_current.name));
            if (g_injury_current.head <= 0)
                g_injury_current.head = injury_match_roster_player(value);
        }
        else if (strcmp(attribute, "INJURY") == 0)
            lstrcpynA(
                g_injury_current.injury,
                value,
                (int)sizeof(g_injury_current.injury));
        else if (strcmp(attribute, "LENGTH") == 0)
            lstrcpynA(
                g_injury_current.length,
                value,
                (int)sizeof(g_injury_current.length));
        else if (strcmp(attribute, "STATUS") == 0)
            lstrcpynA(
                g_injury_current.status,
                value,
                (int)sizeof(g_injury_current.status));
        else if (strcmp(attribute, "PLAYER_NAME") == 0)
        {
            if (g_injury_current.name[0]
                && _stricmp(g_injury_current.name, value) != 0)
            {
                injury_commit_current(provider);
                memset(&g_injury_current, 0, sizeof(g_injury_current));
            }
            lstrcpynA(g_injury_current.name, value,
                (int)sizeof(g_injury_current.name));
            if (g_injury_current.head <= 0)
                g_injury_current.head = injury_match_roster_player(value);
        }
        injury_commit_current(provider);
    }
    g_injury_last_tick = GetTickCount();
    g_set_string(provider, attribute, value);
    if (g_injury_count > count_before)
        injury_refresh_cards_now();
}

/* parse_fixture_score: removed obsolete bridge/scanner path. */


/* form_date_key: removed obsolete bridge/scanner path. */


/* merge_form_match: removed obsolete bridge/scanner path. */


/* form_team_is_in_standings: removed obsolete bridge/scanner path. */


/* ram_tracker_ascii_hex_save_name: removed obsolete bridge/scanner path. */


/* ram_tracker_file_is_career_data: removed obsolete bridge/scanner path. */


/* ram_tracker_get_reference_data_path: removed obsolete bridge/scanner path. */


/* ram_tracker_verify_save_anchors: removed obsolete bridge/scanner path. */


#define RAM_SAVE_CAPTURE_MAGIC 0x31534352u
#define RAM_SAVE_CAPTURE_VERSION 1u

#pragma pack(push, 1)
typedef struct RamSaveCaptureHeader
{
    uint32_t magic;
    uint32_t version;
    uint64_t image_address;
    uint64_t data_size;
    uint32_t anchors;
    uint32_t process_id;
    SYSTEMTIME captured_at;
    char reference_path[1024];
} RamSaveCaptureHeader;
#pragma pack(pop)


/* ram_tracker_dump_save_image: removed obsolete bridge/scanner path. */


/* ram_tracker_scan_save_image: removed obsolete bridge/scanner path. */


/* ram_tracker_raw_known_team: removed obsolete bridge/scanner path. */


/* ram_tracker_raw_expected_stage: removed obsolete bridge/scanner path. */


/* ram_tracker_raw_valid_date: removed obsolete bridge/scanner path. */


/* ram_tracker_scan_raw_calendar: removed obsolete bridge/scanner path. */


/* form_memory_record: removed obsolete bridge/scanner path. */


/* merge_form_memory_run: removed obsolete bridge/scanner path. */


/* form_memory_protection_is_readable: removed obsolete bridge/scanner path. */


/* fixture_memory_record: removed obsolete bridge/scanner path. */


/* fixture_matches_standing_context: removed obsolete bridge/scanner path. */


/* fixture_capture_seed: removed obsolete bridge/scanner path. */


/* rebuild_fixture_capture_from_run: removed obsolete bridge/scanner path. */


/* collect_upcoming_fixtures_from_memory: removed obsolete bridge/scanner path. */


/* fixture_rows_equal: removed obsolete bridge/scanner path. */


/* fixture_rows_same_match: removed obsolete bridge/scanner path. */


/* fixture_date_sort_key: removed obsolete bridge/scanner path. */


/* fixture_rows_same_calendar_slot: removed obsolete bridge/scanner path. */


/* fixture_belongs_to_competition: removed obsolete bridge/scanner path. */


/* merge_live_fixture_state: removed obsolete bridge/scanner path. */


/* merge_fixture_row_into_set: removed obsolete bridge/scanner path. */


/* current_ram_differs_from_disk_snapshot: removed obsolete bridge/scanner path. */


/* ram_tracker_mark_live_priority: removed obsolete bridge/scanner path. */


/* compare_fixture_rows: removed obsolete bridge/scanner path. */


/* collect_competition_fixtures_from_memory: removed obsolete bridge/scanner path. */


/* refresh_fixture_capture_from_memory: removed obsolete bridge/scanner path. */


static void refresh_form_cache_from_memory(void)
{
    /* Authoritative data is supplied by the native snapshot at provider entry. */
}


/* refresh_form_cache: removed obsolete bridge/scanner path. */


/* refresh_upcoming_rows: removed obsolete bridge/scanner path. */


/* refresh_club_previous_from_memory: removed obsolete bridge/scanner path. */


/* refresh_round_rows: removed obsolete bridge/scanner path. */


/* fixture_set_indexed_int_capture: removed obsolete bridge/scanner path. */


/* fixture_set_indexed_string_capture: removed obsolete bridge/scanner path. */


/* capture_club_goals: removed obsolete bridge/scanner path. */


/* capture_club_assists: removed obsolete bridge/scanner path. */


/* capture_club_season_stat: removed obsolete bridge/scanner path. */


/* capture_club_card_stat: removed obsolete bridge/scanner path. */


/* capture_club_cards: removed obsolete bridge/scanner path. */


static void clear_ranked_row(
    void *provider,
    const char *prefix,
    int row)
{
    char key[48];
    snprintf(key, sizeof(key), "%sHEAD%d", prefix, row);
    publish_int_field(provider, key, FORM_ASSET_EMPTY);
    snprintf(key, sizeof(key), "%sLOGO%d", prefix, row);
    publish_int_field(provider, key, FORM_ASSET_EMPTY);
    snprintf(key, sizeof(key), "%sNAME%d", prefix, row);
    publish_string_field(provider, key, "");
    snprintf(key, sizeof(key), "%sVALUE%d", prefix, row);
    publish_string_field(provider, key, "");
    {
        const char *suffix[]={"HEAD","LOGO","NAME","VALUE"};
        SIZE_T k;
        for(k=0;k<4;k++) {
            snprintf(key,sizeof(key),"%s%s%d",prefix,suffix[k],row);
            publish_visibility_field(provider,key,FALSE);
        }
    }
}


static SIZE_T publish_ranked_rows(
    void *provider,
    const char *prefix,
    RankedPlayer *rows,
    SIZE_T count)
{
    if (!provider)
        return 0;

    SIZE_T row;
    SIZE_T stock_count = stock_stat_count_for_prefix(prefix);
    SIZE_T display_count = count > stock_count ? count : stock_count;
    for (row = 0; row < 5; row++)
    {
        if (row >= display_count)
        {
            clear_ranked_row(provider, prefix, (int)row);
            continue;
        }

        /* If only the stock provider has a row, leave its already-published
         * values intact. Native FCE rows remain authoritative whenever they
         * are available. */
        if (row >= count)
            continue;

        char key[48];
        const char *suffix[]={"HEAD","LOGO","NAME","VALUE"};
        SIZE_T k;
        for(k=0;k<4;k++) {
            snprintf(key,sizeof(key),"%s%s%u",prefix,suffix[k],(unsigned int)row);
            publish_visibility_field(provider,key,TRUE);
        }
        RankedPlayer *item = &rows[row];
        snprintf(key, sizeof(key), "%sHEAD%u", prefix, (unsigned int)row);
        publish_int_field(provider, key, item->head);
        snprintf(key, sizeof(key), "%sLOGO%u", prefix, (unsigned int)row);
        publish_int_field(provider, key, item->logo);
        snprintf(key, sizeof(key), "%sNAME%u", prefix, (unsigned int)row);
        publish_string_field(provider, key, item->name);
        snprintf(key, sizeof(key), "%sVALUE%u", prefix, (unsigned int)row);
        publish_int_field(provider, key, item->value);
    }
    return count;
}


/* The empty-state text is a real layout field, so clearing only VISIBLE is
 * not enough when the stock StatisticsData provider has already populated a
 * stale PARAM value. Always overwrite both pieces of state on every refresh:
 * a populated card gets an empty PARAM, while a truly empty card gets the
 * localized message and is made visible. */
static void publish_ranked_empty_state(
    void *provider,
    const char *field,
    SIZE_T display_count)
{
    BOOL empty = display_count == 0;
    publish_string_field(
        provider,
        field,
        empty ? "FIFA_MODS_CM_NO_DATA_RECORDED" : "");
    publish_visibility_field(provider, field, empty);
}


static SIZE_T publish_injury_rows(void *provider, int *source)
{
    InjuryRow live_rows[5];
    InjuryRow *rows=live_rows;
    SIZE_T row,count;
    int live_query_valid=0,live_source=0;
    memset(live_rows,0,sizeof(live_rows));
    count=native_live_injury_rows(native_club,live_rows,5,&live_query_valid,&live_source);
    /* The stock InjuryList provider is authoritative for the rows it shows:
     * it supplies localized return strings (for example, "2 meses") and
     * player IDs. On some careers temp_teamplayerlinks executes successfully
     * but contains no injury rows, so query_valid alone must not mask this
     * captured list. Use the live table only until the current club's native
     * InjuryList has supplied rows. */
    if(g_injury_count>0 && g_injury_club_id==native_club) {
        rows=g_injury_rows;
        count=g_injury_count;
        if(source) *source=1; /* stock InjuryList provider capture */
    } else if(live_query_valid) {
        if(source) *source=live_source;
    } else {
        count=0;
        if(source) *source=0;
    }
    if(count>5) count=5;
    for (row = 0; row < 5; row++)
    {
        char key[48];
        InjuryRow empty;
        BOOL visible = row < count;
        memset(&empty, 0, sizeof(empty));
        InjuryRow *item =
            visible ? &rows[row] : &empty;
        snprintf(key, sizeof(key), "MYTEAM_INJURY_ROW%u", (unsigned int)row);
        publish_visibility_field(provider, key, visible);
        snprintf(key, sizeof(key), "INJURY_HEAD%u", (unsigned int)row);
        publish_visibility_field(provider, key, visible);
        publish_int_field(provider, key,
            visible && item->head > 0 ? item->head : FORM_ASSET_EMPTY);
        snprintf(key, sizeof(key), "INJURY_NAME%u", (unsigned int)row);
        publish_visibility_field(provider, key, visible);
        publish_string_field(provider, key, item->name);
        snprintf(key, sizeof(key), "INJURY_LENGTH%u", (unsigned int)row);
        publish_visibility_field(provider, key, visible);
        publish_string_field(provider, key, item->length);
    }
    publish_visibility_field(provider,"MYTEAM_INJURY_STATUS",count==0);
    if(count>0)
        publish_string_field(provider,"MYTEAM_INJURY_STATUS","");
    else if(live_query_valid)
        publish_string_field(provider,"MYTEAM_INJURY_STATUS","DADOS DE LESOES NAO DISPONIVEIS");
    else
        publish_string_field(provider,"MYTEAM_INJURY_STATUS","DADOS DE LESOES NAO DISPONIVEIS");
    return count;
}


static void publish_upcoming_rows(void *provider)
{
    SIZE_T row;
    for (row = 0; row < 10; row++)
    {
        char key[48];
        FixtureRow empty;
        memset(&empty, 0, sizeof(empty));
        FixtureRow *item =
            row < g_upcoming_count ? &g_upcoming_rows[row] : &empty;
        char display_date[16];
        memset(display_date, 0, sizeof(display_date));
        if (
            item->date[0]
            && item->date[2] == '/'
            && item->date[5] == '/')
            lstrcpynA(display_date, item->date, 6);
        else
            lstrcpynA(
                display_date,
                item->date,
                (int)sizeof(display_date));
        snprintf(key, sizeof(key), "UPCOMING_DATE%u", (unsigned int)row);
        publish_string_field(provider, key, display_date);
        snprintf(key, sizeof(key), "UPCOMING_HOME%u", (unsigned int)row);
        publish_string_field(provider, key, item->home);
        snprintf(
            key,
            sizeof(key),
            "UPCOMING_HOME_LOGO%u",
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            row < g_upcoming_count && item->home_logo > 0
                ? item->home_logo
                : FORM_ASSET_EMPTY);
        publish_visibility_field(
            provider,
            key,
            row < g_upcoming_count && item->home_logo > 0);
        snprintf(key, sizeof(key), "UPCOMING_AWAY%u", (unsigned int)row);
        publish_string_field(provider, key, item->away);
        snprintf(
            key,
            sizeof(key),
            "UPCOMING_AWAY_LOGO%u",
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            row < g_upcoming_count && item->away_logo > 0
                ? item->away_logo
                : FORM_ASSET_EMPTY);
        publish_visibility_field(
            provider,
            key,
            row < g_upcoming_count && item->away_logo > 0);
        snprintf(key, sizeof(key), "UPCOMING_SCORE%u", (unsigned int)row);
        publish_string_field(provider, key, item->score);
        snprintf(key, sizeof(key), "UPCOMING_TIME%u", (unsigned int)row);
        publish_string_field(provider, key, item->time);
        snprintf(
            key,
            sizeof(key),
            "UPCOMING_COMP_LOGO%u",
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            fixture_competition_icon_or_blank(item));
        publish_visibility_field(
            provider,
            key,
            row < g_upcoming_count
                && fixture_competition_icon_or_blank(item)
                    != FORM_ASSET_EMPTY);
    }
}


static void publish_club_previous_rows(void *provider)
{
    publish_round_group(
        provider,
        "CLUB_PREV_",
        g_club_previous_rows,
        g_club_previous_count);
}


static void publish_round_group(
    void *provider,
    const char *prefix,
    FixtureRow *rows,
    SIZE_T count)
{
    SIZE_T row;
    for (row = 0; row < 10; row++)
    {
        char key[48];
        FixtureRow empty;
        memset(&empty, 0, sizeof(empty));
        FixtureRow *item =
            row < count ? &rows[row] : &empty;
        char display_date[16];
        memset(display_date, 0, sizeof(display_date));
        if (
            item->date[0]
            && item->date[2] == '/'
            && item->date[5] == '/')
            lstrcpynA(display_date, item->date, 6);
        else
            lstrcpynA(
                display_date,
                item->date,
                (int)sizeof(display_date));
        snprintf(
            key,
            sizeof(key),
            "%sDATE%u",
            prefix,
            (unsigned int)row);
        publish_string_field(provider, key, display_date);
        snprintf(
            key,
            sizeof(key),
            "%sHOME_LOGO%u",
            prefix,
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            row < count && item->home_logo > 0
                ? item->home_logo
                : FORM_ASSET_EMPTY);
        publish_visibility_field(
            provider,
            key,
            row < count && item->home_logo > 0);
        snprintf(
            key,
            sizeof(key),
            "%sAWAY_LOGO%u",
            prefix,
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            row < count && item->away_logo > 0
                ? item->away_logo
                : FORM_ASSET_EMPTY);
        publish_visibility_field(
            provider,
            key,
            row < count && item->away_logo > 0);
        snprintf(
            key,
            sizeof(key),
            "%sSCORE%u",
            prefix,
            (unsigned int)row);
        publish_string_field(provider, key, item->score);
        snprintf(
            key,
            sizeof(key),
            "%sCOMP_LOGO%u",
            prefix,
            (unsigned int)row);
        publish_int_field(
            provider,
            key,
            fixture_competition_icon_or_blank(item));
        /* Asset id zero can fall back to a cached/default texture in this UI
         * engine. Hide the field itself when there is no completed fixture,
         * instead of leaving a competition crest on an empty previous-game
         * row. This applies to both ROUND_PREV_ and CLUB_PREV_. */
        publish_visibility_field(
            provider,
            key,
            row < count
                && fixture_competition_icon_or_blank(item)
                    != FORM_ASSET_EMPTY);
    }
}


static void publish_round_rows(void *provider)
{
    publish_round_group(
        provider,
        "ROUND_NEXT_",
        g_round_next_rows,
        g_round_next_count);
    publish_round_group(
        provider,
        "ROUND_PREV_",
        g_round_previous_rows,
        g_round_previous_count);
}


static void publish_bridge_status(void *provider)
{
    publish_string_field(provider,"REFRESH_STATUS","");
    publish_string_field(provider,"REFRESH_HINT","");
}


static void publish_competitions(void *provider)
{
    if (!provider)
        return;
    int current_club_id = (int)InterlockedCompareExchange(
        &g_user_club_id,
        0,
        0);
    BOOL current = current_club_id > 0
        && current_club_id == g_competition_club_id;
    SIZE_T slot;
    for (slot = 0; slot < 5; slot++)
    {
        char key[48];
        BOOL visible = current && slot < g_competition_count
            && g_competition_rows[slot].competition_id > 0;
        CompetitionSummary empty;
        memset(&empty, 0, sizeof(empty));
        CompetitionSummary *item = visible
            ? &g_competition_rows[slot]
            : &empty;

        snprintf(key, sizeof(key), "MYCOMP%u_CARD", (unsigned int)slot);
        publish_visibility_field(provider, key, visible);
        snprintf(key, sizeof(key), "MYCOMP%u_TITLE", (unsigned int)slot);
        publish_string_field(provider, key, item->title_key);
        snprintf(key, sizeof(key), "MYCOMP%u_ICON", (unsigned int)slot);
        publish_int_field(
            provider,
            key,
            competition_icon_asset_id(item->competition_id));
        snprintf(key, sizeof(key), "MYCOMP%u_RANK", (unsigned int)slot);
        publish_int_field(provider, key, item->rank);
        snprintf(key, sizeof(key), "MYCOMP%u_PLAYED", (unsigned int)slot);
        publish_int_field(provider, key, item->played);
        snprintf(key, sizeof(key), "MYCOMP%u_POINTS", (unsigned int)slot);
        publish_int_field(provider, key, item->points);
        snprintf(key, sizeof(key), "MYCOMP%u_HOME_LOGO", (unsigned int)slot);
        publish_int_field(provider, key, item->next_home_logo);
        snprintf(key, sizeof(key), "MYCOMP%u_AWAY_LOGO", (unsigned int)slot);
        publish_int_field(provider, key, item->next_away_logo);
        char date[16];
        char time[16];
        memset(date, 0, sizeof(date));
        memset(time, 0, sizeof(time));
        if (item->next_date > 0)
            snprintf(
                date,
                sizeof(date),
                "%02d/%02d",
                item->next_date % 100,
                (item->next_date / 100) % 100);
        if (item->next_time > 0)
            snprintf(
                time,
                sizeof(time),
                "%02d:%02d",
                item->next_time / 100,
                item->next_time % 100);
        snprintf(key, sizeof(key), "MYCOMP%u_DATE", (unsigned int)slot);
        publish_string_field(provider, key, date);
        snprintf(key, sizeof(key), "MYCOMP%u_TIME", (unsigned int)slot);
        publish_string_field(provider, key, time);
    }

    BOOL league_visible = current && g_competition_count > 0
        && g_competition_rows[0].kind == 1;
    publish_visibility_field(provider, "MYCOMP_LEAGUE_CARD", league_visible);
    for (slot = 0; slot < 20; slot++)
    {
        char key[48];
        CompetitionStandingRow empty;
        memset(&empty, 0, sizeof(empty));
        CompetitionStandingRow *item = league_visible
            && g_competition_league_rows[slot].team_id > 0
            ? &g_competition_league_rows[slot]
            : &empty;
        BOOL row_visible = item->team_id > 0;
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_ROW%u", (unsigned int)slot);
        publish_visibility_field(provider, key, row_visible);
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_RANK%u", (unsigned int)slot);
        publish_int_field(provider, key, item->rank);
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_LOGO%u", (unsigned int)slot);
        publish_int_field(provider, key, item->team_id);
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_NAME%u", (unsigned int)slot);
        publish_string_field(provider, key, bridge_team_name(item->team_id));
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_PLAYED%u", (unsigned int)slot);
        publish_int_field(provider, key, item->played);
        snprintf(key, sizeof(key), "MYCOMP_LEAGUE_POINTS%u", (unsigned int)slot);
        publish_int_field(provider, key, item->points);
    }
}


/* The generic statistics service may return a ranked vector left over from
 * another screen.  A competition id alone is not enough to trust it: FIFA
 * labels that stale vector with the current provider competition.  Validate
 * every club against the active standings/fixture context before publishing
 * it to the custom hub. */
/* assist_competition_membership_is_ready: removed obsolete bridge/scanner path. */


/* The statistics service does not use the competition object shown by the
 * hub.  It expects the current competition-progress/stage key (for example
 * hub 1271 -> query 1272 and Libertadores 970 -> query 991).  Passing the
 * display key makes FIFA return its global leaders while still labelling the
 * response as the selected competition. */
/* statistics_query_key_for_competition: removed obsolete bridge/scanner path. */


/* assist_team_belongs_to_competition: removed obsolete bridge/scanner path. */


/* assist_rows_belong_to_competition: removed obsolete bridge/scanner path. */


/* query_top_assists: removed obsolete bridge/scanner path. */


static void clear_assist_row(void *provider, int row)
{
    char key[32];
    snprintf(key, sizeof(key), "ASSIST_HEAD%d", row);
    publish_int_field(provider, key, 0);
    snprintf(key, sizeof(key), "ASSIST_LOGO%d", row);
    publish_int_field(provider, key, 0);
    snprintf(key, sizeof(key), "ASSIST_NAME%d", row);
    publish_string_field(provider, key, "");
    snprintf(key, sizeof(key), "ASSIST_VALUE%d", row);
    publish_int_field(provider, key, 0);
}


static SIZE_T publish_top_assists(void *provider)
{
    if (!provider)
        return 0;

    int active_competition_id = (int)InterlockedCompareExchange(
        &g_active_competition_id,
        0,
        0);
    int requested_competition_id = g_stats_tile_query_competition > 0
        ? g_stats_tile_query_competition
        : active_competition_id;
    BOOL current_cache =
        requested_competition_id > 0
        && g_assist_competition_id == requested_competition_id;
    SIZE_T row;
    for (row = 0; row < 5; row++)
    {
        if (!current_cache || row >= g_assist_count)
        {
            clear_assist_row(provider, (int)row);
            continue;
        }

        RankedPlayer *item = &g_assist_rows[row];
        char key[32];
        snprintf(
            key,
            sizeof(key),
            "ASSIST_HEAD%u",
            (unsigned int)row);
        publish_int_field(provider, key, item->head);
        snprintf(
            key,
            sizeof(key),
            "ASSIST_LOGO%u",
            (unsigned int)row);
        publish_int_field(provider, key, item->logo);
        snprintf(
            key,
            sizeof(key),
            "ASSIST_NAME%u",
            (unsigned int)row);
        publish_string_field(provider, key, item->name);
        snprintf(
            key,
            sizeof(key),
            "ASSIST_VALUE%u",
            (unsigned int)row);
        publish_int_field(provider, key, item->value);
    }
    return current_cache ? (g_assist_count < 5 ? g_assist_count : 5) : 0;
}

static void publish_competition_leader_states(void *provider, SIZE_T assist_count)
{
    SIZE_T row, scorer_count = 0;
    static const char *suffixes[] = {"HEAD", "LOGO", "NAME", "VALUE"};
    char key[48];
    if (!provider) return;
    for (row = 0; row < 5; ++row) {
        SIZE_T k;
        BOOL scorer_visible = g_competition_scorer_present[row];
        BOOL assist_visible = row < assist_count;
        if (scorer_visible) ++scorer_count;
        snprintf(key, sizeof(key), "ROW%u", (unsigned)row);
        publish_visibility_field(provider, key, scorer_visible);
        snprintf(key, sizeof(key), "ASSIST_ROW%u", (unsigned)row);
        publish_visibility_field(provider, key, assist_visible);
        if (!scorer_visible) clear_ranked_row(provider, "", (int)row);
        if (!assist_visible) clear_ranked_row(provider, "ASSIST_", (int)row);
        for (k = 0; k < 4; ++k) {
            if (scorer_visible) {
                snprintf(key, sizeof(key), "%s%u", suffixes[k], (unsigned)row);
                publish_visibility_field(provider, key, TRUE);
            }
            if (assist_visible) {
                snprintf(key, sizeof(key), "ASSIST_%s%u", suffixes[k], (unsigned)row);
                publish_visibility_field(provider, key, TRUE);
            }
        }
    }
    publish_ranked_empty_state(provider, "COMP_SCORERS_EMPTY", scorer_count);
    publish_ranked_empty_state(provider, "COMP_ASSISTS_EMPTY", assist_count);
}


/* Native StatisticsData calls this immediately before setting its dirty flag
 * (0x59CEA91 -> 0x5B14990). Add the whole custom payload BEFORE notifying UI,
 * after all stock rows/empty markers have been written. */
static void stats_mark_dirty_capture(void *notification, unsigned char dirty)
{
    void *owner = g_current_stats_provider_owner;
    void *provider = g_current_stats_provider;
    if (dirty && owner && provider) {
        native_prepare(owner);
        if (native_generation() && native_club > 0) {
            /* Only the competition carousel owns a dynamic page count. */
            if (native_is_competition_round_provider(owner, provider)) {
                int subtiles = g_competition_count > 1
                    ? (int)g_competition_count - 1 : 0;
                if (subtiles > 2) subtiles = 2;
                g_set_int(provider, "LENGTH", subtiles);
            }
            native_publish(provider);
            native_log_transfer_card_context(provider);
            g_stats_applied_generation = native_generation();
            g_stats_publication_completed = TRUE;
        }
        native_end();
    }
    /* Preserve native notification even when custom data is not ready. */
    g_stats_mark_dirty(notification, dirty);
}


#include "career_job_offer.inc"

static void stats_provider_with_diagnostics(void *provider_owner)
{
    int requested = competition_from_statistics_provider(provider_owner);
    int observed_calendar_date = native_calendar_date(provider_owner);
    BOOL replay = InterlockedCompareExchange(&g_pending_stats_refresh_busy, 0, 0) != 0;
    /* Do not depend exclusively on save/load or calendar events. Some
     * competitions do not emit the same notifications as the Brazilian
     * career path. While this provider exists, sample the authoritative FCE
     * model once per second and republish any newly captured generation. */
    if (!replay) fce_runtime_keep_fresh(45000, 1000);
    InterlockedExchange(&g_active_competition_id, requested);
    InterlockedExchange(&g_display_competition_id, requested);
    g_current_stats_object = NULL;
    g_current_stats_provider = NULL;
    g_stats_applied_generation = 0;
    g_stats_publication_completed = FALSE;
    /* A simulation advance can update the live career tables without a save
     * or load event. CalendarManager's TODAY value is the reliable signal.
     * Queue a fresh owner-thread capture once for each observed date. */
    if (fce_date_valid(observed_calendar_date)
        && observed_calendar_date != g_last_requested_calendar_date)
    {
        InterlockedExchange(&g_last_requested_calendar_date, observed_calendar_date);
        fce_runtime_request_refresh();
    }
    /* The finish hook publishes after the query, before native notification. */
    reset_stock_stat_capture();
    g_current_stats_provider_owner = provider_owner;
    __try {
        g_stats_provider(provider_owner);
        if (!replay) remember_pending_stats_refresh(provider_owner);
        if (g_stats_publication_completed)
            card_refresh_applied(&g_stats_refresh_schedule, g_stats_applied_generation);
        log_card_refresh(g_stats_publication_completed ? "published_before_notify" :
            "publication_pending", provider_owner, g_current_stats_provider, replay ? 1 : 0);
    } __finally {
        g_current_stats_provider = NULL;
        g_current_stats_provider_owner = NULL;
        g_current_stats_object = NULL;
        native_end();
    }
    career_job_offer_deliver(provider_owner);
}


#include "native_cards.inc"


static BOOL knockout_pair_matches(
    const CompetitionTabKnockout *current,
    const CompetitionTabKnockout *candidate)
{
    if (!current || !candidate)
        return FALSE;
    return (
        (candidate->home_team == current->home_team
            && candidate->away_team == current->away_team)
        || (candidate->home_team == current->away_team
            && candidate->away_team == current->home_team));
}


/* Publish only the previous leg of the exact fixture currently shown by the
 * native knockout provider. A generic "last cup result" would be wrong for
 * single-leg rounds and would also pick an older round in a multi-round cup. */
static void publish_standing_knockout_details(void *provider)
{
    CompetitionTabKnockout *current;
    CompetitionTabKnockout *previous = NULL;
    size_t index;
    int competition_id;
    int icon_id;
    char value[160];

    if (!provider)
        return;

    g_standing_previous_leg_visible = FALSE;
    g_standing_previous_leg_score[0] = 0;

    competition_id = (int)InterlockedCompareExchange(
        &g_active_competition_id,
        0,
        0);
    icon_id = native_logo(competition_id);
    publish_int_field(
        provider,
        "CM_KO_COMPETITION_ICON",
        icon_id > 0 ? icon_id : FORM_ASSET_EMPTY);
    publish_visibility_field(
        provider,
        "CM_KO_COMPETITION_ICON",
        icon_id > 0);
    publish_int_field(
        provider,
        "TROPHYID",
        icon_id > 0 ? icon_id : FORM_ASSET_EMPTY);
    publish_visibility_field(provider, "TROPHYID", icon_id > 0);
    publish_visibility_field(provider, "CM_KO_LEG_VISIBLE", FALSE);
    publish_knockout_leg_visibility(provider, FALSE);
    publish_string_field(provider, "CM_KO_LEG_LABEL", "");
    publish_string_field(provider, "CM_KO_LEG_DIVIDER", "");
    publish_string_field(provider, "CM_KO_LEG_SCORE", "");
    publish_string_field(provider, "CM_KO_LEG_HOME", "");
    publish_string_field(provider, "CM_KO_LEG_AWAY", "");

    if (g_competition_count == 0)
        return;
    current = g_competition_tab_knockout;
    if (!current->visible
        || current->stage <= 0
        || current->round <= 0
        || current->home_team <= 0
        || current->away_team <= 0)
        return;

    for (index = 0;
        index < g_competition_tab_knockout_history_counts[0];
        index++)
    {
        CompetitionTabKnockout *candidate =
            g_competition_tab_knockout_history[0] + index;
        if (!candidate->played
            || candidate->stage != current->stage
            || candidate->round != current->round
            || candidate->home_score < 0
            || candidate->away_score < 0
            || !knockout_pair_matches(current, candidate))
            continue;
        if (current->played
            && (candidate->date > current->date
                || (candidate->date == current->date
                    && candidate->time >= current->time)))
            continue;
        if (!current->played && candidate->date >= current->date)
            continue;
        if (!previous
            || candidate->date > previous->date
            || (candidate->date == previous->date
                && candidate->time > previous->time))
            previous = candidate;
    }
    if (!previous)
        return;

    publish_string_field(provider, "CM_KO_LEG_LABEL", "IDA");
    publish_string_field(provider, "CM_KO_LEG_DIVIDER", "|");
    snprintf(
        value,
        sizeof(value),
        "%d - %d",
        previous->home_score,
        previous->away_score);
    lstrcpynA(
        g_standing_previous_leg_score,
        value,
        (int)sizeof(g_standing_previous_leg_score));
    g_standing_previous_leg_visible = TRUE;
    publish_string_field(provider, "CM_KO_LEG_SCORE", value);
    native_team_name(previous->home_team, value, sizeof(value));
    publish_string_field(provider, "CM_KO_LEG_HOME", value);
    native_team_name(previous->away_team, value, sizeof(value));
    publish_string_field(provider, "CM_KO_LEG_AWAY", value);
    publish_visibility_field(provider, "CM_KO_LEG_VISIBLE", TRUE);
    publish_knockout_leg_visibility(provider, TRUE);
}

typedef struct CallPatchSpec
{
    const char *name;
    uintptr_t call_rva;
    uintptr_t expected_target_rva;
    void *replacement;
} CallPatchSpec;


static BOOL write_relative_call(
    unsigned char *module_base,
    const CallPatchSpec *patch,
    unsigned char *relay,
    FILE *log)
{
    unsigned char *call = module_base + patch->call_rva;
    if (call[0] != 0xE8)
    {
        fprintf(log, "[CALL OPCODE INVALIDO] %s\n", patch->name);
        return FALSE;
    }

    int32_t original_displacement;
    memcpy(&original_displacement, call + 1, sizeof(original_displacement));
    unsigned char *original_target = call + 5 + original_displacement;
    if (original_target != module_base + patch->expected_target_rva)
    {
        fprintf(
            log,
            "[CALL DESTINO INVALIDO] %s atual=%p esperado=%p\n",
            patch->name,
            (void *)original_target,
            (void *)(module_base + patch->expected_target_rva));
        return FALSE;
    }

    relay[0] = 0x48;
    relay[1] = 0xB8;
    memcpy(relay + 2, &patch->replacement, sizeof(patch->replacement));
    relay[10] = 0xFF;
    relay[11] = 0xE0;

    intptr_t delta = relay - (call + 5);
    if (delta < INT32_MIN || delta > INT32_MAX)
    {
        fprintf(log, "[CALL FORA DE ALCANCE] %s\n", patch->name);
        return FALSE;
    }

    DWORD old_protection;
    if (!VirtualProtect(call, 5, PAGE_EXECUTE_READWRITE, &old_protection))
    {
        fprintf(log, "[CALL VirtualProtect ERRO] %s\n", patch->name);
        return FALSE;
    }

    int32_t displacement = (int32_t)delta;
    memcpy(call + 1, &displacement, sizeof(displacement));
    FlushInstructionCache(GetCurrentProcess(), call, 5);
    FlushInstructionCache(GetCurrentProcess(), relay, 12);

    DWORD ignored;
    VirtualProtect(call, 5, old_protection, &ignored);
    fprintf(
        log,
        "[OK CALL] %s @ %p -> relay %p -> %p\n",
        patch->name,
        (void *)call,
        (void *)relay,
        patch->replacement);
    return TRUE;
}


static const CallPatchSpec g_call_patches[] = {
        {
            "career_startup_object_guard",
            0x05F18BCF,
            0x05573D20,
            (void *)resolve_career_startup_object_guard,
        },
        {
            "calendar_competition_asset",
            0x058FB894,
            0x05BB8BE0,
            (void *)calendar_asset_for_date_capture,
        },
        {
            "standings_provider_wrapper",
            0x05959837,
            0x059CC850,
            (void *)standing_provider_with_context,
        },
        {
            "standings_stat_capture",
            0x059CD786,
            0x04469EB0,
            (void *)standing_stat_capture,
        },
        {
            "standings_extra_columns",
            0x059CD798,
            0x05A51150,
            (void *)set_played_and_extra,
        },
        {
            "standings_field_capture",
            0x059CD772,
            0x05A511E0,
            (void *)standing_string_capture,
        },
        {
            "standings_logo_field_capture",
            0x059CD6EA,
            0x05A511E0,
            (void *)standing_string_capture,
        },
        {
            "standings_logo_value_capture",
            0x059CD700,
            0x05A51150,
            (void *)set_played_and_extra,
        },
        {
            "statistics_object_capture",
            0x059CE14A,
            0x05AC2C60,
            (void *)stats_vector_capture,
        },
        {
            "statistics_provider_capture",
            0x059CE7C2,
            0x05A511E0,
            (void *)stats_string_capture,
        },
        {
            "statistics_provider_wrapper",
            0x0595989C,
            0x059CE0E0,
            (void *)stats_provider_with_diagnostics,
        },
        {
            "contracts_provider_capture",
            0x059847DB,
            0x059C74C0,
            (void *)contracts_provider_capture,
        },
        {
            "injury_player_id_capture",
            0x05901EB1,
            0x05A51150,
            (void *)injury_set_int_capture,
        },
        {
            "injury_player_name_capture",
            0x05901EC7,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "injury_position_capture",
            0x05901EF1,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "injury_description_capture",
            0x05901F18,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "injury_length_capture",
            0x05901F6E,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "injury_status_capture",
            0x05901FD7,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "injury_position_type_capture",
            0x05902045,
            0x05A511E0,
            (void *)injury_set_string_capture,
        },
        {
            "competition_scorer_name_field",
            0x059CE89F,
            0x05A511E0,
            (void *)competition_scorer_name_capture,
        },
        {
            "competition_scorer_name_value",
            0x059CE8D1,
            0x05A511E0,
            (void *)competition_scorer_name_capture,
        },
        {
            "statistics_publish_before_notify",
            0x059CEA91,
            0x05B14990,
            (void *)stats_mark_dirty_capture,
        },
};

/* The protected loader materializes different code regions separately. One
 * decoded standings instruction is not a barrier for all Career call sites.
 * Wait for every byte patch AND every original call target before writing. */
static BOOL career_patch_sites_ready(unsigned char *module_base, FILE *log)
{
    SIZE_T i;
    for (i = 0; i < sizeof(g_patches) / sizeof(g_patches[0]); ++i) {
        const PatchSpec *p = &g_patches[i];
        if (!bytes_equal(module_base + p->rva, p->expected, p->size) &&
            !bytes_equal(module_base + p->rva, p->replacement, p->size)) {
            if (log) fprintf(log, "PRECHECK REJECTED: %s; UI unchanged.\n", p->name);
            return FALSE;
        }
    }
    for (i = 0; i < sizeof(g_call_patches) / sizeof(g_call_patches[0]); ++i) {
        const CallPatchSpec *p = &g_call_patches[i];
        const unsigned char *at = module_base + p->call_rva;
        int32_t displacement;
        memcpy(&displacement, at + 1, sizeof(displacement));
        if (at[0] != 0xE8 || at + 5 + displacement !=
            module_base + p->expected_target_rva) {
            if (log) fprintf(log,
                "PRECHECK REJECTED: %s rva=0x%llX opcode=%02X actual=%p expected=%p; no call sites changed.\n",
                p->name, (unsigned long long)p->call_rva, at[0],
                (const void *)(at + 5 + displacement),
                (const void *)(module_base + p->expected_target_rva));
            return FALSE;
        }
    }
    return TRUE;
}

static unsigned int apply_call_patches(
    unsigned char *module_base,
    FILE *log)
{
    if (!career_patch_sites_ready(module_base, log)) return 0;
    unsigned char *relay_page = (unsigned char *)VirtualAlloc(
        module_base + 0x09600000,
        0x1000,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_EXECUTE_READWRITE);
    if (!relay_page)
    {
        fprintf(
            log,
            "ERRO: VirtualAlloc relay: %lu\n",
            (unsigned long)GetLastError());
        return 0;
    }

    unsigned int patched = 0;
    unsigned int index;
    for (index = 0; index < sizeof(g_call_patches) / sizeof(g_call_patches[0]); index++)
    {
        if (write_relative_call(
            module_base,
            &g_call_patches[index],
            relay_page + (index * 16),
            log))
            patched++;
    }
    return patched;
}


static DWORD WINAPI patch_standings_provider(LPVOID unused)
{
    (void)unused;
    append_loader_log("career_native_20260916_r5_dynamic_context_worker_started");

    char log_path[MAX_PATH];
    wsprintfA(log_path, "%s\\logs\\standings_patch.log", g_mod_dir);

    HMODULE executable = GetModuleHandleA(NULL);
    MODULEINFO module_info;
    if (!executable
        || !GetModuleInformation(
            GetCurrentProcess(),
            executable,
            &module_info,
            sizeof(module_info)))
    {
        return 1;
    }

    /* No save interception and no external bridge in this build. */

    if (module_info.SizeOfImage != 0x09525000)
    {
        FILE *log = fopen(log_path, "wb");
        if (log)
        {
            fprintf(
                log,
                "ERRO: SizeOfImage inesperado: 0x%lX\n",
                (unsigned long)module_info.SizeOfImage);
            fclose(log);
        }
        return 2;
    }

    /* The probe still only observes I/O. The optional retirement engine is
     * separately disabled unless its explicit config enables it. */
    (void)retirement_engine_start(g_mod_dir);

    unsigned char *module_base = (unsigned char *)module_info.lpBaseOfDll;
    g_module_base = module_base;
    g_module_size = module_info.SizeOfImage;
    g_standing_stat = (StandingStatFn)(module_base + 0x04469EB0);
    g_prepare_field = (PrepareFieldFn)(module_base + 0x05A2A4F0);
    g_set_int = (SetIntFn)(module_base + 0x05A51150);
    g_set_string = (SetStringFn)(module_base + 0x05A511E0);
    g_stats_vector = (StatsVectorFn)(module_base + 0x05AC2C60);
    g_stats_provider = (StatsProviderFn)(module_base + 0x059CE0E0);
    g_stats_mark_dirty = (StatsMarkDirtyFn)(module_base + 0x05B14990);
    g_standing_provider =
        (StandingProviderFn)(module_base + 0x059CC850);
    g_get_competition_service_descriptor =
        (GetServiceDescriptorFn)(module_base + 0x04456300);
    g_get_name_service_descriptor =
        (GetServiceDescriptorFn)(module_base + 0x04456560);
    g_get_query_service_descriptor =
        (GetServiceDescriptorFn)(module_base + 0x04456A30);
    g_get_career_service_descriptor =
        (GetServiceDescriptorFn)(module_base + 0x044575E0);
    g_get_selection = (GetSelectionFn)(module_base + 0x05947960);
    g_get_competition_ref =
        (GetCompetitionRefFn)(module_base + 0x05BB57C0);
    g_init_stat_container =
        (InitStatContainerFn)(module_base + 0x05C2FEA0);
    g_query_player_stats =
        (QueryPlayerStatsFn)(module_base + 0x05B99080);
    g_stat_container_count =
        (StatContainerCountFn)(module_base + 0x05C44C70);
    g_stat_container_item =
        (StatContainerItemFn)(module_base + 0x05C44C40);
    g_stat_item_value =
        (StatItemValueFn)(module_base + 0x05C44BC0);
    g_resolve_player_name =
        (ResolvePlayerNameFn)(module_base + 0x05C38130);
    g_resolve_team = (ResolveTeamFn)(module_base + 0x05B8E430);
    native_name_db_bind();
    g_full_stats_category =
        (FullStatsCategoryFn)(module_base + 0x05AB40F0);
    g_get_career_context =
        (GetCareerContextFn)(module_base + 0x05AAFFF0);
    g_get_user_team =
        (GetUserTeamFn)(module_base + 0x05AC5940);
    g_contracts_provider =
        (ContractsProviderFn)(module_base + 0x059C74C0);
    g_set_indexed_int =
        (IndexedIntFn)(module_base + 0x05A143F0);
    g_set_indexed_string =
        (IndexedStringFn)(module_base + 0x042F0B90);
    g_calendar_asset_for_date =
        (CalendarAssetForDateFn)(module_base + 0x05BB8BE0);
    g_resolve_career_startup_object =
        (ResolveCareerStartupObjectFn)(module_base + 0x05573D20);
    fce_runtime_install();
    crowd_runtime_start(g_mod_dir);
    unsigned int attempt;
    for (attempt = 0; attempt < 120; attempt++)
    {
        if (career_patch_sites_ready(module_base, NULL))
            break;
        Sleep(500);
    }

    FILE *log = fopen(log_path, "wb");
    if (!log)
        return 3;

    fprintf(
        log,
        "FIFA 16 Career Standings Provider Patch\n"
        "Base=0x%llX Size=0x%lX Wait=%u ms SaveHooks=%ld\n",
        (unsigned long long)(uintptr_t)module_base,
        (unsigned long)module_info.SizeOfImage,
        attempt * 500,
        InterlockedCompareExchange(&g_save_file_hook_count, 0, 0));

    if (attempt == 120)
    {
        fputs("ERRO: timeout aguardando todos os pontos nativos da carreira.\n", log);
        (void)career_patch_sites_ready(module_base, log);
        fclose(log);
        return 4;
    }
    append_loader_log("career_native_card_sites_ready");

    /* FIFA's protected loader has finished materializing the executable at
     * this point. Install the save I/O probe only after that barrier; doing
     * it earlier can see an incomplete import table and miss DATA writes. */
    (void)install_active_save_read_probe(executable);

    /* Do not patch fifa16.bin here. Its loader-owned image has a different
     * lifetime and replacing the same process-wide callbacks twice can
     * destabilize Career Hub startup. */

    unsigned int patched = 0;
    unsigned int index;
    unsigned int expected_calls = (unsigned int)(sizeof(g_call_patches) / sizeof(g_call_patches[0]));
    unsigned int call_patched = apply_call_patches(module_base, log);
    if(call_patched!=expected_calls) { fclose(log); return 5; }
    for (index = 0; index < sizeof(g_patches) / sizeof(g_patches[0]); index++)
    {
        if (apply_patch(module_base, &g_patches[index], log))
            patched++;
    }
    fprintf(log, "Patches de bytes=%u/%u\n", patched, (unsigned int)(
        sizeof(g_patches) / sizeof(g_patches[0])));
    fprintf(log, "Patches de chamadas=%u/%u\n", call_patched, expected_calls);
    fclose(log);
    if (patched == sizeof(g_patches) / sizeof(g_patches[0]) && call_patched == expected_calls)
    {
        append_loader_log("career_native_card_hooks_installed");
        append_loader_log("career_cards_redraw_v1_hooks_installed");
        swiss_delta_notify_ready(g_self, g_game_dir, g_mod_dir, SWISS_READY_NATIVE);
    }
    return (
        patched == sizeof(g_patches) / sizeof(g_patches[0])
        && call_patched == expected_calls)
        ? 0
        : 5;
}


/* start_career_data_bridge: removed obsolete bridge/scanner path. */


__declspec(dllexport)
HRESULT WINAPI DirectInput8Create(
    HINSTANCE instance,
    DWORD version,
    REFIID interface_id,
    LPVOID *output,
    LPUNKNOWN outer)
{
    if (!load_l9_proxy())
        return E_FAIL;
    HRESULT result = g_direct_input8_create(
        instance,
        version,
        interface_id,
        output,
        outer);
    if (SUCCEEDED(result))
        swiss_delta_notify_ready(g_self, g_game_dir, g_mod_dir, SWISS_READY_DIRECTINPUT);
    return result;
}


HRESULT WINAPI proxy_DllCanUnloadNow(void)
{
    if (!load_l9_proxy() || !g_dll_can_unload_now)
        return E_FAIL;
    return g_dll_can_unload_now();
}


HRESULT WINAPI proxy_DllGetClassObject(
    REFCLSID class_id,
    REFIID interface_id,
    LPVOID *output)
{
    if (!load_l9_proxy() || !g_dll_get_class_object)
        return E_FAIL;
    return g_dll_get_class_object(class_id, interface_id, output);
}


HRESULT WINAPI proxy_DllRegisterServer(void)
{
    if (!load_l9_proxy() || !g_dll_register_server)
        return E_FAIL;
    return g_dll_register_server();
}


HRESULT WINAPI proxy_DllUnregisterServer(void)
{
    if (!load_l9_proxy() || !g_dll_unregister_server)
        return E_FAIL;
    return g_dll_unregister_server();
}


LPCDIDATAFORMAT WINAPI proxy_GetdfDIJoystick(void)
{
    if (!load_l9_proxy() || !g_getdf_di_joystick)
        return NULL;
    return g_getdf_di_joystick();
}

/* The previous DirectInput chain also bootstrapped ModCarrerMode's optional
 * plugin host.  The L9 chain only owns the low-level FIFA patches, so retain
 * that host startup explicitly without loading the old patch chain.  Run this
 * outside DllMain's loader lock; the host discovers enabled.txt beside itself
 * and starts the configured plugins. */
static DWORD WINAPI start_optional_mod_host(LPVOID unused)
{
    char path[MAX_PATH];
    HMODULE host;
    Fifa16ModHostStartFn start;
    (void)unused;

    host = GetModuleHandleA("mod_host.dll");
    if (!host) {
        if (_snprintf_s(path, sizeof(path), _TRUNCATE,
                "%s\\mods\\mod_host.dll", g_mod_dir) < 0) {
            append_loader_log("mod_host_path_too_long");
            return 1;
        }
        host = LoadLibraryA(path);
    }
    if (!host) {
        append_loader_log("mod_host_load_failed");
        return 1;
    }

    start = (Fifa16ModHostStartFn)GetProcAddress(
        host, "Fifa16ModHostStart");
    if (!start) {
        append_loader_log("mod_host_export_missing");
        return 1;
    }
    if (!start()) {
        append_loader_log("mod_host_start_failed");
        return 1;
    }
    append_loader_log("mod_host_started");
    return 0;
}

/* Small versioned surface for optional mods. Consumers resolve these exports
 * instead of depending on private DLL RVAs, so rebuilding the core does not
 * silently disable otherwise-independent plugins. */
unsigned int WINAPI Fifa16CareerApiVersion(void)
{
    return 1U;
}

typedef struct CrowdApiSnapshot
{
    FceLiveSnapshot *source;
    FceModel model;
} CrowdApiSnapshot;

static int crowd_api_effective_date(const FceModel *model)
{
    int date = model ? model->date : -1;
    if (!fce_date_valid(date))
        date = (int)InterlockedCompareExchange(
            &g_last_requested_calendar_date, 0, 0);
    return fce_date_valid(date) ? date : -1;
}

static void log_crowd_api_snapshot(const char *stage, LONG club,
    LONG competition, const FceModel *model)
{
    static volatile LONG state_logged, acquire_logged, model_logged;
    volatile LONG *flag = strcmp(stage, "state") == 0 ? &state_logged
        : strcmp(stage, "acquire") == 0 ? &acquire_logged : &model_logged;
    char path[MAX_PATH];
    FILE *log;
    size_t club_standings = 0, club_fixtures = 0, i;
    if (InterlockedCompareExchange(flag, 1, 0) != 0 || !g_mod_dir[0])
        return;
    if (model) {
        for (i = 0; i < model->standing_count; ++i)
            if (model->standings[i].team == club)
                ++club_standings;
        for (i = 0; i < model->fixture_count; ++i)
            if (model->fixtures[i].home == club
                || model->fixtures[i].away == club)
                ++club_fixtures;
    }
    snprintf(path, sizeof(path), "%s\\logs\\crowd_api_debug.log", g_mod_dir);
    log = fopen(path, "ab");
    if (!log) return;
    fprintf(log,
        "stage=%s club=%ld competition=%ld model=%d date=%d nodes=%llu standings=%llu club_standings=%llu fixtures=%llu club_fixtures=%llu stats=%llu\n",
        stage, club, competition, model != NULL,
        model ? model->date : -1,
        model ? (unsigned long long)model->node_count : 0ULL,
        model ? (unsigned long long)model->standing_count : 0ULL,
        (unsigned long long)club_standings,
        model ? (unsigned long long)model->fixture_count : 0ULL,
        (unsigned long long)club_fixtures,
        model ? (unsigned long long)model->stat_count : 0ULL);
    fclose(log);
}

static BOOL crowd_api_get_live_state(LONG *club_out, LONG *competition_out)
{
    FceLiveSnapshot *snapshot = NULL;
    void *owner = g_pending_stats_provider_owner;
    void *expected_vtable = g_pending_stats_provider_vtable;
    uintptr_t actual_vtable = 0;
    uintptr_t registry = 0;
    uintptr_t wrapper = 0;
    uintptr_t service = 0;
    ServiceDescriptor descriptor;
    void *context = NULL;
    void *team = NULL;
    LONG current_club = InterlockedCompareExchange(&g_user_club_id, 0, 0);
    LONG competition = InterlockedCompareExchange(&g_display_competition_id, 0, 0);

    if (!club_out || !competition_out || current_club <= 0
        || current_club > 2000000 || !owner || !expected_vtable
        || !is_readable_range(owner, sizeof(uintptr_t))
        || !is_readable_range((const unsigned char *)owner + 8U, sizeof(uintptr_t))
        || !g_get_career_service_descriptor || !g_get_career_context
        || !g_get_user_team)
        return FALSE;

    memcpy(&actual_vtable, owner, sizeof(actual_vtable));
    if (actual_vtable != (uintptr_t)expected_vtable)
        return FALSE;
    memcpy(&registry, (const unsigned char *)owner + 8U, sizeof(registry));
    if (!registry)
        return FALSE;

    memset(&descriptor, 0, sizeof(descriptor));
    descriptor.index = -1;
    __try {
        g_get_career_service_descriptor(&descriptor);
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        return FALSE;
    }
    if (descriptor.index < 0 || descriptor.index > 4096)
        return FALSE;

    if (!is_readable_range((const void *)(registry +
            (uintptr_t)descriptor.index * 32U + 0x18U), sizeof(wrapper)))
        return FALSE;
    memcpy(&wrapper, (const void *)(registry +
        (uintptr_t)descriptor.index * 32U + 0x18U), sizeof(wrapper));
    if (!wrapper || !is_readable_range((const void *)wrapper, sizeof(service)))
        return FALSE;
    memcpy(&service, (const void *)wrapper, sizeof(service));
    if (!service)
        return FALSE;

    __try {
        context = g_get_career_context((void *)service);
        if (context)
            team = g_get_user_team(context, 0);
        if (!team || !is_readable_range((const unsigned char *)team + 4U,
                sizeof(current_club)))
            return FALSE;
        memcpy(&current_club, (const unsigned char *)team + 4U,
            sizeof(current_club));
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        return FALSE;
    }
    if (current_club <= 0 || current_club > 2000000)
        return FALSE;

    /* The plugin needs a settled FCE model and a valid career date. In this
     * FIFA career the FCE date remains -1, while CalendarManager supplies
     * TODAY to the card. Do not expose Career until that same date can be
     * attached to the plugin's snapshot view. */
    snapshot = fce_runtime_acquire();
    if (!snapshot || !fce_runtime_is_stable()
        || crowd_api_effective_date(fce_runtime_model(snapshot)) < 0) {
        fce_runtime_release(snapshot);
        return FALSE;
    }
    log_crowd_api_snapshot("state", current_club, competition,
        fce_runtime_model(snapshot));
    fce_runtime_release(snapshot);

    *club_out = current_club;
    *competition_out = competition > 0 && competition <= 65535
        ? competition : 0;
    return TRUE;
}

BOOL WINAPI Fifa16CareerGetState(LONG *club_out, LONG *competition_out)
{
    LONG club = 0;
    LONG competition = 0;
    LONG current_club;
    LONG cached_club;
    FceLiveSnapshot *snapshot;
    const FceModel *model;

    if (!club_out || !competition_out)
        return FALSE;

    if (crowd_api_get_live_state(&club, &competition)) {
        InterlockedExchange(&g_crowd_api_last_live_club, club);
        InterlockedExchange(&g_crowd_api_last_live_competition,
            competition);
        *club_out = club;
        *competition_out = competition;
        return TRUE;
    }

    /* FIFA tears down the Career statistics provider while opening a match.
     * The user's club and the FCE snapshot remain valid, but the live service
     * lookup above briefly fails. Keep the crowd plugin's Career gate open
     * from the last verified club so it does not restore 0.90 at kickoff. */
    current_club = InterlockedCompareExchange(&g_user_club_id, 0, 0);
    cached_club = InterlockedCompareExchange(
        &g_crowd_api_last_live_club, 0, 0);
    if (current_club <= 0 || current_club > 2000000
        || current_club != cached_club)
        return FALSE;

    snapshot = fce_runtime_acquire();
    model = fce_runtime_model(snapshot);
    if (!model || crowd_api_effective_date(model) < 0) {
        fce_runtime_release(snapshot);
        return FALSE;
    }

    competition = InterlockedCompareExchange(
        &g_display_competition_id, 0, 0);
    if (competition <= 0 || competition > 65535)
        competition = InterlockedCompareExchange(
            &g_crowd_api_last_live_competition, 0, 0);
    *club_out = current_club;
    *competition_out = competition;
    fce_runtime_release(snapshot);
    if (InterlockedCompareExchange(&g_crowd_api_fallback_logged, 1, 0) == 0)
        append_loader_log("crowd_state_cached_fallback");
    return TRUE;
}

void *WINAPI Fifa16CareerAcquireSnapshot(void)
{
    FceLiveSnapshot *source = fce_runtime_acquire();
    const FceModel *model = fce_runtime_model(source);
    CrowdApiSnapshot *snapshot = NULL;
    int date = crowd_api_effective_date(model);
    if (model && date > 0) {
        snapshot = (CrowdApiSnapshot *)calloc(1, sizeof(*snapshot));
        if (snapshot) {
            snapshot->source = source;
            snapshot->model = *model;
            /* FCE's own date is absent in this career. CalendarManager's
             * verified TODAY value is already used by the matching card.
             * Override only the exported, shallow model view; the shared
             * FCE snapshot and its fixture/stat buffers stay unchanged. */
            snapshot->model.date = date;
        }
    }
    if (!snapshot)
        fce_runtime_release(source);
    log_crowd_api_snapshot("acquire",
        InterlockedCompareExchange(&g_user_club_id, 0, 0),
        InterlockedCompareExchange(&g_display_competition_id, 0, 0),
        snapshot ? &snapshot->model : NULL);
    return snapshot;
}

/* Match scene callbacks may run without the menu registry service or a career
 * date. Retain only the already-owned snapshot; never call the live registry
 * from those callbacks. The existing crowd-facing acquisition stays intact. */
void *WINAPI Fifa16CareerAcquireCachedSnapshot(void)
{
    FceLiveSnapshot *source = fce_runtime_cached_acquire();
    const FceModel *model = fce_runtime_model(source);
    CrowdApiSnapshot *snapshot = NULL;
    if (model && model->nodes && model->node_count > 0) {
        snapshot = (CrowdApiSnapshot *)calloc(1, sizeof(*snapshot));
        if (snapshot) {
            snapshot->source = source;
            snapshot->model = *model;
        }
    }
    if (!snapshot) fce_runtime_release(source);
    return snapshot;
}

const FceModel *WINAPI Fifa16CareerGetSnapshotModel(const void *snapshot)
{
    const FceModel *model = snapshot
        ? &((const CrowdApiSnapshot *)snapshot)->model : NULL;
    log_crowd_api_snapshot("model",
        InterlockedCompareExchange(&g_user_club_id, 0, 0),
        InterlockedCompareExchange(&g_display_competition_id, 0, 0), model);
    return model;
}

unsigned long WINAPI Fifa16CareerGetSnapshotGeneration(const void *snapshot)
{
    return snapshot ? fce_runtime_generation(
        ((const CrowdApiSnapshot *)snapshot)->source) : 0;
}

void WINAPI Fifa16CareerReleaseSnapshot(void *snapshot)
{
    CrowdApiSnapshot *copy = (CrowdApiSnapshot *)snapshot;
    if (!copy) return;
    fce_runtime_release(copy->source);
    free(copy);
}


#include "career_ui_jobs.inc"

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if(reason == DLL_PROCESS_ATTACH) {
        HANDLE worker;
        g_self=instance; DisableThreadLibraryCalls(instance);
        initialize_paths(); fce_runtime_log_dir(g_mod_dir);
        fce_runtime_set_ready_callback(refresh_initial_competition_provider);
        fce_runtime_set_ui_tick_callback(career_ui_jobs_tick);
        worker=CreateThread(NULL,0,patch_standings_provider,NULL,0,NULL);
        if(worker) CloseHandle(worker);
        worker=CreateThread(NULL,0,start_optional_mod_host,NULL,0,NULL);
        if(worker) CloseHandle(worker);
    }
    return TRUE;
}
