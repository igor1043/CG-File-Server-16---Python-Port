#pragma once
#include <d3d11.h>
#include <vector>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

namespace ultrawide {
enum class Artwork { None, Bootflow, Fallback, PressStart, Count };

// Identify the actual background by its compressed DDS pixels, never by size
// alone. Other UI textures with the same resolution remain ordinary 16:9 UI.
class Backgrounds {
    struct Image {
        UINT width=0,height=0,block=0;DXGI_FORMAT format=DXGI_FORMAT_UNKNOWN;
        std::vector<unsigned char> pixels;
        ID3D11ShaderResourceView *view[2]={};
    };
    struct Pair { Image images[2]; };
    Pair pairs[static_cast<unsigned>(Artwork::Count)-1];
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
    static UINT be_word(const unsigned char *p) {
        return (UINT(p[0])<<24)|(UINT(p[1])<<16)|(UINT(p[2])<<8)|UINT(p[3]);
    }
    // PressStart's picture is entry "2" in the APT container. Its layout,
    // button glyphs and text are separate entries.
    static bool seek_pressstart_picture(FILE *file, size_t &length) {
        unsigned char header[16];
        if(fread(header,1,sizeof(header),file)!=sizeof(header)||
           (memcmp(header,"BIG4",4)&&memcmp(header,"BIGF",4)))return false;
        UINT count=be_word(header+8),end=be_word(header+12);
        if(end<16||end>65536||!count||count>(end-16)/9)return false;
        if(_fseeki64(file,0,SEEK_END))return false;
        const auto size=_ftelli64(file);
        if(size<end||(size!=word(header+4)&&size!=be_word(header+4))||
           _fseeki64(file,16,SEEK_SET))return false;
        std::vector<unsigned char> directory(end-16);
        if(fread(directory.data(),1,directory.size(),file)!=directory.size())return false;
        size_t at=0;
        for(UINT i=0;i<count;++i) {
            if(at+9>directory.size())return false;
            const auto *entry=directory.data()+at;
            const auto *name=entry+8;
            const auto *zero=static_cast<const unsigned char*>(memchr(name,0,directory.size()-at-8));
            if(!zero)return false;
            if(zero-name==1&&name[0]=='2') {
                UINT offset=be_word(entry),bytes=be_word(entry+4);
                if(offset<end||bytes<128||uint64_t(offset)+bytes>uint64_t(size))return false;
                length=bytes;
                return !_fseeki64(file,offset,SEEK_SET);
            }
            at=size_t(zero-directory.data())+1;
        }
        return false;
    }
    static bool load(const wchar_t *path,Image &im,bool pressstart) {
        FILE *file=nullptr;if(_wfopen_s(&file,path,L"rb")||!file)return false;
        size_t length=SIZE_MAX;
        unsigned char h[128];
        bool ok=(!pressstart||seek_pressstart_picture(file,length))&&
            fread(h,1,128,file)==128&&!memcmp(h,"DDS ",4)&&word(h+4)==124&&word(h+76)==32;
        if(ok) {
            im.height=word(h+12);im.width=word(h+16);
            if(!memcmp(h+84,"DXT1",4)){im.format=DXGI_FORMAT_BC1_UNORM;im.block=8;}
            else if(!memcmp(h+84,"DXT3",4)){im.format=DXGI_FORMAT_BC2_UNORM;im.block=16;}
            else if(!memcmp(h+84,"DXT5",4)){im.format=DXGI_FORMAT_BC3_UNORM;im.block=16;}
            ok=im.block&&im.width>=64&&im.height>=64&&im.width<=16384&&im.height<=16384;
        }
        if(ok) {
            size_t bytes=size_t((im.width+3)/4)*((im.height+3)/4)*im.block;
            ok=bytes<=length-sizeof(h);
            if(ok){im.pixels.resize(bytes);ok=fread(im.pixels.data(),1,bytes,file)==bytes;}
        }
        fclose(file);if(!ok)im.pixels.clear();return ok;
    }
    static DXGI_FORMAT typeless(DXGI_FORMAT f) {
        return f==DXGI_FORMAT_BC1_UNORM?DXGI_FORMAT_BC1_TYPELESS:f==DXGI_FORMAT_BC2_UNORM?DXGI_FORMAT_BC2_TYPELESS:DXGI_FORMAT_BC3_TYPELESS;
    }
    static DXGI_FORMAT srgb(DXGI_FORMAT f) {
        return f==DXGI_FORMAT_BC1_UNORM?DXGI_FORMAT_BC1_UNORM_SRGB:f==DXGI_FORMAT_BC2_UNORM?DXGI_FORMAT_BC2_UNORM_SRGB:DXGI_FORMAT_BC3_UNORM_SRGB;
    }
    void release_views(){for(auto &pair:pairs)for(auto &im:pair.images)for(auto &view:im.view)if(view){view->Release();view=nullptr;}if(device){device->Release();device=nullptr;}}
    bool ensure_device(ID3D11DeviceContext *ctx) {
        ID3D11Device *owner=nullptr;ctx->GetDevice(&owner);if(!owner)return false;
        if(device==owner){owner->Release();return true;}
        release_views();device=owner;
        return true;
    }
    void ensure_views(Image &im) {
            if(im.view[0]||im.view[1]||im.pixels.empty())return;
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
    static bool compatible(const D3D11_TEXTURE2D_DESC &desc,const Image &image) {
        return !image.pixels.empty()&&desc.Width==image.width&&desc.Height==image.height&&linear(desc.Format)==image.format;
    }
    Artwork matches(ID3D11DeviceContext *ctx,ID3D11Texture2D *texture) {
        UINT bytes=sizeof(UINT),cached=0;
        if(SUCCEEDED(texture->GetPrivateData(tag,&bytes,&cached))&&bytes==sizeof(cached)&&cached<static_cast<UINT>(Artwork::Count))
            return static_cast<Artwork>(cached);
        D3D11_TEXTURE2D_DESC desc={};texture->GetDesc(&desc);
        bool candidate=false;
        Artwork match=Artwork::None;
        for(auto &pair:pairs)for(auto &im:pair.images)candidate=candidate||compatible(desc,im);
        if(candidate&&desc.ArraySize==1&&desc.SampleDesc.Count==1) {
            D3D11_TEXTURE2D_DESC copy=desc;copy.MipLevels=1;copy.Usage=D3D11_USAGE_STAGING;
            copy.BindFlags=copy.MiscFlags=0;copy.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
            ID3D11Texture2D *staging=nullptr;
            if(SUCCEEDED(device->CreateTexture2D(&copy,nullptr,&staging))) {
                // Only once per matching-size texture, not every frame.
                ctx->CopySubresourceRegion(staging,0,0,0,0,texture,0,nullptr);
                D3D11_MAPPED_SUBRESOURCE mapped={};
                if(SUCCEEDED(ctx->Map(staging,0,D3D11_MAP_READ,0,&mapped))) {
                    for(auto &pair:pairs)for(auto &im:pair.images) {
                        if(match!=Artwork::None||!compatible(desc,im))continue;
                        const size_t row=((im.width+3)/4)*im.block,rows=(im.height+3)/4;
                        bool equal=mapped.RowPitch>=row;
                        for(size_t y=0;equal&&y<rows;++y)equal=!memcmp((unsigned char*)mapped.pData+y*mapped.RowPitch,im.pixels.data()+y*row,row);
                        if(equal)match=static_cast<Artwork>(&pair-pairs+1);
                    }
                    ctx->Unmap(staging,0);
                }
                staging->Release();
            }
        }
        cached=static_cast<UINT>(match);texture->SetPrivateData(tag,sizeof(cached),&cached);return match;
    }
public:
    // The overlay is pinned for the game session. Avoid D3D calls from static
    // destruction under the loader lock, as in the rest of the overlay.
    void clear(){release_views();for(auto &pair:pairs)for(auto &im:pair.images)im.pixels.clear();}
    bool initialize(const wchar_t *standard,const wchar_t *wide,Artwork kind=Artwork::Bootflow) {
        auto &images=pairs[static_cast<unsigned>(kind)-1].images;
        bool pressstart=kind==Artwork::PressStart;
        if(load(standard,images[0],pressstart)&&load(wide,images[1],pressstart))return true;
        for(auto &image:images)image.pixels.clear();
        return false;
    }
    Artwork select_artwork(ID3D11DeviceContext *ctx,bool wide,ID3D11ShaderResourceView *&old) {
        // FIFA's frontend picture is its primary texture. Auxiliary slots may
        // retain the background after the picture draw; they do not identify
        // the next card/font draw as a full-width backdrop.
        ID3D11ShaderResourceView *bound=nullptr;ctx->PSGetShaderResources(0,1,&bound);
        if(!bound)return Artwork::None;
        Artwork kind=Artwork::None;
        ID3D11Resource *resource=nullptr;ID3D11Texture2D *texture=nullptr;bound->GetResource(&resource);
        if(resource&&SUCCEEDED(resource->QueryInterface(__uuidof(ID3D11Texture2D),(void**)&texture))&&ensure_device(ctx)) {
            kind=matches(ctx,texture);
            if(kind!=Artwork::None) {
                D3D11_SHADER_RESOURCE_VIEW_DESC original={};bound->GetDesc(&original);
                bool gamma=original.Format==DXGI_FORMAT_BC1_UNORM_SRGB||original.Format==DXGI_FORMAT_BC2_UNORM_SRGB||original.Format==DXGI_FORMAT_BC3_UNORM_SRGB;
                auto &image=pairs[static_cast<unsigned>(kind)-1].images[wide?1:0];
                ensure_views(image);
                auto replacement=image.view[gamma?1:0];
                if(replacement){old=bound;bound=nullptr;ctx->PSSetShaderResources(0,1,&replacement);}
            }
        }
        if(texture)texture->Release();
        if(resource)resource->Release();
        if(bound)bound->Release();
        return kind;
    }
};
}
