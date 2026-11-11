#pragma once
#include <cstdint>
#include <algorithm>
namespace trophy_shelf {
constexpr unsigned columns=6,rows=3,capacity=columns*rows;
constexpr float left=60,top=205,width=1460,height=576,gap=12,cellWidth=(width-gap*5)/6,cellHeight=(height-gap*2)/3;
struct Status {
 uint32_t size=sizeof(Status),version=2,pid=0,club=0,epoch=0,collection=0,generation=0,total=0,page=0,pages=1,selected=0,ready=0,list=1,detail=0,detailScroll=0;
};
struct State {
 unsigned total=0,page=0,selected=0;
 unsigned pages()const{return std::max(1u,(total+capacity-1)/capacity);}
 unsigned count()const{return total>page*capacity?std::min(capacity,total-page*capacity):0;}
 void clamp(){page=std::min(page,pages()-1);selected=std::min(selected,count()?count()-1:0);}
 void choose(unsigned index){selected=index;clamp();}
 void step(int amount){if(!total)return;int absolute=int(page*capacity+selected);absolute=std::clamp(absolute+amount,0,int(total)-1);page=unsigned(absolute)/capacity;selected=unsigned(absolute)%capacity;}
 void turn(int direction){page=unsigned(std::clamp(int(page)+direction,0,int(pages())-1));clamp();}
};
inline int hit(float x,float y,unsigned count){
 if(x<left||y<top||x>=left+width||y>=top+height)return -1;
 const auto col=unsigned((x-left)/(cellWidth+gap)),row=unsigned((y-top)/(cellHeight+gap));
 if(col>=columns||row>=rows||x-left-col*(cellWidth+gap)>=cellWidth||y-top-row*(cellHeight+gap)>=cellHeight)return -1;
 const auto index=row*columns+col;return index<count?int(index):-1;
}
inline bool historyContains(float x,float y){return x>=1070&&x<=1544&&y>=213&&y<=785;}
}
