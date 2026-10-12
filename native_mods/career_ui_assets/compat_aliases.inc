/* Retain the installed module's goalkeeper thumbnail compatibility. */
static BOOL alias_name(const char *name,char *out,size_t capacity) {
    unsigned team,year;int used=0,length;
    if(sscanf(name,"j2_%u_%u.dds%n",&team,&year,&used)!=2 || used<=0 || name[used] || !team || year!=0)return FALSE;
    length=snprintf(out,capacity,"j30_%u_0.dds",team);
    return length>0 && (size_t)length<capacity;
}
static int prepare_aliases(const char *root) {
    WIN32_FIND_DATAA info;HANDLE find;char folder[MAX_PATH],pattern[MAX_PATH],source[MAX_PATH],target[MAX_PATH],name[64];
    FILE *manifest;unsigned added=0,existing=0,failed=0;
    snprintf(folder,sizeof(folder),"%s\\data\\ui\\imgAssets\\kits",root);
    snprintf(pattern,sizeof(pattern),"%s\\j2_*_0.dds",folder);
    find=FindFirstFileA(pattern,&info);if(find==INVALID_HANDLE_VALUE)return 0;
    snprintf(pattern,sizeof(pattern),"%s\\ModCarrerMode\\logs\\career_ui_kit_aliases.tsv",root);
    manifest=fopen(pattern,"ab");if(!manifest){FindClose(find);return -1;}
    do {
        if((info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) || !alias_name(info.cFileName,name,sizeof(name)))continue;
        snprintf(source,sizeof(source),"%s\\%s",folder,info.cFileName);
        snprintf(target,sizeof(target),"%s\\%s",folder,name);
        if(GetFileAttributesA(target)!=INVALID_FILE_ATTRIBUTES){existing++;continue;}
        if(!valid_dds(source)){failed++;continue;}
        if(CreateHardLinkA(target,source,NULL) || CopyFileA(source,target,TRUE)) {
            fprintf(manifest,"%s|%s\r\n",name,info.cFileName);fflush(manifest);added++;
        } else if(GetFileAttributesA(target)!=INVALID_FILE_ATTRIBUTES)existing++;
        else failed++;
    }while(FindNextFileA(find,&info));
    fclose(manifest);FindClose(find);
    log_line("KIT ALIASES added/existing",(int)added,(int)existing);
    log_line("KIT ALIASES failures",(int)failed,0);
    return failed?-1:(int)added;
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsPrepareAliases(const char *root) {
    if(!root || !root[0] || strlen(root)>MAX_PATH-110)return -1;
    snprintf(game_dir,sizeof(game_dir),"%s",root);
    snprintf(log_path,sizeof(log_path),"%s\\ModCarrerMode\\logs\\career_ui_assets.log",root);
    return prepare_aliases(root);
}
__declspec(dllexport) int WINAPI Fifa16UiAssetsPrepareCalendar(const char *root) {
    if(!root || !root[0] || strlen(root)>MAX_PATH-110)return -1;
    snprintf(game_dir,sizeof(game_dir),"%s",root);
    snprintf(log_path,sizeof(log_path),"%s\\ModCarrerMode\\logs\\career_ui_assets.log",root);
    build_catalog();return (int)calendar_count;
}
