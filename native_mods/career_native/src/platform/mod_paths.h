#ifndef CAREER_MOD_PATHS_H
#define CAREER_MOD_PATHS_H
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <stdio.h>

/* New layout first; older installations remain readable without conversion.
 * This deliberately does not relocate saves, operation journals or plugin DLLs. */
static __inline void career_path_read(char *out, size_t capacity,
    const char *mod, const char *folder, const char *name)
{
    DWORD attrs;
    snprintf(out, capacity, "%s\\%s\\%s", mod, folder, name);
    attrs = GetFileAttributesA(out);
    if (attrs == INVALID_FILE_ATTRIBUTES || (attrs & FILE_ATTRIBUTE_DIRECTORY))
        snprintf(out, capacity, "%s\\%s", mod, name);
}
static __inline void career_path_logs(const char *mod)
{
    char directory[MAX_PATH];
    snprintf(directory, sizeof(directory), "%s\\logs", mod);
    CreateDirectoryA(directory, NULL);
}
#ifdef __cplusplus
#include <string>
namespace career_paths {
inline std::string read(const std::string& mod, const char* folder, const char* name) {
    char file[MAX_PATH];
    career_path_read(file, sizeof(file), mod.c_str(), folder, name);
    return file;
}
}
#endif
#endif
