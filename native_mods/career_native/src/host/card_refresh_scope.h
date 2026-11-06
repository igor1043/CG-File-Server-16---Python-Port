#ifndef FIFA16_CARD_REFRESH_SCOPE_H
#define FIFA16_CARD_REFRESH_SCOPE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef int (*CardScopeReadFn)(uintptr_t, void *, size_t);

typedef enum CardPageKind {
    CARD_PAGE_INVALID = 0,
    CARD_PAGE_BUILDING,
    CARD_PAGE_HUB,
    CARD_PAGE_OTHER
} CardPageKind;

typedef struct CardPageScope {
    uintptr_t view;
    CardPageKind kind;
} CardPageScope;

/* A native StatisticsData request can precede the publication of its Hub
 * page. Distinguish that empty construction interval from a different named
 * screen. Only a confirmed Hub permits deferred calls into FIFA; readable
 * owner/vtable memory alone never proves that those calls are safe. */
static CardPageScope card_refresh_page_scope(uintptr_t image, CardScopeReadFn read)
{
    static const unsigned offsets[] = {232, 192, 136};
    static const char hub[] = "game/screens/fluxHub/FluxHub";
    uintptr_t node = 0, page = 0, check = 0;
    char name[128];
    size_t i;
    CardPageScope scope = {0, CARD_PAGE_INVALID};
    if (!image || !read || !read(image + 0x3809030U, &node, sizeof(node)))
        return scope;
    for (i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        if (!node) { scope.kind = CARD_PAGE_BUILDING; return scope; }
        if (!read(node + offsets[i], &node, sizeof(node))) return scope;
    }
    if (!node) { scope.kind = CARD_PAGE_BUILDING; return scope; }
    if (!read(node + 472U, &page, sizeof(page))) return scope;
    if (page && (!read(page, name, sizeof(name))
        || !memchr(name, 0, sizeof(name)))) return scope;
    if (!read(node + 472U, &check, sizeof(check)) || check != page)
        return scope;
    scope.view = node;
    scope.kind = !page || !name[0] ? CARD_PAGE_BUILDING :
        (strcmp(name, hub) == 0 ? CARD_PAGE_HUB : CARD_PAGE_OTHER);
    return scope;
}

static uintptr_t card_refresh_hub_view(uintptr_t image, CardScopeReadFn read)
{
    CardPageScope scope = card_refresh_page_scope(image, read);
    return scope.kind == CARD_PAGE_HUB ? scope.view : 0;
}
#endif
