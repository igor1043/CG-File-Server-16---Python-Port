#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
namespace uitheme {
struct Palette {
 uint32_t accent=0xb9a274,accent_text=0x17242c,accent_ink=0x76623d,
  accent_hover=0xc8b58f,accent_soft=0xeee7da,focus_outline=0xe5d4b0,
  surface=0xffffff,paper=0xf4f6f7;
};
inline Palette palette;
inline bool hex(const std::string&value,uint32_t&out){
 if(value.size()!=7||value[0]!='#')return false;uint32_t n=0;
 for(size_t i=1;i<7;++i){char c=value[i];int v=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if(v<0)return false;n=(n<<4)|v;}
 out=n;return true;
}
inline void load(const std::filesystem::path&path){
 Palette next;std::ifstream file(path,std::ios::binary);if(!file){palette=next;return;}
 std::string raw((std::istreambuf_iterator<char>(file)),{});if(raw.size()>8192){palette=next;return;}
 std::string compact;for(char c:raw)if(c!=' '&&c!='\r'&&c!='\n'&&c!='\t')compact+=c;
 auto version=compact.find("\"version\":1");if(version==compact.npos||version+11>=compact.size()||(compact[version+11]!=','&&compact[version+11]!='}')){palette=next;return;}
 auto field=[&](const char*key,uint32_t&value){auto at=raw.find(std::string("\"")+key+"\"");if(at==raw.npos)return;at=raw.find(':',at);if(at==raw.npos)return;at=raw.find('"',at+1);if(at==raw.npos)return;auto end=raw.find('"',at+1);if(end!=raw.npos)hex(raw.substr(at+1,end-at-1),value);};
 field("accent",next.accent);field("accent_text",next.accent_text);field("accent_ink",next.accent_ink);field("accent_hover",next.accent_hover);field("accent_soft",next.accent_soft);field("focus_outline",next.focus_outline);field("surface",next.surface);field("paper",next.paper);palette=next;
}
inline uint32_t accent(){return 0xff000000|palette.accent;}
inline uint32_t focus(){return 0xff000000|palette.focus_outline;}
inline uint32_t soft(){return 0xff000000|palette.accent_soft;}
// Match Windows COLORREF / RGB so mixed color declarations retain one type.
inline unsigned long colorref(uint32_t rgb){return ((rgb>>16)&255)|(rgb&0xff00)|((rgb&255)<<16);}
inline unsigned long accentInk(){return colorref(palette.accent_ink);}
inline unsigned long selectedText(){return colorref(palette.accent_text);}
}
