#pragma once
#include <d3d11.h>
#include <vector>
#include <stdio.h>
#include <string.h>

namespace ultrawide {
// Identify the actual background by its compressed DDS pixels, never by size
// alone. Other UI textures with the same resolution remain ordinary 16:9 UI.
class Backgrounds {
    struct Image {
        UINT width=0,height=0,block=0;DXGI_FORMAT format=DXGI_FORMAT_UNKNOWN;
        std::vector<unsigned char> pixels;
        ID3D11ShaderResourceView *view[2]={};
    } images[2];
    ID3D11Device *device=nullptr;
    // Private data lives with the game's texture, so no pointer cache retains
    // scene assets or swapchain buffers across menu changes and ResizeBuffers.
    const GUID tag={0xa53db54a,0x92c1,0x4081,{0x85,0x51,0xf8,0xca,0x28,0x90,0xb1,0x08}};
    static UINT word(const unsigned char *p){UINT n;memcpy(&n,p,4);return n;}
    static DXGI_FORMAT linear(DXGI_FORMAT f) {
        if(f==DXGI_FORMAT_BC1_UNORM_SRGB||f==DXGI_FORMAT_BC1_TYPELESS)return DXGI_FORMAT_BC1_UNORM;
        if(f==DXGI_FORMAT_BC2_UNORM_SRGB||f==DXGI_FORMAT_BC2_TYPELESS)return DXGI_FORMAT_BC2_UNORM;
        if(f==DXGI_FORMAT_BC3_UNORM_SRGB||f==DXGI_FORMAT_BC3_TYPELESS)return DXGI_FORMAT_BC3_UNORM;
        return f;
    }
    static bool load(const wchar_t *path,Image &im) {
        FILE *file=nullptr;if(_wfopen_s(&file,path,L"rb")||!file)return false;
        unsigned char h[128];bool ok=fread(h,1,128,file)==128&&!memcmp(h,"DDS ",4)&&word(h+4)==124&&word(h+76)==32;
        if(ok) {
            im.height=word(h+12);im.width=word(h+16);
            if(!memcmp(h+84,"DXT1",4)){im.format=DXGI_FORMAT_BC1_UNORM;im.block=8;}
            else if(!memcmp(h+84,"DXT3",4)){im.format=DXGI_FORMAT_BC2_UNORM;im.block=16;}
            else if(!memcmp(h+84,"DXT5",4)){im.format=DXGI_FORMAT_BC3_UNORM;im.block=16;}
            ok=im.block&&im.width>=64&&im.height>=64&&im.width<=16384&&im.height<=16384;
        }
        if(ok){im.pixels.resize(size_t((im.width+3)/4)*((im.height+3)/4)*im.block);ok=fread(im.pixels.data(),1,im.pixels.size(),file)==im.pixels.size();}
        fclose(file);if(!ok)im.pixels.clear();return ok;
    }
    static DXGI_FORMAT typeless(DXGI_FORMAT f) {
        return f==DXGI_FORMAT_BC1_UNORM?DXGI_FORMAT_BC1_TYPELESS:f==DXGI_FORMAT_BC2_UNORM?DXGI_FORMAT_BC2_TYPELESS:DXGI_FORMAT_BC3_TYPELESS;
    }
    static DXGI_FORMAT srgb(DXGI_FORMAT f) {
        return f==DXGI_FORMAT_BC1_UNORM?DXGI_FORMAT_BC1_UNORM_SRGB:f==DXGI_FORMAT_BC2_UNORM?DXGI_FORMAT_BC2_UNORM_SRGB:DXGI_FORMAT_BC3_UNORM_SRGB;
    }
    void release_views(){for(auto &im:images)for(auto &view:im.view)if(view){view->Release();view=nullptr;}if(device){device->Release();device=nullptr;}}
    bool ensure_views(ID3D11DeviceContext *ctx) {
        ID3D11Device *owner=nullptr;ctx->GetDevice(&owner);if(!owner)return false;
        if(device==owner){owner->Release();return true;}
        release_views();device=owner;
        for(auto &im:images) {
            if(im.pixels.empty())continue;
            D3D11_TEXTURE2D_DESC desc={};desc.Width=im.width;desc.Height=im.height;desc.MipLevels=desc.ArraySize=1;
            desc.Format=typeless(im.format);desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_IMMUTABLE;desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
            D3D11_SUBRESOURCE_DATA data={im.pixels.data(),((im.width+3)/4)*im.block,0};
            ID3D11Texture2D *texture=nullptr;
            if(SUCCEEDED(device->CreateTexture2D(&desc,&data,&texture))) {
                D3D11_SHADER_RESOURCE_VIEW_DESC view={};view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=1;
                view.Format=im.format;device->CreateShaderResourceView(texture,&view,&im.view[0]);
                view.Format=srgb(im.format);device->CreateShaderResourceView(texture,&view,&im.view[1]);texture->Release();
            }
        }
        return true;
    }
    bool matches(ID3D11DeviceContext *ctx,ID3D11Texture2D *texture) {
        UINT bytes=sizeof(UINT),cached=0;
        if(SUCCEEDED(texture->GetPrivateData(tag,&bytes,&cached))&&bytes==sizeof(cached))return cached==1;
        D3D11_TEXTURE2D_DESC desc={};texture->GetDesc(&desc);
        bool candidate=false,match=false;
        for(auto &im:images)if(!im.pixels.empty()&&desc.Width==im.width&&desc.Height==im.height&&linear(desc.Format)==im.format)candidate=true;
        if(candidate&&desc.ArraySize==1&&desc.SampleDesc.Count==1) {
            D3D11_TEXTURE2D_DESC copy=desc;copy.MipLevels=1;copy.Usage=D3D11_USAGE_STAGING;
            copy.BindFlags=copy.MiscFlags=0;copy.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
            ID3D11Texture2D *staging=nullptr;
            if(SUCCEEDED(device->CreateTexture2D(&copy,nullptr,&staging))) {
                // Only once per matching-size texture, not every frame.
                ctx->CopySubresourceRegion(staging,0,0,0,0,texture,0,nullptr);
                D3D11_MAPPED_SUBRESOURCE mapped={};
                if(SUCCEEDED(ctx->Map(staging,0,D3D11_MAP_READ,0,&mapped))) {
                    for(auto &im:images) {
                        if(desc.Width!=im.width||desc.Height!=im.height||linear(desc.Format)!=im.format||im.pixels.empty())continue;
                        const size_t row=((im.width+3)/4)*im.block,rows=(im.height+3)/4;
                        bool equal=mapped.RowPitch>=row;
                        for(size_t y=0;equal&&y<rows;++y)equal=!memcmp((unsigned char*)mapped.pData+y*mapped.RowPitch,im.pixels.data()+y*row,row);
                        match=match||equal;
                    }
                    ctx->Unmap(staging,0);
                }
                staging->Release();
            }
        }
        cached=match?1:2;texture->SetPrivateData(tag,sizeof(cached),&cached);return match;
    }
public:
    // The overlay is pinned for the game session. Avoid D3D calls from static
    // destruction under the loader lock, as in the rest of the overlay.
    void clear(){release_views();for(auto &im:images)im.pixels.clear();}
    void initialize(const wchar_t *standard,const wchar_t *wide){load(standard,images[0]);load(wide,images[1]);}
    bool select(ID3D11DeviceContext *ctx,bool wide,UINT &slot,ID3D11ShaderResourceView *&old) {
        if(images[0].pixels.empty()||images[1].pixels.empty()||!ensure_views(ctx))return false;
        // FIFA's frontend picture is its primary texture. Auxiliary slots may
        // retain the background after the picture draw; they do not identify
        // the next card/font draw as a full-width backdrop.
        ID3D11ShaderResourceView *bound[1]={};ctx->PSGetShaderResources(0,1,bound);
        bool found=false;
        for(UINT i=0;i<1;++i) {
            if(!bound[i])continue;
            if(!found) {
                ID3D11Resource *resource=nullptr;ID3D11Texture2D *texture=nullptr;bound[i]->GetResource(&resource);
                if(resource&&SUCCEEDED(resource->QueryInterface(__uuidof(ID3D11Texture2D),(void**)&texture))) {
                    if(matches(ctx,texture)) {
                        D3D11_SHADER_RESOURCE_VIEW_DESC original={};bound[i]->GetDesc(&original);
                        bool gamma=original.Format==DXGI_FORMAT_BC1_UNORM_SRGB||original.Format==DXGI_FORMAT_BC2_UNORM_SRGB||original.Format==DXGI_FORMAT_BC3_UNORM_SRGB;
                        auto replacement=images[wide?1:0].view[gamma?1:0];
                        if(replacement){slot=i;old=bound[i];bound[i]=nullptr;found=true;ctx->PSSetShaderResources(i,1,&replacement);}
                    }
                    texture->Release();
                }
                if(resource)resource->Release();
            }
            if(bound[i])bound[i]->Release();
        }
        return found;
    }
};
}
