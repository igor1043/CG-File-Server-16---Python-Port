#include <cassert>
#include <fstream>
#include <iostream>
#include "custom_ui_theme.h"
int main(int argc,char**argv){
 using namespace uitheme;uint32_t value=0;
 assert(hex("#B9A274",value)&&value==0xb9a274);
 assert(!hex("#XYZ123",value)&&!hex("#12345678",value));
 assert(colorref(0xb9a274)==0x74a2b9);
 if(argc>1){load(argv[1]);assert(palette.accent==0xb9a274&&accent()==0xffb9a274);}
 const std::filesystem::path test="theme-fixture.json";
 {std::ofstream out(test);out<<"{\"version\":1,\"accent\":\"#aBc123\",\"accent_text\":\"invalid\"}";}
 load(test);assert(palette.accent==0xabc123&&palette.accent_text==0x17242c);
 {std::ofstream out(test);out<<"{\"version\":2,\"accent\":\"#123456\"}";}
 load(test);assert(palette.accent==0xb9a274);
 {std::ofstream out(test);out<<"{\"version\":10,\"accent\":\"#123456\"}";}
 load(test);assert(palette.accent==0xb9a274);
 std::filesystem::remove(test);
 std::cout<<"PASS shared UI theme: exact gold token, COLORREF/ARGB, custom hex, invalid/version fallback\n";
}
