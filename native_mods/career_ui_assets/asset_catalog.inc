/* Calendar images have their own directory; no league or BIG lookup at runtime. */
static volatile LONG catalog_ready;
static unsigned calendar_count;
static unsigned char legacy_unavailable[65536];
static int calendar_id(const char *name,const char *stem,const char *suffix) {
    const char *number;char *end;unsigned long value;size_t length=strlen(stem);
    if(_strnicmp(name,stem,length))return 0;
    number=name+length;if(*number<'0' || *number>'9')return 0;
    errno=0;value=strtoul(number,&end,10);
    if(errno || value==0 || value>65535 || _stricmp(end,suffix))return 0;
    return (int)value;
}
static BOOL calendar_dds(const char *path) {
    FILE *file=fopen(path,"rb");BYTE header[128];size_t got;long length;
    if(!file)return FALSE;
    got=fread(header,1,sizeof(header),file);
    length=fseek(file,0,SEEK_END)?0:ftell(file);fclose(file);
    return got==128 && length>=16512 && !memcmp(header,"DDS ",4) && integer(header+4)==124 &&
        integer(header+12)==128 && integer(header+16)==128 && !memcmp(header+84,"DXT5",4);
}
static BOOL existing_calendar(int asset) {
    char path[MAX_PATH];int length;
    if(asset<=0 || asset>65535 || !game_dir[0])return FALSE;
    length=snprintf(path,sizeof(path),"%s/data/ui/imgAssets/careerCompetitionIcons/c%d.dds",game_dir,asset);
    return length>0 && (size_t)length<sizeof(path) && calendar_dds(path);
}
static void build_catalog(void) {
    WIN32_FIND_DATAA info;HANDLE find;char pattern[MAX_PATH],line[1024];int id;unsigned count=0;FILE *index;
    InterlockedExchange(&catalog_ready,0);memset(legacy_unavailable,0,sizeof(legacy_unavailable));
    snprintf(pattern,sizeof(pattern),"%s/data/ui/imgAssets/careerCompetitionIcons/index.tsv",game_dir);
    index=fopen(pattern,"rb");
    if(index) {
        while(fgets(line,sizeof(line),index)) {
            char *end,*last=strrchr(line,'\t');long value;
            errno=0;value=strtol(line,&end,10);
            if(errno || value<=0 || value>65535 || *end!='\t' || !last)continue;
            if((last[1]=='0' || last[1]=='1') && (last[2]=='\r' || last[2]=='\n' || !last[2]))
                legacy_unavailable[value]=(unsigned char)(last[1]=='0');
        }
        fclose(index);
    }
    snprintf(pattern,sizeof(pattern),"%s/data/ui/imgAssets/careerCompetitionIcons/c*.dds",game_dir);
    find=FindFirstFileA(pattern,&info);
    if(find!=INVALID_HANDLE_VALUE) {
        do {
            if(!(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) &&
               (id=calendar_id(info.cFileName,"c",".dds"))!=0 && existing_calendar(id))count++;
        }while(FindNextFileA(find,&info));
        FindClose(find);
    }
    calendar_count=count;InterlockedExchange(&catalog_ready,count?1:0);
    log_line("CATALOG careerCompetitionIcons valid DDS",(int)count,3);
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsHasCompetition(int asset) {
    /* Preserve the old host's ID availability, without depending on the old DDS directory. */
    return asset>0 && asset<65536 && InterlockedCompareExchange(&catalog_ready,0,0) &&
        !legacy_unavailable[asset] && existing_calendar(asset);
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsResolveCompetition(int root,const void *registry) {
    /* The host already resolves official competitions. Do not reinterpret their IDs. */
    return Fifa16UiAssetsResolvePreseason(root,registry);
}
static int resolve_image_path(const char *input,char *out,size_t capacity) {
    char normalized[MAX_PATH],prefix[9];const char *relative;size_t i;int id,length;
    if(!input || !out || !capacity || strlen(input)>=sizeof(normalized))return 0;
    strcpy(normalized,input);
    for(i=0;normalized[i];i++)if(normalized[i]=='\\')normalized[i]='/';
    relative=normalized;prefix[0]=0;
    if(!_strnicmp(relative,"data/ui/",8)){relative+=8;strcpy(prefix,"data/ui/");}
    else if(!_strnicmp(relative,"ui/",3)){relative+=3;strcpy(prefix,"ui/");}
    id=calendar_id(relative,"artAssets/cmCalendarCompetitions/cmcomp_",".swf");
    if(!id)id=calendar_id(relative,"artAssets/cmCalendarCompetitions/cmcomp_",".big");
    if(!id)id=calendar_id(relative,"imgAssets/cmCalendarCompetitions/cmCalendarCompetitions",".dds");
    if(!id)id=calendar_id(relative,"imgAssets/cmCalendarCompetitions/light/l",".dds");
    if(!id)id=calendar_id(relative,"imgAssets/cmCalendarCompetitions/dark/l",".dds");
    if(!id || !existing_calendar(id))return 0;
    length=snprintf(out,capacity,"%simgAssets/careerCompetitionIcons/c%d.dds",prefix,id);
    return length>0 && (size_t)length<capacity;
}
