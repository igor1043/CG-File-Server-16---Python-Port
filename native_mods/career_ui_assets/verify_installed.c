#define UI_ASSETS_TEST
#include "career_ui_assets.c"
int main(int argc,char **argv){
    char manifest[MAX_PATH],line[1024],request[MAX_PATH],out[MAX_PATH],expected[MAX_PATH];
    FILE *file;unsigned checked=0,missing=0;int id,visual;
    if(argc!=2 || strlen(argv[1])>=MAX_PATH-110)return 2;
    strcpy(game_dir,argv[1]);build_catalog();
    snprintf(manifest,sizeof(manifest),"%s/data/ui/imgAssets/careerCompetitionIcons/competitions.tsv",game_dir);
    file=fopen(manifest,"rb");if(!file)return 3;
    while(fgets(line,sizeof(line),file)){
        if(sscanf(line,"%d\t%d",&id,&visual)!=2 || id<=0 || id>=65535 || visual<=0 || visual>=65535)continue;
        if(!icon_file(id,"calendar") || !icon_file(id,"cards") || !card_alias_ready[id]){printf("MISSING id=%d visual=%d\n",id,visual);missing++;continue;}
        snprintf(request,sizeof(request),"artAssets/cmCalendarCompetitions/cmcomp_%d.swf",1000000+id);
        snprintf(expected,sizeof(expected),"artAssets/cmCalendarCompetitions/cmcomp_%d.swf",1000000+id);
        if(!resolve_image_path(request,out,sizeof(out)) || strcmp(out,expected))return 4;
        snprintf(request,sizeof(request),"imgAssets/league/light/l%d.dds",1000000+id);
        snprintf(expected,sizeof(expected),"imgAssets/careerCompetitionIcons/cards/c%d.dds",id);
        if(!resolve_image_path(request,out,sizeof(out)) || strcmp(out,expected))return 5;
        ++checked;
    }
    fclose(file);printf("PASS installed %s: native calendar movies=%u complete icons=%u missing=%u\n",game_dir,calendar_count,checked,missing);
    return missing?6:0;
}
