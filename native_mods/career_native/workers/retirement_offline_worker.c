#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/features/retirement/retirement_engine.h"
#include "../src/platform/mod_paths.h"

#define RETIREMENT_FEEDBACK_RESULT 0x16401U

static const char *argument_value(int argc, char **argv, const char *name)
{
    int index;
    for (index = 1; index + 1 < argc; ++index) {
        if (_stricmp(argv[index], name) == 0)
            return argv[index + 1];
    }
    return NULL;
}

/* Flags without a value cannot use argument_value(): the latter deliberately
 * only visits argv entries that have a following value. */
static int argument_present(int argc, char **argv, const char *name)
{
    int index;
    for (index = 1; index < argc; ++index) {
        if (_stricmp(argv[index], name) == 0)
            return 1;
    }
    return 0;
}

static ULONGLONG worker_elapsed_ms(ULONGLONG started_at)
{
    ULONGLONG now = GetTickCount64();
    return now >= started_at ? now - started_at : 0;
}

static void worker_log_event(const char *mod_dir, const char *event,
    const char *data_path, const char *mode, ULONGLONG elapsed_ms)
{
    char log_path[MAX_PATH];
    SYSTEMTIME now;
    FILE *file;
    if (!mod_dir || !*mod_dir || !event
        || !retirement_engine_local_logging_enabled(mod_dir)) return;
    career_path_logs(mod_dir);
    snprintf(log_path, sizeof(log_path), "%s\\logs\\career_retirement_background.log",
        mod_dir);
    file = fopen(log_path, "ab");
    if (!file) return;
    GetLocalTime(&now);
    fprintf(file,
        "event=%s timestamp=%04u-%02u-%02uT%02u:%02u:%02u.%03u "
        "elapsed_ms=%llu pid=%lu data=%s mode=%s\n",
        event, now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute,
        now.wSecond, now.wMilliseconds, (unsigned long long)elapsed_ms,
        (unsigned long)GetCurrentProcessId(), data_path ? data_path : "",
        mode && *mode ? mode : "");
    fclose(file);
}

static void worker_log_result(const char *mod_dir, const char *data_path,
    const char *mode, ULONGLONG elapsed_ms,
    const RetirementApplyResult *result)
{
    char log_path[MAX_PATH];
    SYSTEMTIME now;
    FILE *file;
    if (!mod_dir || !*mod_dir || !result
        || !retirement_engine_local_logging_enabled(mod_dir)) return;
    career_path_logs(mod_dir);
    snprintf(log_path, sizeof(log_path), "%s\\logs\\career_retirement_background.log",
        mod_dir);
    file = fopen(log_path, "ab");
    if (!file) return;
    GetLocalTime(&now);
    fprintf(file,
        "event=worker_result timestamp=%04u-%02u-%02uT%02u:%02u:%02u.%03u "
        "elapsed_ms=%llu status=%d changed=%u retiring=%u budget_before=%u "
        "budget_after=%u budget_added=%u "
        "crc_before=%08X crc_after=%08X message=%s data=%s mode=%s "
        "backup_data=%s backup_index=%s\n",
        now.wYear, now.wMonth, now.wDay, now.wHour, now.wMinute,
        now.wSecond, now.wMilliseconds, (unsigned long long)elapsed_ms,
        result->status, result->players_changed, result->players_retiring,
        result->transfer_budget_before, result->transfer_budget_after,
        result->transfer_budget_added,
        result->crc_before, result->crc_after, result->message,
        data_path ? data_path : "", mode && *mode ? mode : "",
        result->backup_data, result->backup_index);
    fclose(file);
}

static void worker_show_feedback(const char *text, UINT beep_type,
    int allow_modal_fallback)
{
    HWND window;
    COPYDATASTRUCT copy;
    DWORD_PTR ignored = 0;
    if (!text || !*text)
        return;
    MessageBeep(beep_type);
    window = FindWindowA("FifaRetirementFeedbackWindow", NULL);
    if (window) {
        memset(&copy, 0, sizeof(copy));
        copy.dwData = RETIREMENT_FEEDBACK_RESULT;
        copy.cbData = (DWORD)strlen(text) + 1U;
        copy.lpData = (PVOID)text;
        if (SendMessageTimeoutA(window, WM_COPYDATA, 0, (LPARAM)&copy,
                SMTO_ABORTIFHUNG | SMTO_BLOCK, 1500U, &ignored))
            return;
    }
    if (allow_modal_fallback)
        (void)MessageBoxA(NULL, text, "FIFA Friends - Aposentadoria",
            MB_OK | MB_SETFOREGROUND | MB_TOPMOST);
}

static void worker_show_success_feedback(const char *mode, int target_age,
    const RetirementApplyResult *result)
{
    char text[512];
    if (mode && (_stricmp(mode, "add_transfer_budget_1m") == 0
            || _stricmp(mode, "add_transfer_budget_3m") == 0)) {
        if (result && result->transfer_budget_added > 0U)
            snprintf(text, sizeof(text),
                "Orcamento de transferencias atualizado.\n"
                "+%u adicionados. Novo total: %u.\n"
                "O save esta pronto para reabrir a carreira.",
                result->transfer_budget_added,
                result->transfer_budget_after);
        else
            lstrcpyA(text,
                "O orcamento de transferencias ja esta no limite maximo.\n"
                "Nenhum valor foi alterado; o save pode ser reaberto.");
        worker_show_feedback(text, MB_OK, 0);
        return;
    }
    if (mode && _stricmp(mode, "remove_and_rejuvenate") == 0) {
        if (result && result->players_changed > 0U)
            snprintf(text, sizeof(text),
                "Aposentadoria removida e idade redefinida para %d anos em "
                "%u jogador(es).\nO save foi validado e esta pronto para "
                "reabrir a carreira.", target_age, result->players_changed);
        else
            lstrcpyA(text,
                "Processamento de aposentadoria por idade concluido.\n"
                "Nenhuma alteracao adicional era necessaria; o save esta "
                "pronto para reabrir.");
    } else if (result && result->players_changed > 0U) {
        snprintf(text, sizeof(text),
            "Aposentadoria removida de %u jogador(es).\n"
            "O save foi validado e esta pronto para reabrir a carreira.",
            result->players_changed);
    } else {
        lstrcpyA(text,
            "Processamento concluido sem alteracoes.\n"
            "Nenhuma alteracao adicional era necessaria; o save esta "
            "pronto para reabrir.");
    }
    /* Success is always reported in the non-modal FIFA overlay. */
    worker_show_feedback(text, MB_OK, 0);
}

static int parse_unsigned(const char *value, unsigned long *result)
{
    char *end = NULL;
    unsigned long parsed;
    if (!value || !*value || !result) return 0;
    parsed = strtoul(value, &end, 10);
    if (end == value || *end != '\0') return 0;
    *result = parsed;
    return 1;
}

static int parse_process_id(const char *value, DWORD *result)
{
    unsigned long parsed;
    if (!parse_unsigned(value, &parsed) || parsed == 0UL
        || parsed > 0xFFFFFFFFUL)
        return 0;
    *result = (DWORD)parsed;
    return 1;
}

static int wait_for_parent_exit(DWORD process_id)
{
    HANDLE process;
    if (!process_id) return 1;
    process = OpenProcess(SYNCHRONIZE, FALSE, process_id);
    if (!process) {
        /* The parent may already have exited between CreateProcess and this
         * call.  There is no process handle to wait on in that case. */
        return GetLastError() == ERROR_INVALID_PARAMETER;
    }
    (void)WaitForSingleObject(process, INFINITE);
    CloseHandle(process);
    return 1;
}

static int read_file_state(const char *path, ULONGLONG *size,
    ULONGLONG *write_time)
{
    WIN32_FILE_ATTRIBUTE_DATA attributes;
    ULARGE_INTEGER file_size;
    ULARGE_INTEGER timestamp;
    if (!path || !size || !write_time
        || !GetFileAttributesExA(path, GetFileExInfoStandard, &attributes))
        return 0;
    file_size.LowPart = attributes.nFileSizeLow;
    file_size.HighPart = attributes.nFileSizeHigh;
    timestamp.LowPart = attributes.ftLastWriteTime.dwLowDateTime;
    timestamp.HighPart = attributes.ftLastWriteTime.dwHighDateTime;
    *size = file_size.QuadPart;
    *write_time = timestamp.QuadPart;
    return 1;
}

static int can_open_exclusive(const char *path)
{
    HANDLE file;
    if (!path || !*path) return 0;
    file = CreateFileA(path, GENERIC_READ, 0, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    CloseHandle(file);
    return 1;
}

static int wait_for_stable_data(const char *path, unsigned quiet_ms)
{
    ULONGLONG last_size = 0;
    ULONGLONG last_write_time = 0;
    ULONGLONG last_index_size = 0;
    ULONGLONG last_index_write_time = 0;
    unsigned stable_ms = 0;
    unsigned waited_ms = 0;
    char index_path[2048];
    char *slash;
    lstrcpynA(index_path, path, sizeof(index_path));
    slash = strrchr(index_path, '\\');
    if (!slash) return 0;
    lstrcpyA(slash + 1, "INDEX");
    if (quiet_ms < 1000U) quiet_ms = 2500U;
    if (quiet_ms > 10000U) quiet_ms = 10000U;
    /* Leaving Career Mode normally releases DATA while fifa16.exe remains
     * open.  Keep waiting long enough for that transition, but still bound
     * the worker so a malformed request cannot live forever. */
    while (waited_ms < 600000U) {
        ULONGLONG size;
        ULONGLONG write_time;
        ULONGLONG index_size;
        ULONGLONG index_write_time;
        if (read_file_state(path, &size, &write_time)
            && read_file_state(index_path, &index_size, &index_write_time)
            && size >= 1024ULL * 1024ULL
            && can_open_exclusive(path)
            && can_open_exclusive(index_path)) {
            if (size == last_size && write_time == last_write_time
                && index_size == last_index_size
                && index_write_time == last_index_write_time)
                stable_ms += 250U;
            else {
                last_size = size;
                last_write_time = write_time;
                last_index_size = index_size;
                last_index_write_time = index_write_time;
                stable_ms = 0;
            }
            if (stable_ms >= quiet_ms) return 1;
        } else {
            last_size = 0;
            last_write_time = 0;
            last_index_size = 0;
            last_index_write_time = 0;
            stable_ms = 0;
        }
        Sleep(250U);
        waited_ms += 250U;
    }
    return 0;
}

static void print_result(const char *path, const RetirementApplyResult *result)
{
    printf("status=%d message=%s changed=%u retiring=%u budget_before=%u "
           "budget_after=%u budget_added=%u crc_before=%08X "
           "crc_after=%08X data=%s backup_data=%s backup_index=%s\n",
        result->status, result->message, result->players_changed,
        result->players_retiring, result->transfer_budget_before,
        result->transfer_budget_after, result->transfer_budget_added,
        result->crc_before, result->crc_after,
        path ? path : "", result->backup_data, result->backup_index);
}

int main(int argc, char **argv)
{
    const char *pid_text = argument_value(argc, argv, "--pid");
    const char *data_path = argument_value(argc, argv, "--data");
    const char *mode = argument_value(argc, argv, "--mode");
    const char *age_text = argument_value(argc, argv, "--age");
    const char *quiet_text = argument_value(argc, argv, "--quiet-ms");
    const char *mod_dir = argument_value(argc, argv, "--mod-dir");
    int wait_parent = argument_present(argc, argv, "--wait-parent-exit");
    DWORD process_id;
    unsigned long age_value = 18UL;
    unsigned long quiet_value = 2500UL;
    ULONGLONG started_at;
    RetirementApplyResult result;
    char feedback[512];
    if (!data_path || !*data_path || !parse_process_id(pid_text, &process_id)) {
        fprintf(stderr, "usage: retirement_offline_worker.exe --pid PID "
            "--data DATA --mode MODE --age AGE --quiet-ms MS --mod-dir DIR\n");
        return 2;
    }
    if (age_text && (!parse_unsigned(age_text, &age_value) || age_value > 80UL))
        age_value = 18UL;
    if (quiet_text && (!parse_unsigned(quiet_text, &quiet_value)
            || quiet_value < 1000UL || quiet_value > 10000UL))
        quiet_value = 2500UL;
    if (mod_dir && *mod_dir)
        retirement_engine_set_mod_dir(mod_dir);
    started_at = GetTickCount64();
    worker_log_event(mod_dir, "worker_started", data_path, mode, 0);
    if (wait_parent) {
        worker_log_event(mod_dir, "worker_waiting_game_exit", data_path,
            mode, worker_elapsed_ms(started_at));
        if (!wait_for_parent_exit(process_id)) {
            worker_log_event(mod_dir, "worker_error_parent_wait", data_path,
                mode, worker_elapsed_ms(started_at));
            worker_show_feedback(
                "Nao foi possivel confirmar o fechamento completo do FIFA.\n"
                "A operacao foi interrompida; verifique o save antes de reabrir.",
                MB_ICONERROR, 1);
            return 3;
        }
        worker_log_event(mod_dir, "worker_game_exited", data_path, mode,
            worker_elapsed_ms(started_at));
    }
    worker_log_event(mod_dir, "worker_waiting_save_stability", data_path,
        mode, worker_elapsed_ms(started_at));
    if (!wait_for_stable_data(data_path, (unsigned)quiet_value)) {
        worker_log_event(mod_dir, "worker_error_save_not_stable", data_path,
            mode, worker_elapsed_ms(started_at));
        fprintf(stderr, "DATA nao estabilizou: %s\n", data_path);
        snprintf(feedback, sizeof(feedback),
            "O save nao ficou livre e estavel depois de sair da carreira.\n"
            "Nenhuma alteracao foi aplicada. Confira se a carreira foi "
            "fechada e aguarde qualquer salvamento terminar.\nArquivo: %s",
            data_path);
        worker_show_feedback(feedback, MB_ICONERROR, 1);
        return 4;
    }
    memset(&result, 0, sizeof(result));
    if (!retirement_engine_apply_file(data_path,
            mode && *mode ? mode : "remove_retirement", (int)age_value,
            &result)) {
        print_result(data_path, &result);
        worker_log_result(mod_dir, data_path, mode, worker_elapsed_ms(started_at),
            &result);
        snprintf(feedback, sizeof(feedback),
            "Nao foi possivel aplicar a operacao no save.\n%s\n"
            "Confira o backup antes de abrir ou salvar esta carreira.",
            result.message[0] ? result.message : "Erro sem detalhes adicionais.");
        worker_show_feedback(feedback, MB_ICONERROR, 1);
        return 5;
    }
    print_result(data_path, &result);
    worker_log_result(mod_dir, data_path, mode, worker_elapsed_ms(started_at),
        &result);
    worker_show_success_feedback(mode, (int)age_value, &result);
    return 0;
}
