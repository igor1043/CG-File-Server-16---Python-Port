#include <cstdio>
#include <cassert>
static unsigned calls=0,waits=0,failures=0;
static FILE* fakeOpen(const char*){return calls++<failures?nullptr:reinterpret_cast<FILE*>(1);}
#define SERVER16_ARCHIVE_OPEN(path) fakeOpen(path)
#define SERVER16_ARCHIVE_WAIT() (++waits)
#include "../tools/server16_archive_retry.h"
int main(){
 failures=0;assert(server16_open_archive("bundle")==reinterpret_cast<FILE*>(1));assert(calls==1&&waits==0);
 calls=waits=0;failures=3;assert(server16_open_archive("bundle")==reinterpret_cast<FILE*>(1));assert(calls==4&&waits==3);
 calls=waits=0;failures=200;assert(server16_open_archive("bundle")==reinterpret_cast<FILE*>(1));assert(calls==201&&waits==200);
 calls=waits=0;failures=500;assert(server16_open_archive("missing")==nullptr);assert(calls==201&&waits==200);
 std::puts("PASS archive reopen: no delay on success, transient retry, bounded permanent failure");
}
