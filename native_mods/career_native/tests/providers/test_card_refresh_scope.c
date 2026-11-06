#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include <stdio.h>
#include "../../src/host/card_refresh_scope.h"
#include "../../src/host/career_relay_page.h"

static uintptr_t image = 0x140000000ULL;
static char page[128];
static uintptr_t view = 0x44000, page_address = 0x55000;
static int failures, changing, page_reads;
static int read_scope(uintptr_t address, void *out, size_t size)
{
    uintptr_t value;
    if (failures) return 0;
    if (address == page_address && size == sizeof(page)) {
        memcpy(out, page, size); return 1;
    }
    if (size != sizeof(value)) return 0;
    if (address == image + 0x3809030U) value = 0x11000;
    else if (address == 0x11000 + 232U) value = 0x22000;
    else if (address == 0x22000 + 192U) value = 0x33000;
    else if (address == 0x33000 + 136U) value = view;
    else if (address == view + 472U) {
        value = page_address;
        if (changing && ++page_reads > 1) ++value;
    } else return 0;
    memcpy(out, &value, size); return 1;
}
static void name(const char *value)
{
    memset(page, 0, sizeof(page));
    strcpy_s(page, sizeof(page), value);
    page_reads = 0;
}
int main(void)
{
    static const char *blocked[] = {
        "game/screens/career/Results", "game/screens/career/MailBox",
        "game/screens/playNow/KickOffHub", "game/screens/teamsheets/TeamSheetEditor",
        "game/screens/saveload_pc/load", "game/screens/saveload_pc/save",
        "game/screens/career/server16/DressingRoom", "", "TV/bumper"
    };
    unsigned i;
    unsigned char *occupied, *relay;
    uintptr_t fake_image;
    name("game/screens/fluxHub/FluxHub");
    assert(card_refresh_hub_view(image, read_scope) == view);
    assert(card_refresh_page_scope(image, read_scope).kind == CARD_PAGE_HUB);
    for (i = 0; i < sizeof(blocked) / sizeof(blocked[0]); ++i) {
        name(blocked[i]); assert(!card_refresh_hub_view(image, read_scope));
        assert(card_refresh_page_scope(image, read_scope).kind ==
            (blocked[i][0] ? CARD_PAGE_OTHER : CARD_PAGE_BUILDING));
    }
    name("game/screens/fluxHub/FluxHub"); failures = 1;
    assert(!card_refresh_hub_view(image, read_scope)); failures = 0;
    page_address = 0;
    assert(card_refresh_page_scope(image, read_scope).kind == CARD_PAGE_BUILDING);
    assert(!card_refresh_hub_view(image, read_scope));
    page_address = 0x55000;
    changing = 1; assert(!card_refresh_hub_view(image, read_scope)); changing = 0;
    memset(page, 'x', sizeof(page)); assert(!card_refresh_hub_view(image, read_scope));
    name("game/screens/fluxHub/FluxHub"); view += 0x1000;
    assert(card_refresh_hub_view(image, read_scope) == view);

    /* Reproduce the real collision with another plugin's committed page.
     * Both code relays must coexist, preserving every byte of the first.
     */
    occupied = VirtualAlloc(NULL, 0x1000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(occupied && (uintptr_t)occupied > 0x09600000U);
    memset(occupied, 0xA7, 0x1000);
    fake_image = (uintptr_t)occupied - 0x09600000U;
    relay = career_allocate_relay_page(fake_image);
    assert(relay && relay != occupied);
    assert((uintptr_t)relay > fake_image && (uintptr_t)relay - fake_image < INT32_MAX);
    for (i = 0; i < 0x1000; ++i) assert(occupied[i] == 0xA7);
    assert(VirtualFree(relay, 0, MEM_RELEASE));
    assert(VirtualFree(occupied, 0, MEM_RELEASE));
    relay = career_allocate_relay_page(fake_image);
    assert(relay == occupied);
    assert(VirtualFree(relay, 0, MEM_RELEASE));
    puts("PASS: Hub lifetime, results/save/match exclusions, torn page reads, and real relay-address contention");
    return 0;
}
