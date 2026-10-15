/**
 * cgfs16_overlay.cpp  -  DXGI/D3D11 SwapChain::Present hook for FIFA 16
 *
 * FIFA 16 (FIFA Infinity mod) uses D3D11 + a dxgi.dll proxy.
 * We create a tiny D3D11 device+SwapChain to obtain the shared Present vtable.
 * No machine instructions are overwritten. A proxy with a private vtable may
 * not be intercepted; in that case selector shortcuts remain disabled.
 *
 * Overlay: D3D11 colored quads (VS/PS compiled at runtime).
 *   Text: GDI offscreen DIBSection -> D3D11 BGRA texture (no GetDC crash).
 *   Image: WIC -> D3D11 BGRA texture for stadium preview.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>     // CoInitializeEx, CoCreateInstance
#include <initguid.h>    // must precede wincodec.h to define GUIDs inline
#include <wincodec.h>    // WIC
#include <d3d11.h>
#include <dxgi.h>
#include <dxgi1_2.h>
#include <d3dcompiler.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <algorithm>
#include <vector>
#include <cmath>
#include "stadium_selector_bridge.h"
#include "selector_layout.h"

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "ole32.lib")

// ---------------------------------------------------------------------------
// Shared memory (same layout as Python _OverlayShared)
// ---------------------------------------------------------------------------
#define SHMEM_NAME  L"Local\\CGFS16_Overlay_v3"
#define MAX_STR     256
#define MAX_IMG     512

struct OverlayShared {
    volatile LONG visible;
    volatile LONG progress_x100;
    wchar_t stadium_name[MAX_STR];
    wchar_t detail_text[MAX_STR];
    wchar_t image_path[MAX_IMG];  // path to stadium preview image (PNG/JPG/BMP)
    volatile LONG scoreboard_visible;
    volatile LONG scoreboard_progress_x100;
    wchar_t scoreboard_name[MAX_STR];
    wchar_t scoreboard_detail[MAX_STR];
    volatile LONG movie_visible;
    volatile LONG movie_progress_x100;
    wchar_t movie_name[MAX_STR];
    wchar_t movie_detail[MAX_STR];
    volatile LONG narration_visible;
    volatile LONG narration_progress_x100;
    wchar_t narration_name[MAX_STR];
    wchar_t narration_detail[MAX_STR];
    wchar_t narration_image_path[MAX_IMG];
};

static HANDLE        g_hMap  = NULL;
static OverlayShared *g_data = NULL;

// ---------------------------------------------------------------------------
// Log -> %TEMP%\cgfs16_overlay.log
// ---------------------------------------------------------------------------
static char g_logPath[MAX_PATH] = {};
static CRITICAL_SECTION g_logCs;
#ifndef CGFS16_OVERLAY_LOG_FILE
#define CGFS16_OVERLAY_LOG_FILE "cgfs16_overlay.log"
#endif

static void InitLog() {
    InitializeCriticalSection(&g_logCs);
    char tmp[MAX_PATH] = {};
    GetTempPathA(MAX_PATH, tmp);
    snprintf(g_logPath, MAX_PATH, "%s%s", tmp,CGFS16_OVERLAY_LOG_FILE);
    FILE *f = nullptr; fopen_s(&f, g_logPath, "w");
    if (f) { fprintf(f, "[DLL] log: %s\n", g_logPath); fclose(f); }
}
static void Log(const char *fmt, ...) {
    if (!g_logPath[0]) return;
    EnterCriticalSection(&g_logCs);
    FILE *f = nullptr; fopen_s(&f, g_logPath, "a");
    if (f) {
        va_list a; va_start(a, fmt);
        vfprintf(f, fmt, a); va_end(a);
        fputc('\n', f); fclose(f);
    }
    LeaveCriticalSection(&g_logCs);
}
static void SelectorLog(const char *message) { Log("[Selector] %s",message); }

// ---------------------------------------------------------------------------
// Hook state
// Strategy:
//   Phase 1 (inline): We patch the first 14 bytes of the proxy dxgi.dll's Present
//                     body so the VERY FIRST call reaches our hook.
//   Phase 2 (vtable): On that first call we restore the original bytes, save the
//                     real function pointer, and patch FIFA's actual IDXGISwapChain
//                     vtable slot 8. All subsequent calls go through the vtable
//                     hook with NO trampoline — we call the restored original fn.
// ---------------------------------------------------------------------------
typedef HRESULT (WINAPI *PFN_Present)(IDXGISwapChain*, UINT, UINT);

static PFN_Present g_OrigPresent         = nullptr;

static void      **g_fifaVtbl            = nullptr;  // FIFA's swapchain vtable
static bool        g_hookSwitched        = false;    // phase 1 -> phase 2 done

static CRITICAL_SECTION g_drawCs;
static LONG g_frameCount = 0;

// ---------------------------------------------------------------------------
// D3D11 overlay resources
// ---------------------------------------------------------------------------

// Combined shader: colored quads (VSMain/PSMain) + textured quads (VSTexMain/PSTexMain)
static const char kShaderSrc[] = R"(
// --- Colored quads ---
struct VS_IN  { float2 pos : POSITION; float4 col : COLOR; };
struct VS_OUT { float4 pos : SV_POSITION; float4 col : COLOR; };
VS_OUT VSMain(VS_IN v) {
    VS_OUT o; o.pos = float4(v.pos, 0, 1); o.col = v.col; return o;
}
float4 PSMain(VS_OUT v) : SV_TARGET { return v.col; }

// --- Textured quads ---
Texture2D g_tex : register(t0);
SamplerState g_samp : register(s0);
struct VS_IN_T  { float2 pos : POSITION; float2 uv : TEXCOORD; float opacity : COLOR; };
struct VS_OUT_T { float4 pos : SV_POSITION; float2 uv : TEXCOORD; float opacity : COLOR; };
VS_OUT_T VSTexMain(VS_IN_T v) {
    VS_OUT_T o; o.pos = float4(v.pos, 0, 1); o.uv = v.uv; o.opacity=v.opacity; return o;
}
float4 PSTexMain(VS_OUT_T v) : SV_TARGET { float4 color=g_tex.Sample(g_samp,v.uv); color.a*=v.opacity; return color; }
)";

// Colored quad resources
static ID3D11VertexShader    *g_vs  = nullptr;
static ID3D11PixelShader     *g_ps  = nullptr;
static ID3D11InputLayout     *g_il  = nullptr;
static ID3D11Buffer          *g_vb  = nullptr;
static ID3D11BlendState      *g_bs  = nullptr;
static ID3D11RasterizerState *g_rs  = nullptr;
static ID3D11DepthStencilState *g_dss = nullptr;

// Textured quad resources
static ID3D11VertexShader    *g_vsT  = nullptr;
static ID3D11PixelShader     *g_psT  = nullptr;
static ID3D11InputLayout     *g_ilT  = nullptr;
static ID3D11Buffer          *g_vbT  = nullptr;
static ID3D11SamplerState    *g_samp = nullptr;

// Colored quad vertex
struct Vtx11 { float x, y; float r, g, b, a; };
static constexpr size_t kColoredVertexCapacity = 1024;

// Textured quad vertex
struct VtxT { float x, y, u, v, opacity; };

// ---------------------------------------------------------------------------
// Text textures (GDI -> D3D11)
// ---------------------------------------------------------------------------
struct TextTex {
    ID3D11Texture2D           *tex     = nullptr;
    ID3D11ShaderResourceView  *srv     = nullptr;
    int                        width   = 0;
    int                        height  = 0;
    wchar_t                    content[MAX_STR * 2] = {};
};

static TextTex g_ttTitle;    // "Loading Stadium" label
static TextTex g_ttName;     // stadium name
static TextTex g_ttDetail;   // detail / progress message
static TextTex g_ttScoreboardName;
static TextTex g_ttScoreboardDetail;
static TextTex g_ttMovieName;
static TextTex g_ttMovieDetail;
static TextTex g_ttNarrationName;
static TextTex g_ttNarrationDetail;

// ---------------------------------------------------------------------------
// Stadium preview image (WIC -> D3D11)
// ---------------------------------------------------------------------------
static ID3D11Texture2D          *g_previewTex          = nullptr;
static ID3D11ShaderResourceView *g_previewSRV          = nullptr;
static wchar_t                   g_previewLoadedPath[MAX_IMG] = {};
static int                       g_previewNatW          = 0;
static int                       g_previewNatH          = 0;
static ID3D11Texture2D *g_narrationPortraitTex=nullptr;
static ID3D11ShaderResourceView *g_narrationPortraitSRV=nullptr;
static wchar_t g_narrationPortraitPath[MAX_IMG]={};
static int g_narrationPortraitW=0,g_narrationPortraitH=0;
static ID3D11ShaderResourceView *g_previousPhoto=nullptr;
static DWORD g_photoFadeStarted;
static int g_previousWidth,g_previousHeight;
static bool g_selectorTexture=false;
static LONG g_loadedSelectorRevision=0;
static DWORD g_imageRetryAt=0;

static float photo_fade(DWORD elapsed) {
    float t=(std::min)(1.f,(float)elapsed/220.f);
    return t*t*(3.f-2.f*t);
}

static bool InitD3D11Overlay(ID3D11Device *dev) {
    ID3DBlob *vsBlob = nullptr, *psBlob = nullptr, *err = nullptr;

    // ── Colored quads ──────────────────────────────────────────────────────
    HRESULT hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "VSMain", "vs_4_0", 0, 0, &vsBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] VS compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        if (err) err->Release(); return false;
    }
    hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "PSMain", "ps_4_0", 0, 0, &psBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] PS compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        vsBlob->Release(); if (err) err->Release(); return false;
    }

    dev->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &g_vs);
    dev->CreatePixelShader( psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &g_ps);

    D3D11_INPUT_ELEMENT_DESC ied[] = {
        {"POSITION",0,DXGI_FORMAT_R32G32_FLOAT,        0, 0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"COLOR",   0,DXGI_FORMAT_R32G32B32A32_FLOAT,  0, 8,D3D11_INPUT_PER_VERTEX_DATA,0},
    };
    dev->CreateInputLayout(ied, 2,
        vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), &g_il);
    vsBlob->Release(); psBlob->Release();

    D3D11_BUFFER_DESC bd = {};
    bd.ByteWidth      = sizeof(Vtx11) * kColoredVertexCapacity;
    bd.Usage          = D3D11_USAGE_DYNAMIC;
    bd.BindFlags      = D3D11_BIND_VERTEX_BUFFER;
    bd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    dev->CreateBuffer(&bd, nullptr, &g_vb);

    D3D11_BLEND_DESC bsd = {};
    bsd.RenderTarget[0].BlendEnable            = TRUE;
    bsd.RenderTarget[0].SrcBlend              = D3D11_BLEND_SRC_ALPHA;
    bsd.RenderTarget[0].DestBlend             = D3D11_BLEND_INV_SRC_ALPHA;
    bsd.RenderTarget[0].BlendOp               = D3D11_BLEND_OP_ADD;
    bsd.RenderTarget[0].SrcBlendAlpha         = D3D11_BLEND_ONE;
    bsd.RenderTarget[0].DestBlendAlpha        = D3D11_BLEND_ZERO;
    bsd.RenderTarget[0].BlendOpAlpha          = D3D11_BLEND_OP_ADD;
    bsd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    dev->CreateBlendState(&bsd, &g_bs);

    D3D11_RASTERIZER_DESC rsd = {};
    rsd.FillMode        = D3D11_FILL_SOLID;
    rsd.CullMode        = D3D11_CULL_NONE;
    rsd.DepthClipEnable = FALSE;
    dev->CreateRasterizerState(&rsd, &g_rs);

    D3D11_DEPTH_STENCIL_DESC dsd = {};
    dsd.DepthEnable = FALSE;
    dev->CreateDepthStencilState(&dsd, &g_dss);

    // ── Textured quads ─────────────────────────────────────────────────────
    ID3DBlob *vsTBlob = nullptr, *psTBlob = nullptr;
    hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "VSTexMain", "vs_4_0", 0, 0, &vsTBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] VSTexMain compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        if (err) err->Release();
        // Non-fatal: text/image just won't render
    } else {
        hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
            nullptr, nullptr, nullptr, "PSTexMain", "ps_4_0", 0, 0, &psTBlob, &err);
        if (SUCCEEDED(hr)) {
            dev->CreateVertexShader(vsTBlob->GetBufferPointer(), vsTBlob->GetBufferSize(), nullptr, &g_vsT);
            dev->CreatePixelShader( psTBlob->GetBufferPointer(), psTBlob->GetBufferSize(), nullptr, &g_psT);

            D3D11_INPUT_ELEMENT_DESC iedT[] = {
                {"POSITION",0,DXGI_FORMAT_R32G32_FLOAT, 0, 0,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT, 0, 8,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"COLOR",0,DXGI_FORMAT_R32_FLOAT,0,16,D3D11_INPUT_PER_VERTEX_DATA,0},
            };
            dev->CreateInputLayout(iedT, 3,
                vsTBlob->GetBufferPointer(), vsTBlob->GetBufferSize(), &g_ilT);

            D3D11_BUFFER_DESC bdT = {};
            bdT.ByteWidth      = sizeof(VtxT) * 4;
            bdT.Usage          = D3D11_USAGE_DYNAMIC;
            bdT.BindFlags      = D3D11_BIND_VERTEX_BUFFER;
            bdT.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
            dev->CreateBuffer(&bdT, nullptr, &g_vbT);

            D3D11_SAMPLER_DESC sd = {};
            sd.Filter   = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
            sd.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
            sd.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
            sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
            dev->CreateSamplerState(&sd, &g_samp);

            psTBlob->Release();
        } else {
            Log("[D3D11] PSTexMain compile hr=0x%08X", (unsigned)hr);
            if (err) err->Release();
        }
        vsTBlob->Release();
    }

    Log("[D3D11] overlay resources initialized (text=%s image=%s)",
        g_vsT ? "yes" : "no", g_vsT ? "yes" : "no");
    return g_vs && g_ps && g_il && g_vb && g_bs && g_rs && g_dss;
}

// pixel -> clip-space
static float PX(float x, float w) { return  x/w*2.f-1.f; }
static float PY(float y, float h) { return -y/h*2.f+1.f; }

template<size_t Capacity>
static bool PushQuad(Vtx11 (&buf)[Capacity], int &n,
    float x,float y,float w,float h,float vpW,float vpH,DWORD col)
{
    if (n < 0 || static_cast<size_t>(n) + 4 > Capacity) return false;
    float r=((col>>16)&0xFF)/255.f, g2=((col>>8)&0xFF)/255.f,
          b=((col)&0xFF)/255.f,     a=((col>>24)&0xFF)/255.f;
    float x0=PX(x,vpW),y0=PY(y,vpH),x1=PX(x+w,vpW),y1=PY(y+h,vpH);
    buf[n++]={x0,y0,r,g2,b,a}; buf[n++]={x1,y0,r,g2,b,a};
    buf[n++]={x0,y1,r,g2,b,a}; buf[n++]={x1,y1,r,g2,b,a};
    return true;
}

// ---------------------------------------------------------------------------
// GDI text -> D3D11 texture
// fgColor is a COLORREF (0x00BBGGRR, use RGB(r,g,b) macro)
// maxPixW caps the texture width and enables ellipsis trimming
// ---------------------------------------------------------------------------
static void UpdateTextTex(ID3D11Device *dev, TextTex &tt,
    const wchar_t *text, int fontPx, bool bold, COLORREF fgColor, int maxPixW)
{
    if (tt.width == maxPixW && wcscmp(tt.content, text) == 0) return; // unchanged

    if (tt.tex) { tt.tex->Release(); tt.tex = nullptr; }
    if (tt.srv) { tt.srv->Release(); tt.srv = nullptr; }
    tt.width = tt.height = 0;
    tt.content[0] = L'\0';

    if (!text || !text[0]) return;

    LOGFONTW lf = {};
    lf.lfHeight  = -fontPx;
    lf.lfWeight  = bold ? FW_SEMIBOLD : FW_NORMAL;
    lf.lfQuality = ANTIALIASED_QUALITY;
    wcscpy_s(lf.lfFaceName, L"Segoe UI");
    HFONT hf = CreateFontIndirectW(&lf);
    if (!hf) return;

    // Measure text height
    HDC hdcMeas = CreateCompatibleDC(nullptr);
    SelectObject(hdcMeas, hf);
    RECT rcCalc = {0, 0, maxPixW, 2000};
    DrawTextW(hdcMeas, text, -1, &rcCalc,
              DT_LEFT | DT_SINGLELINE | DT_NOPREFIX | DT_CALCRECT);
    DeleteDC(hdcMeas);

    int bmpW = maxPixW;
    int bmpH = (rcCalc.bottom > 0) ? rcCalc.bottom : (fontPx + 4);

    // Create DIBSection (top-down, 32-bpp BGRA)
    BITMAPINFO bi = {};
    bi.bmiHeader.biSize        = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth       = bmpW;
    bi.bmiHeader.biHeight      = -bmpH;
    bi.bmiHeader.biPlanes      = 1;
    bi.bmiHeader.biBitCount    = 32;
    bi.bmiHeader.biCompression = BI_RGB;

    void *bits = nullptr;
    HDC hdc = CreateCompatibleDC(nullptr);
    HBITMAP hbm = CreateDIBSection(hdc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!hbm) { DeleteDC(hdc); DeleteObject(hf); return; }
    HBITMAP hbmOld = (HBITMAP)SelectObject(hdc, hbm);

    memset(bits, 0, (size_t)bmpW * bmpH * 4);
    SelectObject(hdc, hf);
    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, RGB(255,255,255));
    RECT rc = {0, 0, bmpW, bmpH};
    DrawTextW(hdc, text, -1, &rc,
              DT_LEFT | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
    GdiFlush();

    // White-on-black yields coverage independent of the requested ink color.
    // Otherwise dark text on a white panel incorrectly becomes translucent.
    BYTE *px = (BYTE*)bits;
    for (int i = 0; i < bmpW * bmpH; i++) {
        BYTE b = px[0], g = px[1], r = px[2];
        px[3] = (std::max)({b, g, r});
        px[0]=GetBValue(fgColor); px[1]=GetGValue(fgColor); px[2]=GetRValue(fgColor);
        px += 4;
    }

    D3D11_TEXTURE2D_DESC td = {};
    td.Width            = (UINT)bmpW;
    td.Height           = (UINT)bmpH;
    td.MipLevels        = 1;
    td.ArraySize        = 1;
    td.Format           = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage            = D3D11_USAGE_IMMUTABLE;
    td.BindFlags        = D3D11_BIND_SHADER_RESOURCE;

    D3D11_SUBRESOURCE_DATA srd = {};
    srd.pSysMem     = bits;
    srd.SysMemPitch = (UINT)(bmpW * 4);

    dev->CreateTexture2D(&td, &srd, &tt.tex);
    if (tt.tex) {
        dev->CreateShaderResourceView(tt.tex, nullptr, &tt.srv);
        tt.width  = bmpW;
        tt.height = bmpH;
    }
    wcscpy_s(tt.content, text);

    SelectObject(hdc, hbmOld);
    DeleteObject(hbm);
    DeleteObject(hf);
    DeleteDC(hdc);
}

// ---------------------------------------------------------------------------
// WIC -> D3D11 texture for stadium preview
// Returns true if the texture was (re)loaded successfully
// ---------------------------------------------------------------------------
static bool LoadImageWIC(ID3D11Device *dev, const wchar_t *path,
    ID3D11Texture2D *&texture,ID3D11ShaderResourceView *&view,int &width,int &height)
{
    IWICImagingFactory *wicF = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr,
        CLSCTX_INPROC_SERVER, __uuidof(IWICImagingFactory), (void**)&wicF);
    if (FAILED(hr)) { Log("[WIC] CoCreateInstance hr=0x%08X", (unsigned)hr); return false; }

    IWICBitmapDecoder *dec = nullptr;
    hr = wicF->CreateDecoderFromFilename(path, nullptr, GENERIC_READ,
        WICDecodeMetadataCacheOnDemand, &dec);
    if (FAILED(hr)) {
        Log("[WIC] CreateDecoderFromFilename hr=0x%08X", (unsigned)hr);
        wicF->Release(); return false;
    }

    IWICBitmapFrameDecode *frame = nullptr;
    dec->GetFrame(0, &frame);
    dec->Release();
    if (!frame) { wicF->Release(); return false; }

    IWICFormatConverter *conv = nullptr;
    hr=wicF->CreateFormatConverter(&conv);
    if (FAILED(hr) || !conv) { frame->Release(); wicF->Release(); return false; }
    hr = conv->Initialize(frame, GUID_WICPixelFormat32bppBGRA,
        WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom);
    frame->Release();
    if (FAILED(hr)) { if (conv) conv->Release(); wicF->Release(); return false; }

    UINT w = 0, h = 0;
    conv->GetSize(&w, &h);
    if (!w || !h || w>8192 || h>8192) { conv->Release(); wicF->Release(); return false; }

    std::vector<BYTE> pixels((size_t)w * h * 4);
    hr=conv->CopyPixels(nullptr, w * 4, (UINT)pixels.size(), pixels.data());
    conv->Release();
    wicF->Release();
    if (FAILED(hr)) return false;

    D3D11_TEXTURE2D_DESC td = {};
    td.Width            = w;
    td.Height           = h;
    td.MipLevels        = 1;
    td.ArraySize        = 1;
    td.Format           = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage            = D3D11_USAGE_IMMUTABLE;
    td.BindFlags        = D3D11_BIND_SHADER_RESOURCE;

    D3D11_SUBRESOURCE_DATA srd = {};
    srd.pSysMem     = pixels.data();
    srd.SysMemPitch = w * 4;

    ID3D11Texture2D *replacement=nullptr;
    ID3D11ShaderResourceView *replacementView=nullptr;
    hr = dev->CreateTexture2D(&td, &srd, &replacement);
    if (FAILED(hr)) { Log("[WIC] CreateTexture2D hr=0x%08X", (unsigned)hr); return false; }
    hr=dev->CreateShaderResourceView(replacement,nullptr,&replacementView);
    if (FAILED(hr)) { replacement->Release(); return false; }
    if (texture) texture->Release();
    if (view) view->Release();
    texture=replacement; view=replacementView;
    width=(int)w; height=(int)h;
    Log("[WIC] loaded '%ls' %dx%d", path, w, h);
    return true;
}

static bool LoadPreviewImageWIC(ID3D11Device *dev,const wchar_t *path) {
    return LoadImageWIC(dev,path,g_previewTex,g_previewSRV,g_previewNatW,g_previewNatH);
}

// Draw a textured quad; requires g_vsT/g_psT/g_ilT/g_vbT/g_samp already bound.
static void DrawTexQuad(ID3D11DeviceContext *ctx,
    float x, float y, float w, float h, float vpW, float vpH,
    ID3D11ShaderResourceView *srv,float opacity=1.f,float u0=0.f,float v0=0.f,float u1=1.f,float v1=1.f)
{
    if (!srv || !g_vbT) return;
    float x0=PX(x,vpW),y0=PY(y,vpH),x1=PX(x+w,vpW),y1=PY(y+h,vpH);
    VtxT verts[4] = {{x0,y0,u0,v0,opacity},{x1,y0,u1,v0,opacity},{x0,y1,u0,v1,opacity},{x1,y1,u1,v1,opacity}};
    D3D11_MAPPED_SUBRESOURCE ms={};
    if (SUCCEEDED(ctx->Map(g_vbT,0,D3D11_MAP_WRITE_DISCARD,0,&ms))) {
        memcpy(ms.pData,verts,sizeof(verts)); ctx->Unmap(g_vbT,0);
    }
    ctx->PSSetShaderResources(0,1,&srv);
    UINT stride=sizeof(VtxT),offset=0;
    ctx->IASetVertexBuffers(0,1,&g_vbT,&stride,&offset);
    ctx->Draw(4,0);
}

static void DrawOverlay11(IDXGISwapChain *sc, ID3D11Device *dev, ID3D11DeviceContext *ctx) {
    // ── Read shared memory ─────────────────────────────────────────────────
    wchar_t stadium[MAX_STR]={}, detail[MAX_STR]={}, imgPath[MAX_IMG]={};
    float pct=0.f;
    bool stadiumVisible=false, scoreboardVisible=false, movieVisible=false,narrationVisible=false;
    float scoreboardPct=0.f, moviePct=0.f,narrationPct=0.f;
    wchar_t scoreboardName[MAX_STR]={}, scoreboardDetail[MAX_STR]={};
    wchar_t movieName[MAX_STR]={}, movieDetail[MAX_STR]={};
    wchar_t narrationName[MAX_STR]={},narrationDetail[MAX_STR]={},narrationImage[MAX_IMG]={};
    if (g_data) {
        stadiumVisible=InterlockedCompareExchange(&g_data->visible,0,0)!=0;
        wcsncpy_s(stadium, g_data->stadium_name, MAX_STR-1);
        wcsncpy_s(detail,  g_data->detail_text,  MAX_STR-1);
        wcsncpy_s(imgPath, g_data->image_path,   MAX_IMG-1);
        pct = (float)InterlockedCompareExchange(&g_data->progress_x100,0,0)/100.f;
        scoreboardVisible=InterlockedCompareExchange(&g_data->scoreboard_visible,0,0)!=0;
        scoreboardPct=(float)InterlockedCompareExchange(&g_data->scoreboard_progress_x100,0,0)/100.f;
        wcsncpy_s(scoreboardName,g_data->scoreboard_name,MAX_STR-1);
        wcsncpy_s(scoreboardDetail,g_data->scoreboard_detail,MAX_STR-1);
        movieVisible=InterlockedCompareExchange(&g_data->movie_visible,0,0)!=0;
        moviePct=(float)InterlockedCompareExchange(&g_data->movie_progress_x100,0,0)/100.f;
        wcsncpy_s(movieName,g_data->movie_name,MAX_STR-1);
        wcsncpy_s(movieDetail,g_data->movie_detail,MAX_STR-1);
        narrationVisible=InterlockedCompareExchange(&g_data->narration_visible,0,0)!=0;
        narrationPct=(float)InterlockedCompareExchange(&g_data->narration_progress_x100,0,0)/100.f;
        wcsncpy_s(narrationName,g_data->narration_name,MAX_STR-1);
        wcsncpy_s(narrationDetail,g_data->narration_detail,MAX_STR-1);
        wcsncpy_s(narrationImage,g_data->narration_image_path,MAX_IMG-1);
    }
    bool selecting=selector_visible() && g_selector;
    LONG revision=selecting ? InterlockedCompareExchange(&g_selector->render_ready,0,0) : 0;
    LONG requestedWidth=0,requestedHeight=0;
    bool published=false;
    if (selecting && revision>0) {
        requestedWidth=g_selector->width; requestedHeight=g_selector->height;
        wcsncpy_s(imgPath,g_selector->image_path,MAX_IMG-1);
        MemoryBarrier();
        published=revision==InterlockedCompareExchange(&g_selector->render_ready,0,0) && requestedWidth>0 && requestedHeight>0;
    }
    if (selecting && !published) {
        revision=g_loadedSelectorRevision;
        requestedWidth=g_selector_draw_width; requestedHeight=g_selector_draw_height;
        wcscpy_s(imgPath,g_selectorTexture ? g_previewLoadedPath : L"");
    }

    DXGI_SWAP_CHAIN_DESC scd={}; sc->GetDesc(&scd);
    float vpW=(float)(scd.BufferDesc.Width?scd.BufferDesc.Width:1280);
    float vpH=(float)(scd.BufferDesc.Height?scd.BufferDesc.Height:720);

    ID3D11Texture2D *bb=nullptr;
    if (FAILED(sc->GetBuffer(0,__uuidof(ID3D11Texture2D),(void**)&bb))) return;
    D3D11_TEXTURE2D_DESC backDesc={}; bb->GetDesc(&backDesc);
    vpW=(float)backDesc.Width; vpH=(float)backDesc.Height;
    ID3D11RenderTargetView *rtv=nullptr;
    dev->CreateRenderTargetView(bb,nullptr,&rtv);
    bb->Release();
    if (!rtv) return;

    // ── Init D3D resources once ────────────────────────────────────────────
    static bool s_init=false;
    if (!s_init) s_init=InitD3D11Overlay(dev);
    if (!g_vs||!g_ps||!g_il||!g_vb) { rtv->Release(); return; }

    // ── Init COM once (for WIC) on this thread ─────────────────────────────
    static bool s_comInit = false;
    if (!s_comInit) {
        s_comInit = true;
        HRESULT cohr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        Log("[DrawOverlay] CoInitializeEx hr=0x%08X", (unsigned)cohr);
        // S_OK = initialized, S_FALSE = already init MTA, RPC_E_CHANGED_MODE = STA
        // All outcomes leave COM usable on this thread.
    }

    // ── Update text textures (GDI) ─────────────────────────────────────────
    // Panel constants: PW=460, M=20.  Text column starts at px+136 (after image area).
    // maxPixW for text = PW - 136 - 12 = 312 px
    const int kTextMaxW = 312;
    const wchar_t* loadingTitle = L"Carregando est\u00E1dio";
    const wchar_t* loadingName = stadium;
    const wchar_t* narrationPrefix = L"[Narra\u00E7\u00E3o aplicada] ";
    if (!selecting && wcsncmp(stadium,narrationPrefix,wcslen(narrationPrefix))==0) {
        loadingTitle = L"Narra\u00E7\u00E3o aplicada";
        loadingName = stadium + wcslen(narrationPrefix);
    }
    if (!selecting && wcsncmp(stadium, L"[Carregando placar] ", 20) == 0) {
        loadingTitle = L"Carregando placar";
        loadingName = stadium + 20;
    } else if (!selecting && wcsncmp(stadium, L"[Carregando v\u00EDdeo pr\u00E9-jogo] ", 28) == 0) {
        loadingTitle = L"Carregando v\u00EDdeo pr\u00E9-jogo";
        loadingName = stadium + 28;
    }
    const int notificationTextWidth=selecting?252:kTextMaxW;
    UpdateTextTex(dev, g_ttTitle,loadingTitle,15,false,RGB(0x09,0x68,0xF8),notificationTextWidth);
    UpdateTextTex(dev, g_ttName,loadingName,15,true,RGB(0x34,0x46,0x51),notificationTextWidth);
    UpdateTextTex(dev, g_ttDetail,detail,13,false,RGB(0x87,0x97,0xAB),notificationTextWidth);
    wchar_t scoreboardTitle[MAX_STR*2]={}, movieTitle[MAX_STR*2]={};
    swprintf_s(scoreboardTitle,L"Carregando placar - %ls",scoreboardName[0]?scoreboardName:L"Padr\u00E3o");
    swprintf_s(movieTitle,L"Carregando v\u00EDdeo pr\u00E9-jogo - %ls",movieName[0]?movieName:L"Padr\u00E3o");
    int assetTextWidth=selecting?252:388;
    UpdateTextTex(dev,g_ttScoreboardName,scoreboardTitle,13,true,RGB(0x34,0x46,0x51),assetTextWidth);
    UpdateTextTex(dev,g_ttScoreboardDetail,scoreboardDetail,11,false,RGB(0x87,0x97,0xAB),assetTextWidth);
    UpdateTextTex(dev,g_ttMovieName,movieTitle,13,true,RGB(0x34,0x46,0x51),assetTextWidth);
    UpdateTextTex(dev,g_ttMovieDetail,movieDetail,11,false,RGB(0x87,0x97,0xAB),assetTextWidth);
    wchar_t narrationTitle[MAX_STR*2]={};
    swprintf_s(narrationTitle,L"%ls - %ls",narrationPct>=100.f?L"Narra\u00E7\u00E3o aplicada":L"Carregando narra\u00E7\u00E3o",narrationName);
    if(narrationVisible && wcscmp(narrationImage,g_narrationPortraitPath)!=0) {
        if(g_narrationPortraitTex) {g_narrationPortraitTex->Release();g_narrationPortraitTex=nullptr;}
        if(g_narrationPortraitSRV) {g_narrationPortraitSRV->Release();g_narrationPortraitSRV=nullptr;}
        g_narrationPortraitW=g_narrationPortraitH=0;
        wcscpy_s(g_narrationPortraitPath,narrationImage);
        if(narrationImage[0])LoadImageWIC(dev,narrationImage,g_narrationPortraitTex,g_narrationPortraitSRV,g_narrationPortraitW,g_narrationPortraitH);
    }
    const int narrationTextWidth=assetTextWidth-(g_narrationPortraitSRV?58:0);
    UpdateTextTex(dev,g_ttNarrationName,narrationTitle,13,true,RGB(0x34,0x46,0x51),narrationTextWidth);
    UpdateTextTex(dev,g_ttNarrationDetail,narrationDetail,11,false,RGB(0x87,0x97,0xAB),narrationTextWidth);

    // ── Update preview image (WIC) ─────────────────────────────────────────
    bool changed=wcscmp(imgPath,g_previewLoadedPath)!=0 || (selecting && revision!=g_loadedSelectorRevision) || (!selecting && g_selectorTexture);
    if (changed && (!selecting || published) && (!g_imageRetryAt || (LONG)(GetTickCount()-g_imageRetryAt)>=0)) {
        bool transition=selecting && g_selectorTexture && wcsstr(imgPath,L"card_slide_") && g_previewSRV &&
            g_selector_draw_width==requestedWidth && g_selector_draw_height==requestedHeight;
        ID3D11ShaderResourceView *previous=transition ? g_previewSRV : nullptr;
        if (previous) previous->AddRef();
        bool loaded=imgPath[0] && LoadPreviewImageWIC(dev,imgPath);
        if (loaded && transition) {
            if (g_previousPhoto) g_previousPhoto->Release();
            g_previousPhoto=previous; previous=nullptr;
            g_previousWidth=requestedWidth; g_previousHeight=requestedHeight;
            g_photoFadeStarted=GetTickCount();
        } else if (loaded && g_previousPhoto && (!selecting || g_selector_draw_width!=requestedWidth || g_selector_draw_height!=requestedHeight)) {
            g_previousPhoto->Release(); g_previousPhoto=nullptr;
        }
        if (previous) previous->Release();
        if (loaded) {
            wcscpy_s(g_previewLoadedPath,imgPath);
            g_selectorTexture=selecting; g_loadedSelectorRevision=revision;
            if (selecting) { g_selector_draw_width=requestedWidth; g_selector_draw_height=requestedHeight; }
            g_imageRetryAt=0;
        } else if (!imgPath[0] && !selecting) {
            if (g_previewTex) { g_previewTex->Release(); g_previewTex = nullptr; }
            if (g_previewSRV) { g_previewSRV->Release(); g_previewSRV = nullptr; }
            g_previewNatW = g_previewNatH = 0;
            g_selectorTexture=false; g_previewLoadedPath[0]=0;
        } else {
            g_imageRetryAt=GetTickCount()+250;
            if (selecting && !g_selectorTexture) { g_selector->visible=0; rtv->Release(); return; }
        }
    }
    bool drawSelector=selecting && g_selectorTexture && g_previewSRV;
    // ── Save D3D state ─────────────────────────────────────────────────────
    ID3D11RenderTargetView *oldRTV[8]={}; ID3D11DepthStencilView *oldDSV=nullptr;
    ctx->OMGetRenderTargets(8,oldRTV,&oldDSV);
    D3D11_VIEWPORT oldVP={}; UINT nVP=1; ctx->RSGetViewports(&nVP,&oldVP);
    ID3D11BlendState *oldBS=nullptr; float oldBF[4]={}; UINT oldSM=0;
    ctx->OMGetBlendState(&oldBS,oldBF,&oldSM);
    ID3D11RasterizerState *oldRS=nullptr; ctx->RSGetState(&oldRS);
    ID3D11DepthStencilState *oldDSS=nullptr; UINT oldSRef=0;
    ctx->OMGetDepthStencilState(&oldDSS,&oldSRef);
    ID3D11VertexShader *oldVS=nullptr; ctx->VSGetShader(&oldVS,nullptr,nullptr);
    ID3D11PixelShader  *oldPS=nullptr; ctx->PSGetShader(&oldPS,nullptr,nullptr);
    ID3D11InputLayout  *oldIL=nullptr; ctx->IAGetInputLayout(&oldIL);
    D3D11_PRIMITIVE_TOPOLOGY oldTopo; ctx->IAGetPrimitiveTopology(&oldTopo);
    ID3D11Buffer *oldVB=nullptr; UINT oldStride=0,oldOffset=0;
    ctx->IAGetVertexBuffers(0,1,&oldVB,&oldStride,&oldOffset);
    ID3D11GeometryShader *oldGS=nullptr; ctx->GSGetShader(&oldGS,nullptr,nullptr);
    ctx->GSSetShader(nullptr,nullptr,0);
    ID3D11ShaderResourceView *oldSRV=nullptr; ctx->PSGetShaderResources(0,1,&oldSRV);
    ID3D11SamplerState *oldSamp=nullptr; ctx->PSGetSamplers(0,1,&oldSamp);

    // ── Set overlay state (shared by both colored and textured draws) ───────
    ctx->OMSetRenderTargets(1,&rtv,nullptr);
    D3D11_VIEWPORT vp={0,0,vpW,vpH,0,1}; ctx->RSSetViewports(1,&vp);
    ctx->OMSetBlendState(g_bs,nullptr,0xFFFFFFFF);
    ctx->RSSetState(g_rs);
    ctx->OMSetDepthStencilState(g_dss,0);
    ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);

    // ── Layout constants ────────────────────────────────────────────────────
    // Compact loading panel; the blue fill reports actual copy progress.
    const float PW=selecting?280.f:420.f, PH=128.f, M=16.f;
    const float px=vpW-PW-M, py=M;
    const float assetBaseY=py+(stadiumVisible?PH+10.f:0.f);
    // Image box: 96 x 76 at (px+12, py+14)
    const float IX=px+12.f, IY=py+14.f, IW=96.f, IH=76.f;
    // Text column start
    const float TX=px+(selecting?14.f:120.f);

    // ── Colored quads pass ─────────────────────────────────────────────────
    ctx->VSSetShader(g_vs,nullptr,0);
    ctx->PSSetShader(g_ps,nullptr,0);
    ctx->IASetInputLayout(g_il);
    UINT stride=sizeof(Vtx11),offset=0;
    ctx->IASetVertexBuffers(0,1,&g_vb,&stride,&offset);

    Vtx11 verts[kColoredVertexCapacity]; int n=0;
    const int assetCount=(scoreboardVisible?1:0)+(movieVisible?1:0)+(narrationVisible?1:0);
    const float stackHeight=(stadiumVisible?PH:0.f)+(assetCount?(stadiumVisible?10.f:0.f)+assetCount*76.f-10.f:0.f);
    auto noticeLayout=loading_layout(vpW,vpH,PW,std::max(1.f,stackHeight));
    const float loadingScale=noticeLayout.scale;
    const float loadingX=noticeLayout.x;
    auto DrawTexQuad=[&](ID3D11DeviceContext* context,float x,float y,float w,float h,
        float vw,float vh,ID3D11ShaderResourceView* texture,float alpha=1.f,
        float u0=0.f,float v0=0.f,float u1=1.f,float v1=1.f) {
        ::DrawTexQuad(context,loadingX+(x-px)*loadingScale,py+(y-py)*loadingScale,
            w*loadingScale,h*loadingScale,vw,vh,texture,alpha,u0,v0,u1,v1);
    };
    auto R=[&](float x,float y,float w,float h,DWORD col){
        PushQuad(verts,n,loadingX+(x-px)*loadingScale,py+(y-py)*loadingScale,w*loadingScale,h*loadingScale,vpW,vpH,col);
    };
    auto Round=[&](float x,float y,float w,float h,float radius,DWORD col) {
        if (w <= 0.f || h <= 0.f) return;
        radius=std::min(radius,std::min(w,h)/2.f);
        R(x,y+radius,w,h-radius*2,col);
        for (int i=0;i<8;++i) {
            float dy=radius/8.f, distance=radius-(i+.5f)*dy;
            float inset=radius-sqrtf(radius*radius-distance*distance);
            R(x+inset,y+i*dy,w-inset*2,dy,col);
            R(x+inset,y+h-(i+1)*dy,w-inset*2,dy,col);
        }
    };
    // Panel background + borders
    if (stadiumVisible) {
    Round(px,py,PW,PH,12.f,0xFFDFE6EF);
    Round(px+1,py+1,PW-2,PH-2,11.f,0xFFFFFFFF);
    if(!selecting)R(IX,IY,IW,IH,0xFFF0F4F8);
    // Progress track + determinate fill, updated by the stadium-copy worker.
    float tx2=TX, ty2=py+PH-18.f, tw2=PW-(selecting?28.f:132.f), th2=8.f;
    Round(tx2,ty2,tw2,th2,4.f,0xFFEDF2F7);
    float progress=std::max(0.f,std::min(100.f,pct))/100.f;
    if (progress>0.f) Round(tx2,ty2,tw2*progress,th2,4.f,0xFF0968F8);
    }
    {
        auto drawAssetCard=[&](float y,float assetPct) {
            Round(px,y,PW,66.f,10.f,0xFFDFE6EF);
            Round(px+1.f,y+1.f,PW-2.f,64.f,9.f,0xFFFFFFFF);
            Round(px+14.f,y+49.f,PW-28.f,6.f,3.f,0xFFEDF2F7);
            float fill=std::max(0.f,std::min(100.f,assetPct))/100.f;
            if(fill>0.f) Round(px+14.f,y+49.f,(PW-28.f)*fill,6.f,3.f,0xFF0968F8);
        };
        if(scoreboardVisible) drawAssetCard(assetBaseY,scoreboardPct);
        if(movieVisible) drawAssetCard(assetBaseY+(scoreboardVisible?76.f:0.f),moviePct);
        if(narrationVisible) drawAssetCard(assetBaseY+(scoreboardVisible?76.f:0.f)+(movieVisible?76.f:0.f),narrationPct);
    }

    D3D11_MAPPED_SUBRESOURCE ms={};
    if (SUCCEEDED(ctx->Map(g_vb,0,D3D11_MAP_WRITE_DISCARD,0,&ms))){
        memcpy(ms.pData,verts,n*sizeof(Vtx11)); ctx->Unmap(g_vb,0);
    }
    for(int i=0;i<n;i+=4) ctx->Draw(4,i);

    // ── Textured quads pass (text + image) ─────────────────────────────────
    if (g_vsT && g_psT && g_ilT && g_vbT && g_samp) {
        ctx->VSSetShader(g_vsT,nullptr,0);
        ctx->PSSetShader(g_psT,nullptr,0);
        ctx->IASetInputLayout(g_ilT);
        ctx->PSSetSamplers(0,1,&g_samp);

        if (drawSelector) {
            LONG canvasWidth=g_selector_draw_width,canvasHeight=g_selector_draw_height;
            auto layout=selector_layout(vpW,vpH,canvasWidth,canvasHeight);
            float offset=layout.keyboard ? 200.f : 0.f;
            ::DrawTexQuad(ctx,layout.card_x,layout.card_y,layout.card_width*layout.card_scale,layout.card_height*layout.card_scale,
                vpW,vpH,g_previewSRV,1.f,offset/canvasWidth,0.f,(offset+layout.card_width)/canvasWidth,layout.card_height/canvasHeight);
            if (layout.keyboard) {
                ::DrawTexQuad(ctx,layout.keyboard_x,layout.keyboard_y,1000.f*layout.keyboard_scale,230.f*layout.keyboard_scale,
                    vpW,vpH,g_previewSRV,1.f,0.f,600.f/canvasHeight,1.f,1.f);
            }
            if (g_previousPhoto) {
                float progress=photo_fade((DWORD)(GetTickCount()-g_photoFadeStarted));
                if (progress<1.f && g_previousWidth==canvasWidth && g_previousHeight==canvasHeight) {
                    ::DrawTexQuad(ctx,layout.card_x+24.f*layout.card_scale,layout.card_y+130.f*layout.card_scale,
                        552.f*layout.card_scale,232.f*layout.card_scale,vpW,vpH,g_previousPhoto,1.f-progress,
                        (offset+24.f)/g_previousWidth,130.f/g_previousHeight,(offset+576.f)/g_previousWidth,362.f/g_previousHeight);
                } else { g_previousPhoto->Release(); g_previousPhoto=nullptr; }
            }
        }

        // Stadium preview image (aspect-corrected within IW x IH)
        if (!selecting && stadiumVisible && g_previewSRV && g_previewNatW > 0 && g_previewNatH > 0) {
            float imgR = (float)g_previewNatW / (float)g_previewNatH;
            float boxR = IW / IH;
            float dw, dh;
            if (imgR >= boxR) { dw=IW; dh=IW/imgR; }
            else              { dh=IH; dw=IH*imgR;  }
            DrawTexQuad(ctx, IX+(IW-dw)/2.f, IY+(IH-dh)/2.f, dw, dh, vpW, vpH, g_previewSRV);
        }

        // Title "Loading Stadium"
        if (stadiumVisible && g_ttTitle.srv)
            DrawTexQuad(ctx, TX, py+14.f, (float)g_ttTitle.width, (float)g_ttTitle.height, vpW, vpH, g_ttTitle.srv);
        // Stadium name
        if (g_ttName.srv && stadiumVisible && stadium[0])
            DrawTexQuad(ctx, TX, py+36.f, (float)g_ttName.width, (float)g_ttName.height, vpW, vpH, g_ttName.srv);
        // Detail text
        if (g_ttDetail.srv && stadiumVisible && detail[0])
            DrawTexQuad(ctx, TX, py+58.f, (float)g_ttDetail.width, (float)g_ttDetail.height, vpW, vpH, g_ttDetail.srv);
        float assetY=assetBaseY;
        if(scoreboardVisible) {
            if(g_ttScoreboardName.srv) DrawTexQuad(ctx,px+14.f,assetY+9.f,(float)g_ttScoreboardName.width,(float)g_ttScoreboardName.height,vpW,vpH,g_ttScoreboardName.srv);
            if(g_ttScoreboardDetail.srv) DrawTexQuad(ctx,px+14.f,assetY+27.f,(float)g_ttScoreboardDetail.width,(float)g_ttScoreboardDetail.height,vpW,vpH,g_ttScoreboardDetail.srv);
        }
        if(movieVisible) {
            float movieY=assetY+(scoreboardVisible?76.f:0.f);
            if(g_ttMovieName.srv) DrawTexQuad(ctx,px+14.f,movieY+9.f,(float)g_ttMovieName.width,(float)g_ttMovieName.height,vpW,vpH,g_ttMovieName.srv);
            if(g_ttMovieDetail.srv) DrawTexQuad(ctx,px+14.f,movieY+27.f,(float)g_ttMovieDetail.width,(float)g_ttMovieDetail.height,vpW,vpH,g_ttMovieDetail.srv);
        }
        if(narrationVisible) {
            float y=assetBaseY+(scoreboardVisible?76.f:0.f)+(movieVisible?76.f:0.f);
            float textX=px+14.f+(g_narrationPortraitSRV?58.f:0.f);
            if(g_narrationPortraitSRV)DrawTexQuad(ctx,px+12.f,y+5.f,40.f,40.f,vpW,vpH,g_narrationPortraitSRV);
            if(g_ttNarrationName.srv)DrawTexQuad(ctx,textX,y+9.f,(float)g_ttNarrationName.width,(float)g_ttNarrationName.height,vpW,vpH,g_ttNarrationName.srv);
            if(g_ttNarrationDetail.srv)DrawTexQuad(ctx,textX,y+27.f,(float)g_ttNarrationDetail.width,(float)g_ttNarrationDetail.height,vpW,vpH,g_ttNarrationDetail.srv);
        }
    }

    // FIFA can hide its cursor while our modal owns input. Draw a pointer
    // last so it remains visible over both the card and virtual keyboard.
    if (drawSelector || selecting) {
        POINT pointer;
        RECT client;
        if (GetCursorPos(&pointer) && ScreenToClient(scd.OutputWindow,&pointer) &&
            GetClientRect(scd.OutputWindow,&client) && client.right>0 && client.bottom>0) {
            float x=pointer.x*vpW/client.right, y=pointer.y*vpH/client.bottom;
            n=0;
            for(int row=0;row<18;++row) {
                float width=1.f+row*.65f;
                PushQuad(verts,n,x,y+row,width+2.f,1.f,vpW,vpH,0xFF344651);
                if(row>1) PushQuad(verts,n,x+1.f,y+row,width,1.f,vpW,vpH,0xFFFFFFFF);
            }
            ctx->VSSetShader(g_vs,nullptr,0); ctx->PSSetShader(g_ps,nullptr,0);
            ctx->IASetInputLayout(g_il); ctx->IASetVertexBuffers(0,1,&g_vb,&stride,&offset);
            if(SUCCEEDED(ctx->Map(g_vb,0,D3D11_MAP_WRITE_DISCARD,0,&ms))) {
                memcpy(ms.pData,verts,n*sizeof(Vtx11)); ctx->Unmap(g_vb,0);
                for(int i=0;i<n;i+=4) ctx->Draw(4,i);
            }
        }
    }
    // ── Restore D3D state ──────────────────────────────────────────────────
    ctx->OMSetRenderTargets(8,oldRTV,oldDSV);
    ctx->RSSetViewports(1,&oldVP);
    ctx->OMSetBlendState(oldBS,oldBF,oldSM);
    ctx->RSSetState(oldRS);
    ctx->OMSetDepthStencilState(oldDSS,oldSRef);
    ctx->VSSetShader(oldVS,nullptr,0);
    ctx->PSSetShader(oldPS,nullptr,0);
    ctx->IASetInputLayout(oldIL);
    ctx->IASetPrimitiveTopology(oldTopo);
    ctx->IASetVertexBuffers(0,1,&oldVB,&oldStride,&oldOffset);
    ctx->GSSetShader(oldGS,nullptr,0);
    ctx->PSSetShaderResources(0,1,&oldSRV);
    ctx->PSSetSamplers(0,1,&oldSamp);
    for(auto *r:oldRTV) if(r) r->Release();
    if(oldDSV)  oldDSV->Release();
    if(oldBS)   oldBS->Release();
    if(oldRS)   oldRS->Release();
    if(oldDSS)  oldDSS->Release();
    if(oldVS)   oldVS->Release();
    if(oldPS)   oldPS->Release();
    if(oldIL)   oldIL->Release();
    if(oldSRV)  oldSRV->Release();
    if(oldSamp) oldSamp->Release();
    if(oldVB) oldVB->Release();
    if(oldGS) oldGS->Release();
    rtv->Release();
}

// ---------------------------------------------------------------------------
// Hooked IDXGISwapChain::Present
// ---------------------------------------------------------------------------
static HRESULT WINAPI HookedPresent(IDXGISwapChain *sc, UINT syncInterval, UINT flags) {

    LONG n = InterlockedIncrement(&g_frameCount);
    if (n==1 || (n%600)==0)
        Log("[Present] frame=%ld visible=%d", n, g_data?(int)g_data->visible:-1);

    DXGI_SWAP_CHAIN_DESC selectorDesc={}; sc->GetDesc(&selectorDesc);
    selector_tick(selectorDesc.OutputWindow,(float)selectorDesc.BufferDesc.Width,(float)selectorDesc.BufferDesc.Height);
    if ((g_data && (InterlockedCompareExchange(&g_data->visible,0,0) != 0
        || InterlockedCompareExchange(&g_data->scoreboard_visible,0,0) != 0
        || InterlockedCompareExchange(&g_data->movie_visible,0,0) != 0
        || InterlockedCompareExchange(&g_data->narration_visible,0,0) != 0)) || selector_visible()) {
        ID3D11Device *dev=nullptr;
        if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D11Device),(void**)&dev))) {
            ID3D11DeviceContext *ctx=nullptr;
            dev->GetImmediateContext(&ctx);
            EnterCriticalSection(&g_drawCs);
            __try { DrawOverlay11(sc,dev,ctx); }
            __except(EXCEPTION_EXECUTE_HANDLER){ Log("[Present] EXCEPTION DrawOverlay11"); }
            LeaveCriticalSection(&g_drawCs);
            ctx->Release(); dev->Release();
        }
    }
    // Call the RESTORED original proxy Present (no trampoline, no RIP-relative issues)
    return g_OrigPresent(sc, syncInterval, flags);
}

// Install a shared COM-vtable hook without copying machine instructions.
static DWORD WINAPI HookThread(LPVOID) {
    selector_initialize(SelectorLog);
    Log("[HookThread] started pid=%lu", GetCurrentProcessId());
    Sleep(500);

    WNDCLASSEXW wc={}; wc.cbSize=sizeof(wc);
    wc.lpfnWndProc=DefWindowProcW;
    wc.hInstance=GetModuleHandleW(nullptr);
    wc.lpszClassName=L"_CGFS16DXGI";
    RegisterClassExW(&wc);
    HWND hw=CreateWindowExW(0,L"_CGFS16DXGI",L"",WS_POPUP,0,0,1,1,
        nullptr,nullptr,wc.hInstance,nullptr);

    ID3D11Device *tmpDev=nullptr; IDXGISwapChain *tmpSC=nullptr;
    D3D_FEATURE_LEVEL fl=D3D_FEATURE_LEVEL_11_0;
    DXGI_SWAP_CHAIN_DESC scd={};
    scd.BufferCount=1; scd.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow=hw; scd.SampleDesc.Count=1; scd.Windowed=TRUE;

    HRESULT hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_HARDWARE,
        nullptr,0,nullptr,0,D3D11_SDK_VERSION,&scd,&tmpSC,&tmpDev,&fl,nullptr);
    Log("[HookThread] D3D11CreateDeviceAndSwapChain(HW) hr=0x%08X sc=%p",(unsigned)hr,tmpSC);

    if (FAILED(hr)||!tmpSC) {
        hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_WARP,
            nullptr,0,nullptr,0,D3D11_SDK_VERSION,&scd,&tmpSC,&tmpDev,&fl,nullptr);
        Log("[HookThread] WARP fallback hr=0x%08X sc=%p",(unsigned)hr,tmpSC);
    }

    if (FAILED(hr)||!tmpSC) {
        Log("[HookThread] cannot create D3D11 SwapChain, aborting");
        DestroyWindow(hw); UnregisterClassW(wc.lpszClassName,wc.hInstance);
        return 0;
    }

    void **vt=*reinterpret_cast<void***>(tmpSC);
    auto g_presentFnAddr=reinterpret_cast<uint8_t*>(vt[8]); // IDXGISwapChain::Present = slot 8

    MEMORY_BASIC_INFORMATION mbi={};
    VirtualQuery(g_presentFnAddr,&mbi,sizeof(mbi));
    char modPath[MAX_PATH]="(unknown)";
    GetModuleFileNameA((HMODULE)mbi.AllocationBase,modPath,MAX_PATH);
    Log("[HookThread] SwapChain::Present at %p in %s", g_presentFnAddr, modPath);

    tmpSC->Release(); if (tmpDev) tmpDev->Release();
    DestroyWindow(hw); UnregisterClassW(wc.lpszClassName,wc.hInstance);

    // Swapchains sharing this implementation share its COM vtable. Replace
    // only the Present pointer: no arbitrary instruction bytes/trampoline.
    // If a graphics proxy uses a different vtable the selector stays disabled.
    g_fifaVtbl=vt;
    g_OrigPresent=reinterpret_cast<PFN_Present>(vt[8]);
    DWORD previous=0;
    if (VirtualProtect(&vt[8],sizeof(void *),PAGE_READWRITE,&previous)) {
        g_hookSwitched=true;
        InterlockedExchangePointer((PVOID volatile *)&vt[8],(void *)HookedPresent);
        DWORD ignored;
        VirtualProtect(&vt[8],sizeof(void *),previous,&ignored);
        Log("[HookThread] Present vtable hook installed at %p",vt);
    } else Log("[HookThread] Present vtable unavailable; no function bytes changed");

    Log("[HookThread] done");
    return 0;
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------
BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInst);
        InitializeCriticalSection(&g_drawCs);
        InitLog();
        Log("[DllMain] ATTACH pid=%lu", GetCurrentProcessId());

        g_hMap=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,
            PAGE_READWRITE,0,sizeof(OverlayShared),SHMEM_NAME);
        if (g_hMap)
            g_data=reinterpret_cast<OverlayShared*>(
                MapViewOfFile(g_hMap,FILE_MAP_ALL_ACCESS,0,0,sizeof(OverlayShared)));
        Log("[DllMain] shmem hMap=%p data=%p visible=%d",
            g_hMap,g_data,g_data?(int)g_data->visible:-1);

        HANDLE ht=CreateThread(nullptr,0,HookThread,nullptr,0,nullptr);
        if (ht) CloseHandle(ht);

    } else if (reason==DLL_PROCESS_DETACH) {
        Log("[DllMain] DETACH");
        if (g_hookSwitched) {
            // Restore vtable hook
            if (g_fifaVtbl && g_fifaVtbl[8]==reinterpret_cast<void*>(HookedPresent)) {
                DWORD old = 0;
                if (VirtualProtect(&g_fifaVtbl[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
                    g_fifaVtbl[8] = reinterpret_cast<void*>(g_OrigPresent);
                    VirtualProtect(&g_fifaVtbl[8], sizeof(void*), old, &old);
                }
            }
        }
        // Do NOT release D3D11 resources — FIFA is shutting down, releasing COM
        // objects owned by its device here can cause secondary crashes.
        EnterCriticalSection(&g_drawCs);
        if (g_data){ UnmapViewOfFile(g_data); g_data=nullptr; }
        if (g_hMap){ CloseHandle(g_hMap);     g_hMap=nullptr; }
        LeaveCriticalSection(&g_drawCs);
        DeleteCriticalSection(&g_drawCs);
        DeleteCriticalSection(&g_logCs);
    }
    return TRUE;
}
