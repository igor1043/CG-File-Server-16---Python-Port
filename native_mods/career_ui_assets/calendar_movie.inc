#include "calendar_movie_template.h"
/* CalendarCell loads an APT movie. A DDS path cannot replace that resource.
 * Rebuild the small native wrapper from the selected DDS before installing
 * formatter hooks, including when the author removed the generated BIGs. */
static unsigned char calendar_movie_ready[65536];
static unsigned char card_alias_ready[65536];
static BOOL write_asset_view(const char *destination,const BYTE *pixels,size_t length) {
    BYTE chunk[4096];char temporary[MAX_PATH+64];size_t at=0,got;BOOL current=TRUE;FILE *file=fopen(destination,"rb");
    if(file){
        while(at<length){size_t count=length-at;if(count>sizeof(chunk))count=sizeof(chunk);
            got=fread(chunk,1,count,file);if(got!=count || memcmp(chunk,pixels+at,count)){current=FALSE;break;}at+=count;}
        if(current && (fgetc(file)!=EOF || ferror(file)))current=FALSE;
        fclose(file);if(current)return TRUE;
    }
    snprintf(temporary,sizeof(temporary),"%s.tmp.%lu.%lu",destination,GetCurrentProcessId(),GetCurrentThreadId());
    file=fopen(temporary,"wb");if(!file)return FALSE;
    current=fwrite(pixels,1,length,file)==length;if(fclose(file))current=FALSE;
    if(current)current=MoveFileExA(temporary,destination,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    if(!current)DeleteFileA(temporary);return current;
}
static BOOL read_competition_texture(int id,const char *kind,BYTE *pixels,size_t length,unsigned side) {
    char source[MAX_PATH];FILE *file;size_t got;BOOL current;unsigned linear=side*side,zero=0;
    snprintf(source,sizeof(source),"%s/data/ui/imgAssets/careerCompetitionIcons/%s/",game_dir,kind);
    if(id)snprintf(source+strlen(source),sizeof(source)-strlen(source),"c%d.dds",id);
    else strcat(source,"empty.dds");
    file=fopen(source,"rb");if(!file)return FALSE;
    got=fread(pixels,1,length,file);current=got==length && fgetc(file)==EOF && !ferror(file);fclose(file);
    if(!current || memcmp(pixels,"DDS ",4) || integer(pixels+4)!=124 ||
       integer(pixels+12)!=(int)side || integer(pixels+16)!=(int)side || memcmp(pixels+84,"DXT5",4))return FALSE;
    /* Pillow's writer used an uncompressed row pitch as DXT5 linear size.
     * FIFA's native DDS files declare the entire BC3 level and no RGB bits. */
    if(integer(pixels+20)!=(int)linear || integer(pixels+88)!=0){
        memcpy(pixels+20,&linear,4);memcpy(pixels+88,&zero,4);
        if(!write_asset_view(source,pixels,length))return FALSE;
    }
    return TRUE;
}
static BOOL prepare_calendar_aliases(int id,const BYTE *pixels) {
    char directory[MAX_PATH],destination[MAX_PATH];unsigned i;
    static const char *styles[2]={"light","dark"};
    const int asset=id?1000000+id:0;
    snprintf(directory,sizeof(directory),"%s/data/ui/imgAssets/cmCalendarCompetitions",game_dir);
    if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
    snprintf(destination,sizeof(destination),"%s/cmCalendarCompetitions%d.dds",directory,asset);
    if(!write_asset_view(destination,pixels,16512))return FALSE;
    for(i=0;i<2;i++){
        snprintf(directory,sizeof(directory),"%s/data/ui/imgAssets/cmCalendarCompetitions/%s",game_dir,styles[i]);
        if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
        snprintf(destination,sizeof(destination),"%s/l%d.dds",directory,asset);
        if(!write_asset_view(destination,pixels,16512))return FALSE;
    }
    return TRUE;
}
static BOOL prepare_card_aliases(int id) {
    static const char *styles[2]={"light","dark"};
    BYTE pixels[65664];char directory[MAX_PATH],destination[MAX_PATH];unsigned i;
    if(id<=0 || id>=65535)return FALSE;
    if(!read_competition_texture(id,"cards",pixels,sizeof(pixels),256))return FALSE;
    snprintf(directory,sizeof(directory),"%s/data/ui/imgAssets/league",game_dir);
    if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
    for(i=0;i<2;i++){
        snprintf(directory,sizeof(directory),"%s/data/ui/imgAssets/league/%s",game_dir,styles[i]);
        if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
        snprintf(destination,sizeof(destination),"%s/l%d.dds",directory,1000000+id);
        if(!write_asset_view(destination,pixels,sizeof(pixels)))return FALSE;
    }
    return TRUE;
}
static void calendar_big_u32(BYTE *out,unsigned value) {
    out[0]=(BYTE)(value>>24);out[1]=(BYTE)(value>>16);out[2]=(BYTE)(value>>8);out[3]=(BYTE)value;
}
static BOOL prepare_calendar_movie(int id) {
    static const char *names[6]={"0","3","sg1","2","sg2","1"};
    const unsigned sizes[6]={584,288,0,16512,0,48},offsets[6]={128,768,1088,1088,17600,17600};
    BYTE package[17664];char directory[MAX_PATH],destination[MAX_PATH];unsigned i;size_t at=16;
    if(id<0 || id>65535)return FALSE;
    memset(package,0,sizeof(package));
    if(!read_competition_texture(id,"calendar",package+1088,16512,128) || !prepare_calendar_aliases(id,package+1088))return FALSE;
    memcpy(package,"BIG4",4);i=sizeof(package);memcpy(package+4,&i,4);
    calendar_big_u32(package+8,6);calendar_big_u32(package+12,88);at=16;
    for(i=0;i<6;i++){
        size_t length=strlen(names[i])+1;
        calendar_big_u32(package+at,offsets[i]);calendar_big_u32(package+at+4,sizes[i]);at+=8;
        memcpy(package+at,names[i],length);at+=length;
    }
    memcpy(package+at,"L286\x15\x05\0\0",8);
    memcpy(package+128,calendar_movie,sizeof(calendar_movie));
    memcpy(package+768,calendar_geometry,sizeof(calendar_geometry));
    memcpy(package+17600,calendar_constants,sizeof(calendar_constants));
    snprintf(directory,sizeof(directory),"%s/data/ui/artAssets",game_dir);
    if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
    snprintf(directory,sizeof(directory),"%s/data/ui/artAssets/cmCalendarCompetitions",game_dir);
    if(!CreateDirectoryA(directory,NULL) && GetLastError()!=ERROR_ALREADY_EXISTS)return FALSE;
    snprintf(destination,sizeof(destination),"%s/cmcomp_%d.big",directory,id?1000000+id:0);
    return write_asset_view(destination,package,sizeof(package));
}
