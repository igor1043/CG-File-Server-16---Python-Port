#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "ultrawide_background.h"
#include <assert.h>
#include <vector>

static ID3D11ShaderResourceView *native_image(ID3D11Device *device,const wchar_t *file,bool gamma,bool different) {
    FILE *stream=nullptr;assert(!_wfopen_s(&stream,file,L"rb"));
    unsigned char h[128];assert(fread(h,1,128,stream)==128);
    UINT height,width;memcpy(&height,h+12,4);memcpy(&width,h+16,4);
    std::vector<unsigned char> pixels(size_t((width+3)/4)*((height+3)/4)*16);
    assert(fread(pixels.data(),1,pixels.size(),stream)==pixels.size());fclose(stream);
    if(different)pixels[pixels.size()/2]^=0xff;
    D3D11_TEXTURE2D_DESC desc={};desc.Width=width;desc.Height=height;desc.MipLevels=desc.ArraySize=desc.SampleDesc.Count=1;
    desc.Format=DXGI_FORMAT_BC2_TYPELESS;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA data={pixels.data(),((width+3)/4)*16,0};
    ID3D11Texture2D *texture=nullptr;assert(SUCCEEDED(device->CreateTexture2D(&desc,&data,&texture)));
    D3D11_SHADER_RESOURCE_VIEW_DESC view={};view.Format=gamma?DXGI_FORMAT_BC2_UNORM_SRGB:DXGI_FORMAT_BC2_UNORM;
    view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=1;
    ID3D11ShaderResourceView *result=nullptr;assert(SUCCEEDED(device->CreateShaderResourceView(texture,&view,&result)));texture->Release();return result;
}
int wmain(int argc,wchar_t **argv) {
    assert(argc==3);
    ID3D11Device *device=nullptr;ID3D11DeviceContext *ctx=nullptr;
    assert(SUCCEEDED(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&ctx)));
    ultrawide::Backgrounds images;images.initialize(argv[1],argv[2]);
    for(bool gamma:{false,true})for(int source=0;source<2;++source) {
        ID3D11ShaderResourceView *original=native_image(device,argv[source+1],gamma,false);
        for(int i=0;i<20;++i) {
            bool wide=i%2!=0;UINT slot=123;ID3D11ShaderResourceView *old=nullptr;
            ctx->PSSetShaderResources(0,1,&original);
            assert(images.select(ctx,wide,slot,old)&&slot==0&&old==original);
            ID3D11ShaderResourceView *selected=nullptr;ctx->PSGetShaderResources(0,1,&selected);
            D3D11_SHADER_RESOURCE_VIEW_DESC view={};selected->GetDesc(&view);
            assert(view.Format==(gamma?DXGI_FORMAT_BC2_UNORM_SRGB:DXGI_FORMAT_BC2_UNORM));
            ID3D11Resource *resource=nullptr;selected->GetResource(&resource);
            ID3D11Texture2D *texture=nullptr;resource->QueryInterface(__uuidof(ID3D11Texture2D),(void**)&texture);
            D3D11_TEXTURE2D_DESC desc={};texture->GetDesc(&desc);assert(desc.Width==(wide?2560u:1920u)&&desc.Height==1080);
            texture->Release();resource->Release();selected->Release();
            ctx->PSSetShaderResources(slot,1,&old);old->Release();
        }
        ID3D11ShaderResourceView *none=nullptr;ctx->PSSetShaderResources(0,1,&none);
        ctx->PSSetShaderResources(2,1,&original);UINT slot=0;ID3D11ShaderResourceView *old=nullptr;
        assert(!images.select(ctx,true,slot,old)&&old==nullptr);
        ctx->PSSetShaderResources(2,1,&none);original->Release();
    }
    // Same size and format as the real background, but different pixels: a
    // menu, portrait or unrelated full-size texture must never be widened.
    ID3D11ShaderResourceView *other=native_image(device,argv[1],false,true);
    ctx->PSSetShaderResources(0,1,&other);ID3D11ShaderResourceView *none=nullptr;ctx->PSSetShaderResources(2,1,&none);
    UINT slot=0;ID3D11ShaderResourceView *old=nullptr;assert(!images.select(ctx,true,slot,old)&&old==nullptr);
    ctx->PSSetShaderResources(0,1,&none);other->Release();images.clear();ctx->ClearState();ctx->Release();device->Release();
    puts("PASS: exact DDS originals, live switch both directions, native cache, stale auxiliary bindings excluded, sRGB preserved, and unrelated same-size image rejected.");
}
