#define _CRT_SECURE_NO_WARNINGS
/* Include the real initializer to test its actual patch table/barrier.
 * DllMain is not invoked by this console test; no game process is touched. */
#include "../../src/host/dinput8_wrapper.c"
#include "stadium_thumbnail_fixture.h"

static int failures;
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
static void check(int condition, const char *name)
{
    if (!condition) { ++failures; printf("FAIL: %s\n", name); }
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
    check(WritePrivateProfileStringA("scoreboardstdname", "Different Ground",
        "Santa Cruz - Arena NicNet - Ribeir\xC3\xA3o Preto - SP,1", path),
        "write accented scoreboard name with stadium alias and location");
    publish_next_match_card(&failures);
    check(!strcmp(observed_stadium,"Santa Cruz - Arena NicNet"),
        "next-match card keeps stadium alias without overflowing city/state metadata");
    check(native_team_stadium(1,key,sizeof(key),NULL,0,NULL,0) &&
        !strcmp(key,observed_stadium),"club and next-match cards resolve the same stadium title");
    native_stadium_text("Maracan\xE3",key,sizeof(key),0);
    check(!strcmp(key,"Maracan\xC3\xA3"),"Windows 1252 stadium names become valid UTF-8");
    native_stadium_text("Amaz\xC3\xB4nia - Manaus - AM",key,sizeof(key),1);
    check(!strcmp(key,"Amaz\xC3\xB4nia"),"UTF-8 accents remain intact");
    native_stadium_text("Mewa Arena \xE2\x80\x93 Mainz \xE2\x80\x93 GER",key,sizeof(key),1);
    check(!strcmp(key,"Mewa Arena"),"European location separators are removed");
    native_stadium_text("Amaz\xC3\xB4nia",key,6,0);
    check(!strcmp(key,"Amaz"),"small destination never receives half an accented character");
    check(!observed_image_visible && !observed_image_divider && !observed_image[0],
        "a different venue without a picture never borrows the club's default photo");
    WritePrivateProfileStringA("stadium", "1", NULL, path);
    WritePrivateProfileStringA("scoreboardstdname", "Different Ground", NULL, path);
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

int main(void) {
    test_next_match_stadium();
    printf("Career stadium titles and publication: %s (%d failures)\n",failures?"FAIL":"PASS",failures);
    return failures?1:0;
}
