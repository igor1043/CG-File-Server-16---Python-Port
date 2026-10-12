#pragma once
#include <stdint.h>
struct PyroGoals {
    int home=-1,away=-1,highHome=-1,highAway=-1,pendingHome=-1,pendingAway=-1;
    uint64_t since=0;
    bool update(uint64_t now,int h,int a,int clubSide) {
        if (h<0 || a<0 || h>99 || a>99) return false;
        if (home<0) { home=highHome=h;away=highAway=a;return false; }
        if (h==home && a==away) { pendingHome=pendingAway=-1;return false; }
        if (h!=pendingHome || a!=pendingAway) { pendingHome=h;pendingAway=a;since=now;return false; }
        if (now<since || now-since<750) return false;
        const bool goal=clubSide==0 ? h==home+1 && a==away && h>highHome :
            clubSide==1 && a==away+1 && h==home && a>highAway;
        home=h;away=a;if(h>highHome)highHome=h;if(a>highAway)highAway=a;
        pendingHome=pendingAway=-1;return goal;
    }
};
