/* Local PyInstaller bootloader fix. Caller supplies pyi_path_fopen.
 * The original loader reopens the executable once per extracted entry.
 * A transient sharing error must not abort the entire auxiliary process. */
#ifndef SERVER16_ARCHIVE_RETRY_H
#define SERVER16_ARCHIVE_RETRY_H
#ifndef SERVER16_ARCHIVE_OPEN
#define SERVER16_ARCHIVE_OPEN(path) pyi_path_fopen(path, "rb")
#endif
#ifndef SERVER16_ARCHIVE_WAIT
#ifdef _WIN32
#define SERVER16_ARCHIVE_WAIT() Sleep(25)
#else
#define SERVER16_ARCHIVE_WAIT() ((void)0)
#endif
#endif
static FILE *server16_open_archive(const char *path)
{
    unsigned attempt;
    for (attempt = 0; attempt < 201; ++attempt) {
        FILE *input = SERVER16_ARCHIVE_OPEN(path);
        if (input != NULL) return input;
        if (attempt != 200) SERVER16_ARCHIVE_WAIT();
    }
    return NULL;
}
#endif
