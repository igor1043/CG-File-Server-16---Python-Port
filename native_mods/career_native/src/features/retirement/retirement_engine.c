#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retirement_engine.h"
#include "../../platform/mod_paths.h"

#define RETIREMENT_SIGNATURE "DB\0\x08\0\0\0\0"
#define RETIREMENT_SIGNATURE_SIZE 8U
#define RETIREMENT_CRC_OFFSET 0x84U
#define RETIREMENT_CRC_START 0xA0U
#define RETIREMENT_TABLE_CRC_SENTINEL 0xCDCDCDCDU
#define RETIREMENT_MAX_SAVE_SIZE (64ULL * 1024ULL * 1024ULL)
#define RETIREMENT_MAX_TABLES 4096U
#define RETIREMENT_MAX_RECORD_SIZE 4096U
#define RETIREMENT_CAREER_DATE_LOW 20080101U
#define RETIREMENT_WINDOW_DAY_LOW 101U
#define RETIREMENT_TRANSFER_BUDGET_MAX 2147483520U

typedef struct RetirementField {
    uint32_t bit_offset;
    uint32_t bit_depth;
    int found;
} RetirementField;

typedef struct RetirementTable {
    SIZE_T records_offset;
    SIZE_T table_crc_offset;
    SIZE_T table_crc_start;
    uint32_t record_size;
    uint16_t record_count;
    uint8_t field_count;
    RetirementField player_id;
    RetirementField birthdate;
    RetirementField is_retiring;
    RetirementField transfer_budget;
} RetirementTable;

typedef struct RetirementCalendar {
    SIZE_T records_offset;
    uint32_t record_size;
    uint16_t record_count;
    uint8_t field_count;
    RetirementField current_date;
    RetirementField transfer_window_end1;
    RetirementField transfer_window_end2;
} RetirementCalendar;

static SRWLOCK g_retirement_lock = SRWLOCK_INIT;
static HANDLE g_retirement_event;
static HANDLE g_retirement_thread;
static char g_retirement_mod_dir[MAX_PATH];
static char g_retirement_pending_path[1024];
static char g_retirement_requested_mode[64];
static ULONGLONG g_retirement_request_deadline_tick;
/* One retirement action is allowed per visit to a retirement card flow.  The
 * latch is released only when the Career Hub NAV is loaded again, which keeps
 * repeated NAV/file opens and autosaves from rearming the same action. */
static int g_retirement_card_flow_latched;
static volatile LONG g_retirement_running;

static void retirement_log_event(const char *event, const char *path);
static int retirement_take_requested_mode(char *mode, size_t capacity);
static int retirement_peek_requested_mode(char *mode, size_t capacity);
static uint32_t retirement_fifa_crc32(const unsigned char *data, SIZE_T size);

#define RETIREMENT_WATCH_CAPACITY 64U

typedef struct RetirementWatchEntry {
    char path[1024];
    unsigned long long last_signature;
    unsigned long long pending_signature;
    ULONGLONG pending_since;
    int deferred_worker_started;
    int initialized;
} RetirementWatchEntry;

static RetirementWatchEntry g_retirement_watch[RETIREMENT_WATCH_CAPACITY];
static char g_retirement_save_root[MAX_PATH];
static int g_retirement_save_root_ready;
static ULONGLONG g_retirement_watch_start_filetime;
static char g_retirement_deferred_paths[RETIREMENT_WATCH_CAPACITY][1024];

#define RETIREMENT_FEEDBACK_SHOW (WM_APP + 0x164)
#define RETIREMENT_FEEDBACK_RESULT 0x16401U
#define RETIREMENT_FEEDBACK_HIDE_TIMER 1U
#define RETIREMENT_FEEDBACK_WIDTH 780
#define RETIREMENT_FEEDBACK_HEIGHT 176
#define RETIREMENT_FEEDBACK_DURATION_MS 5000U
#define RETIREMENT_CARD_REQUEST_COOLDOWN_MS 500ULL
#define RETIREMENT_CARD_REQUEST_WINDOW_MS 15000ULL
/* Kept only for the legacy input helper below.  The helper is no longer
 * started; retirement requests now come exclusively from the two NAV flows. */
#define RETIREMENT_CARD_MARKER_X0 1790L
#define RETIREMENT_CARD_MARKER_X1 1798L
#define RETIREMENT_CARD_MARKER_X2 1806L
#define RETIREMENT_CARD_MARKER_Y 472L
#define RETIREMENT_CARD_MARKER_TOLERANCE 48
#define RETIREMENT_CARD_SESSION_RELEASE_MS 1000ULL

static SRWLOCK g_retirement_feedback_lock = SRWLOCK_INIT;
static HANDLE g_retirement_feedback_ready;
static HWND g_retirement_feedback_window;
static char g_retirement_feedback_text[512];
static int g_retirement_feedback_persistent;

static void retirement_feedback_start(void);

static uint16_t retirement_u16(const unsigned char *p)
{
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t retirement_u32(const unsigned char *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8)
        | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void retirement_put_u32(unsigned char *p, uint32_t value)
{
    p[0] = (unsigned char)value;
    p[1] = (unsigned char)(value >> 8);
    p[2] = (unsigned char)(value >> 16);
    p[3] = (unsigned char)(value >> 24);
}

static int retirement_name_is(const unsigned char *p, const char *name)
{
    return p[0] == (unsigned char)name[0] && p[1] == (unsigned char)name[1]
        && p[2] == (unsigned char)name[2] && p[3] == (unsigned char)name[3];
}

static int retirement_range_valid(SIZE_T offset, SIZE_T length, SIZE_T size)
{
    return offset <= size && length <= size - offset;
}

static uint32_t retirement_read_bits(const unsigned char *data,
    SIZE_T record_start, const RetirementField *field, uint32_t record_size)
{
    SIZE_T bit_base;
    uint32_t value = 0;
    uint32_t i;
    if (!field->found || !field->bit_depth || field->bit_depth > 32U
        || field->bit_offset > record_size * 8U
        || field->bit_depth > record_size * 8U - field->bit_offset)
        return 0;
    bit_base = record_start * 8U + field->bit_offset;
    for (i = 0; i < field->bit_depth; ++i) {
        SIZE_T absolute = bit_base + i;
        if ((data[absolute >> 3] >> (absolute & 7U)) & 1U)
            value |= 1U << i;
    }
    return value;
}

static int retirement_write_bits(unsigned char *data, SIZE_T record_start,
    const RetirementField *field, uint32_t record_size, uint32_t value)
{
    SIZE_T bit_base;
    uint32_t i;
    if (!field->found || !field->bit_depth || field->bit_depth > 32U
        || field->bit_offset > record_size * 8U
        || field->bit_depth > record_size * 8U - field->bit_offset
        || (field->bit_depth < 32U && value >= (1U << field->bit_depth)))
        return 0;
    bit_base = record_start * 8U + field->bit_offset;
    for (i = 0; i < field->bit_depth; ++i) {
        SIZE_T absolute = bit_base + i;
        unsigned char *byte = &data[absolute >> 3];
        unsigned char mask = (unsigned char)(1U << (absolute & 7U));
        if ((value >> i) & 1U) *byte |= mask;
        else *byte &= (unsigned char)~mask;
    }
    return 1;
}

static int retirement_find_field(const unsigned char *data,
    SIZE_T table_header, uint8_t field_count, uint32_t record_size,
    const char *name, RetirementField *field)
{
    uint32_t index;
    uint32_t total_bits = record_size * 8U;
    for (index = 0; index < field_count; ++index) {
        const unsigned char *descriptor = data + table_header + 36U
            + (SIZE_T)index * 16U;
        uint32_t storage_type = retirement_u32(descriptor);
        uint32_t offset = retirement_u32(descriptor + 4U);
        uint32_t depth = retirement_u32(descriptor + 12U);
        if (storage_type != 3U || !depth || depth > 32U
            || offset > total_bits || depth > total_bits - offset
            || !retirement_name_is(descriptor + 8U, name))
            continue;
        field->bit_offset = offset;
        field->bit_depth = depth;
        field->found = 1;
        return 1;
    }
    return 0;
}

static int retirement_find_tables(const unsigned char *data, SIZE_T size,
    RetirementTable *players, RetirementCalendar *calendar,
    RetirementTable *manager_pref)
{
    SIZE_T cursor = 0;
    int players_found = 0;
    int calendar_found = 0;
    int manager_pref_found = 0;
    if (players) memset(players, 0, sizeof(*players));
    if (calendar) memset(calendar, 0, sizeof(*calendar));
    if (manager_pref) memset(manager_pref, 0, sizeof(*manager_pref));
    while (cursor + RETIREMENT_SIGNATURE_SIZE <= size) {
        SIZE_T db_offset;
        uint32_t db_size;
        uint32_t table_count;
        uint32_t table_index;
        const unsigned char *db;
        SIZE_T directory_end;
        SIZE_T table_data_offset;
        db_offset = cursor;
        while (db_offset + RETIREMENT_SIGNATURE_SIZE <= size
            && memcmp(data + db_offset, RETIREMENT_SIGNATURE,
                RETIREMENT_SIGNATURE_SIZE) != 0)
            ++db_offset;
        if (db_offset + 24U > size) break;
        db = data + db_offset;
        db_size = retirement_u32(db + 8U);
        table_count = retirement_u32(db + 16U);
        if (db_size < 24U || db_size > size - db_offset
            || table_count == 0U || table_count > RETIREMENT_MAX_TABLES)
            break;
        directory_end = 0x18U + (SIZE_T)table_count * 8U;
        table_data_offset = directory_end + 4U;
        if (table_data_offset > db_size) break;
        for (table_index = 0; table_index < table_count; ++table_index) {
            const unsigned char *entry = db + 0x18U
                + (SIZE_T)table_index * 8U;
            uint32_t relative = retirement_u32(entry + 4U);
            SIZE_T table_offset;
            uint32_t record_size;
            uint16_t record_count;
            uint8_t field_count;
            if ((SIZE_T)relative > db_size - table_data_offset)
                continue;
            table_offset = table_data_offset + relative;
            if (!retirement_range_valid(table_offset, 36U, db_size))
                continue;
            record_size = retirement_u32(db + table_offset + 4U);
            record_count = retirement_u16(db + table_offset + 18U);
            field_count = db[table_offset + 24U];
            if (!record_size || record_size > RETIREMENT_MAX_RECORD_SIZE
                || !field_count || field_count > 128U)
                continue;
            if ((SIZE_T)field_count > (SIZE_MAX - table_offset - 36U) / 16U)
                continue;
            if (!retirement_range_valid(table_offset + 36U,
                    (SIZE_T)field_count * 16U, db_size))
                continue;
            {
                SIZE_T records_offset = table_offset + 36U
                    + (SIZE_T)field_count * 16U;
                SIZE_T records_end;
                SIZE_T padded_compressed;
                uint32_t compressed_length = retirement_u32(
                    db + table_offset + 12U);
                if ((SIZE_T)record_count >
                        (SIZE_MAX - records_offset) / record_size
                    || !retirement_range_valid(records_offset,
                        (SIZE_T)record_count * record_size, db_size))
                    continue;
                records_end = records_offset + (SIZE_T)record_count * record_size;
                padded_compressed = compressed_length
                    ? ((SIZE_T)compressed_length + 7U) & ~(SIZE_T)7U : 0U;
                if (records_end > db_size
                    || padded_compressed > db_size - records_end
                    || db_size - records_end - padded_compressed < 4U)
                    continue;
                if (!players_found && retirement_name_is(entry, "CZUM")) {
                    memset(players, 0, sizeof(*players));
                    players->records_offset = db_offset + records_offset;
                    players->table_crc_start = db_offset + table_offset + 36U;
                    players->table_crc_offset = db_offset + records_end
                        + padded_compressed;
                    players->record_size = record_size;
                    players->record_count = record_count;
                    players->field_count = field_count;
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "ykFq", &players->player_id);
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "WVIU", &players->birthdate);
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "kvuF", &players->is_retiring);
                    if (players->birthdate.found &&
                        players->is_retiring.found)
                        players_found = 1;
                }
                if (!calendar_found && retirement_name_is(entry, "GJUr")) {
                    memset(calendar, 0, sizeof(*calendar));
                    calendar->records_offset = db_offset + records_offset;
                    calendar->record_size = record_size;
                    calendar->record_count = record_count;
                    calendar->field_count = field_count;
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "aLZZ", &calendar->current_date);
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "PpdA", &calendar->transfer_window_end1);
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "igYC", &calendar->transfer_window_end2);
                    if (calendar->current_date.found)
                        calendar_found = 1;
                }
                if (manager_pref && !manager_pref_found
                    && retirement_name_is(entry, "dqXv")) {
                    memset(manager_pref, 0, sizeof(*manager_pref));
                    manager_pref->records_offset = db_offset + records_offset;
                    manager_pref->table_crc_start = db_offset + table_offset + 36U;
                    manager_pref->table_crc_offset = db_offset + records_end
                        + padded_compressed;
                    manager_pref->record_size = record_size;
                    manager_pref->record_count = record_count;
                    manager_pref->field_count = field_count;
                    retirement_find_field(db, table_offset, field_count,
                        record_size, "SnDr", &manager_pref->transfer_budget);
                    if (manager_pref->transfer_budget.found)
                        manager_pref_found = 1;
                }
            }
        }
        cursor = db_offset + db_size;
        if (players_found && calendar_found
            && (!manager_pref || manager_pref_found)) break;
    }
    /* Callers that modify players still validate player_id explicitly.  A
     * read-only UI query may legitimately need only the calendar table. */
    return players_found || calendar_found || manager_pref_found;
}

static unsigned int retirement_transfer_budget_amount(const char *mode)
{
    if (mode && _stricmp(mode, "add_transfer_budget_1m") == 0)
        return 10000000U;
    if (mode && _stricmp(mode, "add_transfer_budget_3m") == 0)
        return 100000000U;
    return 0U;
}

static int retirement_recalculate_table_crc(unsigned char *data, SIZE_T size,
    const RetirementTable *table)
{
    uint32_t stored;
    if (!data || !table || table->table_crc_offset > size
        || table->table_crc_start > table->table_crc_offset
        || table->table_crc_offset - table->table_crc_start < 4U)
        return 0;
    stored = retirement_u32(data + table->table_crc_offset);
    if (stored != RETIREMENT_TABLE_CRC_SENTINEL)
        retirement_put_u32(data + table->table_crc_offset,
            retirement_fifa_crc32(data + table->table_crc_start,
                table->table_crc_offset - table->table_crc_start));
    return 1;
}

/* Gregorian day conversion, relative to 1970-01-01. */
static int64_t retirement_days_from_civil(int year, unsigned month,
    unsigned day)
{
    int adjusted_year = year - (month <= 2U);
    int era = adjusted_year >= 0 ? adjusted_year / 400 : (adjusted_year - 399) / 400;
    unsigned year_of_era = (unsigned)(adjusted_year - era * 400);
    int month_adjusted = (int)month + (month > 2U ? -3 : 9);
    unsigned day_of_year = (153U * (unsigned)month_adjusted + 2U) / 5U
        + day - 1U;
    unsigned day_of_era = year_of_era * 365U + year_of_era / 4U
        - year_of_era / 100U + day_of_year;
    return (int64_t)era * 146097 + (int64_t)day_of_era - 719468;
}

static void retirement_civil_from_days(int64_t days, int *year,
    unsigned *month, unsigned *day)
{
    int64_t z = days + 719468;
    int64_t era = z >= 0 ? z / 146097 : (z - 146096) / 146097;
    unsigned day_of_era = (unsigned)(z - era * 146097);
    unsigned day_of_year = (day_of_era - day_of_era / 1460U
        + day_of_era / 36524U - day_of_era / 146096U) / 365U;
    int adjusted_year = (int)day_of_year + (int)era * 400;
    unsigned day_of_year2 = day_of_era - (365U * day_of_year
        + day_of_year / 4U - day_of_year / 100U);
    unsigned month_number = (5U * day_of_year2 + 2U) / 153U;
    *day = day_of_year2 - (153U * month_number + 2U) / 5U + 1U;
    {
        int month_value = (int)month_number + (month_number < 10U ? 3 : -9);
        *month = (unsigned)month_value;
    }
    *year = adjusted_year + (*month <= 2U);
}

static int retirement_parse_date(int yyyymmdd, int *year, unsigned *month,
    unsigned *day)
{
    int y = yyyymmdd / 10000;
    unsigned m = (unsigned)((yyyymmdd / 100) % 100);
    unsigned d = (unsigned)(yyyymmdd % 100);
    int64_t normalized;
    if (y < 1500 || y > 2500 || m < 1U || m > 12U || d < 1U || d > 31U)
        return 0;
    normalized = retirement_days_from_civil(y, m, d);
    retirement_civil_from_days(normalized, &y, &m, &d);
    if (y != yyyymmdd / 10000 || m != (unsigned)((yyyymmdd / 100) % 100)
        || d != (unsigned)(yyyymmdd % 100))
        return 0;
    *year = y; *month = m; *day = d;
    return 1;
}

/* transferwindowend1/2 are stored as the DBOFIELDTYPE_SHORT delta from
 * the schema low value 101. They intentionally have no year: a career
 * calendar defines recurring MMDD closing days. */
static int retirement_window_day_valid(uint32_t raw, unsigned int *mmdd)
{
    unsigned int value = raw + RETIREMENT_WINDOW_DAY_LOW;
    unsigned int month = value / 100U;
    unsigned int day = value % 100U;
    static const unsigned char days[] =
        { 0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    if (month < 1U || month > 12U || day < 1U || day > days[month])
        return 0;
    if (mmdd)
        *mmdd = value;
    return 1;
}

static int retirement_days_in_month(int year, unsigned month)
{
    int64_t first = retirement_days_from_civil(year, month, 1U);
    unsigned next_month = month == 12U ? 1U : month + 1U;
    int next_year = month == 12U ? year + 1 : year;
    return (int)(retirement_days_from_civil(next_year, next_month, 1U) - first);
}

static uint32_t retirement_fifa_date_raw(int year, unsigned month,
    unsigned day)
{
    int64_t epoch = retirement_days_from_civil(1582, 10U, 14U);
    int64_t current = retirement_days_from_civil(year, month, day);
    return current >= epoch ? (uint32_t)(current - epoch) : 0U;
}

static uint32_t retirement_crc32(const unsigned char *data, SIZE_T size)
{
    static uint32_t table[256];
    static LONG initialized;
    uint32_t crc = 0xFFFFFFFFU;
    SIZE_T index;
    if (InterlockedCompareExchange(&initialized, 1, 0) == 0) {
        uint32_t i;
        for (i = 0; i < 256U; ++i) {
            uint32_t value = i;
            uint32_t bit;
            for (bit = 0; bit < 8U; ++bit)
                value = (value >> 1) ^ (0xEDB88320U & (uint32_t)-(int)(value & 1U));
            table[i] = value;
        }
        InterlockedExchange(&initialized, 2);
    } else {
        while (InterlockedCompareExchange(&initialized, 0, 0) != 2)
            Sleep(0);
    }
    for (index = 0; index < size; ++index)
        crc = table[(crc ^ data[index]) & 0xFFU] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFU;
}

static uint32_t retirement_fifa_crc32(const unsigned char *data, SIZE_T size)
{
    uint32_t crc = 0xFFFFFFFFU;
    SIZE_T index;
    for (index = 0; index < size; ++index) {
        uint32_t bit;
        crc ^= (uint32_t)data[index] << 24;
        for (bit = 0; bit < 8U; ++bit)
            crc = (crc & 0x80000000U)
                ? (crc << 1) ^ 0x04C11DB7U : crc << 1;
    }
    return crc;
}

static void retirement_result_clear(RetirementApplyResult *result)
{
    if (result) memset(result, 0, sizeof(*result));
}

static void retirement_result_message(RetirementApplyResult *result,
    int status, const char *message)
{
    if (!result) return;
    result->status = status;
    lstrcpynA(result->message, message ? message : "", sizeof(result->message));
}

static int retirement_read_file(const char *path, unsigned char **data,
    SIZE_T *size)
{
    HANDLE file;
    LARGE_INTEGER length;
    SIZE_T offset = 0;
    *data = NULL; *size = 0;
    file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE || !GetFileSizeEx(file, &length)
        || length.QuadPart <= 0 || (uint64_t)length.QuadPart > RETIREMENT_MAX_SAVE_SIZE) {
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
        return 0;
    }
    *size = (SIZE_T)length.QuadPart;
    *data = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, *size);
    if (!*data) { CloseHandle(file); return 0; }
    while (offset < *size) {
        DWORD request = (DWORD)((*size - offset) > 0x100000U
            ? 0x100000U : (*size - offset));
        DWORD got = 0;
        if (!ReadFile(file, *data + offset, request, &got, NULL) || !got) {
            HeapFree(GetProcessHeap(), 0, *data); *data = NULL; *size = 0;
            CloseHandle(file); return 0;
        }
        offset += got;
    }
    CloseHandle(file);
    return 1;
}

/* Read-only calendar query shared by UI features. This deliberately uses
 * the same table/CRC validation as the retirement writer but never changes
 * the save or creates a backup. */
int retirement_engine_get_transfer_window_ends(const char *data_path,
    unsigned int *first_mmdd, unsigned int *second_mmdd)
{
    unsigned char *data = NULL;
    SIZE_T size = 0;
    RetirementTable players;
    RetirementCalendar calendar;
    unsigned int first = 0, second = 0;
    SIZE_T start;

    if (first_mmdd) *first_mmdd = 0;
    if (second_mmdd) *second_mmdd = 0;
    if (!data_path || !*data_path || !retirement_read_file(data_path, &data, &size))
        return 0;
    if (size < RETIREMENT_CRC_START || size < RETIREMENT_CRC_OFFSET + 4U)
        goto done;
    if (!retirement_find_tables(data, size, &players, &calendar, NULL)
        || !calendar.record_count)
        goto done;
    start = calendar.records_offset;
    if (calendar.transfer_window_end1.found) {
        uint32_t raw = retirement_read_bits(data, start,
            &calendar.transfer_window_end1, calendar.record_size);
        (void)retirement_window_day_valid(raw, &first);
    }
    if (calendar.transfer_window_end2.found) {
        uint32_t raw = retirement_read_bits(data, start,
            &calendar.transfer_window_end2, calendar.record_size);
        (void)retirement_window_day_valid(raw, &second);
    }
    if (!first && !second)
        goto done;
    if (first_mmdd) *first_mmdd = first;
    if (second_mmdd) *second_mmdd = second;
    HeapFree(GetProcessHeap(), 0, data);
    return 1;
done:
    HeapFree(GetProcessHeap(), 0, data);
    return 0;
}

static int retirement_write_atomic(const char *path, const unsigned char *data,
    SIZE_T size)
{
    char temporary[1200];
    HANDLE file;
    SIZE_T offset = 0;
    DWORD tick = GetTickCount();
    snprintf(temporary, sizeof(temporary), "%s.retirement_tmp_%lu_%lu",
        path, (unsigned long)GetCurrentProcessId(), (unsigned long)tick);
    file = CreateFileA(temporary, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    while (offset < size) {
        DWORD request = (DWORD)((size - offset) > 0x100000U
            ? 0x100000U : (size - offset));
        DWORD written = 0;
        if (!WriteFile(file, data + offset, request, &written, NULL)
            || !written) {
            CloseHandle(file); DeleteFileA(temporary); return 0;
        }
        offset += written;
    }
    if (!FlushFileBuffers(file)) {
        CloseHandle(file); DeleteFileA(temporary); return 0;
    }
    CloseHandle(file);
    if (!MoveFileExA(temporary, path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
        DeleteFileA(temporary); return 0;
    }
    return 1;
}

static int retirement_copy_backup(const char *source, const char *suffix,
    char *destination, size_t capacity)
{
    SYSTEMTIME now;
    int attempt;
    GetLocalTime(&now);
    for (attempt = 0; attempt < 100; ++attempt) {
        snprintf(destination, capacity, "%s.retirement_backup_%04u%02u%02u_%02u%02u%02u_%02d%s",
            source, now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute,
            now.wSecond, attempt, suffix ? suffix : "");
        if (CopyFileA(source, destination, TRUE)) return 1;
        if (GetLastError() != ERROR_FILE_EXISTS) return 0;
    }
    return 0;
}

static int retirement_validate_written_file(const char *data_path,
    const char *mode, RetirementApplyResult *result)
{
    unsigned char *data = NULL;
    SIZE_T size = 0;
    RetirementTable players;
    RetirementTable manager_pref;
    RetirementCalendar calendar;
    uint32_t stored_crc;
    uint32_t calculated_crc;
    unsigned int row;
    unsigned int budget_amount = retirement_transfer_budget_amount(mode);
    int rejuvenate = mode && (_stricmp(mode, "remove_and_rejuvenate") == 0
        || _stricmp(mode, "rejuvenate") == 0);
    (void)rejuvenate;

    if (!retirement_read_file(data_path, &data, &size)) return 0;
    if (size < RETIREMENT_CRC_START
        || size < RETIREMENT_CRC_OFFSET + 4U) {
        HeapFree(GetProcessHeap(), 0, data);
        return 0;
    }
    stored_crc = retirement_u32(data + RETIREMENT_CRC_OFFSET);
    calculated_crc = retirement_crc32(data + RETIREMENT_CRC_START,
        size - RETIREMENT_CRC_START);
    if (stored_crc != calculated_crc
        || !retirement_find_tables(data, size, &players, &calendar,
            &manager_pref)) {
        HeapFree(GetProcessHeap(), 0, data);
        return 0;
    }
    if (budget_amount) {
        int valid = result && manager_pref.transfer_budget.found
            && manager_pref.record_count == 1U
            && retirement_read_bits(data, manager_pref.records_offset,
                &manager_pref.transfer_budget, manager_pref.record_size)
                == result->transfer_budget_after;
        HeapFree(GetProcessHeap(), 0, data);
        return valid;
    }
    if (!players.player_id.found || !players.is_retiring.found) {
        HeapFree(GetProcessHeap(), 0, data);
        return 0;
    }
    for (row = 0; row < players.record_count; ++row) {
        SIZE_T start = players.records_offset
            + (SIZE_T)row * players.record_size;
        if (data[start + players.record_size - 1U] & 0x80U) continue;
        if (retirement_read_bits(data, start, &players.is_retiring,
                players.record_size) != 0U) {
            HeapFree(GetProcessHeap(), 0, data);
            return 0;
        }
    }
    if (result) result->crc_after = stored_crc;
    HeapFree(GetProcessHeap(), 0, data);
    return 1;
}

static int retirement_restore_backup(const char *data_path,
    const char *backup_path)
{
    unsigned char *backup = NULL;
    SIZE_T size = 0;
    int ok;
    if (!backup_path || !*backup_path
        || !retirement_read_file(backup_path, &backup, &size))
        return 0;
    ok = retirement_write_atomic(data_path, backup, size);
    HeapFree(GetProcessHeap(), 0, backup);
    return ok;
}

int retirement_engine_local_logging_enabled(const char *mod_dir)
{
    char path[MAX_PATH];
    char line[256];
    FILE *file;
    int enabled = 0;
    if (!mod_dir || !*mod_dir) return 0;
    career_path_read(path, sizeof(path), mod_dir, "config",
        "career_retirement_background.local.ini");
    file = fopen(path, "rb");
    if (!file) return 0;
    while (fgets(line, sizeof(line), file)) {
        char key[64];
        char value[160];
        if (sscanf(line, " %63[^=]= %159[^\r\n]", key, value) != 2)
            continue;
        if (_stricmp(key, "logging") == 0)
            enabled = atoi(value) != 0;
    }
    fclose(file);
    return enabled;
}

static int retirement_get_config(const char *mod_dir, int *enabled,
    char *mode, size_t mode_capacity, int *target_age, unsigned *quiet_ms,
    int *defer_until_game_exit)
{
    char path[MAX_PATH];
    char line[256];
    FILE *file;
    *enabled = 0; *target_age = 18; *quiet_ms = 2500U;
    /* The worker waits until DATA and INDEX are stable and exclusively open.
     * Closing the career releases the save while FIFA can remain at the menu. */
    if (defer_until_game_exit) *defer_until_game_exit = 0;
    lstrcpynA(mode, "remove_retirement", (int)mode_capacity);
    career_path_read(path, sizeof(path), mod_dir, "config", "career_retirement_background.ini");
    file = fopen(path, "rb");
    if (!file) return 0;
    while (fgets(line, sizeof(line), file)) {
        char key[64], value[160];
        if (sscanf(line, " %63[^=]= %159[^\r\n]", key, value) != 2)
            continue;
        if (_stricmp(key, "enabled") == 0) *enabled = atoi(value) != 0;
        else if (_stricmp(key, "mode") == 0)
            lstrcpynA(mode, value, (int)mode_capacity);
        else if (_stricmp(key, "target_age") == 0) *target_age = atoi(value);
        else if (_stricmp(key, "quiet_ms") == 0) *quiet_ms = (unsigned)atoi(value);
        else if (_stricmp(key, "defer_until_game_exit") == 0
            && defer_until_game_exit)
            *defer_until_game_exit = atoi(value) != 0;
    }
    fclose(file);
    if (*target_age < 1 || *target_age > 80) *target_age = 18;
    if (*quiet_ms < 1000U || *quiet_ms > 10000U) *quiet_ms = 2500U;
    return 1;
}

int retirement_engine_apply_file(const char *data_path, const char *mode,
    int target_age, RetirementApplyResult *result)
{
    unsigned char *data = NULL;
    SIZE_T size = 0;
    RetirementTable players;
    RetirementTable manager_pref;
    RetirementCalendar calendar;
    uint32_t stored_crc;
    uint32_t calculated_crc;
    int current_year = 2026;
    unsigned current_month = 1U, current_day = 1U;
    int current_date_valid = 0;
    unsigned int budget_amount = retirement_transfer_budget_amount(mode);
    int rejuvenate = mode && (_stricmp(mode, "remove_and_rejuvenate") == 0
        || _stricmp(mode, "rejuvenate") == 0);
    unsigned int row;
    if (!result || !data_path || !*data_path) return 0;
    retirement_result_clear(result);
    if (!retirement_read_file(data_path, &data, &size)) {
        retirement_result_message(result, 10, "DATA nao pode ser lido"); return 0;
    }
    if (size < RETIREMENT_CRC_START || size < RETIREMENT_CRC_OFFSET + 4U) {
        retirement_result_message(result, 11, "DATA pequeno demais"); goto fail;
    }
    stored_crc = retirement_u32(data + RETIREMENT_CRC_OFFSET);
    calculated_crc = retirement_crc32(data + RETIREMENT_CRC_START,
        size - RETIREMENT_CRC_START);
    result->crc_before = stored_crc;
    if (stored_crc != calculated_crc) {
        retirement_result_message(result, 12, "CRC original invalido; nada foi alterado"); goto fail;
    }
    if (!retirement_find_tables(data, size, &players, &calendar,
            &manager_pref)) {
        retirement_result_message(result, 13, "Tabela CZUM/fields nao encontrados"); goto fail;
    }
    if (budget_amount) {
        uint32_t old_budget;
        uint32_t new_budget;
        SIZE_T start;
        if (!manager_pref.transfer_budget.found
            || manager_pref.record_count != 1U) {
            retirement_result_message(result, 24,
                "Tabela career_managerpref/transferbudget nao encontrada");
            goto fail;
        }
        start = manager_pref.records_offset;
        if (data[start + manager_pref.record_size - 1U] & 0x80U) {
            retirement_result_message(result, 24,
                "Registro career_managerpref invalido");
            goto fail;
        }
        old_budget = retirement_read_bits(data, start,
            &manager_pref.transfer_budget, manager_pref.record_size);
        if (old_budget > RETIREMENT_TRANSFER_BUDGET_MAX) {
            retirement_result_message(result, 24,
                "Orcamento de transferencias fora do intervalo seguro");
            goto fail;
        }
        new_budget = old_budget > RETIREMENT_TRANSFER_BUDGET_MAX - budget_amount
            ? RETIREMENT_TRANSFER_BUDGET_MAX : old_budget + budget_amount;
        result->transfer_budget_before = old_budget;
        result->transfer_budget_after = new_budget;
        result->transfer_budget_added = new_budget - old_budget;
        if (!result->transfer_budget_added) {
            result->crc_after = calculated_crc;
            retirement_result_message(result, 0,
                "Orcamento ja esta no limite maximo");
            HeapFree(GetProcessHeap(), 0, data);
            return 1;
        }
        if (!retirement_write_bits(data, start,
                &manager_pref.transfer_budget, manager_pref.record_size,
                new_budget)) {
            retirement_result_message(result, 24,
                "Falha ao atualizar transferbudget");
            goto fail;
        }
    } else {
        if (!players.player_id.found) {
            retirement_result_message(result, 13,
                "Tabela CZUM/fields nao encontrados"); goto fail;
        }
    }
    if (calendar.current_date.found && calendar.record_count > 0U) {
        SIZE_T start = calendar.records_offset;
        uint32_t raw = retirement_read_bits(data, start, &calendar.current_date,
            calendar.record_size);
        current_date_valid = retirement_parse_date(
            (int)(raw + RETIREMENT_CAREER_DATE_LOW), &current_year,
            &current_month, &current_day);
    }
    if (!budget_amount && rejuvenate
        && (!current_date_valid || target_age < 12 || target_age > 50)) {
        retirement_result_message(result, 19,
            !current_date_valid ? "Data da carreira nao encontrada; nada foi alterado"
                                : "Idade-alvo fora do intervalo seguro 12..50");
        goto fail;
    }
    for (row = 0; !budget_amount && row < players.record_count; ++row) {
        SIZE_T start = players.records_offset + (SIZE_T)row * players.record_size;
        if (data[start + players.record_size - 1U] & 0x80U)
            continue;
        result->players_seen++;
        uint32_t retiring = retirement_read_bits(data, start,
            &players.is_retiring, players.record_size);
        if (retiring != 1U) continue;
        result->players_retiring++;
        if (!retirement_write_bits(data, start, &players.is_retiring,
                players.record_size, 0U)) {
            retirement_result_message(result, 14, "Falha ao escrever isretiring"); goto fail;
        }
        if (rejuvenate) {
            uint32_t old_raw = retirement_read_bits(data, start,
                &players.birthdate, players.record_size);
            int old_year; unsigned old_month, old_day;
            uint32_t new_raw;
            int birth_year;
            unsigned birth_month, birth_day;
            {
                int64_t epoch = retirement_days_from_civil(1582, 10U, 14U);
                int64_t birth_days = epoch + old_raw;
                retirement_civil_from_days(birth_days, &old_year, &old_month, &old_day);
            }
            birth_year = current_year - target_age;
            if (current_month < old_month
                || (current_month == old_month && current_day < old_day))
                birth_year--;
            birth_month = old_month; birth_day = old_day;
            if (birth_day > (unsigned)retirement_days_in_month(birth_year, birth_month))
                birth_day = (unsigned)retirement_days_in_month(birth_year, birth_month);
            new_raw = retirement_fifa_date_raw(birth_year, birth_month, birth_day);
            if (!retirement_write_bits(data, start, &players.birthdate,
                    players.record_size, new_raw)) {
                retirement_result_message(result, 15, "Falha ao escrever birthdate"); goto fail;
            }
        }
        result->players_changed++;
    }
    if (!budget_amount && !result->players_changed) {
        result->crc_after = calculated_crc;
        retirement_result_message(result, 0, "Nenhum jogador marcado para aposentadoria");
        HeapFree(GetProcessHeap(), 0, data); return 1;
    }
    {
        char index_path[1200];
        char backup_index[1200];
        char backup_data[1200];
        char *slash;
        const RetirementTable *changed_table = budget_amount
            ? &manager_pref : &players;
        if (!retirement_recalculate_table_crc(data, size, changed_table)) {
            retirement_result_message(result, 25,
                "CRC da tabela alterada nao pode ser atualizado");
            goto fail;
        }
        retirement_put_u32(data + RETIREMENT_CRC_OFFSET,
            retirement_crc32(data + RETIREMENT_CRC_START,
                size - RETIREMENT_CRC_START));
        result->crc_after = retirement_u32(data + RETIREMENT_CRC_OFFSET);
        if (!retirement_copy_backup(data_path, "", backup_data, sizeof(backup_data))) {
            retirement_result_message(result, 16, "Backup do DATA falhou; nada foi alterado"); goto fail;
        }
        lstrcpynA(result->backup_data, backup_data, sizeof(result->backup_data));
        lstrcpynA(index_path, data_path, sizeof(index_path));
        slash = strrchr(index_path, '\\');
        if (slash) { lstrcpyA(slash + 1, "INDEX"); }
        if (GetFileAttributesA(index_path) != INVALID_FILE_ATTRIBUTES) {
            if (!retirement_copy_backup(index_path, "", backup_index, sizeof(backup_index))) {
                retirement_result_message(result, 17, "Backup do INDEX falhou; DATA nao foi alterado"); goto fail;
            }
            lstrcpynA(result->backup_index, backup_index, sizeof(result->backup_index));
        }
        if (!retirement_write_atomic(data_path, data, size)) {
            retirement_result_message(result, 18, "DATA bloqueado; backup preservado e nada foi alterado"); goto fail;
        }
        if (!retirement_validate_written_file(data_path, mode, result)) {
            int restored = retirement_restore_backup(data_path,
                result->backup_data);
            retirement_result_message(result, restored ? 22 : 23,
                restored
                    ? "Validacao pos-escrita falhou; backup restaurado"
                    : "Validacao pos-escrita falhou; restaure o backup manualmente");
            goto fail;
        }
    }
    retirement_result_message(result, 1, budget_amount
        ? "Orcamento de transferencias atualizado com backup"
        : "Patch global concluido com backup");
    HeapFree(GetProcessHeap(), 0, data); return 1;
fail:
    HeapFree(GetProcessHeap(), 0, data);
    return 0;
}

int retirement_engine_apply_buffer(void *buffer, SIZE_T size,
    const char *mode, int target_age, RetirementApplyResult *result)
{
    unsigned char *data = (unsigned char *)buffer;
    RetirementTable players;
    RetirementCalendar calendar;
    uint32_t stored_crc;
    uint32_t calculated_crc;
    int current_year = 2026;
    unsigned current_month = 1U, current_day = 1U;
    int current_date_valid = 0;
    int rejuvenate = mode && (_stricmp(mode, "remove_and_rejuvenate") == 0
        || _stricmp(mode, "rejuvenate") == 0);
    unsigned int row;
    if (!result || !data || size < RETIREMENT_CRC_START
        || size < RETIREMENT_CRC_OFFSET + 4U)
        return 0;
    retirement_result_clear(result);
    stored_crc = retirement_u32(data + RETIREMENT_CRC_OFFSET);
    calculated_crc = retirement_crc32(data + RETIREMENT_CRC_START,
        size - RETIREMENT_CRC_START);
    result->crc_before = stored_crc;
    if (stored_crc != calculated_crc) {
        retirement_result_message(result, 12,
            "CRC original invalido; nada foi alterado");
        return 0;
    }
    if (!retirement_find_tables(data, size, &players, &calendar, NULL)
        || !players.player_id.found) {
        retirement_result_message(result, 13,
            "Tabela CZUM/fields nao encontrados");
        return 0;
    }
    if (calendar.current_date.found && calendar.record_count > 0U) {
        SIZE_T start = calendar.records_offset;
        uint32_t raw = retirement_read_bits(data, start, &calendar.current_date,
            calendar.record_size);
        current_date_valid = retirement_parse_date(
            (int)(raw + RETIREMENT_CAREER_DATE_LOW), &current_year,
            &current_month, &current_day);
    }
    if (rejuvenate && (!current_date_valid || target_age < 12 || target_age > 50)) {
        retirement_result_message(result, 19,
            !current_date_valid ? "Data da carreira nao encontrada; nada foi alterado"
                                : "Idade-alvo fora do intervalo seguro 12..50");
        return 0;
    }
    for (row = 0; row < players.record_count; ++row) {
        SIZE_T start = players.records_offset + (SIZE_T)row * players.record_size;
        uint32_t retiring;
        if (data[start + players.record_size - 1U] & 0x80U)
            continue;
        result->players_seen++;
        retiring = retirement_read_bits(data, start, &players.is_retiring,
            players.record_size);
        if (retiring != 1U) continue;
        result->players_retiring++;
        if (!retirement_write_bits(data, start, &players.is_retiring,
                players.record_size, 0U)) {
            retirement_result_message(result, 14,
                "Falha ao escrever isretiring");
            return 0;
        }
        if (rejuvenate) {
            uint32_t old_raw = retirement_read_bits(data, start,
                &players.birthdate, players.record_size);
            int old_year;
            unsigned old_month, old_day;
            uint32_t new_raw;
            int birth_year;
            unsigned birth_month, birth_day;
            {
                int64_t epoch = retirement_days_from_civil(1582, 10U, 14U);
                int64_t birth_days = epoch + old_raw;
                retirement_civil_from_days(birth_days, &old_year, &old_month,
                    &old_day);
            }
            birth_year = current_year - target_age;
            if (current_month < old_month
                || (current_month == old_month && current_day < old_day))
                birth_year--;
            birth_month = old_month;
            birth_day = old_day;
            if (birth_day > (unsigned)retirement_days_in_month(
                    birth_year, birth_month))
                birth_day = (unsigned)retirement_days_in_month(
                    birth_year, birth_month);
            new_raw = retirement_fifa_date_raw(birth_year, birth_month,
                birth_day);
            if (!retirement_write_bits(data, start, &players.birthdate,
                    players.record_size, new_raw)) {
                retirement_result_message(result, 15,
                    "Falha ao escrever birthdate");
                return 0;
            }
        }
        result->players_changed++;
    }
    if (!result->players_changed) {
        result->crc_after = calculated_crc;
        retirement_result_message(result, 0,
            "Nenhum jogador marcado para aposentadoria");
        return 1;
    }
    if (players.table_crc_offset <= size
        && players.table_crc_start <= players.table_crc_offset
        && players.table_crc_offset - players.table_crc_start >= 4U) {
        uint32_t table_crc = retirement_u32(data + players.table_crc_offset);
        if (table_crc != RETIREMENT_TABLE_CRC_SENTINEL)
            retirement_put_u32(data + players.table_crc_offset,
                retirement_fifa_crc32(data + players.table_crc_start,
                    players.table_crc_offset - players.table_crc_start));
    }
    retirement_put_u32(data + RETIREMENT_CRC_OFFSET,
        retirement_crc32(data + RETIREMENT_CRC_START,
            size - RETIREMENT_CRC_START));
    result->crc_after = retirement_u32(data + RETIREMENT_CRC_OFFSET);
    retirement_result_message(result, 1,
        "Patch em memoria pronto para salvar");
    return 1;
}

int retirement_engine_apply_selection(void *buffer, SIZE_T size,
    const unsigned int *player_ids, SIZE_T count, int reset_age, int target_age,
    RetirementApplyResult *result)
{
    unsigned char *original = (unsigned char *)buffer, *copy = NULL, *allowed = NULL;
    unsigned char *seen = NULL;
    RetirementTable players;
    RetirementCalendar calendar;
    unsigned int row;
    SIZE_T i, header;
    int year = 0;
    unsigned month = 0, day = 0;
    uint32_t crc;
    int ok = 0;
    const char *stage = "Selecao/schema/CRC divergente; original preservado";
    if (!result) return 0;
    retirement_result_clear(result);
    retirement_result_message(result, 30, "Selecao invalida; original preservado");
    if (!original || size < RETIREMENT_CRC_START + 24U || size > RETIREMENT_MAX_SAVE_SIZE
        || count > 60000U || (count && !player_ids) || (!count && player_ids)
        || (reset_age != 0 && reset_age != 1)
        || (reset_age && (target_age < 12 || target_age > 50))) return 0;
    for (i = 0; i < count; ++i) {
        SIZE_T j;
        /* Career-generated players use IDs 350000+ despite the base XML's
         * older rangehigh=300000. The native field is an unsigned 19-bit ID. */
        if (!player_ids[i] || player_ids[i] >= (1U << 19U)) return 0;
        for (j = 0; j < i; ++j) if (player_ids[i] == player_ids[j]) return 0;
    }
    memset(&players, 0, sizeof(players)); memset(&calendar, 0, sizeof(calendar));
    crc = retirement_crc32(original + RETIREMENT_CRC_START, size - RETIREMENT_CRC_START);
    if (retirement_u32(original + RETIREMENT_CRC_OFFSET) != crc
        || !retirement_find_tables(original, size, &players, &calendar, NULL)
        || !players.player_id.found || !players.is_retiring.found || !players.birthdate.found
        || players.player_id.bit_depth != 19U || players.birthdate.bit_depth != 20U
        || players.is_retiring.bit_depth != 1U || !calendar.current_date.found
        || calendar.record_count != 1U) goto done;
    header = players.records_offset - 36U - (SIZE_T)players.field_count * 16U;
    stage = "CZUM comprimido/checksum divergente; original preservado";
    /* Unknown compressed blocks must never be rewritten by the selection UI. */
    if (retirement_u32(original + header + 12U) != 0U
        || !retirement_range_valid(players.table_crc_offset, 4U, size)
        || players.table_crc_start > players.table_crc_offset) goto done;
    if (retirement_u32(original + players.table_crc_offset) != RETIREMENT_TABLE_CRC_SENTINEL
        && retirement_u32(original + players.table_crc_offset) !=
            retirement_fifa_crc32(original + players.table_crc_start,
                players.table_crc_offset - players.table_crc_start)) goto done;
    for (i = 0; i < players.field_count; ++i) {
        const unsigned char *descriptor = original + header + 36U + i * 16U;
        uint32_t at = retirement_u32(descriptor + 4U), depth = retirement_u32(descriptor + 12U);
        const RetirementField *fields[2] = { &players.is_retiring, &players.birthdate };
        unsigned j;
        stage = "Descriptors sobrepostos; original preservado";
        for (j = 0; j < 2U; ++j) {
            const RetirementField *field = fields[j];
            const char *name = j ? "WVIU" : "kvuF";
            if (field->bit_offset + field->bit_depth > players.record_size * 8U - 1U
                || (!retirement_name_is(descriptor + 8U, name) && depth
                    && at < field->bit_offset + field->bit_depth
                    && field->bit_offset < (uint64_t)at + depth)) goto done;
        }
    }
    stage = "Calendario invalido; original preservado";
    if (!retirement_parse_date((int)(retirement_read_bits(original, calendar.records_offset,
            &calendar.current_date, calendar.record_size) + RETIREMENT_CAREER_DATE_LOW),
            &year, &month, &day)) goto done;
    copy = (unsigned char *)malloc(size); allowed = (unsigned char *)calloc(size, 1);
    if (count) seen = (unsigned char *)calloc(count, 1);
    if (!copy || !allowed || (count && !seen)) goto done;
    memcpy(copy, original, size); result->crc_before = crc;
    stage = "Jogador/ID/data ausente ou invalida; original preservado";
    for (row = 0; row < players.record_count; ++row) {
        SIZE_T start = players.records_offset + (SIZE_T)row * players.record_size;
        uint32_t id, retiring, new_raw = 0U;
        unsigned bit;
        if (original[start + players.record_size - 1U] & 0x80U) continue;
        id = retirement_read_bits(original, start, &players.player_id, players.record_size);
        if (!id) continue; /* The schema permits the native empty/template ID 0. */
        if (id >= (1U << 19U)) goto done;
        if (count) {
            for (i = 0; i < count && player_ids[i] != id; ++i) {}
            if (i == count) continue;
            if (seen[i]) goto done;
            seen[i] = 1;
        }
        ++result->players_seen;
        retiring = retirement_read_bits(original, start, &players.is_retiring, players.record_size);
        if (retiring) ++result->players_retiring;
        if (reset_age) {
            int old_year, new_year;
            unsigned birth_month, birth_day;
            uint32_t raw = retirement_read_bits(original, start, &players.birthdate, players.record_size);
            retirement_civil_from_days(retirement_days_from_civil(1582, 10U, 14U) + raw,
                &old_year, &birth_month, &birth_day);
            if (old_year < 1900 || old_year > year) goto done;
            new_year = year - target_age - (month < birth_month || (month == birth_month && day < birth_day));
            if (birth_day > (unsigned)retirement_days_in_month(new_year, birth_month))
                birth_day = (unsigned)retirement_days_in_month(new_year, birth_month);
            new_raw = retirement_fifa_date_raw(new_year, birth_month, birth_day);
            if (!retirement_write_bits(copy, start, &players.birthdate, players.record_size, new_raw)) goto done;
            for (bit = 0; bit < players.birthdate.bit_depth; ++bit) {
                SIZE_T at = start * 8U + players.birthdate.bit_offset + bit;
                allowed[at / 8U] |= (unsigned char)(1U << (at % 8U));
            }
        }
        if (!retirement_write_bits(copy, start, &players.is_retiring, players.record_size, 0U)) goto done;
        for (bit = 0; bit < players.is_retiring.bit_depth; ++bit) {
            SIZE_T at = start * 8U + players.is_retiring.bit_offset + bit;
            allowed[at / 8U] |= (unsigned char)(1U << (at % 8U));
        }
        if (memcmp(copy + start, original + start, players.record_size)) ++result->players_changed;
    }
    for (i = 0; i < count; ++i) if (!seen[i]) goto done;
    stage = "Bit externo a selecao alterado; original preservado";
    if (result->players_changed) {
        if (retirement_u32(copy + players.table_crc_offset) != RETIREMENT_TABLE_CRC_SENTINEL) {
            retirement_put_u32(copy + players.table_crc_offset,
                retirement_fifa_crc32(copy + players.table_crc_start,
                    players.table_crc_offset - players.table_crc_start));
            memset(allowed + players.table_crc_offset, 255, 4);
        }
        retirement_put_u32(copy + RETIREMENT_CRC_OFFSET,
            retirement_crc32(copy + RETIREMENT_CRC_START, size - RETIREMENT_CRC_START));
        memset(allowed + RETIREMENT_CRC_OFFSET, 255, 4);
    }
    /* A positive proof of the exact writable bit set, not just a checksum test. */
    for (i = 0; i < size; ++i) if (((original[i] ^ copy[i]) & ~allowed[i]) != 0) goto done;
    result->crc_after = retirement_u32(copy + RETIREMENT_CRC_OFFSET);
    memcpy(original, copy, size); ok = 1;
    retirement_result_message(result, result->players_changed ? 1 : 0,
        "Selecao validada em memoria; nenhum arquivo gravado");
done:
    free(copy); free(allowed); free(seen);
    if (!ok) retirement_result_message(result, 30, stage);
    return ok;
}

int retirement_engine_apply_buffer_from_config(void *buffer, SIZE_T size,
    RetirementApplyResult *result)
{
    char mode[64];
    int enabled;
    int target_age;
    unsigned quiet_ms;
    int defer_until_game_exit;
    (void)quiet_ms;
    if (!retirement_get_config(g_retirement_mod_dir, &enabled, mode,
            sizeof(mode), &target_age, &quiet_ms,
            &defer_until_game_exit) || !enabled) {
        if (result) {
            retirement_result_clear(result);
            retirement_result_message(result, 20,
                "Engine desabilitado na configuracao");
        }
        return 0;
    }
    /* Save mutation is intentionally owned by the external worker.  The
     * process-local WriteFile hook must pass FIFA's original buffer through;
     * changing it here can leave FIFA's in-memory save state out of sync with
     * the DATA/INDEX pair it later manages. */
    (void)buffer;
    (void)size;
    (void)mode;
    (void)target_age;
    (void)defer_until_game_exit;
    if (result) {
        retirement_result_clear(result);
        retirement_result_message(result, 21,
            "Patch delegado ao worker externo");
    }
    return 0;
}

int retirement_engine_backup_before_write(const char *data_path)
{
    char index_path[1200];
    char backup_data[1200];
    char backup_index[1200];
    char *slash;
    if (!data_path || !*data_path)
        return 0;
    /* FIFA commonly writes a fresh DATA file in a temporary career folder
     * and only replaces the old file after the write succeeds.  There is no
     * old DATA to copy in that case, so the absence of the target is itself
     * a safe/expected state.  Existing DATA files still require a real
     * backup before we allow the in-memory patch through. */
    if (GetFileAttributesA(data_path) != INVALID_FILE_ATTRIBUTES
        && !retirement_copy_backup(data_path, "", backup_data,
            sizeof(backup_data)))
        return 0;
    lstrcpynA(index_path, data_path, sizeof(index_path));
    slash = strrchr(index_path, '\\');
    if (slash) lstrcpyA(slash + 1, "INDEX");
    if (GetFileAttributesA(index_path) != INVALID_FILE_ATTRIBUTES
        && !retirement_copy_backup(index_path, "", backup_index,
            sizeof(backup_index)))
        return 0;
    return 1;
}

int retirement_engine_patch_write_buffer(void *buffer, SIZE_T size,
    const char *data_path, RetirementApplyResult *result)
{
    char requested_mode[64];
    char configured_mode[64];
    const char *name;
    int enabled;
    int target_age;
    unsigned quiet_ms;
    int defer_until_game_exit;

    if (!buffer || size < 1024ULL * 1024ULL || !data_path || !*data_path
        || !result || !retirement_peek_requested_mode(requested_mode,
            sizeof(requested_mode)))
        return 0;
    name = strrchr(data_path, '\\');
    if (!name || _stricmp(name + 1, "DATA") != 0)
        return 0;
    if (!retirement_get_config(g_retirement_mod_dir, &enabled,
            configured_mode, sizeof(configured_mode), &target_age, &quiet_ms,
            &defer_until_game_exit) || !enabled)
        return 0;

    /* DATA/INDEX backups are made before the modified buffer is handed back
     * to FIFA.  For a newly-created save folder this is a safe no-op; for an
     * existing folder it preserves the pre-action pair. */
    if (!retirement_engine_backup_before_write(data_path))
        return 0;
    if (!retirement_engine_apply_buffer(buffer, size, requested_mode,
            target_age, result))
        return 0;
    if (result->players_changed == 0U)
        return 0;
    return 1;
}

void retirement_engine_set_mod_dir(const char *mod_dir)
{
    if (!mod_dir || !*mod_dir) {
        g_retirement_mod_dir[0] = '\0';
        return;
    }
    lstrcpynA(g_retirement_mod_dir, mod_dir, sizeof(g_retirement_mod_dir));
}

static int retirement_claim_deferred_path(const char *path)
{
    unsigned int index;
    if (!path || !*path) return 0;
    AcquireSRWLockExclusive(&g_retirement_lock);
    for (index = 0; index < RETIREMENT_WATCH_CAPACITY; ++index) {
        if (g_retirement_deferred_paths[index][0]
            && _stricmp(g_retirement_deferred_paths[index], path) == 0) {
            ReleaseSRWLockExclusive(&g_retirement_lock);
            return 0;
        }
    }
    for (index = 0; index < RETIREMENT_WATCH_CAPACITY; ++index) {
        if (!g_retirement_deferred_paths[index][0]) {
            lstrcpynA(g_retirement_deferred_paths[index], path,
                sizeof(g_retirement_deferred_paths[index]));
            ReleaseSRWLockExclusive(&g_retirement_lock);
            return 1;
        }
    }
    ReleaseSRWLockExclusive(&g_retirement_lock);
    return 0;
}

static void retirement_release_deferred_path(const char *path)
{
    unsigned int index;
    if (!path || !*path) return;
    AcquireSRWLockExclusive(&g_retirement_lock);
    for (index = 0; index < RETIREMENT_WATCH_CAPACITY; ++index) {
        if (_stricmp(g_retirement_deferred_paths[index], path) == 0) {
            g_retirement_deferred_paths[index][0] = '\0';
            break;
        }
    }
    ReleaseSRWLockExclusive(&g_retirement_lock);
}

static int retirement_launch_deferred_worker(const char *data_path,
    const char *mode, int target_age, unsigned quiet_ms,
    int wait_for_parent_exit)
{
    char worker_path[MAX_PATH];
    char command_line[4096];
    STARTUPINFOA startup;
    PROCESS_INFORMATION process;
    if (!data_path || !*data_path || !g_retirement_mod_dir[0]) return 0;
    if (!retirement_claim_deferred_path(data_path)) return 1;
    snprintf(worker_path, sizeof(worker_path), "%s\\retirement_offline_worker.exe",
        g_retirement_mod_dir);
    if (GetFileAttributesA(worker_path) == INVALID_FILE_ATTRIBUTES) {
        retirement_release_deferred_path(data_path);
        return 0;
    }
    snprintf(command_line, sizeof(command_line),
        "\"%s\" --pid %lu --data \"%s\" --mode %s --age %d "
        "--quiet-ms %u --mod-dir \"%s\"%s",
        worker_path, (unsigned long)GetCurrentProcessId(), data_path,
        mode && *mode ? mode : "remove_retirement", target_age, quiet_ms,
        g_retirement_mod_dir, wait_for_parent_exit ? " --wait-parent-exit" : "");
    memset(&startup, 0, sizeof(startup));
    memset(&process, 0, sizeof(process));
    startup.cb = sizeof(startup);
    if (!CreateProcessA(NULL, command_line, NULL, NULL, FALSE,
            CREATE_NO_WINDOW, NULL, NULL, &startup, &process)) {
        retirement_release_deferred_path(data_path);
        return 0;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return 1;
}

static void retirement_log_result(const RetirementApplyResult *result,
    const char *path)
{
    char log_path[MAX_PATH];
    FILE *file;
    if (!retirement_engine_local_logging_enabled(g_retirement_mod_dir)) return;
    career_path_logs(g_retirement_mod_dir);
    snprintf(log_path, sizeof(log_path), "%s\\logs\\career_retirement_background.log",
        g_retirement_mod_dir);
    file = fopen(log_path, "ab");
    if (!file) return;
    fprintf(file, "status=%d changed=%u retiring=%u crc_before=%08X crc_after=%08X message=%s data=%s backup_data=%s backup_index=%s\n",
        result->status, result->players_changed, result->players_retiring,
        result->crc_before, result->crc_after, result->message, path,
        result->backup_data, result->backup_index);
    fclose(file);
}

static void retirement_log_event(const char *event, const char *path)
{
    char log_path[MAX_PATH];
    FILE *file;
    if (!retirement_engine_local_logging_enabled(g_retirement_mod_dir)) return;
    career_path_logs(g_retirement_mod_dir);
    snprintf(log_path, sizeof(log_path), "%s\\logs\\career_retirement_background.log",
        g_retirement_mod_dir);
    file = fopen(log_path, "ab");
    if (!file) return;
    fprintf(file, "event=%s path=%s save_root=%s\n", event ? event : "",
        path ? path : "", g_retirement_save_root);
    fclose(file);
}

void retirement_engine_show_feedback(const char *text, UINT beep_type)
{
    HWND window;
    COPYDATASTRUCT copy;
    DWORD_PTR ignored = 0;
    if (!text || !*text)
        return;
    window = g_retirement_feedback_window;
    if (!window || !IsWindow(window)) {
        g_retirement_feedback_window = NULL;
        retirement_feedback_start();
        window = g_retirement_feedback_window;
    }
    if (!window)
        window = FindWindowA("FifaRetirementFeedbackWindow", NULL);
    if (window) {
        memset(&copy, 0, sizeof(copy));
        copy.dwData = RETIREMENT_FEEDBACK_RESULT;
        copy.cbData = (DWORD)strlen(text) + 1U;
        copy.lpData = (PVOID)text;
        (void)SendMessageTimeoutA(window, WM_COPYDATA, 0, (LPARAM)&copy,
            SMTO_ABORTIFHUNG | SMTO_BLOCK, 1500U, &ignored);
    }
    if (beep_type)
        MessageBeep(beep_type);
}

static void retirement_feedback_show_result(const RetirementApplyResult *result)
{
    if (!result || result->status != 1 || result->players_changed == 0U)
        return;
    retirement_engine_show_feedback(
        "Aposentadoria concluida com sucesso.\nO save esta pronto para ser reaberto.",
        MB_OK);
}

static void retirement_feedback_show_ready(const char *mode)
{
    /* This non-modal layer lets the NAV save and exit flow continue. */
    if (retirement_transfer_budget_amount(mode))
        retirement_engine_show_feedback(
            "Aumento do orcamento preparado.\n"
            "Saia do save sem salvar.\n"
            "Ao voltar a tela anterior, aguarde o processamento.",
            MB_ICONINFORMATION);
    else
        retirement_engine_show_feedback(
            "Aposentadoria preparada.\n"
            "Saia do save sem salvar.\n"
            "Ao voltar a tela anterior, aguarde o processamento.",
            MB_ICONINFORMATION);
}

void retirement_engine_note_buffer_write(const char *data_path,
    const RetirementApplyResult *result)
{
    char consumed_mode[64];
    if (!data_path || !result || result->status != 1
        || result->players_changed == 0U)
        return;
    if (!retirement_take_requested_mode(consumed_mode,
            sizeof(consumed_mode)))
        return;
    retirement_log_event("buffer_patch_written", data_path);
    retirement_log_result(result, data_path);
    retirement_feedback_show_result(result);
}

static int retirement_set_requested_mode(const char *mode)
{
    int accepted = 0;
    if (!mode || !*mode) return 0;
    AcquireSRWLockExclusive(&g_retirement_lock);
    if (!g_retirement_requested_mode[0]
        && !g_retirement_card_flow_latched) {
        lstrcpynA(g_retirement_requested_mode, mode,
            sizeof(g_retirement_requested_mode));
        g_retirement_request_deadline_tick = GetTickCount64()
            + RETIREMENT_CARD_REQUEST_WINDOW_MS;
        g_retirement_card_flow_latched = 1;
        accepted = 1;
    }
    ReleaseSRWLockExclusive(&g_retirement_lock);
    return accepted;
}

void retirement_engine_note_ui_signal(const char *path)
{
    const char *name;
    const char *slash;
    const char *mode = NULL;
    const char *event = NULL;
    char configured_mode[64];
    int enabled;
    int target_age;
    unsigned quiet_ms;
    int defer_until_game_exit;

    if (!path || !*path)
        return;
    slash = strrchr(path, '\\');
    {
        const char *forward_slash = strrchr(path, '/');
        if (forward_slash && (!slash || forward_slash > slash))
            slash = forward_slash;
    }
    name = slash ? slash + 1 : path;

    /* Returning to Career Hub is the boundary between card visits.  It is
     * the only event that unlocks a previously consumed retirement action. */
    if (_stricmp(name, "mainmenuhubflow.nav") == 0) {
        AcquireSRWLockExclusive(&g_retirement_lock);
        g_retirement_card_flow_latched = 0;
        ReleaseSRWLockExclusive(&g_retirement_lock);
        return;
    }

    /* These names are private to the two retirement-card transitions.  This
     * is deliberately narrower than a screen, cursor rectangle or save I/O:
     * opening any other NAV file cannot arm the retirement operation. */
    if (_stricmp(name, "retirementremoveflow.nav") == 0) {
        mode = "remove_retirement";
        event = "nav_remove_request";
    } else if (_stricmp(name, "retirementresetageflow.nav") == 0) {
        mode = "remove_and_rejuvenate";
        event = "nav_reset_age_request";
    } else if (_stricmp(name, "retirementaddfunds1mflow.nav") == 0) {
        mode = "add_transfer_budget_1m";
        event = "nav_add_transfer_budget_1m_request";
    } else if (_stricmp(name, "retirementaddfunds3mflow.nav") == 0) {
        mode = "add_transfer_budget_3m";
        event = "nav_add_transfer_budget_3m_request";
    } else {
        return;
    }

    if (!retirement_get_config(g_retirement_mod_dir, &enabled,
            configured_mode, sizeof(configured_mode), &target_age, &quiet_ms,
            &defer_until_game_exit) || !enabled) {
        retirement_log_event("nav_signal_ignored_disabled", path);
        return;
    }
    if (retirement_set_requested_mode(mode)) {
        retirement_log_event(event, path);
        retirement_feedback_show_ready(mode);
    } else
        retirement_log_event("nav_request_ignored_latched", path);
}

static int retirement_take_requested_mode(char *mode, size_t capacity)
{
    int ready;
    ULONGLONG now;
    if (!mode || capacity == 0) return 0;
    AcquireSRWLockExclusive(&g_retirement_lock);
    ready = g_retirement_requested_mode[0] != '\0';
    now = GetTickCount64();
    if (ready && g_retirement_request_deadline_tick
        && now >= g_retirement_request_deadline_tick) {
        g_retirement_requested_mode[0] = '\0';
        g_retirement_request_deadline_tick = 0;
        ready = 0;
        retirement_log_event("card_request_expired", "");
    }
    if (ready) {
        lstrcpynA(mode, g_retirement_requested_mode, (int)capacity);
        g_retirement_requested_mode[0] = '\0';
        g_retirement_request_deadline_tick = 0;
    }
    ReleaseSRWLockExclusive(&g_retirement_lock);
    return ready;
}

static int retirement_peek_requested_mode(char *mode, size_t capacity)
{
    int ready;
    ULONGLONG now;
    if (!mode || capacity == 0) return 0;
    AcquireSRWLockExclusive(&g_retirement_lock);
    ready = g_retirement_requested_mode[0] != '\0';
    now = GetTickCount64();
    if (ready && g_retirement_request_deadline_tick
        && now >= g_retirement_request_deadline_tick) {
        g_retirement_requested_mode[0] = '\0';
        g_retirement_request_deadline_tick = 0;
        ready = 0;
    }
    if (ready)
        lstrcpynA(mode, g_retirement_requested_mode, (int)capacity);
    ReleaseSRWLockExclusive(&g_retirement_lock);
    return ready;
}

#include "retirement_feedback_paint.inc"

static LRESULT CALLBACK retirement_feedback_window_proc(HWND window,
    UINT message, WPARAM wparam, LPARAM lparam)
{
    (void)lparam;
    switch (message) {
    case WM_PAINT:
    {
        PAINTSTRUCT paint;
        RECT client;
        char text[512];
        HDC dc = BeginPaint(window, &paint);
        GetClientRect(window, &client);
        AcquireSRWLockShared(&g_retirement_feedback_lock);
        lstrcpynA(text, g_retirement_feedback_text, sizeof(text));
        ReleaseSRWLockShared(&g_retirement_feedback_lock);
        retirement_feedback_paint(dc, &client, text);
        EndPaint(window, &paint);
        return 0;
    }
    case WM_COPYDATA:
    {
        const COPYDATASTRUCT *copy = (const COPYDATASTRUCT *)lparam;
        SIZE_T length;
        char incoming[512];
        int persistent;
        if (copy && copy->dwData == 0x16403U) {
            if (g_retirement_feedback_persistent) {
                g_retirement_feedback_persistent=0;
                KillTimer(window, RETIREMENT_FEEDBACK_HIDE_TIMER);
                ShowWindow(window, SW_HIDE);
            }
            return 1;
        }
        if (!copy || (copy->dwData != RETIREMENT_FEEDBACK_RESULT && copy->dwData != 0x16402U)
            || !copy->lpData || !copy->cbData)
            return 0;
        persistent=copy->dwData == 0x16402U;
        length = copy->cbData;
        if (length >= sizeof(g_retirement_feedback_text))
            length = sizeof(g_retirement_feedback_text) - 1U;
        memcpy(incoming, copy->lpData, length);
        incoming[length] = '\0';
        AcquireSRWLockExclusive(&g_retirement_feedback_lock);
        /* A duplicate does not restart the five-second display timer. */
        if (!strcmp(g_retirement_feedback_text, incoming) && IsWindowVisible(window)
                && persistent == g_retirement_feedback_persistent) {
            ReleaseSRWLockExclusive(&g_retirement_feedback_lock);
            return 1;
        }
        lstrcpynA(g_retirement_feedback_text, incoming, sizeof(g_retirement_feedback_text));
        g_retirement_feedback_persistent=persistent;
        ReleaseSRWLockExclusive(&g_retirement_feedback_lock);
        SendMessageA(window, RETIREMENT_FEEDBACK_SHOW, 0, 0);
        return 1;
    }
    case RETIREMENT_FEEDBACK_SHOW:
    {
        HWND foreground = GetForegroundWindow();
        RECT target;
        int x;
        int y;
        if (foreground && GetWindowRect(foreground, &target)) {
            x = target.left + ((target.right - target.left) - RETIREMENT_FEEDBACK_WIDTH) / 2;
            y = target.top + 42;
        } else {
            x = (GetSystemMetrics(SM_CXSCREEN) - RETIREMENT_FEEDBACK_WIDTH) / 2;
            y = 42;
        }
        SetWindowPos(window, HWND_TOPMOST, x, y,
            RETIREMENT_FEEDBACK_WIDTH, RETIREMENT_FEEDBACK_HEIGHT,
            SWP_NOACTIVATE | SWP_SHOWWINDOW);
        KillTimer(window, RETIREMENT_FEEDBACK_HIDE_TIMER);
        if (!g_retirement_feedback_persistent)
            SetTimer(window, RETIREMENT_FEEDBACK_HIDE_TIMER,
                RETIREMENT_FEEDBACK_DURATION_MS, NULL);
        InvalidateRect(window, NULL, TRUE);
        return 0;
    }
    case WM_TIMER:
        if (wparam == RETIREMENT_FEEDBACK_HIDE_TIMER) {
            if (g_retirement_feedback_persistent)return 0;
            KillTimer(window, RETIREMENT_FEEDBACK_HIDE_TIMER);
            ShowWindow(window, SW_HIDE);
            return 0;
        }
        break;
    case WM_NCHITTEST:
        return HTTRANSPARENT;
    case WM_MOUSEACTIVATE:
        return MA_NOACTIVATE;
    }
    return DefWindowProcA(window, message, wparam, lparam);
}

static DWORD WINAPI retirement_feedback_worker(void *unused)
{
    WNDCLASSA window_class;
    MSG message;
    HINSTANCE instance = GetModuleHandleA(NULL);
    const char *class_name = "FifaRetirementFeedbackWindow";
    (void)unused;
    memset(&window_class, 0, sizeof(window_class));
    window_class.lpfnWndProc = retirement_feedback_window_proc;
    window_class.hInstance = instance;
    window_class.hCursor = LoadCursorA(NULL, IDC_ARROW);
    window_class.lpszClassName = class_name;
    if (!RegisterClassA(&window_class)
        && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        SetEvent(g_retirement_feedback_ready);
        return 0;
    }
    g_retirement_feedback_window = CreateWindowExA(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            | WS_EX_LAYERED | WS_EX_TRANSPARENT,
        class_name, "FIFA 16", WS_POPUP, 0, 0, RETIREMENT_FEEDBACK_WIDTH,
        RETIREMENT_FEEDBACK_HEIGHT, NULL, NULL,
        instance, NULL);
    if (!g_retirement_feedback_window) {
        SetEvent(g_retirement_feedback_ready);
        return 0;
    }
    {
        HRGN rounded = CreateRoundRectRgn(0, 0, RETIREMENT_FEEDBACK_WIDTH,
            RETIREMENT_FEEDBACK_HEIGHT, 20, 20);
        if (rounded && !SetWindowRgn(g_retirement_feedback_window, rounded, FALSE))
            DeleteObject(rounded);
    }
    SetLayeredWindowAttributes(g_retirement_feedback_window, 0, 255, LWA_ALPHA);
    SetEvent(g_retirement_feedback_ready);
    while (GetMessageA(&message, NULL, 0, 0) > 0) {
        TranslateMessage(&message);
        DispatchMessageA(&message);
    }
    return 0;
}

static void retirement_feedback_start(void)
{
    HANDLE thread;
    if (g_retirement_feedback_window) return;
    g_retirement_feedback_ready = CreateEventA(NULL, FALSE, FALSE, NULL);
    if (!g_retirement_feedback_ready) return;
    thread = CreateThread(NULL, 0, retirement_feedback_worker, NULL, 0, NULL);
    if (!thread) {
        CloseHandle(g_retirement_feedback_ready);
        g_retirement_feedback_ready = NULL;
        return;
    }
    (void)WaitForSingleObject(g_retirement_feedback_ready, 500U);
    CloseHandle(thread);
    CloseHandle(g_retirement_feedback_ready);
    g_retirement_feedback_ready = NULL;
}

static int retirement_marker_matches(COLORREF pixel, COLORREF expected)
{
    int red;
    int green;
    int blue;
    if (pixel == CLR_INVALID) return 0;
    red = (int)GetRValue(pixel) - (int)GetRValue(expected);
    green = (int)GetGValue(pixel) - (int)GetGValue(expected);
    blue = (int)GetBValue(pixel) - (int)GetBValue(expected);
    return abs(red) <= RETIREMENT_CARD_MARKER_TOLERANCE
        && abs(green) <= RETIREMENT_CARD_MARKER_TOLERANCE
        && abs(blue) <= RETIREMENT_CARD_MARKER_TOLERANCE;
}

static int retirement_card_marker_mode(HWND foreground, char *mode,
    size_t capacity)
{
    HDC device_context;
    RECT client;
    LONG width;
    LONG height;
    LONG marker_x0;
    LONG marker_x1;
    LONG marker_x2;
    LONG marker_y;
    COLORREF marker0;
    COLORREF marker1;
    COLORREF marker2;

    if (!mode || capacity == 0 || !foreground
        || !GetClientRect(foreground, &client))
        return 0;
    width = client.right - client.left;
    height = client.bottom - client.top;
    if (width <= 0 || height <= 0) return 0;
    marker_x0 = RETIREMENT_CARD_MARKER_X0 * width / 1920L;
    marker_x1 = RETIREMENT_CARD_MARKER_X1 * width / 1920L;
    marker_x2 = RETIREMENT_CARD_MARKER_X2 * width / 1920L;
    marker_y = RETIREMENT_CARD_MARKER_Y * height / 1080L;
    device_context = GetDC(foreground);
    if (!device_context) return 0;
    marker0 = GetPixel(device_context, marker_x0, marker_y);
    marker1 = GetPixel(device_context, marker_x1, marker_y);
    marker2 = GetPixel(device_context, marker_x2, marker_y);
    ReleaseDC(foreground, device_context);
    if (retirement_marker_matches(marker1, RGB(0, 0, 255))
        && retirement_marker_matches(marker2, RGB(255, 255, 0))
        && retirement_marker_matches(marker0, RGB(0, 255, 0))) {
        lstrcpynA(mode, "remove_retirement", (int)capacity);
        return 1;
    }
    if (retirement_marker_matches(marker1, RGB(0, 0, 255))
        && retirement_marker_matches(marker2, RGB(0, 255, 255))
        && retirement_marker_matches(marker0, RGB(255, 0, 255))) {
        lstrcpynA(mode, "remove_and_rejuvenate", (int)capacity);
        return 1;
    }
    return 0;
}

static int retirement_card_marker_visible(char *mode, size_t capacity)
{
    HWND foreground;
    DWORD process_id = 0;
    if (!mode || capacity == 0) return 0;
    foreground = GetForegroundWindow();
    if (!foreground) return 0;
    GetWindowThreadProcessId(foreground, &process_id);
    if (process_id != GetCurrentProcessId()) return 0;
    return retirement_card_marker_mode(foreground, mode, capacity);
}

static int retirement_card_mode_at_cursor(char *mode, size_t capacity)
{
    HWND foreground;
    DWORD process_id = 0;
    RECT client;
    POINT point;
    LONG width;
    LONG height;
    LONG logical_x;
    LONG logical_y;

    if (!mode || capacity == 0 || !GetCursorPos(&point)) return 0;
    foreground = GetForegroundWindow();
    if (!foreground) return 0;
    GetWindowThreadProcessId(foreground, &process_id);
    if (process_id != GetCurrentProcessId()
        || !GetClientRect(foreground, &client)
        || !ScreenToClient(foreground, &point))
        return 0;
    width = client.right - client.left;
    height = client.bottom - client.top;
    if (width <= 0 || height <= 0) return 0;
    logical_x = point.x * 1920L / width;
    logical_y = point.y * 1080L / height;
    if (logical_x < 965L || logical_x >= 1811L
        || logical_y < 278L || logical_y >= 482L)
        return 0;
    return retirement_card_marker_mode(foreground, mode, capacity);
}

static DWORD WINAPI retirement_input_worker(void *unused)
{
    SHORT previous_left = 0;
    int input_armed = 0;
    int card_session_active = 0;
    ULONGLONG last_card_request_tick = 0;
    ULONGLONG card_hidden_since = 0;
    (void)unused;
    while (InterlockedCompareExchange(&g_retirement_running, 0, 0)) {
        SHORT left = GetAsyncKeyState(VK_LBUTTON);
        char mode[64];
        char pending_mode[64];
        char visible_mode[64];
        ULONGLONG now = GetTickCount64();
        int request_pending = retirement_peek_requested_mode(
            pending_mode, sizeof(pending_mode));
        int pressed = input_armed
            && ((left & 0x8000) && !(previous_left & 0x8000));
        if (!(left & 0x8000)) input_armed = 1;
        if (card_session_active) {
            if (!retirement_card_marker_visible(visible_mode,
                    sizeof(visible_mode))) {
                if (!card_hidden_since) card_hidden_since = now;
                else if (now - card_hidden_since
                    >= RETIREMENT_CARD_SESSION_RELEASE_MS) {
                    card_session_active = 0;
                    card_hidden_since = 0;
                }
            } else {
                card_hidden_since = 0;
            }
        }
        if (!card_session_active && pressed && !request_pending
            && (!last_card_request_tick
                || now - last_card_request_tick
                    >= RETIREMENT_CARD_REQUEST_COOLDOWN_MS)
            && retirement_card_mode_at_cursor(mode, sizeof(mode))
            && retirement_set_requested_mode(mode)) {
            last_card_request_tick = now;
            card_session_active = 1;
            card_hidden_since = 0;
            retirement_log_event(
                _stricmp(mode, "remove_and_rejuvenate") == 0
                    ? "card_reset_age_request" : "card_remove_request",
                mode);
        }
        previous_left = left;
        Sleep(25U);
    }
    return 0;
}

static int retirement_get_save_root(char *root, size_t capacity)
{
    char profile[MAX_PATH];
    DWORD length;
    if (!root || capacity == 0) return 0;
    length = GetEnvironmentVariableA("USERPROFILE", profile,
        (DWORD)sizeof(profile));
    if (!length || length >= sizeof(profile)) return 0;
    snprintf(root, capacity, "%s\\Documents\\FIFA 16\\0\\FIFA16", profile);
    return GetFileAttributesA(root) != INVALID_FILE_ATTRIBUTES;
}

static int retirement_file_signature(const char *path,
    unsigned long long *signature)
{
    WIN32_FILE_ATTRIBUTE_DATA attributes;
    ULARGE_INTEGER time_value;
    ULARGE_INTEGER size_value;
    if (!path || !signature || !GetFileAttributesExA(path,
            GetFileExInfoStandard, &attributes))
        return 0;
    time_value.LowPart = attributes.ftLastWriteTime.dwLowDateTime;
    time_value.HighPart = attributes.ftLastWriteTime.dwHighDateTime;
    size_value.LowPart = attributes.nFileSizeLow;
    size_value.HighPart = attributes.nFileSizeHigh;
    *signature = time_value.QuadPart ^ (size_value.QuadPart * 0x9E3779B97F4A7C15ULL);
    if (*signature == 0) *signature = 1;
    return 1;
}

static int retirement_file_is_new_save(const char *path)
{
    WIN32_FILE_ATTRIBUTE_DATA attributes;
    ULARGE_INTEGER time_value;
    ULARGE_INTEGER size_value;
    if (!path || !GetFileAttributesExA(path, GetFileExInfoStandard,
            &attributes))
        return 0;
    time_value.LowPart = attributes.ftLastWriteTime.dwLowDateTime;
    time_value.HighPart = attributes.ftLastWriteTime.dwHighDateTime;
    size_value.LowPart = attributes.nFileSizeLow;
    size_value.HighPart = attributes.nFileSizeHigh;
    return time_value.QuadPart > g_retirement_watch_start_filetime
        && size_value.QuadPart >= 1024ULL * 1024ULL;
}

static int retirement_watch_slot(const char *path)
{
    unsigned int index;
    int free_slot = -1;
    for (index = 0; index < RETIREMENT_WATCH_CAPACITY; ++index) {
        if (g_retirement_watch[index].path[0]
            && _stricmp(g_retirement_watch[index].path, path) == 0)
            return (int)index;
        if (free_slot < 0 && !g_retirement_watch[index].path[0])
            free_slot = (int)index;
    }
    if (free_slot >= 0)
        lstrcpynA(g_retirement_watch[free_slot].path, path,
            sizeof(g_retirement_watch[free_slot].path));
    return free_slot;
}

static void retirement_watch_observe(const char *path, const char *mode,
    int target_age, unsigned quiet_ms, int defer_until_game_exit)
{
    unsigned long long signature;
    ULONGLONG now;
    int slot;
    RetirementWatchEntry *entry;
    (void)mode;
    if (!retirement_file_signature(path, &signature)) return;
    slot = retirement_watch_slot(path);
    if (slot < 0) return;
    entry = &g_retirement_watch[slot];
    now = GetTickCount64();
    if (!entry->initialized) {
        if (retirement_file_is_new_save(path)) {
            /* A DATA created after the watcher started is a save candidate,
             * not a baseline. Keep the pending signature but leave the last
             * signature empty so the next stable poll actually enters the
             * quiet-time apply branch. */
            entry->last_signature = 0;
            entry->pending_signature = signature;
            entry->pending_since = now;
        } else {
            entry->last_signature = signature;
            entry->pending_signature = 0;
            entry->pending_since = 0;
        }
        entry->initialized = 1;
        return;
    }
    if (signature != entry->last_signature) {
        if (entry->pending_signature != signature) {
            entry->pending_signature = signature;
            entry->pending_since = now;
        } else if (now - entry->pending_since >= quiet_ms) {
            char requested_mode[64];
            if (!entry->deferred_worker_started
                && retirement_peek_requested_mode(requested_mode,
                    sizeof(requested_mode))
                && retirement_launch_deferred_worker(path, requested_mode,
                    target_age, quiet_ms, defer_until_game_exit)) {
                (void)retirement_take_requested_mode(requested_mode,
                    sizeof(requested_mode));
                entry->deferred_worker_started = 1;
                entry->last_signature = signature;
                entry->pending_signature = 0;
                entry->pending_since = 0;
                retirement_log_event("deferred_worker_started", path);
            }
        }
    }
}

static void retirement_watch_poll(const char *mode, int target_age,
    unsigned quiet_ms, int defer_until_game_exit)
{
    char pattern[MAX_PATH];
    WIN32_FIND_DATAA find_data;
    HANDLE search;
    if (!g_retirement_save_root_ready) {
        if (!retirement_get_save_root(g_retirement_save_root,
                sizeof(g_retirement_save_root)))
            return;
        g_retirement_save_root_ready = 1;
        retirement_log_event("watcher_started", g_retirement_save_root);
    }
    snprintf(pattern, sizeof(pattern), "%s\\*", g_retirement_save_root);
    search = FindFirstFileA(pattern, &find_data);
    if (search == INVALID_HANDLE_VALUE) return;
    do {
        char data_path[MAX_PATH];
        if ((find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
            && strcmp(find_data.cFileName, ".") != 0
            && strcmp(find_data.cFileName, "..") != 0) {
            snprintf(data_path, sizeof(data_path), "%s\\%s\\DATA",
                g_retirement_save_root, find_data.cFileName);
            retirement_watch_observe(data_path, mode, target_age, quiet_ms,
                defer_until_game_exit);
        }
    } while (FindNextFileA(search, &find_data));
    FindClose(search);
}

static DWORD WINAPI retirement_engine_worker(void *unused)
{
    (void)unused;
    while (InterlockedCompareExchange(&g_retirement_running, 0, 0)) {
        char path[1024] = "";
        char mode[64];
        char requested_mode[64];
        int enabled, target_age;
        int defer_until_game_exit;
        unsigned quiet_ms;
        DWORD wait = WaitForSingleObject(g_retirement_event, 1000U);
        if (!retirement_get_config(g_retirement_mod_dir, &enabled,
                mode, sizeof(mode), &target_age, &quiet_ms,
                &defer_until_game_exit) || !enabled)
            continue;
        if (wait == WAIT_OBJECT_0) {
            Sleep(quiet_ms);
            AcquireSRWLockShared(&g_retirement_lock);
            lstrcpynA(path, g_retirement_pending_path, sizeof(path));
            ReleaseSRWLockShared(&g_retirement_lock);
            if (path[0] && retirement_take_requested_mode(requested_mode,
                    sizeof(requested_mode))) {
                if (retirement_launch_deferred_worker(path, requested_mode,
                        target_age, quiet_ms, defer_until_game_exit))
                    retirement_log_event("deferred_worker_started", path);
                else
                    retirement_set_requested_mode(requested_mode);
            }
        }
    }
    return 0;
}

int retirement_engine_start(const char *mod_dir)
{
    FILETIME start_time;
    if (!mod_dir || !*mod_dir) return 0;
    retirement_engine_set_mod_dir(mod_dir);
    GetSystemTimeAsFileTime(&start_time);
    g_retirement_watch_start_filetime =
        ((ULONGLONG)start_time.dwHighDateTime << 32)
        | (ULONGLONG)start_time.dwLowDateTime;
    if (InterlockedCompareExchange(&g_retirement_running, 1, 0) != 0)
        return 1;
    g_retirement_event = CreateEventA(NULL, FALSE, FALSE, NULL);
    if (!g_retirement_event) { InterlockedExchange(&g_retirement_running, 0); return 0; }
    g_retirement_thread = CreateThread(NULL, 0, retirement_engine_worker, NULL, 0, NULL);
    if (!g_retirement_thread) {
        CloseHandle(g_retirement_event); g_retirement_event = NULL;
        InterlockedExchange(&g_retirement_running, 0); return 0;
    }
    retirement_feedback_start();
    CloseHandle(g_retirement_thread); g_retirement_thread = NULL;
    return 1;
}

void retirement_engine_note_write(const char *data_path)
{
    const char *name;
    char mode[64];
    int enabled;
    int target_age;
    int defer_until_game_exit;
    unsigned quiet_ms;
    if (!data_path || !*data_path || !g_retirement_event) return;
    name = strrchr(data_path, '\\');
    if (!name || _stricmp(name + 1, "DATA") != 0) return;
    /* FIFA also writes small auxiliary DATA files while navigating Career
     * Mode.  They do not contain the career database (CZUM), so never arm
     * the retirement worker for anything below the real save size. */
    {
        WIN32_FILE_ATTRIBUTE_DATA attributes;
        ULARGE_INTEGER size_value;
        if (!GetFileAttributesExA(data_path, GetFileExInfoStandard,
                &attributes))
            return;
        size_value.LowPart = attributes.nFileSizeLow;
        size_value.HighPart = attributes.nFileSizeHigh;
        if (size_value.QuadPart < 1024ULL * 1024ULL)
            return;
    }
    if (retirement_get_config(g_retirement_mod_dir, &enabled, mode,
            sizeof(mode), &target_age, &quiet_ms,
            &defer_until_game_exit) && enabled) {
        char requested_mode[64];
        if (retirement_take_requested_mode(requested_mode,
                sizeof(requested_mode))) {
            if (!retirement_launch_deferred_worker(data_path, requested_mode,
                    target_age, quiet_ms, defer_until_game_exit))
                retirement_set_requested_mode(requested_mode);
        }
    }
    AcquireSRWLockExclusive(&g_retirement_lock);
    lstrcpynA(g_retirement_pending_path, data_path, sizeof(g_retirement_pending_path));
    ReleaseSRWLockExclusive(&g_retirement_lock);
    SetEvent(g_retirement_event);
}
