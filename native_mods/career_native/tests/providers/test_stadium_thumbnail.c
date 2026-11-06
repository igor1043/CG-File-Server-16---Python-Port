#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "../../src/platform/stadium_thumbnail.h"
#include "stadium_thumbnail_fixture.h"
#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); return 1; \
} } while (0)

static unsigned big_u32(const unsigned char *p)
{
    return (unsigned)p[0] << 24 | (unsigned)p[1] << 16 | (unsigned)p[2] << 8 | p[3];
}

static int test_package(const char *dds, const char *directory)
{
    char key[40], same[40], path[MAX_PATH];
    unsigned char data[2048], pixels[144];
    unsigned offset, size, i;
    DWORD got;
    HANDLE file;
    FILETIME before, after;
    CHECK(stadium_thumbnail_package(dds, directory, key, sizeof(key)) == STADIUM_IMAGE_CONVERTED);
    CHECK(!strncmp(key, "cmphoto_", 8) && strlen(key) == 24);
    snprintf(path, sizeof(path), "%s\\stadium_%s.big", directory, key);
    file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE);
    CHECK(GetFileTime(file, NULL, NULL, &before));
    CHECK(ReadFile(file, data, sizeof(data), &got, NULL) && got >= 1216);
    CloseHandle(file);
    CHECK(!memcmp(data, "BIG4", 4) && big_u32(data + 8) == 6 && big_u32(data + 12) == 88);
    CHECK(big_u32(data + 16) == 88 && big_u32(data + 20) == 584);
    CHECK(!memcmp(data + 88, "Apt Data:1:7:8", 13));
    CHECK(*(DWORD *)(data + 88 + 0x98) == 2 && *(DWORD *)(data + 88 + 0x9c) == 2);
    CHECK(*(float *)(data + 88 + 0x118) == 2 && *(float *)(data + 88 + 0x11c) == 2);
    CHECK(*(float *)(data + 704 + 0xe0) == 2 && *(float *)(data + 704 + 0xe4) == 2);
    offset = big_u32(data + 48); size = big_u32(data + 52);
    CHECK(offset == 1024 && size == 144 && !memcmp(data + 56, "2\0", 2));
    file = CreateFileA(dds, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE && ReadFile(file, pixels, 144, &got, NULL) && got == 144);
    CloseHandle(file);
    CHECK(!memcmp(data + offset, pixels, 144)); /* No resampling or compression. */
    CHECK(stadium_thumbnail_package(dds, directory, same, sizeof(same)) == STADIUM_IMAGE_CURRENT && !strcmp(same, key));
    file = CreateFileA(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE && GetFileTime(file, NULL, NULL, &after));
    CHECK(CompareFileTime(&before, &after) == 0);
    CHECK(WriteFile(file, "FAIL", 4, &got, NULL)); CloseHandle(file);
    CHECK(stadium_thumbnail_package(dds, directory, same, sizeof(same)) == STADIUM_IMAGE_CONVERTED && !strcmp(same, key));
    CHECK(!stadium_thumbnail_package(dds, directory, same, 8) && !same[0]);
    DeleteFileA(path);
    /* A changed source must use another resource name to bypass cached fallback. */
    file = CreateFileA(dds, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE && SetFilePointer(file, 128, NULL, FILE_BEGIN) == 128);
    pixels[128] = 10;
    CHECK(WriteFile(file, pixels + 128, 1, &got, NULL)); CloseHandle(file);
    CHECK(stadium_thumbnail_package(dds, directory, same, sizeof(same)) == STADIUM_IMAGE_CONVERTED && strcmp(same, key));
    snprintf(path, sizeof(path), "%s\\stadium_%s.big", directory, same); DeleteFileA(path);
    file = CreateFileA(dds, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE && WriteFile(file, "FAIL", 4, &got, NULL)); CloseHandle(file);
    for (i = 0; i < sizeof(same); ++i) same[i] = 'x';
    CHECK(!stadium_thumbnail_package(dds, directory, same, sizeof(same)) && !same[0]);
    return 0;
}

int main(int argc, char **argv)
{
    char source[MAX_PATH], destination[MAX_PATH], copied[MAX_PATH], root[MAX_PATH];
    unsigned char bytes[144];
    DWORD count;
    HANDLE file;
    WIN32_FILE_ATTRIBUTE_DATA before, after;
    ULARGE_INTEGER changed;
    FILETIME changed_time;
    int result;
    if (argc == 4 && !strcmp(argv[1], "--package")) {
        char key[40];
        result = stadium_thumbnail_package(argv[2], argv[3], key, sizeof(key));
        printf("stadium_package result=%d key=%s\n", result, key);
        return result ? 0 : 1;
    }
    if (argc == 3) {
        result = stadium_thumbnail_sync(argv[1], argv[2]);
        printf("stadium_thumbnail result=%d source=%s destination=%s\n", result, argv[1], argv[2]);
        return result ? 0 : 1;
    }
    CHECK(GetTempPathA(sizeof(root), root));
    CHECK(GetTempFileNameA(root, "s16", 0, source));
    CHECK(snprintf(destination, sizeof(destination), "%s.dds", source) > 0);
    CHECK(snprintf(copied, sizeof(copied), "%s.copy.dds", source) > 0);
    CHECK(write_stadium_fixture(source));
    CHECK(GetFileAttributesExA(source, GetFileExInfoStandard, &before));
    CHECK(stadium_thumbnail_sync(source, destination) == STADIUM_IMAGE_CONVERTED);
    CHECK(stadium_thumbnail_valid_dds(destination));
    file = CreateFileA(destination, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE);
    CHECK(ReadFile(file, bytes, sizeof(bytes), &count, NULL) && count == sizeof(bytes));
    CloseHandle(file);
    CHECK(*(DWORD *)(bytes + 12) == 2 && *(DWORD *)(bytes + 16) == 2);
    CHECK(bytes[128] == 0 && bytes[129] == 0 && bytes[130] == 255 && bytes[131] == 255);
    CHECK(bytes[132] == 0 && bytes[133] == 255 && bytes[134] == 0 && bytes[135] == 255);
    CHECK(stadium_thumbnail_sync(source, destination) == STADIUM_IMAGE_CURRENT);
    CHECK(GetFileAttributesExA(source, GetFileExInfoStandard, &after));
    CHECK(before.nFileSizeLow == after.nFileSizeLow &&
        CompareFileTime(&before.ftLastWriteTime, &after.ftLastWriteTime) == 0);
    CHECK(stadium_thumbnail_sync(destination, copied) == STADIUM_IMAGE_COPIED);
    CHECK(stadium_thumbnail_valid_dds(copied));
    CHECK(stadium_thumbnail_sync("missing-stadium-image.jpg", destination) == 0);
    CHECK(stadium_thumbnail_valid_dds(destination));
    file = CreateFileA(source, FILE_WRITE_ATTRIBUTES, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE);
    changed.LowPart = before.ftLastWriteTime.dwLowDateTime;
    changed.HighPart = before.ftLastWriteTime.dwHighDateTime;
    changed.QuadPart += 10000000;
    changed_time.dwLowDateTime = changed.LowPart; changed_time.dwHighDateTime = changed.HighPart;
    CHECK(SetFileTime(file, NULL, NULL, &changed_time)); CloseHandle(file);
    CHECK(stadium_thumbnail_sync(source, destination) == STADIUM_IMAGE_CONVERTED);
    file = CreateFileA(source, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE);
    CHECK(WriteFile(file, "broken", 6, &count, NULL)); CloseHandle(file);
    CHECK(stadium_thumbnail_sync(source, destination) == 0);
    file = CreateFileA(copied, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    CHECK(file != INVALID_HANDLE_VALUE);
    CHECK(WriteFile(file, "DDS ", 4, &count, NULL)); CloseHandle(file);
    CHECK(!stadium_thumbnail_valid_dds(copied));
    CHECK(stadium_thumbnail_sync(copied, destination) == 0);
    CHECK(stadium_thumbnail_sync(source, copied) == 0);
    /* Restore a valid image to exercise the actual six-member movie writer. */
    CHECK(write_stadium_fixture(source));
    CHECK(stadium_thumbnail_sync(source, copied) != 0);
    CHECK(test_package(copied, root) == 0);
    {char native_path[MAX_PATH],native_key[40];
     CHECK(!stadium_thumbnail_native(root,156,native_key,sizeof(native_key)));
     snprintf(native_path,sizeof(native_path),"%sstadium_156_0.big",root);
     /* Only the native BIG header is needed to locate an existing movie. */
     file=CreateFileA(native_path,GENERIC_WRITE,0,NULL,CREATE_NEW,0,NULL);
     CHECK(file!=INVALID_HANDLE_VALUE);
     CHECK(WriteFile(file,"BIG4\0\0\0\0\0\0\0\6\0\0\0\20",16,&count,NULL));CloseHandle(file);
     CHECK(stadium_thumbnail_native(root,156,native_key,sizeof(native_key)));
     CHECK(!strcmp(native_key,"156_0"));
     CHECK(!stadium_thumbnail_native(root,156,native_key,3));
     CHECK(!stadium_thumbnail_native(root,0,native_key,sizeof(native_key)));
     DeleteFileA(native_path);}
    DeleteFileA(source); DeleteFileA(destination); DeleteFileA(copied);
    puts("PASS: exact DDS pixels, native movie geometry/payload, content keys, repaired cache, source preservation and invalid image rejection.");
    return 0;
}
