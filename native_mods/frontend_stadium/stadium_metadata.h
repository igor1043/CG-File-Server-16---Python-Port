#pragma once
namespace frontend_stadium {
inline int metadataCount(const wchar_t* text,int missing){
    if(!text||!*text)return missing;
    int value=0;
    for(const wchar_t* p=text;*p;++p){
        if(*p<L'0'||*p>L'9'||value>200000)return missing;
        value=value*10+(*p-L'0');
        if(value>2000000)return missing;
    }
    return value;
}
}
