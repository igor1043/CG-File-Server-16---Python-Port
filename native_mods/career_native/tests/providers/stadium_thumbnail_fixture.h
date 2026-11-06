#ifndef FIFA16_STADIUM_THUMBNAIL_FIXTURE_H
#define FIFA16_STADIUM_THUMBNAIL_FIXTURE_H
/* 2x2 RGB BMP: top red/green, bottom blue/white. WIC detects file content. */
static int write_stadium_fixture(const char *path)
{
    static const unsigned char bmp[70] = {
        0x42,0x4d,70,0,0,0,0,0,0,0,54,0,0,0,40,0,0,0,2,0,0,0,2,0,0,0,
        1,0,24,0,0,0,0,0,16,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        255,0,0,255,255,255,0,0,0,0,255,0,255,0,0,0
    };
    DWORD written = 0;
    HANDLE file = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    int result;
    if (file == INVALID_HANDLE_VALUE) return 0;
    result = WriteFile(file, bmp, sizeof(bmp), &written, NULL) && written == sizeof(bmp);
    CloseHandle(file);
    return result;
}
#endif
