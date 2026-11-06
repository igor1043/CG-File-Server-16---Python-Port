#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include "crowd_runtime.h"
#include "../../platform/mod_paths.h"
#include "../retirement/retirement_engine.h"

#define CROWD_DEFAULT_FACTOR 0.90f
#define CROWD_MIN_FACTOR 0.09f
#define CROWD_MAX_FACTOR 0.90f
#define CROWD_REPUTATION_CAPACITY 2048
#define CROWD_LEAGUE_LINK_CAPACITY 2048
#define CROWD_LEAGUE_DEFINITION_CAPACITY 512
#define CROWD_RIVAL_CAPACITY 4096
#define CROWD_CONFIG_FILE_CAPACITY 16384

typedef struct CrowdReputation
{
    int team_id;
    int domestic;
    int international;
} CrowdReputation;

typedef struct CrowdLeagueLink
{
    int team_id;
    int league_id;
} CrowdLeagueLink;

typedef struct CrowdLeagueDefinition
{
    int league_id;
    int level;
} CrowdLeagueDefinition;

typedef struct CrowdLeagueRating
{
    int team_id;
    int level;
} CrowdLeagueRating;

typedef struct CrowdRival
{
    int team_id1;
    int team_id2;
    int type;
} CrowdRival;

static SRWLOCK g_crowd_config_lock = SRWLOCK_INIT;
static volatile LONG g_enabled;
static volatile LONG g_factor_bits;
static volatile LONG g_started;
static volatile LONG g_last_logged_enabled = 0;
static volatile LONG g_log_enabled;
static char g_log_dir[MAX_PATH];
static CrowdReputation g_reputations[CROWD_REPUTATION_CAPACITY];
static SIZE_T g_reputation_count;
static CrowdLeagueRating g_league_ratings[CROWD_LEAGUE_LINK_CAPACITY];
static SIZE_T g_league_rating_count;
static CrowdRival g_rivals[CROWD_RIVAL_CAPACITY];
static SIZE_T g_rival_count;
static volatile LONG g_reputation_loaded;

static float clamp_factor(float value)
{
    if (value < CROWD_MIN_FACTOR)
        return CROWD_MIN_FACTOR;
    if (value > CROWD_MAX_FACTOR)
        return CROWD_MAX_FACTOR;
    return value;
}

static LONG float_bits(float value)
{
    LONG bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static float bits_float(LONG bits)
{
    float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static FILE *open_log(void)
{
    char path[MAX_PATH];
    if (!g_log_dir[0]
        || InterlockedCompareExchange(&g_log_enabled, 0, 0) == 0)
        return NULL;
    career_path_logs(g_log_dir);
    snprintf(path, sizeof(path), "%s\\logs\\crowd_attendance_runtime.log", g_log_dir);
    return fopen(path, "ab");
}

static int crowd_config_int_from_section(const char *section,
    const char *key, int fallback)
{
    char path[MAX_PATH];
    char value[64];
    DWORD length;
    if (!section || !key || !g_log_dir[0])
        return fallback;
    career_path_read(path, sizeof(path), g_log_dir, "config", "crowd.ini");
    length = GetPrivateProfileStringA(section, key, "", value,
        (DWORD)sizeof(value), path);
    return length ? atoi(value) : fallback;
}

static int crowd_config_int(const char *key, int fallback)
{
    return crowd_config_int_from_section("crowd", key, fallback);
}

float crowd_runtime_international_bonus(void)
{
    char path[MAX_PATH], value[64], *end;
    double bonus;
    if (!g_log_dir[0])
        return 0.06f;
    career_path_read(path, sizeof(path), g_log_dir, "config", "crowd.ini");
    GetPrivateProfileStringA("crowd_weights", "international_competition_bonus",
        "0.06", value, (DWORD)sizeof(value), path);
    bonus = strtod(value, &end);
    while (*end == ' ' || *end == '\t') ++end;
    if (end == value || *end || !_finite(bonus) || bonus < 0.0 || bonus > 0.20)
        return 0.06f;
    return (float)bonus;
}

int crowd_runtime_competition_setting(const char *key,const char *suffix,
    int fallback,int maximum)
{
    char name[96],path[MAX_PATH],value[32],*end;
    long number;
    if(!key || !suffix || !g_log_dir[0])return fallback;
    if(snprintf(name,sizeof(name),"%s_%s_percent",key,suffix)>=(int)sizeof(name))return fallback;
    career_path_read(path,sizeof(path),g_log_dir,"config","crowd.ini");
    if(!GetPrivateProfileStringA("competition_attendance",name,"",value,sizeof(value),path))return fallback;
    number=strtol(value,&end,10);
    while(*end==' ' || *end=='\t')++end;
    if(end==value || *end || number<0 || number>maximum)return fallback;
    return (int)number;
}

static void crowd_dynamic_limits(int *minimum, int *maximum)
{
    int low = crowd_config_int_from_section(
        "crowd_weights", "minimum_dynamic_percent", 9);
    int high = crowd_config_int_from_section(
        "crowd_weights", "maximum_dynamic_percent", 90);
    if (low < 0 || low > 90)
        low = 9;
    if (high < 0 || high > 90 || high < low)
        high = 90;
    if (minimum)
        *minimum = low;
    if (maximum)
        *maximum = high;
}

static float clamp_dynamic_factor(float value)
{
    int minimum, maximum;
    float low, high;
    crowd_dynamic_limits(&minimum, &maximum);
    low = (float)minimum / 100.0f;
    high = (float)maximum / 100.0f;
    if (value < low)
        return low;
    if (value > high)
        return high;
    return value;
}

/* The crowd plugin's static path is the proven live writer: changing this
 * integer while FIFA is running makes its validated AttribDB writer apply
 * the value.  The career controller publishes the exact rounded factor from
 * the card calculation here whenever that calculation has a real next
 * fixture.  Replace only the digits so comments and all other weights stay
 * byte-for-byte intact. */
static int publish_static_factor_percent(int percent)
{
    char path[MAX_PATH];
    char temporary[MAX_PATH];
    char output[CROWD_CONFIG_FILE_CAPACITY];
    unsigned char input[CROWD_CONFIG_FILE_CAPACITY];
    HANDLE file = INVALID_HANDLE_VALUE;
    HANDLE temp_file = INVALID_HANDLE_VALUE;
    LARGE_INTEGER file_size;
    DWORD bytes_read = 0;
    DWORD bytes_written = 0;
    SIZE_T line_start = 0;
    SIZE_T value_start = 0;
    SIZE_T value_end = 0;
    SIZE_T input_size;
    SIZE_T output_size;
    char number[16];
    BOOL in_crowd_section = FALSE;
    int result = -1;

    if (percent < 0 || percent > 90 || !g_log_dir[0])
        return -1;
    career_path_read(path, sizeof(path), g_log_dir, "config", "crowd.ini");
    if (snprintf(temporary, sizeof(temporary), "%s.runtime.tmp", path)
            >= (int)sizeof(temporary))
        return -1;

    file = CreateFileA(path, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE)
        goto cleanup;
    if (!GetFileSizeEx(file, &file_size) || file_size.QuadPart < 0
        || file_size.QuadPart >= (LONGLONG)sizeof(input))
        goto cleanup;
    input_size = (SIZE_T)file_size.QuadPart;
    if (!ReadFile(file, input, (DWORD)input_size, &bytes_read, NULL)
        || bytes_read != (DWORD)input_size)
        goto cleanup;
    CloseHandle(file);
    file = INVALID_HANDLE_VALUE;

    while (line_start < input_size) {
        SIZE_T line_end = line_start;
        SIZE_T first = line_start;
        while (line_end < input_size && input[line_end] != '\n')
            ++line_end;
        while (first < line_end
            && (input[first] == ' ' || input[first] == '\t'
                || input[first] == '\r'))
            ++first;
        if (first < line_end && input[first] == '[') {
            static const char section[] = "[crowd]";
            SIZE_T content_end = line_end;
            while (content_end > first &&
                (input[content_end - 1U] == ' ' || input[content_end - 1U] == '\t'
                    || input[content_end - 1U] == '\r'))
                --content_end;
            in_crowd_section = content_end - first == sizeof(section) - 1U
                && memcmp(input + first, section, sizeof(section) - 1U) == 0;
        } else if (in_crowd_section) {
            static const char key_prefix[] = "static_factor_percent";
            SIZE_T key_end = first + sizeof(key_prefix) - 1U;
            SIZE_T value_limit = line_end;
            while (value_limit > first
                && (input[value_limit - 1U] == ' ' || input[value_limit - 1U] == '\t'
                    || input[value_limit - 1U] == '\r'))
                --value_limit;
            if (key_end < value_limit
                && memcmp(input + first, key_prefix,
                    sizeof(key_prefix) - 1U) == 0
                && input[key_end] == '=') {
                char current[32];
                SIZE_T current_length;
                value_start = key_end + 1U;
                while (value_start < value_limit
                    && (input[value_start] == ' ' || input[value_start] == '\t'))
                    ++value_start;
                value_end = value_start;
                while (value_end < value_limit && input[value_end] != ';'
                    && input[value_end] != ' ' && input[value_end] != '\t')
                    ++value_end;
                current_length = value_end - value_start;
                if (current_length >= sizeof(current))
                    goto cleanup;
                memcpy(current, input + value_start, current_length);
                current[current_length] = '\0';
                if (atoi(current) == percent) {
                    result = 0;
                    goto cleanup;
                }
                break;
            }
        }
        line_start = line_end < input_size ? line_end + 1U : input_size;
    }
    if (value_start == 0 || value_end < value_start)
        goto cleanup;

    snprintf(number, sizeof(number), "%d", percent);
    output_size = value_start + strlen(number) + input_size - value_end;
    if (output_size >= sizeof(output))
        goto cleanup;
    memcpy(output, input, value_start);
    memcpy(output + value_start, number, strlen(number));
    memcpy(output + value_start + strlen(number), input + value_end,
        input_size - value_end);

    temp_file = CreateFileA(temporary, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (temp_file == INVALID_HANDLE_VALUE)
        goto cleanup;
    if (!WriteFile(temp_file, output, (DWORD)output_size,
            &bytes_written, NULL)
        || bytes_written != (DWORD)output_size
        || !FlushFileBuffers(temp_file))
        goto cleanup;
    CloseHandle(temp_file);
    temp_file = INVALID_HANDLE_VALUE;
    if (!MoveFileExA(temporary, path,
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        goto cleanup;
    result = 1;

cleanup:
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    if (temp_file != INVALID_HANDLE_VALUE)
        CloseHandle(temp_file);
    if (result < 0)
        DeleteFileA(temporary);
    return result;
}

static void log_factor_bridge(const CrowdDecision *decision, int percent,
    int publish_result)
{
    FILE *log = open_log();
    if (!log || !decision)
        return;
    fprintf(log,
        "dynamic_factor_bridge club=%d competition=%d opponent=%d date=%d round=%d factor=%.3f percent=%d result=%s\n",
        decision->club_id, decision->competition_id,
        decision->next_opponent, decision->next_date,
        decision->next_round, decision->factor, percent,
        publish_result > 0 ? "updated" :
            (publish_result == 0 ? "unchanged" : "failed"));
    fclose(log);
}

static uint16_t database_u16(const unsigned char *address)
{
    return (uint16_t)address[0]
        | ((uint16_t)address[1] << 8);
}

static uint32_t database_u32(const unsigned char *address)
{
    return (uint32_t)address[0]
        | ((uint32_t)address[1] << 8)
        | ((uint32_t)address[2] << 16)
        | ((uint32_t)address[3] << 24);
}

static BOOL database_name_is(const unsigned char *address, const char *name)
{
    return address[0] == (unsigned char)name[0]
        && address[1] == (unsigned char)name[1]
        && address[2] == (unsigned char)name[2]
        && address[3] == (unsigned char)name[3];
}

static BOOL database_range_valid(SIZE_T offset, SIZE_T length, SIZE_T size)
{
    return offset <= size && length <= size - offset;
}

static uint32_t database_packed_integer(const unsigned char *record,
    SIZE_T record_size, uint32_t bit_offset, uint32_t bit_depth)
{
    SIZE_T byte_offset = (SIZE_T)(bit_offset / 8U);
    uint32_t shift = bit_offset % 8U;
    uint64_t packed = 0;
    uint32_t mask;
    uint32_t byte_index;

    if (!bit_depth || bit_depth > 32U || byte_offset >= record_size)
        return 0;
    if (bit_depth > 32U - shift || byte_offset + 5U > record_size)
        return 0;
    for (byte_index = 0; byte_index < 5U; ++byte_index)
        packed |= (uint64_t)record[byte_offset + byte_index]
            << (byte_index * 8U);
    mask = bit_depth == 32U ? UINT32_MAX : ((1U << bit_depth) - 1U);
    return (uint32_t)((packed >> shift) & (uint64_t)mask);
}

static void log_database_reputation(const char *path, const char *status)
{
    FILE *log = open_log();
    if (!log)
        return;
    fprintf(log,
        "reputation_source database_%s loaded=%llu leagues=%llu rivals=%llu path=%s\\n",
        status, (unsigned long long)g_reputation_count,
        (unsigned long long)g_league_rating_count,
        (unsigned long long)g_rival_count, path);
    fclose(log);
}

typedef struct DatabaseTableView
{
    SIZE_T records_offset;
    uint32_t record_size;
    uint16_t written_count;
    uint8_t field_count;
} DatabaseTableView;

static BOOL database_find_table_view(const unsigned char *database,
    SIZE_T database_size, DWORD table_count, const char *short_name,
    DatabaseTableView *view)
{
    DWORD table_index;
    SIZE_T directory_end = 0x18U + (SIZE_T)table_count * 8U;
    SIZE_T table_data_offset = directory_end + 4U;

    if (!database_range_valid(0, table_data_offset, database_size))
        return FALSE;
    for (table_index = 0; table_index < table_count; ++table_index) {
        const unsigned char *entry = database + 0x18U
            + (SIZE_T)table_index * 8U;
        SIZE_T table_offset;
        SIZE_T descriptor_offset;
        SIZE_T records_offset;
        uint32_t relative_offset = database_u32(entry + 4U);
        uint32_t record_size;
        uint16_t record_count;
        uint16_t written_count;
        uint8_t field_count;

        if (!database_name_is(entry, short_name)
            || (SIZE_T)relative_offset > database_size - table_data_offset)
            continue;
        table_offset = table_data_offset + (SIZE_T)relative_offset;
        if (!database_range_valid(table_offset, 36U, database_size))
            continue;
        record_size = database_u32(database + table_offset + 4U);
        record_count = database_u16(database + table_offset + 16U);
        written_count = database_u16(database + table_offset + 18U);
        field_count = database[table_offset + 24U];
        if (!record_size || record_size > 4096U || !field_count
            || field_count > 128U || written_count > record_count)
            continue;
        descriptor_offset = table_offset + 36U;
        if ((SIZE_T)field_count > (SIZE_MAX - descriptor_offset) / 16U)
            continue;
        records_offset = descriptor_offset + (SIZE_T)field_count * 16U;
        if ((SIZE_T)written_count >
                (SIZE_MAX - records_offset) / (SIZE_T)record_size
            || !database_range_valid(records_offset,
                (SIZE_T)written_count * (SIZE_T)record_size, database_size))
            continue;
        view->records_offset = records_offset;
        view->record_size = record_size;
        view->written_count = written_count;
        view->field_count = field_count;
        return TRUE;
    }
    return FALSE;
}

static BOOL database_find_field(const unsigned char *database,
    const DatabaseTableView *table, const char *short_name,
    uint32_t *bit_offset, uint32_t *bit_depth)
{
    uint32_t field_index;
    uint32_t total_bits = table->record_size * 8U;
    for (field_index = 0; field_index < table->field_count; ++field_index) {
        const unsigned char *descriptor = database + table->records_offset
            - (SIZE_T)table->field_count * 16U
            + (SIZE_T)field_index * 16U;
        uint32_t storage_type = database_u32(descriptor);
        uint32_t offset = database_u32(descriptor + 4U);
        uint32_t depth = database_u32(descriptor + 12U);
        if (storage_type != 3U || !depth || depth > 32U
            || offset > total_bits || depth > total_bits - offset
            || !database_name_is(descriptor + 8U, short_name))
            continue;
        *bit_offset = offset;
        *bit_depth = depth;
        return TRUE;
    }
    return FALSE;
}

static void append_rival(int team_id1, int team_id2, int type)
{
    if (team_id1 <= 0 || team_id2 <= 0 || team_id1 == team_id2
        || g_rival_count >= CROWD_RIVAL_CAPACITY)
        return;
    g_rivals[g_rival_count].team_id1 = team_id1;
    g_rivals[g_rival_count].team_id2 = team_id2;
    g_rivals[g_rival_count].type = type;
    ++g_rival_count;
}

/* FIFA 16 stores reputation, league tier and rivalries in its proprietary
 * T3DB database. This reader intentionally covers only the verified fields
 * required by the crowd model. */
static BOOL load_team_reputation_from_database(void)
{
    char path[MAX_PATH];
    HANDLE file = INVALID_HANDLE_VALUE;
    LARGE_INTEGER file_size;
    unsigned char *database = NULL;
    SIZE_T database_size;
    SIZE_T read_offset;
    DWORD table_count;
    DatabaseTableView teams_table;
    DatabaseTableView leagues_table;
    DatabaseTableView links_table;
    DatabaseTableView rivals_table;
    CrowdLeagueDefinition league_definitions[CROWD_LEAGUE_DEFINITION_CAPACITY];
    CrowdLeagueLink league_links[CROWD_LEAGUE_LINK_CAPACITY];
    SIZE_T league_definition_count = 0;
    SIZE_T league_link_count = 0;
    BOOL success = FALSE;

    if (!g_log_dir[0])
        return FALSE;
    snprintf(path, sizeof(path), "%s\\..\\data\\db\\fifa_ng_db.db",
        g_log_dir);
    file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE)
        goto cleanup;
    if (!GetFileSizeEx(file, &file_size) || file_size.QuadPart < 0 ||
        (uint64_t)file_size.QuadPart > 64ULL * 1024ULL * 1024ULL)
        goto cleanup;
    database_size = (SIZE_T)file_size.QuadPart;
    if (database_size < 0x20U)
        goto cleanup;
    database = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, database_size);
    if (!database)
        goto cleanup;
    read_offset = 0;
    while (read_offset < database_size) {
        DWORD request = (DWORD)((database_size - read_offset) > 0x100000U
            ? 0x100000U : database_size - read_offset);
        DWORD bytes_read = 0;
        if (!ReadFile(file, database + read_offset, request, &bytes_read, NULL)
            || !bytes_read)
            goto cleanup;
        read_offset += bytes_read;
    }
    if (database[0] != 0x44 || database[1] != 0x42
        || database[2] != 0x00 || database[3] != 0x08
        || database[4] != 0x00 || database[5] != 0x00
        || database[6] != 0x00 || database[7] != 0x00)
        goto cleanup;
    if (database_u32(database + 0x08) > database_size
        || database_u32(database + 0x08) < 0x20U)
        goto cleanup;
    table_count = database_u32(database + 0x10);
    if (!table_count || table_count > 4096U)
        goto cleanup;

    memset(league_definitions, 0, sizeof(league_definitions));
    memset(league_links, 0, sizeof(league_links));
    if (!database_find_table_view(database, database_size, table_count,
            "lyxL", &teams_table))
        goto cleanup;
    {
        uint32_t team_bit, team_depth, domestic_bit, domestic_depth;
        uint32_t international_bit, international_depth;
        uint32_t rival_bit, rival_depth;
        BOOL rival_field;
        uint16_t row;
        if (!database_find_field(database, &teams_table, "mCXg",
                &team_bit, &team_depth)
            || !database_find_field(database, &teams_table, "ppLE",
                &domestic_bit, &domestic_depth)
            || !database_find_field(database, &teams_table, "edvw",
                &international_bit, &international_depth))
            goto cleanup;
        rival_field=database_find_field(database, &teams_table, "erSL",
            &rival_bit, &rival_depth);
        for (row = 0; row < teams_table.written_count
            && g_reputation_count < CROWD_REPUTATION_CAPACITY; ++row) {
            const unsigned char *record = database + teams_table.records_offset
                + (SIZE_T)row * (SIZE_T)teams_table.record_size;
            uint32_t team;
            uint32_t domestic;
            uint32_t international;
            if (record[teams_table.record_size - 1U] & 0x80U)
                continue;
            team = database_packed_integer(record, teams_table.record_size,
                team_bit, team_depth) + 1U;
            domestic = database_packed_integer(record, teams_table.record_size,
                domestic_bit, domestic_depth);
            international = database_packed_integer(record, teams_table.record_size,
                international_bit, international_depth);
            if (!team || domestic > 20U || international > 20U)
                continue;
            g_reputations[g_reputation_count].team_id = (int)team;
            g_reputations[g_reputation_count].domestic = (int)domestic;
            g_reputations[g_reputation_count].international = (int)international;
            ++g_reputation_count;
            if (rival_field) {
                uint32_t rival = database_packed_integer(record,
                    teams_table.record_size, rival_bit, rival_depth) + 1U;
                append_rival((int)team, (int)rival, 1);
            }
        }
    }

    if (database_find_table_view(database, database_size, table_count,
            "LbKk", &rivals_table)) {
        uint32_t team1_bit, team1_depth, team2_bit, team2_depth;
        uint32_t type_bit, type_depth;
        uint16_t row;
        if (database_find_field(database, &rivals_table, "fmFo",
                &team1_bit, &team1_depth)
            && database_find_field(database, &rivals_table, "afAW",
                &team2_bit, &team2_depth)
            && database_find_field(database, &rivals_table, "ytXF",
                &type_bit, &type_depth)) {
            for (row = 0; row < rivals_table.written_count; ++row) {
                const unsigned char *record = database + rivals_table.records_offset
                    + (SIZE_T)row * (SIZE_T)rivals_table.record_size;
                uint32_t team1, team2, type;
                if (record[rivals_table.record_size - 1U] & 0x80U)
                    continue;
                team1=database_packed_integer(record,rivals_table.record_size,
                    team1_bit,team1_depth)+1U;
                team2=database_packed_integer(record,rivals_table.record_size,
                    team2_bit,team2_depth)+1U;
                type=database_packed_integer(record,rivals_table.record_size,
                    type_bit,type_depth);
                append_rival((int)team1,(int)team2,(int)type);
            }
        }
    }

    if (database_find_table_view(database, database_size, table_count,
            "onMQ", &leagues_table)) {
        uint32_t league_id_bit, league_id_depth, level_bit, level_depth;
        uint16_t row;
        if (database_find_field(database, &leagues_table, "aQrQ",
                &league_id_bit, &league_id_depth)
            && database_find_field(database, &leagues_table, "paPI",
                &level_bit, &level_depth)) {
            for (row = 0; row < leagues_table.written_count
                && league_definition_count < CROWD_LEAGUE_DEFINITION_CAPACITY;
                ++row) {
                const unsigned char *record = database + leagues_table.records_offset
                    + (SIZE_T)row * (SIZE_T)leagues_table.record_size;
                int league_id, level;
                if (record[leagues_table.record_size - 1U] & 0x80U)
                    continue;
                league_id=(int)database_packed_integer(record,
                    leagues_table.record_size,league_id_bit,league_id_depth)+1;
                level=(int)database_packed_integer(record,
                    leagues_table.record_size,level_bit,level_depth)+1;
                if (league_id>0 && level>=1 && level<=7) {
                    league_definitions[league_definition_count].league_id=league_id;
                    league_definitions[league_definition_count].level=level;
                    ++league_definition_count;
                }
            }
        }
    }

    if (database_find_table_view(database, database_size, table_count,
            "qdZF", &links_table)) {
        uint32_t team_bit, team_depth, league_id_bit, league_id_depth;
        uint16_t row;
        if (database_find_field(database, &links_table, "mCXg",
                &team_bit, &team_depth)
            && database_find_field(database, &links_table, "aQrQ",
                &league_id_bit, &league_id_depth)) {
            for (row = 0; row < links_table.written_count
                && league_link_count < CROWD_LEAGUE_LINK_CAPACITY; ++row) {
                const unsigned char *record = database + links_table.records_offset
                    + (SIZE_T)row * (SIZE_T)links_table.record_size;
                if (record[links_table.record_size - 1U] & 0x80U)
                    continue;
                league_links[league_link_count].team_id=(int)
                    (database_packed_integer(record,links_table.record_size,
                        team_bit,team_depth)+1U);
                league_links[league_link_count].league_id=(int)
                    (database_packed_integer(record,links_table.record_size,
                        league_id_bit,league_id_depth)+1U);
                ++league_link_count;
            }
        }
    }

    {
        SIZE_T link_index, definition_index;
        for (link_index = 0; link_index < league_link_count
            && g_league_rating_count < CROWD_LEAGUE_LINK_CAPACITY; ++link_index) {
            for (definition_index = 0; definition_index < league_definition_count;
                ++definition_index) {
                if (league_links[link_index].league_id ==
                    league_definitions[definition_index].league_id) {
                    g_league_ratings[g_league_rating_count].team_id=
                        league_links[link_index].team_id;
                    g_league_ratings[g_league_rating_count].level=
                        league_definitions[definition_index].level;
                    ++g_league_rating_count;
                    break;
                }
            }
        }
    }

    success = g_reputation_count != 0;
    if (!success)
        goto cleanup;
    log_database_reputation(path, "loaded");

cleanup:
    if (database)
        HeapFree(GetProcessHeap(), 0, database);
    if (file != INVALID_HANDLE_VALUE)
        CloseHandle(file);
    if (!success)
        log_database_reputation(path, "unavailable");
    return success;
}

static void load_team_reputation(void)
{
    if (InterlockedCompareExchange(&g_reputation_loaded, 1, 0) != 0)
        return;
    (void)load_team_reputation_from_database();
}

float crowd_runtime_team_reputation(int team_id)
{
    SIZE_T index;
    load_team_reputation();
    for(index=0;index<g_reputation_count;++index) {
        const CrowdReputation *item=g_reputations+index;
        if(item->team_id==team_id)
            return ((float)item->domestic+(float)item->international)/40.0f;
    }
    return 0.50f;
}

int crowd_runtime_team_reputation_available(int team_id)
{
    SIZE_T index;
    load_team_reputation();
    for (index = 0; index < g_reputation_count; ++index)
        if (g_reputations[index].team_id == team_id)
            return 1;
    return 0;
}

float crowd_runtime_league_reputation(int team_id)
{
    SIZE_T index;
    load_team_reputation();
    for (index = 0; index < g_league_rating_count; ++index) {
        const CrowdLeagueRating *item = g_league_ratings + index;
        if (item->team_id == team_id) {
            float level = (float)item->level;
            /* Keep lower leagues relevant: level 1 is 1.00, level 7 is
             * 0.30, with a linear scale between them. */
            return 0.30f + 0.70f * (1.0f - ((level - 1.0f) / 6.0f));
        }
    }
    return 0.50f;
}

float crowd_runtime_rivalry(int team_id, int opponent_id)
{
    SIZE_T index;
    float best = 0.0f;
    load_team_reputation();
    if (team_id <= 0 || opponent_id <= 0 || team_id == opponent_id)
        return 0.0f;
    for (index = 0; index < g_rival_count; ++index) {
        const CrowdRival *item = g_rivals + index;
        BOOL matches = (item->team_id1 == team_id
                && item->team_id2 == opponent_id)
            || (item->team_id1 == opponent_id
                && item->team_id2 == team_id);
        float score;
        if (!matches)
            continue;
        /* Type 1 is the database's strongest derby/classic category.
         * Type 2 is a regional rivalry; type 0 is a lighter rivalry. */
        score = item->type == 1 ? 1.0f :
            (item->type == 2 ? 0.75f : 0.45f);
        if (score > best)
            best = score;
    }
    return best;
}

static void log_decision(const CrowdDecision *decision)
{
    FILE *log = open_log();
    if (!log)
        return;
    if (decision) {
        fprintf(log,
            "decision enabled=%d club=%d competition=%d rank=%d/%d played=%d "
            "form=%.3f reputation=%.3f league=%.3f rivalry=%.3f "
            "position=%.3f progress=%.3f danger=%.3f "
            "last_result=%d last_margin=%d streak=%d streak_sign=%d gap_safety=%d "
            "momentum=%.3f escape=%.3f importance=%.3f phase=%.3f international_bonus=%.3f factor=%.3f "
            "next_opponent=%d home=%d date=%d round=%d\\n",
            decision->enabled, decision->club_id, decision->competition_id,
            decision->rank, decision->team_count, decision->played,
            decision->form, decision->reputation, decision->league_reputation,
            decision->rivalry, decision->position_score,
            decision->season_progress, decision->danger,
            decision->last_result, decision->last_margin, decision->streak,
            decision->streak_sign, decision->points_gap_to_safety,
            decision->momentum, decision->escape_opportunity,
            decision->importance, decision->phase,
            decision->international_bonus, decision->factor, decision->next_opponent, decision->next_is_home,
            decision->next_date, decision->next_round);
    } else {
        fputs("decision enabled=0 reason=context_reset\\n", log);
    }
    fclose(log);
}

void crowd_runtime_start(const char *log_dir)
{
    if (log_dir)
        lstrcpynA(g_log_dir, log_dir, sizeof(g_log_dir));
    InterlockedExchange(&g_log_enabled,
        retirement_engine_local_logging_enabled(g_log_dir));
    if (InterlockedCompareExchange(&g_started, 1, 0) != 0)
        return;
    InterlockedExchange(&g_factor_bits, float_bits(CROWD_DEFAULT_FACTOR));
    /* The former heuristic memory scanner was removed after a dump showed it
     * could target unrelated game data. Dynamic attendance uses the config
     * bridge instead; this module does not write arbitrary FIFA memory. */
    {
        FILE *log = open_log();
        if (log) {
            fputs("attendance_scanner disabled_after_dump_safe_mode\n", log);
            fclose(log);
        }
    }
}

void crowd_runtime_disable(void)
{
    InterlockedExchange(&g_enabled, 0);
    if (InterlockedCompareExchange(&g_last_logged_enabled, 0, 1) == 1)
        log_decision(NULL);
}

void crowd_runtime_set_decision(const CrowdDecision *decision)
{
    CrowdDecision copy;
    int automatic_controller;
    int static_percent;
    if (!decision || !decision->enabled) {
        crowd_runtime_disable();
        return;
    }
    copy = *decision;
    automatic_controller = crowd_config_int(
        "automatic_dynamic_controller", 1) != 0;
    static_percent = crowd_config_int("static_factor_percent", -1);
    if (automatic_controller) {
        int percent, minimum, maximum;
        int publish_result = 0;
        crowd_dynamic_limits(&minimum, &maximum);
        copy.factor = clamp_dynamic_factor(copy.factor);
        percent = (int)(copy.factor * 100.0f + 0.5f);
        if (percent < minimum) percent = minimum;
        if (percent > maximum) percent = maximum;
        if (copy.next_opponent > 0 && copy.next_date > 0) {
            AcquireSRWLockExclusive(&g_crowd_config_lock);
            publish_result = publish_static_factor_percent(percent);
            ReleaseSRWLockExclusive(&g_crowd_config_lock);
            log_factor_bridge(&copy, percent, publish_result);
        }
    } else if (static_percent >= 0 && static_percent <= 90) {
        /* Keep the preview card consistent with an explicit static test. */
        copy.factor = (float)static_percent / 100.0f;
    } else {
        copy.factor = clamp_factor(copy.factor);
    }
    InterlockedExchange(&g_factor_bits, float_bits(copy.factor));
    InterlockedExchange(&g_enabled, 1);
    if (InterlockedCompareExchange(&g_last_logged_enabled, 1, 0) == 0)
        log_decision(&copy);
    else {
        FILE *log = open_log();
        if (log) {
            fprintf(log, "decision_update club=%d competition=%d rank=%d/%d reputation=%.3f league=%.3f rivalry=%.3f position=%.3f progress=%.3f danger=%.3f last_result=%d last_margin=%d streak=%d gap_safety=%d momentum=%.3f escape=%.3f factor=%.3f\\n",
                copy.club_id, copy.competition_id, copy.rank, copy.team_count,
                copy.reputation, copy.league_reputation, copy.rivalry,
                copy.position_score, copy.season_progress,
                copy.danger, copy.last_result, copy.last_margin, copy.streak,
                copy.points_gap_to_safety, copy.momentum,
                copy.escape_opportunity, copy.factor);
            fclose(log);
        }
    }
}

int crowd_runtime_attendance_percent(void)
{
    float factor;
    int percent;
    if (InterlockedCompareExchange(&g_enabled, 0, 0) == 0)
        return -1;
    if (!crowd_config_int("automatic_dynamic_controller", 1)) {
        int static_percent = crowd_config_int("static_factor_percent", -1);
        if (static_percent >= 0 && static_percent <= 90)
            return static_percent;
    }
    factor = clamp_dynamic_factor(bits_float(InterlockedCompareExchange(
        &g_factor_bits, float_bits(CROWD_DEFAULT_FACTOR), 0)));
    percent = (int)(factor * 100.0f + 0.5f);
    if (percent < 1 || percent > 100)
        return -1;
    return percent;
}
