#define UI_ASSETS_TEST
#include "career_ui_assets.c"
#include "path_hooks.inc"
#define CHECK(x) do {if(!(x)){printf("FAIL %d %s\n",__LINE__,#x);return 1;}} while(0)
static int __cdecl test_print_core(void *writer,void *object,const char *format,va_list arguments) {
    struct {char *buffer;size_t written;size_t capacity;BYTE truncated;} *sink=object;
    (void)writer;
    if(sink->truncated)return -1;
    return vsnprintf(sink->buffer,sink->capacity,format,arguments);
}
static void __cdecl test_string_core(void *object,const char *format,va_list arguments) {
    char **parts=object;size_t capacity=(size_t)(parts[2]-parts[0]);
    int length=vsnprintf(parts[0],capacity,format,arguments);
    parts[1]=parts[0]+(length>=0 && (size_t)length<capacity?length:0);
}
int main(int argc,char **argv) {
    BYTE rows[2*0x5c]={0},registry[21*32]={0},competition[0x10+400*0x5c]={0};
    BYTE *competition_pointer=competition,*wrapper=(BYTE*)&competition_pointer;
    int id=2240,type=3,asset=820;char name[MAX_PATH],resolved[MAX_PATH],tiny[8],alias[64];
    const char *request="artAssets/cmCalendarCompetitions/cmcomp_1693.swf";
    const char *expected="imgAssets/careerCompetitionIcons/c1693.dds";
    CHECK(argc==2 && strlen(argv[1])<MAX_PATH-110);strcpy(game_dir,argv[1]);
    build_catalog();CHECK(calendar_count==2 && InterlockedCompareExchange(&catalog_ready,0,0));
    CHECK(existing_calendar(1693) && existing_calendar(820));
    CHECK(!Fifa16UiAssetsHasCompetition(1693) && Fifa16UiAssetsHasCompetition(820));
    CHECK(!Fifa16UiAssetsHasCompetition(65536));
    CHECK(!existing_calendar(1615));CHECK(!existing_calendar(-1));
    CHECK(!existing_calendar(65536));CHECK(!existing_calendar(1700));
    CHECK(calendar_id("C1693.DDS","c",".dds")==1693);
    CHECK(!calendar_id("c1693.dds.bad","c",".dds"));
    CHECK(!calendar_id("c4294968989.dds","c",".dds"));
    CHECK(resolve_image_path(request,resolved,sizeof(resolved)) && !strcmp(resolved,expected));
    CHECK(resolve_image_path("data\\ui\\artAssets\\cmCalendarCompetitions\\cmcomp_1693.big",resolved,sizeof(resolved)) && !strcmp(resolved,"data/ui/imgAssets/careerCompetitionIcons/c1693.dds"));
    CHECK(resolve_image_path("UI/ARTASSETS/CMCALENDARCOMPETITIONS/CMCOMP_1693.SWF",resolved,sizeof(resolved)) && !strcmp(resolved,"ui/imgAssets/careerCompetitionIcons/c1693.dds"));
    CHECK(resolve_image_path("imgAssets/cmCalendarCompetitions/cmCalendarCompetitions1693.dds",resolved,sizeof(resolved)) && !strcmp(resolved,expected));
    CHECK(resolve_image_path("imgAssets/cmCalendarCompetitions/light/l1693.dds",resolved,sizeof(resolved)) && !strcmp(resolved,expected));
    CHECK(resolve_image_path("imgAssets/cmCalendarCompetitions/dark/l1693.dds",resolved,sizeof(resolved)) && !strcmp(resolved,expected));
    CHECK(!resolve_image_path(request,tiny,sizeof(tiny)));
    CHECK(!resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_1615.swf",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_4294968989.swf",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_1693.swf.bad",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("invalid/artAssets/cmCalendarCompetitions/cmcomp_1693.swf",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("artAssets/cmCalendar/cmcalendar_8.swf",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("imgAssets/cmCalendar/cmCalendar8.dds",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("imgAssets/league/light/l1693.dds",resolved,sizeof(resolved)));
    CHECK(!resolve_image_path("ui/imgAssets/kits/j30_110636_0.dds",resolved,sizeof(resolved)));
    native_print_core=test_print_core;native_string_core=test_string_core;
    /* Locale formatting uses this same game function before any artwork. */
    CHECK(ui_print(name,sizeof(name),"%s_%s","por","br")==6 && !strcmp(name,"por_br"));
    CHECK(ui_print(name,sizeof(name),"data/loc/%s.db","por_br")==18 && !strcmp(name,"data/loc/por_br.db"));
    CHECK(ui_print(name,sizeof(name),"kit %d %s",30,"preserved")==16 && !strcmp(name,"kit 30 preserved"));
    CHECK(ui_print(name,sizeof(name),"artAssets/cmCalendarCompetitions/cmcomp_%d.swf",1693)==(int)strlen(expected) && !strcmp(name,expected));
    CHECK(ui_print(name,4,"%s","abcdef")==6 && !strcmp(name,"abc"));
    CHECK(ui_print(name,strlen(request),"%s",request)==(int)strlen(request) && strlen(name)==strlen(request)-1);
    {char *parts[3]={name,name,name+sizeof(name)};
     CHECK(ui_string(parts,"artAssets/cmCalendarCompetitions/cmcomp_%d.swf",1693)==parts);
     CHECK(!strcmp(name,expected) && parts[1]==name+strlen(name));
     ui_string(parts,"ui/imgAssets/kits/j%d_%d_0.dds",30,110636);
     CHECK(!strcmp(name,"ui/imgAssets/kits/j30_110636_0.dds"));}
    memcpy(rows,&id,4);memcpy(rows+4,&type,4);memcpy(rows+12,"CRTR",5);
    memcpy(rows+17,"cm_pst_champions_trophy",23);memcpy(rows+0x54,&asset,4);
    CHECK(resolve_rows(rows,2,id)==820);CHECK(!resolve_rows(rows,2,2239));
    memcpy(rows+0x5c,rows,0x5c);CHECK(!resolve_rows(rows,2,id));memset(rows+0x5c,0,0x5c);
    memcpy(competition+0x10,rows,0x5c);memcpy(registry+20*32+24,&wrapper,sizeof(wrapper));
    InterlockedExchange(&capacity_ready,1);
    CHECK(Fifa16UiAssetsResolveCompetition(id,registry)==820);
    CHECK(!Fifa16UiAssetsResolveCompetition(1693,NULL)); /* Host owns official ID resolution. */
    CHECK(alias_name("j2_110636_0.dds",alias,sizeof(alias)) && !strcmp(alias,"j30_110636_0.dds"));
    CHECK(!alias_name("j2_110636_1.dds",alias,sizeof(alias)));
    puts("PASS: dedicated DDS without BIG/league directories, missing/invalid files, IDs, formatter bounds, preseason and unrelated UI paths");return 0;
}
