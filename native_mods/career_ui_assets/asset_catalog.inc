/* Calendar images have their own directory; no league or BIG lookup at runtime. */
static volatile LONG catalog_ready;
static unsigned calendar_count;
static int calendar_id(const char *name,const char *stem,const char *suffix) {
    const char *number;char *end;unsigned long value;size_t length=strlen(stem);
    if(_strnicmp(name,stem,length))return 0;
    number=name+length;if(*number<'0' || *number>'9')return 0;
    errno=0;value=strtoul(number,&end,10);
    if(errno || value==0 || value>1065535 || _stricmp(end,suffix))return 0;
    return (int)value;
}
static unsigned short visual_competition[65536];
static BOOL icon_file(int id,const char *kind) {
    char path[MAX_PATH];FILE *file;BYTE header[128];long length;size_t got;int side;
    if(id<=0 || id>65535)return FALSE;
    snprintf(path,sizeof(path),"%s/data/ui/imgAssets/careerCompetitionIcons/%s/c%d.dds",game_dir,kind,id);
    file=fopen(path,"rb");if(!file)return FALSE;
    got=fread(header,1,sizeof(header),file);length=fseek(file,0,SEEK_END)?0:ftell(file);fclose(file);
    side=!strcmp(kind,"calendar")?128:256;
    return got==128 && length>=128+side*side && !memcmp(header,"DDS ",4) && integer(header+4)==124 &&
        integer(header+12)==side && integer(header+16)==side && !memcmp(header+84,"DXT5",4);
}
static BOOL existing_calendar(int visual) {
    int id=visual>0 && visual<65536?visual_competition[visual]:0;
    return id>0 && id<65535 && icon_file(id,"calendar");
}
static void build_catalog(void) {
    char path[MAX_PATH],line[1024];FILE *file;int id,visual;unsigned count=0;
    memset(visual_competition,0,sizeof(visual_competition));
    snprintf(path,sizeof(path),"%s/data/ui/imgAssets/careerCompetitionIcons/competitions.tsv",game_dir);
    file=fopen(path,"rb");
    if(file){while(fgets(line,sizeof(line),file)){
        if(sscanf(line,"%d\t%d",&id,&visual)!=2 || id<=0 || id>65535 || visual<=0 || visual>65535)continue;
        if(visual_competition[visual] && visual_competition[visual]!=id)visual_competition[visual]=65535;
        else visual_competition[visual]=(unsigned short)id;
        if(icon_file(id,"calendar") && icon_file(id,"cards"))count++;
    }fclose(file);}
    calendar_count=count;InterlockedExchange(&catalog_ready,1);
    log_line("CATALOG unified competition-ID icons",(int)count,4);
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsHasCompetition(int asset) {
    int id=asset>1000000 && asset<=1065535?asset-1000000:asset>0 && asset<65536?visual_competition[asset]:0;
    return id>0 && id<65535 && icon_file(id,"calendar") && icon_file(id,"cards");
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsResolveCompetition(int root,const void *registry) {
    /* The host already resolves official competitions. Do not reinterpret their IDs. */
    return Fifa16UiAssetsResolvePreseason(root,registry);
}
static int resolve_image_path(const char *input,char *out,size_t capacity) {
    char normalized[MAX_PATH],prefix[9];const char *relative,*kind="cards";size_t i;int asset,id,length;
    if(!input || !out || !capacity || strlen(input)>=sizeof(normalized))return 0;
    strcpy(normalized,input);for(i=0;normalized[i];i++)if(normalized[i]=='\\')normalized[i]='/';
    relative=normalized;prefix[0]=0;
    if(!_strnicmp(relative,"data/ui/",8)){relative+=8;strcpy(prefix,"data/ui/");}
    else if(!_strnicmp(relative,"ui/",3)){relative+=3;strcpy(prefix,"ui/");}
    asset=calendar_id(relative,"artAssets/cmCalendarCompetitions/cmcomp_",".swf");
    if(!asset)asset=calendar_id(relative,"artAssets/cmCalendarCompetitions/cmcomp_",".big");
    if(!asset)asset=calendar_id(relative,"imgAssets/cmCalendarCompetitions/cmCalendarCompetitions",".dds");
    if(!asset)asset=calendar_id(relative,"imgAssets/cmCalendarCompetitions/light/l",".dds");
    if(!asset)asset=calendar_id(relative,"imgAssets/cmCalendarCompetitions/dark/l",".dds");
    if(asset || !_strnicmp(relative,"artAssets/cmCalendarCompetitions/cmcomp_",strlen("artAssets/cmCalendarCompetitions/cmcomp_")) || !_strnicmp(relative,"imgAssets/cmCalendarCompetitions/",strlen("imgAssets/cmCalendarCompetitions/")))kind="calendar";
    else {
        asset=calendar_id(relative,"imgAssets/league/light/l",".dds");
        if(!asset)asset=calendar_id(relative,"imgAssets/league/dark/l",".dds");
    }
    id=asset>1000000 && asset<=1065535?asset-1000000:asset>0 && asset<65536?visual_competition[asset]:0;
    if(id<=0 || id>=65535 || !icon_file(id,kind)) {
        if(strcmp(kind,"calendar") && asset<=1000000 && (id<=0 || id>=65535))return 0;
        /* Missing calendar artwork has a transparent DDS, never a BIG fallback. */
        length=snprintf(out,capacity,"%simgAssets/careerCompetitionIcons/%s/empty.dds",prefix,kind);
        return length>0 && (size_t)length<capacity;
    }
    length=snprintf(out,capacity,"%simgAssets/careerCompetitionIcons/%s/c%d.dds",prefix,kind,id);
    return length>0 && (size_t)length<capacity;
}
