#pragma once
#include <windows.h>
#include <stdint.h>
#include <stddef.h>

// A Lua lookup does not call back into the engine. Reuse VirtualQuery results
// only inside that lookup, and retain SEH around every actual memory read.
// Nothing survives the call or is shared between render/AI/score threads.
struct MascotScopedMemoryReader {
    struct Range { uintptr_t begin, end; };
    Range ranges[8]{};
    unsigned int rangeCount = 0, nextRange = 0;

    bool readable(uintptr_t address, size_t length)
    {
        if (address < 0x10000 || !length || address + length < address) return false;
        const uintptr_t end = address + length;
        for (unsigned int i=0; i<rangeCount; ++i)
            if (address >= ranges[i].begin && end <= ranges[i].end) return true;
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery((void*)address, &info, sizeof(info)) || info.State != MEM_COMMIT ||
            (info.Protect & (PAGE_NOACCESS | PAGE_GUARD))) return false;
        const uintptr_t begin = (uintptr_t)info.BaseAddress;
        const uintptr_t regionEnd = begin + info.RegionSize;
        if (regionEnd < begin || end > regionEnd) return false;
        ranges[nextRange] = {begin, regionEnd};
        nextRange = (nextRange + 1) % 8;
        if (rangeCount < 8) ++rangeCount;
        return true;
    }

    template<typename T> bool get(uintptr_t address, T& value)
    {
        if (!readable(address, sizeof(value))) return false;
        __try { value = *(const T*)address; return true; }
        __except(EXCEPTION_EXECUTE_HANDLER) { rangeCount=nextRange=0; return false; }
    }
};
