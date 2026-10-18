#define UI_ASSETS_TEST
#include "career_ui_assets.c"
#include "path_hooks.inc"
#include "../career_native/src/host/calendar_icon_identity.h"
#include "../career_native/src/core/fce_contracts.c"
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
    char name[MAX_PATH],out[MAX_PATH],alias[64];int reference[3]={1738,1739,820};
    const FceCompNode nodes[]={{1437,1361,3,1003,0},{1458,1437,4,-1,2},{1597,1596,3,229,0},
        {1702,1597,4,-1,0},{1738,1596,3,7,0},{1739,1738,4,-1,0},{2419,2314,3,23,0},{2430,2419,4,-1,0}};
    FceCompetition identity;
    CHECK(argc==2 && strlen(argv[1])<MAX_PATH-110);strcpy(game_dir,argv[1]);
    build_catalog();CHECK(calendar_count==5);
    CHECK(Fifa16UiAssetsHasCompetition(1001761));CHECK(Fifa16UiAssetsHasCompetition(7));
    CHECK(!Fifa16UiAssetsHasCompetition(1738));CHECK(!Fifa16UiAssetsHasCompetition(1001700));
    CHECK(resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_1001761.swf",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/calendar/c1761.dds"));
    CHECK(resolve_image_path("data\\ui\\artAssets\\cmCalendarCompetitions\\cmcomp_1001460.big",out,sizeof(out)));
    CHECK(!strcmp(out,"data/ui/imgAssets/careerCompetitionIcons/calendar/c1460.dds"));
    CHECK(resolve_image_path("ui/imgAssets/league/dark/l1001620.dds",out,sizeof(out)));
    CHECK(!strcmp(out,"ui/imgAssets/careerCompetitionIcons/cards/c1620.dds"));
    CHECK(resolve_image_path("imgAssets/league/light/l1003.dds",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/cards/c1460.dds"));
    CHECK(resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_0.swf",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/calendar/empty.dds"));
    CHECK(resolve_image_path("artAssets/cmCalendarCompetitions/cmcomp_1001700.big",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/calendar/empty.dds"));
    CHECK(resolve_image_path("imgAssets/league/light/l1001700.dds",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/cards/empty.dds"));
    visual_competition[3003]=1918;
    CHECK(resolve_image_path("imgAssets/league/light/l3003.dds",out,sizeof(out)));
    CHECK(!strcmp(out,"imgAssets/careerCompetitionIcons/cards/empty.dds"));
    CHECK(!resolve_image_path("artAssets/cmCalendar/cmcalendar_8.swf",out,sizeof(out)));
    CHECK(!resolve_image_path("imgAssets/crest/light/l1043.dds",out,sizeof(out)));
    CHECK(!resolve_image_path("artAssets/stadium/stadium_cmphoto_0123456789abcdef.big",out,sizeof(out)));
    native_print_core=test_print_core;native_string_core=test_string_core;
    CHECK(ui_print(name,sizeof(name),"%s_%s","por","br")==6 && !strcmp(name,"por_br"));
    CHECK(ui_print(name,sizeof(name),"data/loc/%s.db","por_br")==18 && !strcmp(name,"data/loc/por_br.db"));
    CHECK(ui_print(name,sizeof(name),"artAssets/cmCalendarCompetitions/cmcomp_%d.swf",1002442)>0);
    CHECK(!strcmp(name,"imgAssets/careerCompetitionIcons/calendar/c2442.dds"));
    {char *parts[3]={name,name,name+sizeof(name)};
     CHECK(ui_string(parts,"ui/imgAssets/league/light/l%d.dds",1002442)==parts);
     CHECK(!strcmp(name,"ui/imgAssets/careerCompetitionIcons/cards/c2442.dds"));}
    CHECK(alias_name("j2_110636_0.dds",alias,sizeof(alias)) && !strcmp(alias,"j30_110636_0.dds"));
    CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_OK && identity.asset==7);
    reference[2]=437;CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_OK && identity.asset==7);
    reference[0]=1437;reference[1]=1458;reference[2]=839;
    CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_OK && identity.asset==1003);
    reference[0]=1597;reference[1]=1702;CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_OK && identity.asset==229);
    reference[0]=2419;reference[1]=2430;CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_OK && identity.asset==23);
    reference[0]=1738;reference[1]=1458;CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_CONFLICT);
    reference[0]=9999;reference[1]=9998;reference[2]=1738;
    CHECK(calendar_icon_identity(nodes,8,reference,&identity)==FCE_UNKNOWN);
    puts("PASS: one competition-ID folder, calendar/cards proportions, no BIG resources, live career identity, fixture namespace isolation and unrelated paths");return 0;
}
