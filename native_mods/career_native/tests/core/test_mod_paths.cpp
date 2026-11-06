#define _CRT_SECURE_NO_WARNINGS
#include "../../src/platform/mod_paths.h"
#include <cstring>
#include <cstdio>

int main() {
    char temp[MAX_PATH], base[MAX_PATH], config[MAX_PATH], oldFile[MAX_PATH], newFile[MAX_PATH], actual[MAX_PATH], logs[MAX_PATH];
    if (!GetTempPathA(sizeof(temp),temp)) return 1;
    snprintf(base,sizeof(base),"%scareer-paths-%lu-%llu",temp,(unsigned long)GetCurrentProcessId(),(unsigned long long)GetTickCount64());
    if (!CreateDirectoryA(base,nullptr)) return 1;
    snprintf(config,sizeof(config),"%s\\config",base);
    snprintf(oldFile,sizeof(oldFile),"%s\\example.ini",base);
    snprintf(newFile,sizeof(newFile),"%s\\example.ini",config);
    FILE* f=fopen(oldFile,"wb");if(!f)return 1;fputs("old",f);fclose(f);
    career_path_read(actual,sizeof(actual),base,"config","example.ini");
    bool legacy=strcmp(actual,oldFile)==0;
    CreateDirectoryA(config,nullptr);
    f=fopen(newFile,"wb");if(!f)return 1;fputs("new",f);fclose(f);
    career_path_read(actual,sizeof(actual),base,"config","example.ini");
    bool preferred=strcmp(actual,newFile)==0;
    bool cpp=career_paths::read(base,"config","example.ini")==newFile;
    career_path_logs(base);snprintf(logs,sizeof(logs),"%s\\logs",base);
    bool logging=GetFileAttributesA(logs)!=INVALID_FILE_ATTRIBUTES;
    DeleteFileA(oldFile);DeleteFileA(newFile);RemoveDirectoryA(config);RemoveDirectoryA(logs);RemoveDirectoryA(base);
    printf("%s: organized paths, legacy fallback, C++ resolution and log directory\n",legacy&&preferred&&cpp&&logging?"PASS":"FAIL");
    return legacy&&preferred&&cpp&&logging?0:1;
}
