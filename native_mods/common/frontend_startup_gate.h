#ifndef FIFA_FRONTEND_STARTUP_GATE_H
#define FIFA_FRONTEND_STARTUP_GATE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef int (*FifaStartupRead)(void *, uintptr_t, void *, size_t);

/* Byte signatures can become visible before the executable's protected
 * startup has finished. A live native screen is the readiness boundary for
 * optional plugins; do not call any engine function to discover it. */
static int fifa_frontend_startup_ready(FifaStartupRead read, void *context,
    uintptr_t base, int engine_loaded, int career_hooks_ready)
{
    static const uintptr_t offsets[] = {0xE8, 0xC0, 0x88, 0x1D8};
    uintptr_t pointer = 0;
    char page[128];
    size_t i;
    if (!read || !base || !engine_loaded || !career_hooks_ready
        || base > UINTPTR_MAX - 0x03809030U
        || !read(context, base + 0x03809030U, &pointer, sizeof(pointer)))
        return 0;
    for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        if (pointer < 0x10000U || pointer > UINTPTR_MAX - offsets[i]
            || !read(context, pointer + offsets[i], &pointer, sizeof(pointer)))
            return 0;
    }
    if (pointer < 0x10000U || !read(context, pointer, page, sizeof(page))
        || memcmp(page, "game/screens/", 13) != 0)
        return 0;
    for (i = 13; i < sizeof(page); ++i) {
        unsigned char character = (unsigned char)page[i];
        if (!character) return i > 13;
        if (character < 0x20 || character > 0x7E) return 0;
    }
    return 0;
}
#ifndef FIFA_STARTUP_GATE_TEST
static int fifa_startup_read_current(void *context, uintptr_t address,
    void *output, size_t size)
{
    SIZE_T received = 0;
    (void)context;
    return ReadProcessMemory(GetCurrentProcess(), (const void *)address,
        output, size, &received) && received == size;
}

static int fifa_frontend_startup_current(uintptr_t base)
{
    typedef BOOL (WINAPI *Ready)(void);
    HMODULE core = GetModuleHandleA("dinput8.dll");
    Ready ready = core ? (Ready)(void *)GetProcAddress(core,
        "Fifa16CareerHooksReady") : NULL;
    return fifa_frontend_startup_ready(fifa_startup_read_current, NULL,
        base, GetModuleHandleA("BCEnginezf.dll") != NULL,
        ready ? ready() : 1);
}
#endif
#endif
