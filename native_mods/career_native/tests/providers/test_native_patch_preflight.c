#define _CRT_SECURE_NO_WARNINGS
/* Keep the real provider/scheduler code, but control FCE readiness without
 * loading or calling a game's engine in this isolated process. */
static int test_fce_stable;
#define fce_runtime_is_stable test_fce_is_stable
/* Include the real initializer to test its actual patch table/barrier.
 * DllMain is not invoked by this console test; no game process is touched. */
#include "../../src/host/dinput8_wrapper.c"
#undef fce_runtime_is_stable
#include "stadium_thumbnail_fixture.h"
int test_fce_is_stable(void) { return test_fce_stable; }

static int failures;
static void *fake_vector_result;
static int vector_calls, notify_calls;
static void *last_notification;
static unsigned char last_dirty;
static char observed_field[96], observed_image[256], observed_stadium[256];
static int observed_image_visible, observed_image_divider;
static void observe_prepare(void *provider) { (void)provider; observed_field[0] = 0; }
static void observe_string(void *provider, const char *key, const char *value)
{
    (void)provider;
    if (!strcmp(key, "ID")) lstrcpynA(observed_field, value, sizeof(observed_field));
    if (!strcmp(key, "PARAM")) {
        if (!strcmp(observed_field, "MYTEAM_NEXT_STADIUM_IMAGE"))
            lstrcpynA(observed_image, value, sizeof(observed_image));
        if (!strcmp(observed_field, "MYTEAM_NEXT_STADIUM"))
            lstrcpynA(observed_stadium, value, sizeof(observed_stadium));
    }
}
static void observe_int(void *provider, const char *key, int value)
{
    (void)provider;
    if (strcmp(key, "VISIBLE")) return;
    if (!strcmp(observed_field, "MYTEAM_NEXT_STADIUM_IMAGE")) observed_image_visible = value;
    if (!strcmp(observed_field, "MYTEAM_NEXT_INFO_DIVIDER0")) observed_image_divider = value;
}
static void *fake_stats_vector(void *object, int category, unsigned char enabled)
{
    if (object && category == 4 && enabled == 1) ++vector_calls;
    return fake_vector_result;
}
static void fake_mark_dirty(void *notification, unsigned char dirty)
{
    ++notify_calls;
    last_notification = notification;
    last_dirty = dirty;
}
static void check(int condition, const char *name)
{
    if (!condition) { ++failures; printf("FAIL: %s\n", name); }
}

static int commit_site(unsigned char *base, uintptr_t rva)
{
    return VirtualAlloc(base + (rva & ~(uintptr_t)4095), 4096,
        MEM_COMMIT, PAGE_READWRITE) != NULL;
}

typedef struct LeaderField {
    char id[48], text[128];
    int visible, value;
} LeaderField;
static LeaderField leader_fields[64], *leader_current;
static SIZE_T leader_field_count;
static LeaderField *leader_field(const char *id)
{
    SIZE_T i;
    for (i = 0; i < leader_field_count; ++i)
        if (!strcmp(leader_fields[i].id, id)) return leader_fields + i;
    if (leader_field_count == 64) return NULL;
    lstrcpynA(leader_fields[i].id, id, sizeof(leader_fields[i].id));
    ++leader_field_count;
    return leader_fields + i;
}
static void leader_prepare(void *provider) { (void)provider; leader_current = NULL; }
static void leader_string(void *provider, const char *attribute, const char *value)
{
    (void)provider;
    if (!strcmp(attribute, "ID")) leader_current = leader_field(value);
    else if (leader_current && !strcmp(attribute, "PARAM"))
        lstrcpynA(leader_current->text, value, sizeof(leader_current->text));
    else if (leader_current && !strcmp(attribute, "VISIBLE"))
        leader_current->visible = !_stricmp(value, "TRUE");
}
static void leader_int(void *provider, const char *attribute, int value)
{
    (void)provider;
    if (leader_current && !strcmp(attribute, "VISIBLE")) leader_current->visible = value;
    else if (leader_current && !strcmp(attribute, "PARAM")) leader_current->value = value;
}
static void test_competition_leader_empty_states(void)
{
    void *provider = &failures;
    SIZE_T i;
    char key[48];
    g_prepare_field = leader_prepare; g_set_string = leader_string; g_set_int = leader_int;
    reset_stock_stat_capture();
    /* These are the native ID/PARAM pairs observed at the guarded call sites.
     * A HEAD field or a hidden NAME slot alone must not count as a player. */
    competition_scorer_name_capture(provider, "ID", "HEAD0");
    competition_scorer_name_capture(provider, "PARAM", "123");
    competition_scorer_name_capture(provider, "ID", "NAME0");
    competition_scorer_name_capture(provider, "PARAM", "Jogador A");
    competition_scorer_name_capture(provider, "ID", "NAME1");
    competition_scorer_name_capture(provider, "VISIBLE", "FALSE");
    competition_scorer_name_capture(provider, "ID", "NAME4");
    competition_scorer_name_capture(provider, "PARAM", "Jogador B");
    competition_scorer_name_capture(provider, "ID", "NAME5");
    competition_scorer_name_capture(provider, "PARAM", "Outside the card");
    publish_competition_leader_states(provider, 2);
    check(leader_field("ROW0")->visible && leader_field("ROW4")->visible &&
        !leader_field("ROW1")->visible && !leader_field("NAME1")->text[0],
        "scorers preserve actual native rows and hide missing positions");
    check(!leader_field("COMP_SCORERS_EMPTY")->visible &&
        !leader_field("COMP_SCORERS_EMPTY")->text[0] &&
        !leader_field("COMP_ASSISTS_EMPTY")->visible && !leader_field("COMP_ASSISTS_EMPTY")->text[0],
        "populated competition cards clear both empty message text and visibility");
    reset_stock_stat_capture();
    publish_competition_leader_states(provider, 0);
    for (i = 0; i < 5; ++i) {
        snprintf(key, sizeof(key), "ROW%u", (unsigned)i);
        check(!leader_field(key)->visible, "empty scorer card hides row panels");
        snprintf(key, sizeof(key), "ASSIST_ROW%u", (unsigned)i);
        check(!leader_field(key)->visible, "empty assist card hides row panels");
    }
    check(leader_field("COMP_SCORERS_EMPTY")->visible &&
        !strcmp(leader_field("COMP_SCORERS_EMPTY")->text, "FIFA_MODS_CM_NO_DATA_RECORDED") &&
        leader_field("COMP_ASSISTS_EMPTY")->visible &&
        !strcmp(leader_field("COMP_ASSISTS_EMPTY")->text, "FIFA_MODS_CM_NO_DATA_RECORDED"),
        "empty competition cards show the localized no-data message");
    check(!leader_field("NAME0")->text[0] && !leader_field("NAME4")->text[0] &&
        !leader_field("HEAD0")->visible && leader_field("HEAD0")->value == FORM_ASSET_EMPTY &&
        !leader_field("ASSIST_VALUE0")->visible,
        "empty transition clears old player names, values, crests and portraits");
    InterlockedExchange(&g_active_competition_id, 41);
    g_stats_tile_query_competition = 42; g_assist_competition_id = 41; g_assist_count = 1;
    lstrcpynA(g_assist_rows[0].name, "Assist player", sizeof(g_assist_rows[0].name));
    g_assist_rows[0].head = 10; g_assist_rows[0].logo = 20; g_assist_rows[0].value = 3;
    publish_competition_leader_states(provider, publish_top_assists(provider));
    check(leader_field("COMP_ASSISTS_EMPTY")->visible &&
        !leader_field("ASSIST_ROW0")->visible && !leader_field("ASSIST_NAME0")->text[0],
        "assist cache from a different competition is empty for the current card");
    g_assist_competition_id = 42;
    competition_scorer_name_capture(provider, "ID", "NAME0");
    competition_scorer_name_capture(provider, "PARAM", "Returned scorer");
    publish_competition_leader_states(provider, publish_top_assists(provider));
    check(!leader_field("COMP_SCORERS_EMPTY")->visible && !leader_field("COMP_SCORERS_EMPTY")->text[0] &&
        !leader_field("COMP_ASSISTS_EMPTY")->visible && !leader_field("COMP_ASSISTS_EMPTY")->text[0] &&
        leader_field("NAME0")->visible && !strcmp(leader_field("NAME0")->text, "Returned scorer") &&
        leader_field("ASSIST_NAME0")->visible && !strcmp(leader_field("ASSIST_NAME0")->text, "Assist player"),
        "new data removes empty banners and restores the actual current players");
    reset_stock_stat_capture();
    g_assist_count = 0; g_stats_tile_query_competition = 0; g_assist_competition_id = 0;
    InterlockedExchange(&g_active_competition_id, 0);
    g_prepare_field = observe_prepare; g_set_string = observe_string; g_set_int = observe_int;
}

static void test_next_match_stadium(void)
{
    static const char *folders[] = {"data", "data\\catalogs", "data\\ui",
        "data\\ui\\imgAssets", "data\\ui\\imgAssets\\stadium", "data\\ui\\artAssets",
        "data\\ui\\artAssets\\stadium", "StadiumGBD",
        "StadiumGBD\\render", "StadiumGBD\\render\\thumbnail",
        "StadiumGBD\\render\\thumbnail\\stadium", "FSW"};
    char temporary[MAX_PATH], fixture[MAX_PATH], path[MAX_PATH];
    char image[MAX_PATH], cached[MAX_PATH], catalogue[MAX_PATH], key[256], package_key[256];
    FILE *file;
    SIZE_T i;
    if (!GetTempPathA(sizeof(temporary), temporary) ||
        !GetTempFileNameA(temporary, "c16", 0, fixture)) { check(0, "stadium fixture path"); return; }
    DeleteFileA(fixture);
    check(CreateDirectoryA(fixture, NULL), "create isolated stadium fixture");
    for (i = 0; i < sizeof(folders) / sizeof(folders[0]); ++i) {
        snprintf(path, sizeof(path), "%s\\%s", fixture, folders[i]);
        check(CreateDirectoryA(path, NULL), "create stadium fixture directory");
    }
    lstrcpynA(g_game_dir, fixture, sizeof(g_game_dir));
    lstrcpynA(g_mod_dir, fixture, sizeof(g_mod_dir));
    snprintf(image, sizeof(image), "%s\\StadiumGBD\\render\\thumbnail\\stadium\\Fixture Photo.jpg", fixture);
    snprintf(cached, sizeof(cached), "%s\\data\\ui\\imgAssets\\stadium\\stadium_Fixture Photo.dds", fixture);
    snprintf(catalogue, sizeof(catalogue), "%s\\data\\catalogs\\club_stadium_fallback.tsv", fixture);
    check(write_stadium_fixture(image), "write source stadium picture");
    check(native_stadium_image_key("Fixture Photo", key, sizeof(key)) &&
        !strncmp(key, "cmphoto_", 8) && stadium_thumbnail_valid_dds(cached),
        "convert JPG and generate the movie required by the native stadium helper");
    lstrcpynA(package_key, key, sizeof(package_key));
    check(native_stadium_image_key("Fixture Photo5", key, sizeof(key)) && !strcmp(key, package_key),
        "malformed FSW render suffix still resolves the actual image");
    check(!native_stadium_image_key("../outside", key, sizeof(key)), "reject image path traversal");
    file = fopen(catalogue, "wb");
    check(file != NULL, "create stadium fallback catalogue");
    if (file) { fputs("1|1|10000|Fixture Ground|Fixture Photo|10|10\n", file); fclose(file); }
    g_prepare_field = observe_prepare; g_set_string = observe_string; g_set_int = observe_int;
    g_next_match_fixture_valid = 1; g_upcoming_count = 1;
    memset(&g_next_match_fixture, 0, sizeof(g_next_match_fixture));
    g_next_match_fixture.home = 1; g_next_match_fixture.away = 2;
    g_next_match_fixture.date_raw = 20260111; g_next_match_fixture.time_raw = 1600;
    publish_next_match_card(&failures);
    check(observed_image_visible == 1 && observed_image_divider == 1 &&
        !strcmp(observed_image, package_key) && !strcmp(observed_stadium, "Fixture Ground"),
        "publish stadium picture and DB name even without optional FSW mapping");
    snprintf(path, sizeof(path), "%s\\FSW\\settings.ini", fixture);
    check(WritePrivateProfileStringA("stadium", "1", "Different Ground,5,3,0", path),
        "create explicit FSW venue override");
    publish_next_match_card(&failures);
    check(!observed_image_visible && !observed_image_divider && !observed_image[0],
        "a different venue without a picture never borrows the club's default photo");
    WritePrivateProfileStringA("stadium", "1", NULL, path);
    WritePrivateProfileStringA(NULL, NULL, NULL, path);
    DeleteFileA(path);
    DeleteFileA(image);
    publish_next_match_card(&failures);
    check(!observed_image_visible && !observed_image_divider && !observed_image[0] &&
        !strcmp(observed_stadium, "Fixture Ground"),
        "a missing photo hides the slot/divider and clears the previous picture");
    g_next_match_fixture_valid = 0;
    publish_next_match_card(&failures);
    check(!observed_image_visible && !observed_image_divider, "no fixture keeps stadium image hidden");
    DeleteFileA(cached); DeleteFileA(catalogue);
    snprintf(path, sizeof(path), "%s\\data\\ui\\artAssets\\stadium\\stadium_%s.big", fixture, package_key);
    DeleteFileA(path);
    for (i = sizeof(folders) / sizeof(folders[0]); i > 0; --i) {
        snprintf(path, sizeof(path), "%s\\%s", fixture, folders[i - 1]); RemoveDirectoryA(path);
    }
    RemoveDirectoryA(fixture);
    g_game_dir[0] = 0; g_mod_dir[0] = 0;
}

static void test_updated_competition_identities(void)
{
    FceCompNode nodes[] = {
        {1597, 0, 3, 229, 0}, {1664, 1597, 4, 0, 0},
        {1687, 1664, 5, 0, 0}, {1688, 1664, 5, 0, 0},
        {1816, 0, 3, 9, 0}, {1817, 1816, 4, 0, 0}, {1818, 1817, 5, 0, 0}
    };
    FceCompetition resolved;
    int parts[3] = {1687, 1597, 1664};
    native_view.nodes = nodes; native_view.node_count = sizeof(nodes) / sizeof(nodes[0]);
    memset(&g_competition_identity, 0, sizeof(g_competition_identity));
    g_competition_identity.nodes[0] = (CompIdentityNode){1597,3,0,"C229","TrophyName_Abbr15_229"};
    g_competition_identity.nodes[1] = (CompIdentityNode){1816,3,0,"C9","TrophyName_Abbr15_9"};
    g_competition_identity.slot[1597] = 1; g_competition_identity.slot[1816] = 2;
    g_competition_identity.count = 2;
    InterlockedExchange(&g_compdata_index_state, 2);
    check(native_logo(1687) == 1001597 && native_logo(1688) == 1001597,
        "Copa groups resolve through current semantic artwork namespace");
    check(native_logo(1816) == 1001816 && native_logo(1818) == 1001816,
        "Supercopa hierarchy resolves to its installed identity");
    check(calendar_icon_identity(nodes, native_view.node_count, parts, &resolved) == FCE_OK
        && resolved.competition == 1597 && resolved.asset == 229,
        "calendar resolves both object references in the same live snapshot");
    parts[1] = 1816;
    check(calendar_icon_identity(nodes, native_view.node_count, parts, &resolved) == FCE_CONFLICT,
        "calendar cannot combine objects from unrelated competitions");
    native_view.nodes = NULL; native_view.node_count = 0;
    memset(&g_competition_identity, 0, sizeof(g_competition_identity));
    InterlockedExchange(&g_compdata_index_state, 0);
}

static int pending_native_calls;
static void fake_pending_native_query(void *owner)
{
    if (owner == g_pending_stats_provider_owner) ++pending_native_calls;
    g_stats_publication_completed = TRUE;
    g_stats_applied_generation = 7;
}
static void test_calendar_descriptor(ServiceDescriptor *descriptor)
{
    descriptor->index = -1;
}
static void test_pending_provider_scope(void)
{
    unsigned char *image = VirtualAlloc(NULL, 0x380a000, MEM_RESERVE, PAGE_NOACCESS);
    unsigned char nodes[4][512] = {{0}};
    char page[128] = "game/screens/fluxHub/FluxHub";
    uintptr_t owner[80] = {0x1111,0x2222};
    uintptr_t pointer;
    unsigned i;
    const unsigned offsets[] = {232,192,136};
    check(image != NULL && commit_site(image, 0x3809030), "page-chain fixture");
    if (!image) return;
    pointer = (uintptr_t)nodes[0]; memcpy(image + 0x3809030, &pointer, sizeof(pointer));
    for (i=0; i<3; ++i) { pointer=(uintptr_t)nodes[i+1]; memcpy(nodes[i]+offsets[i],&pointer,sizeof(pointer)); }
    pointer = (uintptr_t)page; memcpy(nodes[3]+472,&pointer,sizeof(pointer));
    g_module_base = image;
    remember_pending_stats_refresh(owner);
    check(g_stats_refresh_schedule.view_revision == 1 && g_pending_stats_hub_view == (uintptr_t)nodes[3]
        && g_pending_stats_provider_registry == (void *)owner[1], "live Hub arms its exact native view");
    strcpy_s(page,sizeof(page),"game/screens/career/Results");
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner && !g_stats_refresh_schedule.view_revision,
        "results cancels the stale owner before calling native StatisticsData");
    remember_pending_stats_refresh(owner);
    check(!g_pending_stats_provider_owner, "results cannot arm another deferred native query");

    /* The first native request runs before the page name is published.
     * Data becomes ready once; there is no user navigation or second request. */
    g_stats_confirmed_hub_context = 0;
    page[0] = 0;
    remember_pending_stats_refresh(owner);
    check(g_pending_stats_provider_owner == owner && g_pending_stats_hub_deadline
        && !g_pending_stats_hub_view && !g_stats_refresh_schedule.view_revision,
        "initial native request waits for the unpublished Hub");
    refresh_initial_competition_provider(7);
    test_fce_stable = 1;
    g_stats_provider = fake_pending_native_query;
    native_calendar_descriptor = test_calendar_descriptor;
    drain_pending_stats_refresh();
    check(!pending_native_calls && g_stats_ready_generation == 7,
        "ready data cannot invoke StatisticsData while the view is under construction");
    injury_refresh_cards_now();
    check(g_pending_stats_provider_owner == owner && !pending_native_calls,
        "initial injury rows cannot cancel the pending Hub publication");
    strcpy_s(page,sizeof(page),"game/screens/fluxHub/FluxHub");
    drain_pending_stats_refresh();
    check(g_pending_stats_hub_view == (uintptr_t)nodes[3]
        && !g_pending_stats_hub_deadline && !pending_native_calls,
        "first Hub binds the genuine request and lets native view setup settle");
    g_stats_refresh_schedule.entered_at -= 100;
    test_fce_stable = 0;
    drain_pending_stats_refresh();
    check(!pending_native_calls, "first Hub still waits for FCE to finish reconstruction");
    test_fce_stable = 1;
    drain_pending_stats_refresh();
    check(pending_native_calls == 1 && g_stats_refresh_schedule.applied_generation == 7,
        "first career view receives ready values without opening another screen");

    /* A bound Hub may never follow even a blank transition to another view. */
    page[0] = 0;
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner, "a bound Hub is cancelled at transition start");
    remember_pending_stats_refresh(owner);
    check(!g_pending_stats_provider_owner,
        "a later blank transition cannot create another initial request in the same career");
    g_stats_confirmed_hub_context = 0;
    remember_pending_stats_refresh(owner);
    strcpy_s(page,sizeof(page),"game/screens/career/Results");
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner && pending_native_calls == 1,
        "a construction candidate cannot cross Results or issue a native query there");
    strcpy_s(page,sizeof(page),"game/screens/fluxHub/FluxHub");
    drain_pending_stats_refresh();
    check(pending_native_calls == 1, "returning to Hub cannot resurrect the cancelled owner");
    page[0] = 0;
    remember_pending_stats_refresh(owner);
    strcpy_s(page,sizeof(page),"game/screens/saveload_pc/save");
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner, "saving cancels an initial construction candidate");
    page[0] = 0;
    remember_pending_stats_refresh(owner);
    g_pending_stats_hub_deadline = GetTickCount64() - 1;
    strcpy_s(page,sizeof(page),"game/screens/fluxHub/FluxHub");
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner, "an expired initial request cannot enter a later Hub");
    page[0] = 0;
    remember_pending_stats_refresh(owner);
    ++g_pending_stats_context_epoch;
    strcpy_s(page,sizeof(page),"game/screens/fluxHub/FluxHub");
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner, "a different career invalidates the initial request");
    page[0] = 0;
    remember_pending_stats_refresh(owner);
    pointer = 0; memcpy(image + 0x3809030, &pointer, sizeof(pointer));
    drain_pending_stats_refresh();
    check(g_pending_stats_provider_owner == owner && !g_pending_stats_hub_view,
        "a not-yet-created page chain waits without invoking FIFA");
    pointer = (uintptr_t)nodes[0]; memcpy(image + 0x3809030, &pointer, sizeof(pointer));
    strcpy_s(page,sizeof(page),"game/screens/fluxHub/FluxHub");
    drain_pending_stats_refresh();
    owner[1] = 0x3333;
    g_stats_refresh_schedule.entered_at -= 100;
    drain_pending_stats_refresh();
    check(!g_pending_stats_provider_owner && pending_native_calls == 1,
        "a replaced native registry cannot receive the initial publication");
    native_calendar_descriptor = NULL;
    test_fce_stable = 0;
    g_stats_provider = NULL;
    g_module_base = NULL;
    VirtualFree(image,0,MEM_RELEASE);
}


int main(void)
{
    SIZE_T i;
    unsigned char *base = (unsigned char *)VirtualAlloc(NULL, 0x09525000,
        MEM_RESERVE, PAGE_NOACCESS);
    unsigned char *missing;
    unsigned char *unexpected;
    unsigned char original[5];
    if (!base) return 2;
    for (i = 0; i < sizeof(g_patches) / sizeof(g_patches[0]); ++i) {
        const PatchSpec *p = &g_patches[i];
        if (!commit_site(base, p->rva)) return 2;
        memcpy(base + p->rva, p->expected, p->size);
    }
    for (i = 0; i < sizeof(g_call_patches) / sizeof(g_call_patches[0]); ++i) {
        const CallPatchSpec *p = &g_call_patches[i];
        int32_t delta = (int32_t)((intptr_t)p->expected_target_rva -
            (intptr_t)p->call_rva - 5);
        if (!commit_site(base, p->call_rva)) return 2;
        base[p->call_rva] = 0xE8;
        memcpy(base + p->call_rva + 1, &delta, sizeof(delta));
    }
    check(career_patch_sites_ready(base, NULL), "all native sites are ready");
    check(!Fifa16CareerHooksReady(), "plugins wait until the entire host installation finishes");
    InterlockedExchange(&g_career_hooks_ready, 1);
    check(Fifa16CareerHooksReady(), "explicit hook ownership readiness is observable");
    InterlockedExchange(&g_career_hooks_ready, 0);
    missing = base + g_call_patches[0].call_rva;
    memcpy(original, missing, sizeof(original));
    memset(missing, 0xCC, sizeof(original));
    check(!career_patch_sites_ready(base, NULL),
        "a decoded standings marker is not enough to start Career hooks");
    check(missing[0] == 0xCC && missing[4] == 0xCC,
        "waiting does not modify an encrypted call site");
    memcpy(missing, original, sizeof(original));
    check(career_patch_sites_ready(base, NULL),
        "late native decryption allows initialization on the next attempt");
    unexpected = base + g_call_patches[18].call_rva;
    unexpected[1] ^= 1;
    check(!career_patch_sites_ready(base, NULL),
        "an unexpected original target stays rejected");
    unexpected[1] ^= 1;
    unexpected = base + g_call_patches[sizeof(g_call_patches) / sizeof(g_call_patches[0]) - 1].call_rva;
    unexpected[1] ^= 1;
    check(!career_patch_sites_ready(base, NULL),
        "the new pre-notification hook must match before any patch is installed");
    unexpected[1] ^= 1;
    check(career_patch_sites_ready(base, NULL),
        "the new pre-notification hook can recover after its target is restored");
    base[g_patches[1].rva] ^= 1;
    check(!career_patch_sites_ready(base, NULL),
        "every byte-patch site is checked before writing any call");
    base[g_patches[1].rva] ^= 1;
    check(career_patch_sites_ready(base, NULL), "readiness can recover safely");
    VirtualFree(base, 0, MEM_RELEASE);
    g_stats_vector = fake_stats_vector;
    fake_vector_result = (void *)(uintptr_t)0x1234;
    g_current_stats_provider_owner = (void *)(uintptr_t)0x4567;
    check(stats_vector_capture(&failures, 4, 1) == fake_vector_result &&
        g_current_stats_provider == fake_vector_result && vector_calls == 1,
        "capture UI vector without depending on a scorer string row");
    fake_vector_result = NULL;
    check(stats_vector_capture(&failures, 4, 1) == NULL &&
        g_current_stats_provider == NULL,
        "a missing native destination cannot reuse an earlier vector");
    g_stats_mark_dirty = fake_mark_dirty;
    stats_mark_dirty_capture(&failures, 1);
    check(notify_calls == 1 && last_notification == &failures && last_dirty == 1 &&
        !g_stats_publication_completed,
        "native notification survives missing custom payload without acknowledgement");
    g_current_stats_provider = (void *)(uintptr_t)0x1234;
    stats_mark_dirty_capture(&failures, 0);
    check(notify_calls == 2 && !last_dirty && !g_stats_publication_completed,
        "a clean native notification does not publish custom fields");
    g_current_stats_provider_owner = NULL;
    g_current_stats_provider = NULL;
    test_pending_provider_scope();
    test_competition_leader_empty_states();
    test_next_match_stadium();
    test_updated_competition_identities();
    printf("Career native patch readiness: %s (%d failures)\n",
        failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
