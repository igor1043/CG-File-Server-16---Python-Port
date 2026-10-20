/* Check the real initializer's complete patch barrier in private memory. */
#include "../../src/host/dinput8_wrapper.c"
#include <assert.h>
static int commit_page(unsigned char *base,uintptr_t rva)
{
    return VirtualAlloc(base+(rva&~(uintptr_t)4095),4096,MEM_COMMIT,PAGE_READWRITE)!=NULL;
}
int main(void)
{
    SIZE_T i;
    int transfer_count=0;
    unsigned char *base=(unsigned char *)VirtualAlloc(NULL,0x09525000,MEM_RESERVE,PAGE_NOACCESS);
    assert(base);
    for(i=0;i<sizeof(g_patches)/sizeof(g_patches[0]);++i) {
        const PatchSpec *p=&g_patches[i];
        assert(commit_page(base,p->rva));memcpy(base+p->rva,p->expected,p->size);
    }
    for(i=0;i<sizeof(g_call_patches)/sizeof(g_call_patches[0]);++i) {
        const CallPatchSpec *p=&g_call_patches[i];
        int32_t delta=(int32_t)((intptr_t)p->expected_target_rva-(intptr_t)p->call_rva-5);
        assert(commit_page(base,p->call_rva));base[p->call_rva]=0xE8;
        memcpy(base+p->call_rva+1,&delta,sizeof(delta));
        if(p->replacement==(void *)career_transfer_cards_publish) ++transfer_count;
    }
    assert(transfer_count==4 && career_patch_sites_ready(base,NULL));
    for(i=0;i<sizeof(g_call_patches)/sizeof(g_call_patches[0]);++i) {
        const CallPatchSpec *p=&g_call_patches[i];
        if(p->replacement!=(void *)career_transfer_cards_publish) continue;
        base[p->call_rva]=0xCC;
        assert(!career_patch_sites_ready(base,NULL));
        base[p->call_rva]=0xE8;
        base[p->call_rva+1]^=1;
        assert(!career_patch_sites_ready(base,NULL));
        base[p->call_rva+1]^=1;
        assert(career_patch_sites_ready(base,NULL));
    }
    VirtualFree(base,0,MEM_RELEASE);
    puts("PASS: all four transfer call sites validated before installation; encrypted/changed sites rejected without writes");
    return 0;
}
