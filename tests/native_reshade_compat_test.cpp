// Runs in a standalone process; local dxgi.dll may be the untouched ReShade DLL.
#define CGFS16_OVERLAY_LOG_FILE "cgfs16_reshade_compat_test.log"
#include "../server16_py/d3d_overlay/cgfs16_overlay.cpp"
#include <cassert>
static SelectorShared shared={};
SelectorShared *g_selector=&shared;
LONG g_selector_draw_width=0,g_selector_draw_height=0;
void selector_initialize(void (*)(const char *)) {}
void selector_tick(HWND,float,float) {}
bool selector_visible() { return false; }

int wmain(int argc,wchar_t **) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    InitLog(); InitializeCriticalSection(&g_drawCs);
    g_ownModule=GetModuleHandleW(nullptr);
    HWND window=CreateWindowExW(0,L"STATIC",L"Server16 compatibility test",WS_POPUP,0,0,640,480,
        nullptr,nullptr,g_ownModule,nullptr);
    assert(window);g_renderWindow=window; // Hidden test window is explicitly selected.
    HMODULE reshade=FindReShade();
    assert((argc>1)==(reshade!=nullptr));
    if (reshade) assert(RegisterReShade(reshade));
    OverlayShared loading={};loading.visible=1;wcscpy_s(loading.stadium_name,L"Compatibility test");g_data=&loading;
    for(int generation=0;generation<3;++generation) {
        g_renderWindow=window;
        DXGI_SWAP_CHAIN_DESC d={};d.BufferDesc.Width=640;d.BufferDesc.Height=480;
        d.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;d.BufferCount=1;
        d.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;d.OutputWindow=window;d.SampleDesc.Count=1;d.Windowed=TRUE;
        IDXGISwapChain *swap=nullptr;ID3D11Device *dev=nullptr;ID3D11DeviceContext *ctx=nullptr;
        // ReShade intentionally excludes the WARP driver; use a real GPU only
        // in the isolated compatibility process, never FIFA's running device.
        assert(SUCCEEDED(D3D11CreateDeviceAndSwapChain(nullptr,reshade?D3D_DRIVER_TYPE_HARDWARE:D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,
            D3D11_SDK_VERSION,&d,&swap,&dev,nullptr,&ctx)));
        LONG before=g_frameCount;
        for(int i=0;i<60;++i) {
            if (!reshade) RenderSwapchain(swap);
            assert(SUCCEEDED(swap->Present(0,0)));
        }
        assert(g_frameCount>=before+60);
        assert(g_resourceDevice && g_vs && g_vb && !g_hookSwitched);
        assert(SUCCEEDED(swap->ResizeBuffers(0,800,600,DXGI_FORMAT_UNKNOWN,0)));
        for(int i=0;i<10;++i) {if(!reshade) RenderSwapchain(swap);assert(SUCCEEDED(swap->Present(0,0)));}
        if (!reshade) ReleaseOverlayResources();
        ctx->ClearState();ctx->Flush();ctx->Release();dev->Release();swap->Release();
        // ReShade's destroy_effect_runtime callback releases our references too.
        assert(!g_resourceDevice);
    }
    if (reshade) {
        auto unregisterAddon=reinterpret_cast<void(*)(HMODULE)>(GetProcAddress(reshade,"ReShadeUnregisterAddon"));
        unregisterAddon(g_ownModule);
    }
    g_data=nullptr;DestroyWindow(window);
    puts("PASS: 210 frames, three device lifetimes and ResizeBuffers; no competing Present hook");
    return 0;
}
