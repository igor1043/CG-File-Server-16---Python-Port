#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <objbase.h>
#include <wincodec.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdio.h>
#include "stadium_thumbnail.h"
#include "stadium_art_template.h"

int stadium_thumbnail_native(const char *directory,int stadium,char *key,size_t capacity)
{
    static const int variants[]={0,1,3,4};
    size_t i;char path[MAX_PATH],candidate[40];
    if(!key || !capacity)return 0;
    key[0]=0;
    if(!directory || stadium<=0 || stadium>1000000)return 0;
    for(i=0;i<sizeof(variants)/sizeof(variants[0]);++i){
        FILE *file;BYTE header[16];size_t got;int length;
        length=snprintf(candidate,sizeof(candidate),"%d_%d",stadium,variants[i]);
        if(length<=0 || (size_t)length>=capacity)return 0;
        length=snprintf(path,sizeof(path),"%s\\stadium_%s.big",directory,candidate);
        if(length<=0 || (size_t)length>=sizeof(path))return 0;
        file=fopen(path,"rb");if(!file)continue;
        got=fread(header,1,sizeof(header),file);fclose(file);
        if(got==sizeof(header) && (!memcmp(header,"BIG4",4) || !memcmp(header,"BIGF",4))){
            strcpy(key,candidate);return 1;
        }
    }
    return 0;
}

static int wide_path(const char *path, WCHAR *out, int capacity)
{
    return path && MultiByteToWideChar(CP_ACP, 0, path, -1, out, capacity) > 0;
}

int stadium_thumbnail_valid_dds(const char *path)
{
    HANDLE file;
    DWORD header[32], read_bytes;
    LARGE_INTEGER length;
    uint64_t payload, blocks;
    unsigned bits, fourcc;
    int valid = 0;
    file = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE |
        FILE_SHARE_DELETE, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 0;
    if (!ReadFile(file, header, sizeof(header), &read_bytes, NULL) ||
        read_bytes != sizeof(header) || !GetFileSizeEx(file, &length)) goto done;
    if (header[0] != 0x20534444 || header[1] != 124 || header[19] != 32 ||
        !header[3] || !header[4] || header[3] > 4096 || header[4] > 4096) goto done;
    fourcc = header[21]; bits = header[22];
    blocks = ((uint64_t)header[4] + 3) / 4 * (((uint64_t)header[3] + 3) / 4);
    if ((header[20] & 4) && fourcc == 0x31545844) payload = blocks * 8; /* DXT1 */
    else if ((header[20] & 4) &&
        (fourcc == 0x33545844 || fourcc == 0x35545844)) payload = blocks * 16;
    else if ((header[20] & 0x40) && (bits == 24 || bits == 32))
        payload = (uint64_t)header[4] * header[3] * (bits / 8);
    else goto done;
    valid = (uint64_t)length.QuadPart >= sizeof(header) + payload;
done:
    CloseHandle(file);
    return valid;
}

static int write_converted_dds(const WCHAR *source, const WCHAR *temporary,
    const FILETIME *source_time, int *owned)
{
    IWICImagingFactory *factory = NULL;
    IWICBitmapDecoder *decoder = NULL;
    IWICBitmapFrameDecode *frame = NULL;
    IWICFormatConverter *converter = NULL;
    HANDLE file = INVALID_HANDLE_VALUE;
    BYTE *pixels = NULL;
    UINT width = 0, height = 0, stride, count;
    DWORD header[32] = {0}, written;
    HRESULT apartment = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    int result = 0;
    if (FAILED(apartment) && apartment != RPC_E_CHANGED_MODE) return 0;
    if (FAILED(CoCreateInstance(&CLSID_WICImagingFactory, NULL, CLSCTX_INPROC_SERVER,
        &IID_IWICImagingFactory, (void **)&factory))) goto done;
    if (FAILED(IWICImagingFactory_CreateDecoderFromFilename(factory, source, NULL,
        GENERIC_READ, WICDecodeMetadataCacheOnLoad, &decoder))) goto done;
    if (FAILED(IWICBitmapDecoder_GetFrame(decoder, 0, &frame)) ||
        FAILED(IWICBitmapFrameDecode_GetSize(frame, &width, &height)) ||
        !width || !height || width > 4096 || height > 4096) goto done;
    stride = width * 4; count = stride * height;
    pixels = (BYTE *)malloc(count);
    if (!pixels || FAILED(IWICImagingFactory_CreateFormatConverter(factory, &converter))) goto done;
    if (FAILED(IWICFormatConverter_Initialize(converter, (IWICBitmapSource *)frame,
        &GUID_WICPixelFormat32bppBGRA, WICBitmapDitherTypeNone, NULL, 0,
        WICBitmapPaletteTypeCustom)) ||
        FAILED(IWICFormatConverter_CopyPixels(converter, NULL, stride, count, pixels))) goto done;
    header[0] = 0x20534444; header[1] = 124; header[2] = 0x100f;
    header[3] = height; header[4] = width; header[5] = stride;
    header[19] = 32; header[20] = 0x41; header[22] = 32;
    header[23] = 0x00ff0000; header[24] = 0x0000ff00;
    header[25] = 0x000000ff; header[26] = 0xff000000; header[27] = 0x1000;
    file = CreateFileW(temporary, GENERIC_WRITE, FILE_SHARE_READ, NULL,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) goto done;
    *owned = 1;
    if (!WriteFile(file, header, sizeof(header), &written, NULL) || written != sizeof(header) ||
        !WriteFile(file, pixels, count, &written, NULL) || written != count ||
        !SetFileTime(file, NULL, NULL, source_time) || !FlushFileBuffers(file)) goto done;
    result = 1;
done:
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    free(pixels);
    if (converter) IWICFormatConverter_Release(converter);
    if (frame) IWICBitmapFrameDecode_Release(frame);
    if (decoder) IWICBitmapDecoder_Release(decoder);
    if (factory) IWICImagingFactory_Release(factory);
    if (SUCCEEDED(apartment)) CoUninitialize();
    return result;
}

int stadium_thumbnail_sync(const char *source, const char *destination)
{
    WIN32_FILE_ATTRIBUTE_DATA input, cached;
    WCHAR source_w[MAX_PATH], destination_w[MAX_PATH], temporary[MAX_PATH + 64];
    const char *extension;
    int dds, owned = 0, result = STADIUM_IMAGE_MISSING;
    HANDLE file;
    if (!source || !destination || !_stricmp(source, destination) ||
        !GetFileAttributesExA(source, GetFileExInfoStandard, &input) ||
        (input.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) return 0;
    extension = strrchr(source, '.');
    dds = extension && !_stricmp(extension, ".dds");
    if (dds && !stadium_thumbnail_valid_dds(source)) return 0;
    if (GetFileAttributesExA(destination, GetFileExInfoStandard, &cached) &&
        CompareFileTime(&input.ftLastWriteTime, &cached.ftLastWriteTime) == 0 &&
        stadium_thumbnail_valid_dds(destination)) return STADIUM_IMAGE_CURRENT;
    if (!wide_path(source, source_w, MAX_PATH) ||
        !wide_path(destination, destination_w, MAX_PATH)) return 0;
    if (_snwprintf_s(temporary, sizeof(temporary) / sizeof(temporary[0]), _TRUNCATE,
        L"%ls.tmp.%lu.%lu.%llu", destination_w, GetCurrentProcessId(),
        GetCurrentThreadId(), (unsigned long long)GetTickCount64()) < 0) return 0;
    if (dds) {
        if (CopyFileW(source_w, temporary, TRUE)) {
            owned = 1;
            file = CreateFileW(temporary, FILE_WRITE_ATTRIBUTES, FILE_SHARE_READ,
                NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
            if (file != INVALID_HANDLE_VALUE) {
                if (SetFileTime(file, NULL, NULL, &input.ftLastWriteTime))
                    result = STADIUM_IMAGE_COPIED;
                CloseHandle(file);
            }
        }
    } else if (write_converted_dds(source_w, temporary, &input.ftLastWriteTime, &owned)) {
        result = STADIUM_IMAGE_CONVERTED;
    }
    if (result && !MoveFileExW(temporary, destination_w,
        MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) result = 0;
    if (owned) DeleteFileW(temporary);
    return result;
}

static void stadium_big_u32(BYTE *out, DWORD value)
{
    out[0] = (BYTE)(value >> 24); out[1] = (BYTE)(value >> 16);
    out[2] = (BYTE)(value >> 8); out[3] = (BYTE)value;
}

static void stadium_art_float(BYTE *out, DWORD value)
{
    float number = (float)value;
    memcpy(out, &number, sizeof(number));
}

int stadium_thumbnail_package(const char *dds, const char *art_directory,
    char *key, size_t capacity)
{
    static const char *names[] = {"0", "3", "sg1", "2", "sg2", "1"};
    BYTE *image = NULL, *package = NULL;
    DWORD offsets[6], sizes[6], count = 0, length, width, height, total;
    WIN32_FILE_ATTRIBUTE_DATA attributes;
    HANDLE input = INVALID_HANDLE_VALUE, output = INVALID_HANDLE_VALUE;
    LARGE_INTEGER file_size;
    uint64_t hash = UINT64_C(14695981039346656037);
    char asset[40], path[MAX_PATH], temporary[MAX_PATH + 64];
    size_t i, index;
    int owned = 0, result = 0, written;
    if (!key || !capacity) return 0;
    key[0] = 0;
    if (!dds || !art_directory || !stadium_thumbnail_valid_dds(dds)) return 0;
    input = CreateFileA(dds, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (input == INVALID_HANDLE_VALUE || !GetFileSizeEx(input, &file_size) ||
        file_size.QuadPart < 128 || file_size.QuadPart > 70 * 1024 * 1024) goto done;
    length = (DWORD)file_size.QuadPart;
    image = (BYTE *)malloc(length);
    if (!image || !ReadFile(input, image, length, &count, NULL) || count != length) goto done;
    memcpy(&height, image + 12, 4); memcpy(&width, image + 16, 4);
    /* Version the key as well as the image bytes: stale notfound cache entries
     * from earlier sessions/implementations must not mask a newly valid photo. */
    hash = (hash ^ 1) * UINT64_C(1099511628211);
    for (i = 0; i < length; ++i) hash = (hash ^ image[i]) * UINT64_C(1099511628211);
    written = snprintf(asset, sizeof(asset), "cmphoto_%016llx", (unsigned long long)hash);
    if (written <= 0 || (size_t)written >= sizeof(asset) || (size_t)written >= capacity) goto done;
    written = snprintf(path, sizeof(path), "%s\\stadium_%s.big", art_directory, asset);
    if (written <= 0 || (size_t)written >= sizeof(path)) goto done;
    if (!GetFileAttributesExA(art_directory, GetFileExInfoStandard, &attributes)) {
        if (!CreateDirectoryA(art_directory, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) goto done;
    } else if (!(attributes.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) goto done;

    /* Match the native six-member movie package; DDS pixels stay byte exact. */
    offsets[0] = 88; sizes[0] = sizeof(stadium_art_movie);
    offsets[1] = 704; sizes[1] = sizeof(stadium_art_geometry);
    offsets[2] = offsets[3] = 1024; sizes[2] = 0; sizes[3] = length;
    offsets[4] = offsets[5] = (1024 + length + 63) & ~(DWORD)63;
    sizes[4] = 0; sizes[5] = sizeof(stadium_art_constants);
    total = offsets[5] + sizes[5];
    package = (BYTE *)calloc(1, total);
    if (!package) goto done;
    memcpy(package, "BIG4", 4); memcpy(package + 4, &total, 4);
    stadium_big_u32(package + 8, 6); stadium_big_u32(package + 12, 88);
    index = 16;
    for (i = 0; i < 6; ++i) {
        size_t name_length = strlen(names[i]) + 1;
        stadium_big_u32(package + index, offsets[i]);
        stadium_big_u32(package + index + 4, sizes[i]); index += 8;
        memcpy(package + index, names[i], name_length); index += name_length;
    }
    memcpy(package + index, "L286\x15\x05\0\0", 8);
    memcpy(package + offsets[0], stadium_art_movie, sizes[0]);
    memcpy(package + offsets[1], stadium_art_geometry, sizes[1]);
    memcpy(package + offsets[3], image, length);
    memcpy(package + offsets[5], stadium_art_constants, sizes[5]);
    memcpy(package + offsets[0] + 0x98, &width, 4);
    memcpy(package + offsets[0] + 0x9c, &height, 4);
    stadium_art_float(package + offsets[0] + 0x118, width);
    stadium_art_float(package + offsets[0] + 0x11c, height);
    stadium_art_float(package + offsets[1] + 0xa0, width);
    stadium_art_float(package + offsets[1] + 0xc0, width);
    stadium_art_float(package + offsets[1] + 0xe0, width);
    stadium_art_float(package + offsets[1] + 0x64, height);
    stadium_art_float(package + offsets[1] + 0xe4, height);
    stadium_art_float(package + offsets[1] + 0x104, height);
    /* Validate the whole cache, including the movie and geometry, so a partial
     * or edited generated file is repaired instead of being advertised. */
    output = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (output != INVALID_HANDLE_VALUE) {
        LARGE_INTEGER cached_size;
        if (GetFileSizeEx(output, &cached_size) && cached_size.QuadPart == total) {
            BYTE buffer[4096]; DWORD position = 0;
            while (position < total) {
                DWORD chunk = total - position;
                if (chunk > sizeof(buffer)) chunk = sizeof(buffer);
                if (!ReadFile(output, buffer, chunk, &count, NULL) || count != chunk ||
                    memcmp(buffer, package + position, chunk)) break;
                position += chunk;
            }
            if (position == total) result = STADIUM_IMAGE_CURRENT;
        }
        CloseHandle(output); output = INVALID_HANDLE_VALUE;
        if (result) goto ready;
    }
    written = snprintf(temporary, sizeof(temporary), "%s.tmp.%lu.%lu.%llu", path,
        GetCurrentProcessId(), GetCurrentThreadId(), (unsigned long long)GetTickCount64());
    if (written <= 0 || (size_t)written >= sizeof(temporary)) goto done;
    output = CreateFileA(temporary, GENERIC_WRITE, FILE_SHARE_READ, NULL,
        CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (output == INVALID_HANDLE_VALUE) goto done;
    owned = 1;
    if (!WriteFile(output, package, total, &count, NULL) || count != total ||
        !FlushFileBuffers(output)) goto done;
    CloseHandle(output); output = INVALID_HANDLE_VALUE;
    if (!MoveFileExA(temporary, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) goto done;
    result = STADIUM_IMAGE_CONVERTED;
ready:
    memcpy(key, asset, strlen(asset) + 1);
done:
    if (input != INVALID_HANDLE_VALUE) CloseHandle(input);
    if (output != INVALID_HANDLE_VALUE) CloseHandle(output);
    if (owned) DeleteFileA(temporary);
    free(image); free(package);
    return result;
}
