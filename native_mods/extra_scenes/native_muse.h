#pragma once
// Verified BCEnginezf build: native ProcessGraph allocation, registration,
// scheduling and skip. Every object below is created/owned by FIFA itself.
namespace native_muse {
using Update=bool(__fastcall*)(void*,double);
using Play=bool(__fastcall*)(void*,int,const char*,void*);
static Update updateOriginal=nullptr;
static Play playOriginal=nullptr;
static uintptr_t impl=0,manager=0,cueContext=0,ownedGraph=0;
static uintptr_t observedManager=0,lastObservedContext=0;
static uint64_t cueTick=0,playedTick=0,lastEnd=0;
static unsigned registrations=0,cueSerial=0;
static bool registered=false;
static unsigned registeredDuration=0;
static bool cueThrowIn=false,registeredThrowIn=false;
static int registeredTeam=-1;
static char names[2][80]{};
static int cuePriority=0;
static bool cancelOwned=false;
static uint64_t diagnosticTick=0;
static bool safePointer(uintptr_t p){return p>=0x10000&&p<0x7ffffffff000;}
static bool contextValid(uintptr_t c,uintptr_t i){
 return safePointer(c)&&get<uintptr_t>(c)==bc+0x128a70&&
        get<uintptr_t>(c+0x58)==i&&get<uintptr_t>(i)==bc+0x12c890&&
        get<uintptr_t>(get<uintptr_t>(i+0xa0))==bc+0x12c300;
}
static void releaseContext(){
 const auto previous=cueContext;cueContext=0;
 if(previous&&get<uintptr_t>(previous)==bc+0x128a70){
  using Release=unsigned(__fastcall*)(void*);
  ((Release)get<uintptr_t>(get<uintptr_t>(previous)+8))((void*)previous);
 }
 cueTick=0;
}
static uintptr_t package(const char* name,uintptr_t graphManager=manager){
 if(get<uintptr_t>(graphManager)!=bc+0x12c300)return 0;
 const auto buckets=get<uintptr_t>(graphManager+0x78);const auto count=get<uint32_t>(graphManager+0x80);
 if(!safePointer(buckets)||count<1||count>65536)return 0;
 uint32_t hash=0x811c9dc5;
 for(const unsigned char* p=(const unsigned char*)name;*p;++p)hash=hash*0x1000193u^*p;
 uintptr_t entry=get<uintptr_t>(buckets+static_cast<uintptr_t>(hash%count)*8);
 for(unsigned n=0;entry&&n<128;++n){
  char key[96]{};if(!read(get<uintptr_t>(entry),key,sizeof key-1))return 0;
  if(!strcmp(key,name)){
   const auto vector=get<uintptr_t>(entry+8),first=get<uintptr_t>(vector),end=get<uintptr_t>(vector+8);
   if(!safePointer(first)||end<first||end-first>1024||(end-first)%16)return 0;
   for(auto p=first;p<end;p+=16){
    const auto graph=get<uintptr_t>(p);
    if(get<uintptr_t>(graph)==bc+0x12eff0)return graph;
   }
   return 0;
  }
  entry=get<uintptr_t>(entry+0x10);
 }
 return 0;
}
static uintptr_t taskGraph(uintptr_t graphManager,const char* name){
 const auto processor=get<uintptr_t>(graphManager+0xb0),first=get<uintptr_t>(processor+0x28),end=get<uintptr_t>(processor+0x30);
 if(!safePointer(first)||end<first||end-first>4096||(end-first)%8)return 0;
 for(auto p=first;p<end;p+=8){
  const auto task=get<uintptr_t>(p);
  const auto graph=get<uintptr_t>(task+8);char actual[96]{};
  if(read(graph+0x18,actual,sizeof actual-1)&&!strcmp(actual,name))return graph;
 }
 return 0;
}
static bool running(const char* name){return taskGraph(manager,name)!=0;}
static void discoverManager(uintptr_t engine){
 // Follow the live BCEngine scene's MUSE adapter, not a previous match's
 // heap address. Verify each interface in this supported engine build.
 const auto scene=get<uintptr_t>(engine+0x68),services=get<uintptr_t>(scene+0x10);
 if(get<uintptr_t>(services)!=bc+0x1165b0)return;
 const auto adapter=get<uintptr_t>(services+0x50);
 if(get<uintptr_t>(adapter)!=bc+0x1166d0)return;
 const auto candidate=get<uintptr_t>(adapter+0x58);
 if(get<uintptr_t>(candidate)!=bc+0x12c890)return;
 const auto target=get<uintptr_t>(candidate+0xa0);
 if(target==observedManager)return;
 if(package("emotion_shot_missed",target)&&package("package_throwin",target)){
  observedManager=target;lastObservedContext=0;log("NATIVE_ACTIVE_MANAGER",static_cast<int>(target));
 }
}
static bool standardCut(uintptr_t except=0){
 const auto processor=get<uintptr_t>(manager+0xb0),first=get<uintptr_t>(processor+0x28),end=get<uintptr_t>(processor+0x30);
 if(!safePointer(first)||end<first||end-first>4096||(end-first)%8)return true;
 for(auto p=first;p<end;p+=8){
  const auto task=get<uintptr_t>(p),graph=get<uintptr_t>(task+8);
  // +0x18 is the native sequence category, not a playback state:
  // STANDARD=0, FILLER=1, FILLER_SKIPPABLE=2, PERSISTENT=3, NONDISRUPTIVE=4.
  // A filler can keep a cinematic camera name after the actual cut finishes.
  if(graph&&graph!=except&&get<int>(task+0x18)==0)return true;
 }
 return false;
}
static bool registerPackages(unsigned duration){
 if(registered&&registeredDuration==duration&&registeredThrowIn==cueThrowIn&&registeredTeam==coachTeam)return true;
 // Unique names allow a changed duration without mutating any loaded graph.
 for(int actor=0;actor<2;++actor){
  sprintf_s(names[actor],"server16_extra_v5_%s_%s_%u_t%d",actor?"mascot":"coach",cueThrowIn?"throwin":"missed_shot",duration,coachTeam);
  if(package(names[actor]))continue;
  char xml[8192]{};
  const int length=sprintf_s(xml,R"xml(<?xml version="1.0" encoding="us-ascii"?>
<import><ProcessGraph.ProcessGraph>
<property name="name" type="string" value="%s"/>
<property name="DisplayCategory" type="string" value="emotion"/>
<property name="priority" type="int" value="0"/>
<property name="sequenceflagtype" type="string" value="STANDARD"/>
<property name="numinstancesrequired" type="int" value="2"/>
<ProcessGraph.SerialNode><property name="Behavior" type="int" value="1"/>
<FIFAPresentationNodes.RenderEffectNode>
<property name="renderObjectMasks" type="int" value="512"/>
<ChildrenList><FIFAPresentationNodes.CameraNode><EvalCoordsCollection/>
<CameraSetCollection/>
<FIFAExpressionProperty><property name="PropertyName" type="string" value="cameraViewContext"/><ExpressionTree.Variable><property name="int" type="int" value="0"/><property name="enumType" type="string" value="CameraViewContext"/><property name="enumValue" type="string" value="None"/></ExpressionTree.Variable></FIFAExpressionProperty>
<CameraTargetCollection><CameraTarget>
<FIFAExpressionProperty><property name="PropertyName" type="string" value="targetType"/><ExpressionTree.Variable><property name="int" type="int" value="-1"/><property name="enumType" type="string" value="ObjectTypes"/><property name="enumValue" type="string" value="%s"/></ExpressionTree.Variable></FIFAExpressionProperty>
<FIFAExpressionProperty><property name="PropertyName" type="string" value="targetId"/>%s</FIFAExpressionProperty>
<FIFAExpressionProperty><property name="PropertyName" type="string" value="targetComponent"/><ExpressionTree.Variable><property name="int" type="int" value="-1"/><property name="enumType" type="string" value="ObjectComponents"/><property name="enumValue" type="string" value="Spine3"/></ExpressionTree.Variable></FIFAExpressionProperty>
</CameraTarget></CameraTargetCollection>
<CameraCollection><CameraInstance>
<property name="cameraName" type="string" value="%s"/>
<property name="cameraEvaluators" type="int" value="0"/>
<property name="cameraFramingOption" type="int" value="0"/>
<property name="blendLength" type="float" value="0"/>
<property name="blendPolicy" type="int" value="1"/>
<ZoomModifierCollection/><FocalDistModifierCollection/>
</CameraInstance></CameraCollection><ChildrenList/>
<property name="name" type="string" value="Server16 extra reaction"/>
<property name="duration" type="float" value="%.3f"/>
</FIFAPresentationNodes.CameraNode></ChildrenList>
<property name="name" type="string" value="Server16 reaction render"/>
<property name="duration" type="float" value="%.3f"/>
</FIFAPresentationNodes.RenderEffectNode>
<property name="name" type="string" value="Server16 reaction sequence"/>
<property name="duration" type="float" value="%.3f"/>
</ProcessGraph.SerialNode>
<property name="actionvariablesdefname" type="string" value="%s"/>
</ProcessGraph.ProcessGraph></import>)xml",names[actor],actor?"Player":(coachTeam==1?"Away_Manager":"Home_Manager"),actor?(cueThrowIn?"<Muse.Fifa.ActionVariable><property name=\"VariableName\" type=\"string\" value=\"ThrowerId\"/></Muse.Fifa.ActionVariable>":"<Muse.Fifa.ActionVariable><property name=\"VariableName\" type=\"string\" value=\"ReactingPlayerId\"/></Muse.Fifa.ActionVariable>"):"<ExpressionTree.Variable><property name=\"int\" type=\"int\" value=\"0\"/></ExpressionTree.Variable>",coachTeam==1?"Manager_0_Away_Pos":"Manager_0_Home_Pos",duration*.001,duration*.001,duration*.001,cueThrowIn?"FIFA_Base,FIFA_QuickThrowIn":"FIFA_Emotion_Base,FIFA_EndPlay");
  if(length<=0||length>=static_cast<int>(sizeof xml))return false;
  using Load=void(__fastcall*)(void*,const char*,unsigned,uintptr_t,bool);
  ((Load)(bc+0xada50))((void*)manager,xml,static_cast<unsigned>(length),0,false);
  if(!package(names[actor]))return false;
  ++registrations;
 }
 registered=true;registeredDuration=duration;registeredThrowIn=cueThrowIn;registeredTeam=coachTeam;log("NATIVE_PACKAGES_REGISTERED",static_cast<int>(duration));return true;
}
static void skipOwned(int reason=0){
 if(ownedGraph){
  FILE* f=nullptr;if(!_wfopen_s(&f,logPath,L"ab")){std::fprintf(f,"%llu NATIVE_REACTION_ENDED reason=%d wall_ms=%llu applied=%llu shot=%d\r\n",GetTickCount64(),reason,GetTickCount64()-playedTick,ExtraScenesStatus.applied,currentShot);std::fclose(f);}
 }
 if(ownedGraph&&get<uintptr_t>(ownedGraph)==bc+0x12eff0){
  const auto node=get<uintptr_t>(ownedGraph+8),vt=get<uintptr_t>(node);
  const auto skip=get<uintptr_t>(vt+0xe0);
  if(vt>=bc+0x110000&&vt<bc+0x140000&&skip>=bc&&skip<bc+0x110000){
   using Skip=void(__fastcall*)(void*);((Skip)skip)((void*)node);
  }
 }
 if(ownedGraph)lastEnd=GetTickCount64();ownedGraph=0;playedTick=0;cancelOwned=false;tripod.reset();
}
// Called only from the native update/play thread, with gate held.
static void capture(void* self,int priority,const char* name,void* context){
 const auto currentManager=get<uintptr_t>((uintptr_t)self+0xa0);
 if(!stopping&&options.enabled&&!ownedGraph){
  releaseContext();
  if(currentManager!=manager){registered=false;registeredDuration=0;ownedGraph=0;}
  impl=(uintptr_t)self;manager=currentManager;
  cueThrowIn=!strcmp(name,"package_throwin");
  // Play actions may supply a temporary context that FIFA resets explicitly.
  // A refcount does not extend that temporary's lifetime. Use exactly the
  // engine Clone operation used by GraphManager::Queue (vtable + 0x30).
  using Clone=void*(__fastcall*)(void*);
  cueContext=(uintptr_t)((Clone)get<uintptr_t>(get<uintptr_t>((uintptr_t)context)+0x30))(context);
  if(contextValid(cueContext,impl)){
   cueTick=GetTickCount64();cuePriority=priority;++cueSerial;
   lastObservedContext=(uintptr_t)context;
   log(cueThrowIn?"NATIVE_THROWIN_CLONED":(!strcmp(name,"emotion")?"NATIVE_GOALKICK_REACTION_CLONED":"NATIVE_MISSED_SHOT_CLONED"),priority);
   log("NATIVE_CUE_PHASE",get<int>(get<uintptr_t>(image+0x3517c10)+0x3c));
  }else{releaseContext();log("NATIVE_CONTEXT_CLONE_FAILED");}
 }
}
static void observeQueue(){
 if(!observedManager||cueContext||ownedGraph)return;
 const auto processor=get<uintptr_t>(observedManager+0xb0),first=get<uintptr_t>(processor+0x28),end=get<uintptr_t>(processor+0x30);
 if(!safePointer(first)||end<first||end-first>4096||(end-first)%8)return;
 const bool goalKick=taskGraph(observedManager,"package_gk_unintentional_endplay")!=0;
 uintptr_t selected=0;int priority=-1;char selectedName[96]{};
 for(auto p=first;p<end;p+=8){
  const auto task=get<uintptr_t>(p),graph=get<uintptr_t>(task+8),context=get<uintptr_t>(task+0x20);
  char name[96]{};
  if(!read(graph+0x18,name,sizeof name-1)||!nativeReactionCue(name,goalKick))continue;
  const int candidatePriority=get<int>(task+4);
  if(candidatePriority>priority&&contextValid(context,get<uintptr_t>(context+0x58))){
   selected=context;priority=candidatePriority;strcpy_s(selectedName,name);
  }
 }
 if(!selected){lastObservedContext=0;return;}
 if(selected!=lastObservedContext){
  log("NATIVE_QUEUE_EVENT_OBSERVED",priority);
  capture((void*)get<uintptr_t>(selected+0x58),priority,selectedName,(void*)selected);
 }
}
static bool __fastcall playHook(void* self,int priority,const char* name,void* context){
 const bool result=playOriginal(self,priority,name,context);
 char copy[96]{};read((uintptr_t)name,copy,sizeof copy-1);
 if(!result||!contextValid((uintptr_t)context,(uintptr_t)self))return result;
 const auto currentManager=get<uintptr_t>((uintptr_t)self+0xa0);
 AcquireSRWLockExclusive(&gate);
 if(package("emotion_shot_missed",currentManager)&&package("package_throwin",currentManager))observedManager=currentManager;
 const bool goalKick=taskGraph(currentManager,"package_gk_unintentional_endplay")!=0;
 if(nativeReactionCue(copy,goalKick))capture(self,priority,copy,context);
 ReleaseSRWLockExclusive(&gate);return result;
}
static bool __fastcall updateHook(void* self,double time){
 ExtraScenesEngine=(uintptr_t)self;
 const bool result=updateOriginal(self,time);
 AcquireSRWLockExclusive(&gate);
 const auto now=GetTickCount64(),scene=get<uintptr_t>(image+0x3517c10);
 const int phase=get<int>(scene+0x3c);
 discoverManager((uintptr_t)self);
 const bool safe=!stopping&&options.enabled&&onMatchPage()&&!get<unsigned char>(scene+0x39)&&stoppedScenePhase(phase);
 if(safe)observeQueue();
 if(ownedGraph){
  const int endReason=cancelOwned?1:!safe?2:standardCut(ownedGraph)?3:!running(names[currentShot/2])?5:0;
  if(endReason)skipOwned(endReason);
 }
 if(cueContext){
  const bool originalReaction=standardCut(ownedGraph);
  const ReactionWindow window{now,contextValid(cueContext,impl),!stopping&&options.enabled,safe,phase==15,!onMatchPage(),originalReaction,!originalReaction};
  const auto decision=reactionDecision(cueTick,window);
  if(now-diagnosticTick>=1000||decision!=ReactionDecision::Wait){
   diagnosticTick=now;
   const int flags=(window.valid?1:0)|(window.enabled?2:0)|(window.stopped?4:0)|(window.live?8:0)|(window.outside?16:0)|(window.originalReaction?32:0)|(window.slotAvailable?64:0)|(get<unsigned char>(scene+0x39)?128:0);
   log("NATIVE_CUE_WINDOW",flags);
  }
  if(decision==ReactionDecision::Discard){log("NATIVE_CUE_DISCARDED",static_cast<int>(now-cueTick));releaseContext();}
  else if(decision==ReactionDecision::Queue&&!ownedGraph){
     const auto cfg=options;
     const bool chance=sceneOpportunity(cfg.test,pendingPreview,now,lastEnd,cfg.cooldown,cueSerial,cfg.chance);
     SceneActorSnapshot actors{};Actor subject{};Camera view{};
     const bool hasSnapshot=chance&&snapshot(actors);
     const bool hasSubject=hasSnapshot&&choose(cfg,actors,view,subject);
     const bool hasPackages=hasSubject&&registerPackages(cfg.duration);
     const bool hasTripod=hasPackages&&tripod.begin(subject,view,now,currentShot%2==1);
     if(hasTripod||!chance||now-diagnosticTick>=500){log("NATIVE_CUE_READY",(chance?1:0)|(hasSnapshot?2:0)|(hasSubject?4:0)|(hasPackages?8:0)|(hasTripod?16:0));diagnosticTick=now;}
     if(hasTripod){
      // GraphManager's original queue clones the action context and owns its nodes.
      using Queue=bool(__fastcall*)(void*,int,const char*,void*);
      const bool queued=((Queue)(bc+0xb08c0))((void*)manager,cuePriority,names[currentShot/2],(void*)cueContext);
      if(queued){ownedGraph=taskGraph(manager,names[currentShot/2]);playedTick=now;pendingPreview=false;ExtraScenesStatus.inserted++;log("NATIVE_REACTION_QUEUED",currentShot);}
      else log("NATIVE_QUEUE_FAILED",currentShot);
     }
     if(hasTripod||!chance)releaseContext();
  }
 }
 ReleaseSRWLockExclusive(&gate);
 if(stopping)swapAt(0x113300,(uintptr_t)&updateHook,(uintptr_t)updateOriginal);
 return result;
}
static bool lease(uint64_t now,Camera& view,const SceneActorSnapshot& actors){
 if(!ownedGraph||standardCut(ownedGraph)||!running(names[currentShot/2])||now<playedTick)return false;
 Actor subject{};
 if((currentShot<2?coach(actors,subject):mascot(actors,subject))&&tripod.update(subject,now,view))return true;
 cancelOwned=true;return tripod.current(view);
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModBindNativeManager(const uintptr_t* request){
 uintptr_t target=0;
 if(!read((uintptr_t)request,&target,sizeof target)||!package("emotion_shot_missed",target)||!package("package_throwin",target))return FALSE;
 AcquireSRWLockExclusive(&gate);observedManager=target;lastObservedContext=0;ReleaseSRWLockExclusive(&gate);
 log("NATIVE_QUEUE_OBSERVER_BOUND");return TRUE;
}
}
