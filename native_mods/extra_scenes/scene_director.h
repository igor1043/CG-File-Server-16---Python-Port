#pragma once
#include <stdint.h>
namespace extra {
enum class Window {Outside,Live,Native,Idle};
struct Input {uint64_t now=0,fixture=0;Window window=Window::Outside;bool enabled=true,preview=false;unsigned duration=5000,cooldown=45000,chance=35;};
class Director {
 uint64_t fixture_=0,stopSince_=0,idleSince_=0,end_=0,lastEnd_=0;unsigned serial_=0;
 bool live_=false,stopped_=false,sawNative_=false,consumed_=false,active_=false;
 void finish(uint64_t now){if(active_)lastEnd_=now;active_=false;consumed_=true;}
public:
 bool started=false;
 bool active()const{return active_;}
 void reject(uint64_t now){finish(now);}
 void reset(){*this=Director{};}
 bool tick(const Input& in){
  started=false;
  if(!in.enabled||!in.fixture||in.window==Window::Outside){reset();return false;}
  if(fixture_!=in.fixture){reset();fixture_=in.fixture;}
  if(in.window==Window::Live){if(active_)finish(in.now);live_=true;stopped_=false;idleSince_=0;return false;}
  if(!stopped_){if(!live_)return false;stopped_=true;stopSince_=in.now;idleSince_=0;sawNative_=consumed_=false;++serial_;}
  if(in.window==Window::Native){
   // An original cutscene has absolute priority, including one arriving mid-extra.
   if(active_)finish(in.now);sawNative_=true;idleSince_=0;return false;
  }
  if(active_){if(in.now>=end_)finish(in.now);return active_;}
  if(consumed_||in.now-stopSince_>15000)return false;
  if(!idleSince_){idleSince_=in.now;return false;}
  if(in.now-idleSince_<500)return false;
  if(!in.preview){
   if(!sawNative_||in.now-lastEnd_<in.cooldown)return false;
   const uint32_t random=serial_*2654435761u+static_cast<uint32_t>(fixture_);
   if(random%100>=in.chance){consumed_=true;return false;}
  }
  active_=true;started=true;end_=in.now+in.duration;return true;
 }
};
}
