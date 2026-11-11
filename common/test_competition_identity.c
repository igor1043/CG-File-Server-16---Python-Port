#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include "competition_identity.h"
static CompIdentityIndex index;
int main(void) {
    char dir[MAX_PATH],fixture[MAX_PATH],key[1024];FILE *file=NULL;int visual=0;
    assert(GetTempPathA(sizeof(dir),dir));assert(GetTempFileNameA(dir,"cmp",0,fixture));
    assert(!fopen_s(&file,fixture,"wb"));
    fputs("0,0,FIFA,FIFA,-1\n10,3,C83,TrophyName_Abbr15_83,0\n30,3,C7,TrophyName_Abbr15_7,0\n31,4,S1,FCE_Setup_Stage,30\n",file);fclose(file);
    assert(comp_identity_load(&index,fixture));
    assert(comp_identity_mapping(&index,"10|117|C7|TrophyName_Abbr15_7\n",&visual)==30 && visual==117);
    assert(!comp_identity_mapping(&index,"10|7\n",&visual));
    assert(comp_identity_mapping(&index,"10|83\n",&visual)==10 && visual==83);
    assert(comp_identity_visual(comp_identity_root(&index,31))==7);
    assert(comp_identity_key(&index,31,key,sizeof(key)) && !strcmp(key,"3:C7:TrophyName_Abbr15_7~4:S1:FCE_Setup_Stage"));
    assert(!fopen_s(&file,fixture,"ab"));fputs("40,3,C7,TrophyName_Abbr15_7,0\n",file);fclose(file);
    assert(comp_identity_load(&index,fixture));assert(!comp_identity_mapping(&index,"10|117|C7|TrophyName_Abbr15_7",&visual));
    assert(DeleteFileA(fixture));
    puts("PASS semantic identities: shifted IDs, reused numeric IDs, phases, custom icons and ambiguous roots");return 0;
}
