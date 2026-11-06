#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/features/retirement/retirement_engine.h"

int main(int argc, char **argv)
{
    RetirementApplyResult result;
    if (argc == 3 && _stricmp(argv[2], "calendar") == 0) {
        unsigned int first = 0, second = 0;
        int ok = retirement_engine_get_transfer_window_ends(argv[1], &first, &second);
        printf("calendar_ok=%d window_end1=%04u window_end2=%04u\n",
            ok, first, second);
        return ok ? 0 : 1;
    }
    if (argc >= 3 && _stricmp(argv[2], "buffer") == 0) {
        FILE *file = fopen(argv[1], "rb");
        long file_size;
        unsigned char *buffer;
        size_t read_size;
        int ok;
        if (!file) {
            fprintf(stderr, "buffer test: DATA could not be opened\n");
            return 3;
        }
        if (fseek(file, 0, SEEK_END) != 0
            || (file_size = ftell(file)) <= 0
            || fseek(file, 0, SEEK_SET) != 0) {
            fclose(file);
            fprintf(stderr, "buffer test: DATA size could not be read\n");
            return 3;
        }
        buffer = (unsigned char *)malloc((size_t)file_size);
        if (!buffer) {
            fclose(file);
            fprintf(stderr, "buffer test: allocation failed\n");
            return 3;
        }
        read_size = fread(buffer, 1, (size_t)file_size, file);
        fclose(file);
        if (read_size != (size_t)file_size) {
            free(buffer);
            fprintf(stderr, "buffer test: DATA could not be read\n");
            return 3;
        }
        memset(&result, 0, sizeof(result));
        ok = retirement_engine_apply_buffer(buffer, (SIZE_T)file_size,
            "remove_retirement", argc > 3 ? atoi(argv[3]) : 18, &result);
        printf("buffer_ok=%d status=%d message=%s changed=%u retiring=%u crc_before=%08X crc_after=%08X\n",
            ok, result.status, result.message, result.players_changed,
            result.players_retiring, result.crc_before, result.crc_after);
        free(buffer);
        return ok ? 0 : 1;
    }
    if (argc < 3) {
        fprintf(stderr, "usage: retirement_engine_test DATA mode [age]\n");
        return 2;
    }
    memset(&result, 0, sizeof(result));
    if (!retirement_engine_apply_file(argv[1], argv[2],
            argc > 3 ? atoi(argv[3]) : 18, &result)) {
        printf("status=%d message=%s changed=%u retiring=%u\n",
            result.status, result.message, result.players_changed,
            result.players_retiring);
        return 1;
    }
    printf("status=%d message=%s changed=%u retiring=%u crc_before=%08X crc_after=%08X backup_data=%s backup_index=%s\n",
        result.status, result.message, result.players_changed,
        result.players_retiring, result.crc_before, result.crc_after,
        result.backup_data, result.backup_index);
    return 0;
}
