#pragma once
#include <windows.h>
#include <stdint.h>
#include <string.h>

static bool mascot_rx3_file_valid(const wchar_t* path, bool texture)
{
    HANDLE file = CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER size{}; uint32_t header[4]{}; DWORD got=0;
    bool valid = GetFileSizeEx(file,&size) && size.QuadPart >= 32 && size.QuadPart <= 64*1024*1024 &&
        ReadFile(file,header,sizeof(header),&got,nullptr) && got==sizeof(header) &&
        memcmp(header,"RX3l",4)==0 && header[2]>=32 && header[2]<=(uint32_t)size.QuadPart &&
        header[3]>0 && header[3]<=20000 && 16ull+header[3]*16ull <= (uint64_t)size.QuadPart;
    bool mesh=false, vertex=false, index=false, format=false, tex=false;
    for (uint32_t i=0; valid && i<header[3]; ++i) {
        uint32_t section[4];
        valid = ReadFile(file,section,sizeof(section),&got,nullptr) && got==sizeof(section) &&
            section[1] >= 16+header[3]*16 && section[2]>=4 &&
            (uint64_t)section[1]+section[2] <= (uint64_t)size.QuadPart;
        if (!valid) break;
        mesh |= section[0]==0xd48d7880; vertex |= section[0]==0x00587aa1;
        index |= section[0]==0x005878f4; format |= section[0]==0xc28193f0;
        tex |= section[0]==0x7a0b60da;
    }
    CloseHandle(file);
    return valid && (texture ? tex : mesh && vertex && index && format);
}
