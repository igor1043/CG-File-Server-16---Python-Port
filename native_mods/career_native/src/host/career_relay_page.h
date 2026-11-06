#ifndef FIFA16_CAREER_RELAY_PAGE_H
#define FIFA16_CAREER_RELAY_PAGE_H
#include <windows.h>
#include <stdint.h>
#include <limits.h>

/* Independent startup plugins can reserve the former fixed relay address.
 * Keep the preferred location when free; otherwise reserve another free,
 * allocation-aligned page inside the CALL rel32 range. Never replace memory.
 */
static unsigned char *career_allocate_relay_page(uintptr_t image)
{
    SYSTEM_INFO system;
    MEMORY_BASIC_INFORMATION info;
    uintptr_t cursor, limit, granularity;
    unsigned char *page = (unsigned char *)VirtualAlloc(
        (void *)(image + 0x09600000U), 0x1000,
        MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (page) return page;
    GetSystemInfo(&system);
    granularity = system.dwAllocationGranularity;
    cursor = (image + 0x09530000U + granularity - 1U) & ~(granularity - 1U);
    limit = image + (uintptr_t)INT32_MAX - 0x10000U;
    while (cursor < limit && VirtualQuery((void *)cursor, &info, sizeof(info))) {
        uintptr_t end = (uintptr_t)info.BaseAddress + info.RegionSize;
        if (end <= cursor) break;
        if (info.State == MEM_FREE) {
            uintptr_t aligned = (cursor + granularity - 1U) & ~(granularity - 1U);
            if (aligned < limit && aligned <= end && end - aligned >= 0x1000U) {
                page = (unsigned char *)VirtualAlloc((void *)aligned, 0x1000,
                    MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
                if (page) return page;
            }
        }
        cursor = end;
    }
    return NULL;
}
#endif
