#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "ultrawide_bridge.h"
#include "ultrawide_math.h"
#include "ultrawide_background.h"
#include <d3d11_3.h>
#include <shlobj.h>
#include <stdio.h>
#include <string.h>
#include <algorithm>
#include <intrin.h>
#include "mod_overlay_screens.h"
#pragma comment(lib,"shell32.lib")

namespace {
static void (*log_line)(const char *);
static wchar_t ini[MAX_PATH],status_path[MAX_PATH];
static float *aspect_address,original_aspect;
static volatile LONG enabled,stopping;
static SRWLOCK aspect_lock=SRWLOCK_INIT;
static HWND game_window;
static WNDPROC previous_proc;
static ID3D11DeviceContext *game_context;
static ID3D11Resource *backbuffer;
static void **context_vtable,**native_vtable;
static unsigned char *dispatch_code;
static uint64_t next_poll;
static UINT width,height;
static bool final_pass,scene_copied,ready;
struct ImageRange {uintptr_t first,last;};
static ImageRange game_images[2];
static ultrawide::Backgrounds backgrounds;
static thread_local bool overlay,inside;
typedef void (STDMETHODCALLTYPE *DrawFn)(ID3D11DeviceContext*,UINT,UINT);
typedef void (STDMETHODCALLTYPE *DrawIndexedFn)(ID3D11DeviceContext*,UINT,UINT,INT);
typedef void (STDMETHODCALLTYPE *DrawInstancedFn)(ID3D11DeviceContext*,UINT,UINT,UINT,UINT);
typedef void (STDMETHODCALLTYPE *DrawIndexedInstancedFn)(ID3D11DeviceContext*,UINT,UINT,UINT,INT,UINT);
typedef void (STDMETHODCALLTYPE *DrawAutoFn)(ID3D11DeviceContext*);
typedef void (STDMETHODCALLTYPE *DrawIndirectFn)(ID3D11DeviceContext*,ID3D11Buffer*,UINT);
typedef void (STDMETHODCALLTYPE *TargetsFn)(ID3D11DeviceContext*,UINT,ID3D11RenderTargetView *const*,ID3D11DepthStencilView*);
typedef void (STDMETHODCALLTYPE *TargetsUavFn)(ID3D11DeviceContext*,UINT,ID3D11RenderTargetView *const*,ID3D11DepthStencilView*,UINT,UINT,ID3D11UnorderedAccessView *const*,const UINT*);
static DrawFn draw_original;
static DrawIndexedFn indexed_original;
static DrawInstancedFn instanced_original;
static DrawIndexedInstancedFn indexed_instanced_original;
static DrawAutoFn auto_original;
static DrawIndirectFn indirect_original,indexed_indirect_original;
static TargetsFn targets_original;
static TargetsUavFn targets_uav_original;
static void locate_game_images() {
    const wchar_t *names[]={L"fifa16.exe",L"fifa16.bin"};
    for(unsigned i=0;i<2;++i) {
        auto base=(unsigned char*)GetModuleHandleW(names[i]);
#ifdef ULTRAWIDE_TEST
        if(i==0)base=(unsigned char*)GetModuleHandleW(nullptr);
#endif
        if(!base)continue;
        auto dos=(IMAGE_DOS_HEADER*)base;if(dos->e_magic!=IMAGE_DOS_SIGNATURE)continue;
        auto nt=(IMAGE_NT_HEADERS64*)(base+dos->e_lfanew);
        if(nt->Signature==IMAGE_NT_SIGNATURE)game_images[i]={(uintptr_t)base,(uintptr_t)base+nt->OptionalHeader.SizeOfImage};
    }
}
static bool native_draw(void *caller) {
    uintptr_t address=(uintptr_t)caller;
    for(auto &image:game_images)if(address>=image.first&&address<image.last)return true;
    return false;
}
static bool map_pointer(HWND window,POINT *position,bool screen) {
    if(!ready||stopping||!window||!position||width<64||height<64)return false;
#ifndef ULTRAWIDE_TEST
    // Our modal overlays poll their own physical mouse and perform their own
    // centring; only FIFA's native input is converted here.
    if(mod_screen_captures_input())return false;
#endif
    RECT r={};POINT origin={};
    if(!GetClientRect(window,&r)||(screen&&!ClientToScreen(window,&origin)))return false;
    position->x=origin.x+LONG(lroundf(ultrawide::ui_pointer_x(float(position->x-origin.x),float(r.right-r.left),float(width),float(height))));
    return true;
}
struct AspectLock {
    AspectLock(){AcquireSRWLockExclusive(&aspect_lock);}
    ~AspectLock(){ReleaseSRWLockExclusive(&aspect_lock);}
};

static bool write_aspect(float value) {
    AspectLock guard;
    if(!aspect_address||fabsf(*aspect_address-value)<.00001f)return aspect_address!=nullptr;
    // Do not overwrite a concurrent widescreen tool's change.
    static float ours=ultrawide::native_aspect;
    float actual=*aspect_address;
    if(fabsf(actual-ours)>.00001f&&fabsf(actual-original_aspect)>.00001f)return false;
    DWORD old,ignored;
    if(!VirtualProtect(aspect_address,4,PAGE_READWRITE,&old))return false;
    InterlockedExchange((volatile LONG*)aspect_address,*(LONG*)&value);
    VirtualProtect(aspect_address,4,old,&ignored);ours=value;return true;
}
static bool locate_aspect() {
    auto base=(unsigned char*)GetModuleHandleW(nullptr);
    auto dos=(IMAGE_DOS_HEADER*)base;
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE)return false;
    auto nt=(IMAGE_NT_HEADERS64*)(base+dos->e_lfanew);
    if(nt->Signature!=IMAGE_NT_SIGNATURE||nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC)return false;
    size_t hits=0;float *found=nullptr;
    auto section=IMAGE_FIRST_SECTION(nt);
    for(unsigned i=0;i<nt->FileHeader.NumberOfSections;++i) {
        if(!(section[i].Characteristics&IMAGE_SCN_MEM_READ)||(section[i].Characteristics&IMAGE_SCN_MEM_EXECUTE))continue;
        size_t at=0,size=section[i].Misc.VirtualSize;
        if(uint64_t(section[i].VirtualAddress)+size>nt->OptionalHeader.SizeOfImage)continue;
        // Never walk a discarded/uncommitted section directly in the game.
        auto copy=(uint8_t*)HeapAlloc(GetProcessHeap(),0,size);SIZE_T read=0;
        if(!copy)continue;
        size_t n=0;
        if(ReadProcessMemory(GetCurrentProcess(),base+section[i].VirtualAddress,copy,size,&read)&&read==size)
            n=ultrawide::find_anchor(copy,size,at);
        HeapFree(GetProcessHeap(),0,copy);
        hits+=n;if(n==1)found=(float*)(base+section[i].VirtualAddress+at);
    }
    if(hits!=1||!found||((uintptr_t)found&3))return false;
    aspect_address=found;original_aspect=*found;return true;
}
static void initial_resolution() {
    wchar_t documents[MAX_PATH],file[MAX_PATH];
    if(FAILED(SHGetFolderPathW(nullptr,CSIDL_PERSONAL,nullptr,SHGFP_TYPE_CURRENT,documents)))return;
    _snwprintf_s(file,_countof(file),_TRUNCATE,L"%s\\FIFA 16\\fifasetup.ini",documents);
    FILE *input=nullptr;if(_wfopen_s(&input,file,L"rt")||!input)return;
    char line[256];unsigned w=0,h=0;
    while(fgets(line,sizeof(line),input)) {
        sscanf_s(line,"RESOLUTIONWIDTH = %u",&w);sscanf_s(line,"RESOLUTIONHEIGHT = %u",&h);
    }fclose(input);
    if(w>=64&&h>=64)write_aspect(enabled?ultrawide::aspect(w,h):original_aspect);
}
static LRESULT CALLBACK window_proc(HWND hwnd,UINT message,WPARAM wp,LPARAM lp) {
    if(message==WM_SIZE&&wp!=SIZE_MINIMIZED&&!stopping) {
        unsigned w=LOWORD(lp),h=HIWORD(lp);
        if(w>=64&&h>=64)write_aspect(enabled?ultrawide::aspect(w,h):original_aspect);
    }
    bool client=message==WM_MOUSEMOVE||message==WM_MOUSEHOVER||
        (message>=WM_LBUTTONDOWN&&message<=WM_XBUTTONDBLCLK);
    bool screen=message==WM_MOUSEWHEEL||message==WM_MOUSEHWHEEL;
    if(client||screen) {
        POINT point={SHORT(LOWORD(lp)),SHORT(HIWORD(lp))};
        if(map_pointer(hwnd,&point,screen))lp=MAKELPARAM(SHORT(point.x),SHORT(point.y));
    }
    return CallWindowProcW(previous_proc,hwnd,message,wp,lp);
}
static void set_final_target(ID3D11DeviceContext *ctx) {
    if(ctx!=game_context||overlay||inside)return;
    ID3D11RenderTargetView *rt=nullptr;ctx->OMGetRenderTargets(1,&rt,nullptr);
    ID3D11Resource *resource=nullptr;if(rt){rt->GetResource(&resource);rt->Release();}
    bool next=resource&&resource==backbuffer;
    if(next&&!final_pass)scene_copied=false;
    final_pass=next;
    if(resource)resource->Release();
}
static void STDMETHODCALLTYPE targets_hook(ID3D11DeviceContext *ctx,UINT n,ID3D11RenderTargetView *const *rt,ID3D11DepthStencilView *ds) {
    targets_original(ctx,n,rt,ds);set_final_target(ctx);
}
static void STDMETHODCALLTYPE targets_uav_hook(ID3D11DeviceContext *ctx,UINT n,ID3D11RenderTargetView *const *rt,ID3D11DepthStencilView *ds,UINT start,UINT count,ID3D11UnorderedAccessView *const *uav,const UINT *initial) {
    targets_uav_original(ctx,n,rt,ds,start,count,uav,initial);set_final_target(ctx);
}
// Transform just the final UI draws, leaving every world/depth/shadow pass
// untouched. Restore exactly the caller's viewport and scissor after EACH draw.
struct UiDraw {
    ID3D11DeviceContext *ctx;UINT nv=16,nr=16;
    D3D11_VIEWPORT view[16];D3D11_RECT rect[16];bool applied=false;
    ID3D11ShaderResourceView *backgroundView=nullptr;UINT backgroundSlot=0;
    explicit UiDraw(ID3D11DeviceContext *c,void *caller):ctx(c) {
        if(c!=game_context||!ready||stopping||overlay||inside||!final_pass||!native_draw(caller))return;
        if(!scene_copied){scene_copied=true;return;}
        inside=true;
        const bool background=backgrounds.select(c,enabled!=0,backgroundSlot,backgroundView);
        inside=false;
        // Keep only the verified native backdrop at full width, behind all UI.
        // Its texture also switches live if FIFA cached the other DDS already.
        if(background||!enabled)return;
        auto region=ultrawide::ui_region(float(width),float(height));if(region.scale==1)return;
        inside=true;c->RSGetViewports(&nv,view);c->RSGetScissorRects(&nr,rect);
        if(nv==1&&ultrawide::centred_view(view[0].TopLeftX,view[0].Width,float(width),float(height))){inside=false;return;}
        D3D11_VIEWPORT mapped[16];D3D11_RECT scissors[16];
        for(UINT i=0;i<nv;++i){mapped[i]=view[i];mapped[i].TopLeftX=region.x+view[i].TopLeftX*region.scale;mapped[i].Width*=region.scale;}
        for(UINT i=0;i<nr;++i){scissors[i]=rect[i];scissors[i].left=LONG(lroundf(region.x+rect[i].left*region.scale));scissors[i].right=LONG(lroundf(region.x+rect[i].right*region.scale));}
        c->RSSetViewports(nv,mapped);c->RSSetScissorRects(nr,scissors);applied=true;
    }
    ~UiDraw(){
        if(applied){ctx->RSSetViewports(nv,view);ctx->RSSetScissorRects(nr,rect);inside=false;}
        if(backgroundView){ctx->PSSetShaderResources(backgroundSlot,1,&backgroundView);backgroundView->Release();}
    }
};
static void STDMETHODCALLTYPE draw_hook(ID3D11DeviceContext*c,UINT a,UINT b){UiDraw guard(c,_ReturnAddress());draw_original(c,a,b);}
static void STDMETHODCALLTYPE indexed_hook(ID3D11DeviceContext*c,UINT a,UINT b,INT d){UiDraw guard(c,_ReturnAddress());indexed_original(c,a,b,d);}
static void STDMETHODCALLTYPE instanced_hook(ID3D11DeviceContext*c,UINT a,UINT b,UINT d,UINT e){UiDraw guard(c,_ReturnAddress());instanced_original(c,a,b,d,e);}
static void STDMETHODCALLTYPE indexed_instanced_hook(ID3D11DeviceContext*c,UINT a,UINT b,UINT d,INT e,UINT f){UiDraw guard(c,_ReturnAddress());indexed_instanced_original(c,a,b,d,e,f);}
static void STDMETHODCALLTYPE auto_hook(ID3D11DeviceContext*c){UiDraw guard(c,_ReturnAddress());auto_original(c);}
static void STDMETHODCALLTYPE indirect_hook(ID3D11DeviceContext*c,ID3D11Buffer*b,UINT offset){UiDraw guard(c,_ReturnAddress());indirect_original(c,b,offset);}
static void STDMETHODCALLTYPE indexed_indirect_hook(ID3D11DeviceContext*c,ID3D11Buffer*b,UINT offset){UiDraw guard(c,_ReturnAddress());indexed_indirect_original(c,b,offset);}
static bool patch_slot(unsigned index,void *replacement,void **prior) {
    DWORD old,ignored;if(!VirtualProtect(context_vtable+index,sizeof(void*),PAGE_READWRITE,&old))return false;
    *prior=InterlockedExchangePointer((PVOID volatile*)(context_vtable+index),replacement);
    VirtualProtect(context_vtable+index,sizeof(void*),old,&ignored);return true;
}
static void restore_slot(unsigned index,void *replacement,void *prior) {
    if(!context_vtable||context_vtable[index]!=replacement)return;
    DWORD old,ignored;if(VirtualProtect(context_vtable+index,sizeof(void*),PAGE_READWRITE,&old)) {
        InterlockedCompareExchangePointer((PVOID volatile*)(context_vtable+index),prior,replacement);
        VirtualProtect(context_vtable+index,sizeof(void*),old,&ignored);
    }
}
static void restore_hooks() {
#define RESTORE(slot,name,hook) if(name)restore_slot(slot,(void*)hook,(void*)name)
    RESTORE(12,indexed_original,indexed_hook);RESTORE(13,draw_original,draw_hook);
    RESTORE(20,indexed_instanced_original,indexed_instanced_hook);RESTORE(21,instanced_original,instanced_hook);
    RESTORE(33,targets_original,targets_hook);RESTORE(34,targets_uav_original,targets_uav_hook);
    RESTORE(38,auto_original,auto_hook);RESTORE(39,indexed_indirect_original,indexed_indirect_hook);RESTORE(40,indirect_original,indirect_hook);
#undef RESTORE
}
static bool install_context(ID3D11DeviceContext *ctx) {
    if(game_context)return game_context==ctx;
    // The D3D runtime rewrites its embedded dispatch table after Map and state
    // swaps. A private table keeps our wrappers out of those mutable slots.
    // Preserve every method of the highest interface sharing this COM pointer.
    native_vtable=*(void***)ctx;
    size_t methods=115;
    ID3D11DeviceContext4 *v4=nullptr;ID3D11DeviceContext3 *v3=nullptr;
    ID3D11DeviceContext2 *v2=nullptr;ID3D11DeviceContext1 *v1=nullptr;
    if(SUCCEEDED(ctx->QueryInterface(__uuidof(ID3D11DeviceContext4),(void**)&v4))){if((void*)v4==(void*)ctx)methods=149;v4->Release();}
    if(methods==115&&SUCCEEDED(ctx->QueryInterface(__uuidof(ID3D11DeviceContext3),(void**)&v3))){if((void*)v3==(void*)ctx)methods=147;v3->Release();}
    if(methods==115&&SUCCEEDED(ctx->QueryInterface(__uuidof(ID3D11DeviceContext2),(void**)&v2))){if((void*)v2==(void*)ctx)methods=144;v2->Release();}
    if(methods==115&&SUCCEEDED(ctx->QueryInterface(__uuidof(ID3D11DeviceContext1),(void**)&v1))){if((void*)v1==(void*)ctx)methods=134;v1->Release();}
    context_vtable=(void**)VirtualAlloc(nullptr,methods*sizeof(void*),MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if(!context_vtable)return false;
    // Forward non-intercepted methods through the runtime's LIVE table. Copying
    // the old function addresses freezes its state-specific dispatch and can
    // lose shaders after SwapDeviceContextState. These stubs contain no copied
    // Microsoft instructions and preserve every argument register.
    dispatch_code=(unsigned char*)VirtualAlloc(nullptr,methods*16,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if(!dispatch_code){VirtualFree(context_vtable,0,MEM_RELEASE);context_vtable=nullptr;return false;}
    for(size_t i=0;i<methods;++i) {
        unsigned char *code=dispatch_code+i*16;void **slot=native_vtable+i;
        code[0]=0x48;code[1]=0xb8;memcpy(code+2,&slot,8);code[10]=0xff;code[11]=0x20;
        context_vtable[i]=code;
    }
    DWORD oldProtection;
    if(!VirtualProtect(dispatch_code,methods*16,PAGE_EXECUTE_READ,&oldProtection))return false;
    FlushInstructionCache(GetCurrentProcess(),dispatch_code,methods*16);
    bool ok=true;
#define HOOK(slot,name,hook) ok=patch_slot(slot,(void*)hook,(void**)&name)&&ok
    HOOK(12,indexed_original,indexed_hook);HOOK(13,draw_original,draw_hook);
    HOOK(20,indexed_instanced_original,indexed_instanced_hook);HOOK(21,instanced_original,instanced_hook);
    HOOK(33,targets_original,targets_hook);HOOK(34,targets_uav_original,targets_uav_hook);
    HOOK(38,auto_original,auto_hook);HOOK(39,indexed_indirect_original,indexed_indirect_hook);HOOK(40,indirect_original,indirect_hook);
#undef HOOK
    if(!ok){restore_hooks();return false;}
    game_context=ctx;ctx->AddRef();
    InterlockedExchangePointer((PVOID volatile*)ctx,context_vtable);
    return true;
}
static void publish_status() {
    wchar_t temp[MAX_PATH];_snwprintf_s(temp,_countof(temp),_TRUNCATE,L"%s.tmp",status_path);
    FILE *out=nullptr;if(_wfopen_s(&out,temp,L"wt")||!out)return;
    fprintf(out,"UW1 %lu %llu %ld %u %u %d\n",GetCurrentProcessId(),GetTickCount64(),enabled,width,height,ready?1:0);
    fclose(out);MoveFileExW(temp,status_path,MOVEFILE_REPLACE_EXISTING);
}
}
void ultrawide_initialize(HMODULE owner,void (*logger)(const char *)) {
    locate_game_images();
    log_line=logger;wchar_t path[MAX_PATH];GetModuleFileNameW(owner,path,_countof(path));
    wchar_t *last=wcsrchr(path,L'\\');if(!last)return;*last=0;
    _snwprintf_s(ini,_countof(ini),_TRUNCATE,L"%s\\..\\ultrawide\\ultrawide.ini",path);
    _snwprintf_s(status_path,_countof(status_path),_TRUNCATE,L"%s\\..\\ultrawide\\runtime_state.txt",path);
    wchar_t standard[MAX_PATH],wide[MAX_PATH];
    _snwprintf_s(standard,_countof(standard),_TRUNCATE,L"%s\\..\\..\\data\\ultrawide\\st_bootflow_standard.dds",path);
    _snwprintf_s(wide,_countof(wide),_TRUNCATE,L"%s\\..\\..\\data\\ultrawide\\st_bootflow_ultrawide.dds",path);
    backgrounds.initialize(standard,wide);
    ready=locate_aspect();enabled=ready&&GetPrivateProfileIntW(L"ultrawide",L"enabled",0,ini)!=0;
    if(ready)initial_resolution();
    if(logger)logger(ready?"Ultrawide: unique native aspect anchor verified; config bridge ready":"Ultrawide: unsupported aspect anchor; no memory changed");
}
void ultrawide_present(IDXGISwapChain *sc) {
    if(stopping||!sc||!aspect_address)return;
    DXGI_SWAP_CHAIN_DESC desc={};if(FAILED(sc->GetDesc(&desc)))return;
    uint64_t now=GetTickCount64();
    if(now>=next_poll) {
        next_poll=now+500;
        LONG want=GetPrivateProfileIntW(L"ultrawide",L"enabled",0,ini)!=0;
        if(want!=enabled) {
            InterlockedExchange(&enabled,want);
            write_aspect(want?ultrawide::aspect(desc.BufferDesc.Width,desc.BufferDesc.Height):original_aspect);
            // Ask FIFA to rebuild its projection using its normal resize path.
            RECT r={};if(GetClientRect(desc.OutputWindow,&r)&&r.right>=64&&r.bottom>=64)
                PostMessageW(desc.OutputWindow,WM_SIZE,SIZE_RESTORED,MAKELPARAM(r.right,r.bottom));
            if(log_line)log_line(want?"Ultrawide enabled; native resize requested":"Ultrawide disabled; original aspect restored");
        }
        publish_status();
    }
    if(!game_window) {
        game_window=desc.OutputWindow;SetLastError(0);
        previous_proc=(WNDPROC)SetWindowLongPtrW(game_window,GWLP_WNDPROC,(LONG_PTR)window_proc);
        if(!previous_proc){game_window=nullptr;ready=false;return;}
    }
    width=desc.BufferDesc.Width;height=desc.BufferDesc.Height;
    if(!write_aspect(enabled?ultrawide::aspect(width,height):original_aspect)){ready=false;return;}
    ID3D11Device *device=nullptr;ID3D11DeviceContext *ctx=nullptr;
    if(FAILED(sc->GetDevice(__uuidof(ID3D11Device),(void**)&device)))return;
    device->GetImmediateContext(&ctx);device->Release();
    if(ctx){if(!install_context(ctx))ready=false;ctx->Release();}
    ID3D11Resource *buffer=nullptr;
    if(SUCCEEDED(sc->GetBuffer(0,__uuidof(ID3D11Resource),(void**)&buffer))) {
        // Do not retain the swapchain buffer: that would block ResizeBuffers.
        backbuffer=buffer;buffer->Release();
    }else backbuffer=nullptr;
    final_pass=false;scene_copied=false;
    if(game_context)set_final_target(game_context);
}
void ultrawide_overlay(bool drawing){overlay=drawing;}
void ultrawide_cursor_position(POINT *position){map_pointer(game_window,position,true);}
void ultrawide_stop() {
    InterlockedExchange(&stopping,1);write_aspect(original_aspect);
    if(game_window&&IsWindow(game_window)&&(WNDPROC)GetWindowLongPtrW(game_window,GWLP_WNDPROC)==window_proc)
        SetWindowLongPtrW(game_window,GWLP_WNDPROC,(LONG_PTR)previous_proc);
    // The host pins the overlay DLL. Keep forwarding hooks for cached callers;
    // stopping makes every draw pass through without modifying the pipeline.
}
#ifdef ULTRAWIDE_TEST
extern "C" void ultrawide_test_backgrounds(const wchar_t *standard,const wchar_t *wide){backgrounds.initialize(standard,wide);}
extern "C" bool ultrawide_test_pointer(HWND window,POINT *p,bool screen){return map_pointer(window,p,screen);}
extern "C" LRESULT ultrawide_test_message(HWND window,UINT message,WPARAM wp,LPARAM lp,WNDPROC callback) {
    previous_proc=callback;return window_proc(window,message,wp,lp);
}
extern "C" void ultrawide_test_attach(IDXGISwapChain *sc,ID3D11DeviceContext *ctx,bool active) {
    locate_game_images();
    DXGI_SWAP_CHAIN_DESC desc={};sc->GetDesc(&desc);width=desc.BufferDesc.Width;height=desc.BufferDesc.Height;
    enabled=active;ready=true;stopping=0;install_context(ctx);
    ID3D11Resource *buffer=nullptr;sc->GetBuffer(0,__uuidof(ID3D11Resource),(void**)&buffer);backbuffer=buffer;if(buffer)buffer->Release();
    scene_copied=false;final_pass=false;
}
extern "C" void ultrawide_test_release() {
    backgrounds.clear();
    if(game_context){InterlockedCompareExchangePointer((PVOID volatile*)game_context,native_vtable,context_vtable);game_context->Release();}
    game_context=nullptr;if(context_vtable)VirtualFree(context_vtable,0,MEM_RELEASE);context_vtable=nullptr;
    if(dispatch_code)VirtualFree(dispatch_code,0,MEM_RELEASE);dispatch_code=nullptr;backbuffer=nullptr;
}
#endif
