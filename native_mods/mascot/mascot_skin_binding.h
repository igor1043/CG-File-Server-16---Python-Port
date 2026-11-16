#pragma once
#include <windows.h>
#include <stdint.h>
#include <math.h>
#include <string.h>

// RX3 bind transforms belong to the asset, whereas the SLE draw palette is
// multiplied by the renderer's shared inverse bind. Keep those spaces apart.
// Shader result: (modelPose * inverseModelBind * rendererBind)
//               * inverseRendererBind == modelPose * inverseModelBind.
struct MascotSkinBinding {
    float modelBind[31][16]{};
    float compensation[31][16]{};
};

static bool mascot_skin_affine(const float m[16]) {
    for(unsigned int i=0;i<16;++i)if(!isfinite(m[i]) || fabsf(m[i])>20000)return false;
    return fabsf(m[3])<.001f && fabsf(m[7])<.001f && fabsf(m[11])<.001f && fabsf(m[15]-1)<.001f;
}
static bool mascot_skin_inverse(const float matrix[16],float out[16]) {
    if(!mascot_skin_affine(matrix))return false;
    const float a=matrix[0],b=matrix[4],c=matrix[8],d=matrix[1],e=matrix[5],f=matrix[9],g=matrix[2],h=matrix[6],i=matrix[10];
    const float determinant=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
    if(!isfinite(determinant) || fabsf(determinant)<.0001f)return false;
    memset(out,0,16*sizeof(float));out[15]=1;
    const float rows[9]={e*i-f*h,c*h-b*i,b*f-c*e,f*g-d*i,a*i-c*g,c*d-a*f,d*h-e*g,b*g-a*h,a*e-b*d};
    for(unsigned int row=0;row<3;++row)for(unsigned int column=0;column<3;++column)out[column*4+row]=rows[row*3+column]/determinant;
    for(unsigned int row=0;row<3;++row)out[12+row]=-(out[row]*matrix[12]+out[4+row]*matrix[13]+out[8+row]*matrix[14]);
    return mascot_skin_affine(out);
}
static void mascot_skin_multiply(const float a[16],const float b[16],float out[16]) {
    float result[16]{};
    for(unsigned int column=0;column<4;++column)for(unsigned int row=0;row<4;++row)
        for(unsigned int k=0;k<4;++k)result[column*4+row]+=a[k*4+row]*b[column*4+k];
    memcpy(out,result,sizeof(result));
}
static bool mascot_skin_prepare(const float modelInverse[31][16],const float rendererInverse[31][16],MascotSkinBinding& result) {
    MascotSkinBinding next{};
    for(unsigned int bone=0;bone<31;++bone) {
        float rendererBind[16];
        if(!mascot_skin_inverse(modelInverse[bone],next.modelBind[bone]) || !mascot_skin_inverse(rendererInverse[bone],rendererBind))return false;
        mascot_skin_multiply(modelInverse[bone],rendererBind,next.compensation[bone]);
        if(!mascot_skin_affine(next.compensation[bone]))return false;
    }
    result=next;return true;
}
static bool mascot_skin_palette(const MascotSkinBinding& binding,const float pose[31][16],float palette[31][16]) {
    for(unsigned int bone=0;bone<31;++bone) {
        if(!mascot_skin_affine(pose[bone]))return false;
        mascot_skin_multiply(pose[bone],binding.compensation[bone],palette[bone]);
        if(!mascot_skin_affine(palette[bone]))return false;
    }
    return true;
}

static bool mascot_read_model_inverse(const wchar_t* path,float inverse[31][16]) {
    HANDLE file=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    LARGE_INTEGER size{};DWORD got=0;uint32_t header[4]{};
    bool valid=GetFileSizeEx(file,&size) && size.QuadPart>=32 && size.QuadPart<=64*1024*1024 &&
        ReadFile(file,header,sizeof(header),&got,nullptr) && got==sizeof(header) && memcmp(header,"RX3l",4)==0 &&
        header[2]>=32 && header[2]<=(uint32_t)size.QuadPart && header[3]>0 && header[3]<=20000 &&
        16ull+header[3]*16ull<=(uint64_t)header[2];
    uint32_t bindOffset=0;bool found=false;
    for(uint32_t i=0;valid && i<header[3];++i) {
        uint32_t section[4]{};
        valid=ReadFile(file,section,sizeof(section),&got,nullptr) && got==sizeof(section) &&
            section[1]>=16ull+header[3]*16ull && section[2]>=4 && (uint64_t)section[1]+section[2]<=header[2];
        if(valid && section[0]==0xdf9aec1e) {
            if(found || section[2]!=16+31*64){valid=false;break;}
            bindOffset=section[1];found=true;
        }
    }
    float candidate[31][16]{};
    if(valid && found) {
        LARGE_INTEGER offset{};offset.QuadPart=bindOffset;uint32_t bindHeader[4]{};
        valid=SetFilePointerEx(file,offset,nullptr,FILE_BEGIN) &&
            ReadFile(file,bindHeader,sizeof(bindHeader),&got,nullptr) && got==sizeof(bindHeader) &&
            bindHeader[0]==16+31*64 && bindHeader[1]==31 &&
            ReadFile(file,candidate,sizeof(candidate),&got,nullptr) && got==sizeof(candidate);
        for(unsigned int bone=0;valid && bone<31;++bone) {
            // Original RX3 stores affine 3x4 transforms with a zero padding
            // element (Palmeiras); authored exports store homogeneous 1.
            if(candidate[bone][15]==0)candidate[bone][15]=1;
            float test[16];valid=mascot_skin_inverse(candidate[bone],test);
        }
    } else valid=false;
    CloseHandle(file);
    if(valid)memcpy(inverse,candidate,sizeof(candidate));
    return valid;
}
