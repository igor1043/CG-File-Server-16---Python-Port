#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <iostream>
#include <vector>
#include "field_prop_shadow.h"
namespace {
uintptr_t image;
alignas(16) unsigned char object[0x38]{},implementation[0x80]{},objectContext[0x40]{},composite[0x30]{},globalTable[0x40]{},renderTable[0x40]{},names[5][96]{};
alignas(16) unsigned char groupObject[0x38]{},groupImplementation[0x80]{},groupContext[0x40]{},luaVm[0x90]{};
alignas(16) unsigned char resource[0x80]{},meshPart[40]{};
alignas(16) unsigned char baseContext[0x50]{};
alignas(16) unsigned char replacementGlobals[0x40]{};
alignas(16) unsigned char extraObjects[3][0x38]{},extraImplementations[3][0x80]{},extraContexts[3][0x40]{};
alignas(16) unsigned char flatParent[0x20]{},selfParent[0x20]{},flatData[0x580]{},selfData[0x4e0]{};
alignas(16) unsigned char nextFlatParent[0x20]{},nextFlatData[0x580]{};
uintptr_t compositePointer,allocatorVtable[4]{},allocator;
struct Value{uint64_t bits;int tag,padding;};struct Node{Value value,key;uintptr_t next;};Node nodes[4]{},renderNodes[2]{};
unsigned creates=0,binds=0,sets=0,prepares=0;bool readyFlag=true;std::array<bool,64> shown{};std::array<fieldshadow::Matrix,64> matrices{};
unsigned groupCreates=0;std::vector<std::pair<uintptr_t,unsigned>> draws;
void ptr(unsigned char* memory,size_t offset,uintptr_t value){memcpy(memory+offset,&value,8);}
void* __fastcall allocate(void*,size_t bytes,const char*,int){assert(bytes==sizeof(object));return creates?groupObject:object;}
void* __fastcall getAllocator(){return &allocator;}
void* __fastcall construct(void* storage,void*,const char* type,int index,int lods,int instances){
 assert(index==0&&lods==1&&instances==64);const bool group=storage==groupObject;
 assert(group?strstr(type,"server16_field_shadow_group_")!=nullptr:strstr(type,"server16_field_shadow_var_cabin_")!=nullptr);
 if(group)++groupCreates;else ++creates;auto* o=group?groupObject:object;auto* impl=group?groupImplementation:implementation;auto* ctx=group?groupContext:objectContext;
 ptr(o,0,image+0x2210dc0);ptr(o,0x20,(uintptr_t)impl);ptr(o,0x30,(uintptr_t)ctx);ptr(ctx,8,(uintptr_t)o);
 if(!group){ptr(o,0x28,(uintptr_t)baseContext);ptr(baseContext,0x28,(uintptr_t)o);}
 unsigned one=1,capacity=64;memcpy(impl+0x18,&one,4);memcpy(impl+0x38,&capacity,4);compositePointer=(uintptr_t)composite;ptr(impl,0x20,(uintptr_t)&compositePointer);composite[0x10]=1;
 ptr(composite,0,(uintptr_t)resource);ptr(resource,0,(uintptr_t)meshPart);ptr(resource,8,(uintptr_t)meshPart+40);ptr(meshPart,0,0x12345678);meshPart[18]=1;return o;
}
void __fastcall registerObject(void* o,const char* type,int index){assert((o==object||o==groupObject)&&strstr(type,"field_shadow_")&&index==0);}
void __fastcall set(void* o,int i,const float* m,bool active){assert((o==object||o==groupObject)&&i>=0&&i<64);if(o==groupObject)return;++sets;memcpy(matrices[i].data(),m,64);shown[i]=active;}
void __fastcall nativeRender(void* o,unsigned pass,void*){draws.emplace_back((uintptr_t)o,pass);}
void __fastcall prepare(void* o){assert(o==composite);++prepares;}
bool __fastcall ready(void* o){assert(o==object);return readyFlag;}
void __fastcall console(const char* script,size_t bytes,const char* tag){
 assert(bytes==strlen(script)&&!strcmp(tag,"field_prop_shadows"));
 if(strstr(script,"S16FieldShadowBound=false")){
  assert(!strstr(script,"AddSubObject")); // Native checked writer owns registration.
  assert(!strstr(script,"ContextAddRenderable")&&!strstr(script,"flatshadow',1"));++binds;
 }nodes[0].value.bits=nodes[1].value.bits=1;
}
void entry(uintptr_t rva,void* target,bool signature=false){
 auto p=(unsigned char*)(image+rva);auto page=(void*)((uintptr_t)p&~uintptr_t(4095));assert(VirtualAlloc(page,4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE));
 if(signature){const unsigned char bytes[]={0x4c,0x8b,0x51,0x20,0x41,0x8b,0x00,0x4c,0x63,0xda};memcpy(p,bytes,sizeof(bytes));p+=sizeof(bytes);}
 const unsigned char jump[]={0xff,0x25,0,0,0,0};memcpy(p,jump,6);memcpy(p+6,&target,8);
}
void registry(uintptr_t vt,uintptr_t method,unsigned char* parent,unsigned char* data,unsigned countAt,unsigned initial,bool instrumented=false){
 const unsigned char writer[58]={0x48,0x83,0xec,0x18,0x4c,0x8b,0x49,0x10,0x44,0x89,0x44,0x24,0x08,0x48,0x8b,0x44,0x24,0x08,0x49,0x63,0x89,0x48,0x05,0,0,0x48,0x01,0xc9,0x49,0x89,0x94,0xc9,0xa8,0,0,0,0x49,0x89,0x84,0xc9,0xb0,0,0,0,0x41,0xff,0x81,0x48,0x05,0,0,0xb0,0x01,0x48,0x83,0xc4,0x18,0xc3};
 // Execute the exact unsafe append instructions captured in the user's dump,
 // on owned test memory. The production guard must stop it before capacity.
 auto* code=(unsigned char*)(image+method);assert(VirtualAlloc((void*)((uintptr_t)code&~uintptr_t(4095)),4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE));
 if(vt==0x2217870){
  memcpy(code,writer,25);memcpy(code+21,&countAt,4);unsigned tail=25;
  if(instrumented){const unsigned char counter[]={0x9c,0xfe,0x05,0,0,0,0,0x9d};memcpy(code+tail,counter,8);const int displacement=0x300-32;memcpy(code+28,&displacement,4);tail=33;}
  const unsigned char selfTail[]={0x48,0x83,0xc1,0x07,0x48,0x01,0xc9,0x49,0x89,0x14,0xc9,0x49,0x89,0x44,0xc9,0x08,0x41,0xff,0x81,0,0,0,0,0xb0,0x01,0x48,0x83,0xc4,0x18,0xc3};
  memcpy(code+tail,selfTail,sizeof(selfTail));memcpy(code+tail+19,&countAt,4);
 }else{memcpy(code,writer,sizeof(writer));memcpy(code+21,&countAt,4);memcpy(code+47,&countAt,4);}
 auto* table=(unsigned char*)(image+vt);assert(VirtualAlloc((void*)((uintptr_t)table&~uintptr_t(4095)),4096,MEM_COMMIT,PAGE_READWRITE));ptr(table,0x90,image+method);
 ptr(parent,0,image+vt);ptr(parent,0x10,(uintptr_t)data);memcpy(data+countAt,&initial,4);
}
}
int main(){
 std::array<bool,64> instanceIds{};
 const char* instanceKeys[]={"var_cabin","stands","balls","entrance"};const unsigned sizes[]={1,13,13,1};
 for(unsigned k=0;k<4;++k)for(unsigned i=0;i<sizes[k];++i){auto id=fieldshadow::nativeInstance(instanceKeys[k],i);assert(id<64&&!instanceIds[id]);instanceIds[id]=true;}
 assert(fieldshadow::nativeInstance("balls",13)==64&&fieldshadow::nativeInstance("entrance",1)==64);
 image=(uintptr_t)VirtualAlloc(nullptr,0x5000000,MEM_RESERVE,PAGE_NOACCESS);assert(image);
 assert(VirtualAlloc((void*)(image+0x2210000),4096,MEM_COMMIT,PAGE_READWRITE));
 assert(VirtualAlloc((void*)(image+0x3613000),4096,MEM_COMMIT,PAGE_READWRITE));
 ptr((unsigned char*)(image+0x3613000),0xfd0,(uintptr_t)luaVm);ptr(luaVm,0x78,(uintptr_t)globalTable);unsigned tag=5;memcpy(luaVm+0x80,&tag,4);
 entry(0x43c8f30,(void*)nativeRender);ptr((unsigned char*)(image+0x2210dc0),0x18,image+0x43c8f30);
 entry(0x4abfba0,(void*)getAllocator);entry(0x43c8be0,(void*)construct);entry(0x4ac5450,(void*)registerObject);entry(0x4ad80b0,(void*)set,true);
 entry(0x4adca80,(void*)prepare);entry(0x4ad7d80,(void*)ready);entry(0x4ac35e0,(void*)console);
 allocatorVtable[2]=(uintptr_t)allocate;allocator=(uintptr_t)allocatorVtable;
 globalTable[8]=5;globalTable[11]=2;ptr(globalTable,32,(uintptr_t)nodes);
 renderTable[8]=5;renderTable[11]=1;ptr(renderTable,32,(uintptr_t)renderNodes);
 const char* labels[]={"S16FieldShadowBound","S16FieldShadowAlive","gRenderObj","flatShadow","selfshadow"};
 for(unsigned i=0;i<5;++i){const size_t length=strlen(labels[i]);memcpy(names[i]+16,&length,8);memcpy(names[i]+24,labels[i],length);auto& node=i<3?nodes[i]:renderNodes[i-3];node.key={uint64_t(names[i]),4,0};node.value={1,1,0};}
 nodes[2].value={(uint64_t)renderTable,5,0};renderNodes[0].value={(uint64_t)flatParent,2,0};renderNodes[1].value={(uint64_t)selfParent,2,0};
 registry(0x22063b0,0x436f080,flatParent,flatData,0x548,73);
 registry(0x2217870,0x44022e0,selfParent,selfData,0x4d0,63,true);
 fieldshadow::Caster caster("var_cabin");SceneLuaSnapshot scope{(uintptr_t)luaVm,(uintptr_t)globalTable};auto pose=fieldshadow::transform(800,2,-3800,.4f);
 assert(fieldshadow::update(caster,image,31,scope,"data/sceneassets/var_cabin/model.rx3","var_cabin_",&pose,1,true,nullptr));
 assert(creates==1&&binds==1&&prepares==1&&shown[0]&&matrices[0]==pose);
 assert(caster.api.read<unsigned>((uintptr_t)flatData+0x548)==74);
 assert(caster.api.read<unsigned>((uintptr_t)selfData+0x4d0)==64);
 auto boundsApi=caster.api;boundsApi.localBounds={-960,-11,-2098,1,935,430,1000,1};
 assert(boundsApi.applyBounds((uintptr_t)object)&&!memcmp(baseContext,boundsApi.localBounds.data(),32));
 const auto validBounds=boundsApi.localBounds;boundsApi.localBounds[4]=boundsApi.localBounds[0];assert(!boundsApi.applyBounds((uintptr_t)object));
 boundsApi.localBounds=validBounds;ptr(baseContext,0x28,0);assert(!boundsApi.applyBounds((uintptr_t)object));ptr(baseContext,0x28,(uintptr_t)object);
 assert(groupCreates==1&&caster.api.read<uintptr_t>((uintptr_t)flatData+0xa8+73*16)==(uintptr_t)groupObject);
 // A full 74-entry native table still accommodates all four modules through
 // exactly one private group. Both native atlas passes preserve child order.
 const char* keys[]={"stands","balls","entrance"};
 for(unsigned i=0;i<3;++i){memcpy(extraObjects[i],object,sizeof object);memcpy(extraImplementations[i],implementation,sizeof implementation);ptr(extraObjects[i],0x20,(uintptr_t)extraImplementations[i]);ptr(extraObjects[i],0x30,(uintptr_t)extraContexts[i]);ptr(extraContexts[i],8,(uintptr_t)extraObjects[i]);auto api=caster.api;api.key=keys[i];assert(fieldshadow::connectFlatGroup(api,(uintptr_t)extraObjects[i]));}
 auto render=(void(__fastcall*)(void*,unsigned,void*))caster.api.read<uintptr_t>(caster.api.read<uintptr_t>((uintptr_t)groupObject)+0x18);
 int context=0;render(groupObject,5,&context);render(groupObject,2,&context);assert(draws.size()==8);
 for(unsigned i=0;i<4;++i){assert(draws[i].first==(i?(uintptr_t)extraObjects[i-1]:(uintptr_t)object));assert(draws[i].second==5&&draws[i+4].first==draws[i].first&&draws[i+4].second==2);}
 assert(caster.api.read<unsigned>((uintptr_t)flatData+0x548)==74&&groupCreates==1);
 // The live selfshadow writer has seven free slots, independently of the
 // full flat renderer. All four mod casters fit without replacing natives.
 for(unsigned i=0;i<6;++i)assert(caster.api.connect((uintptr_t)selfParent,0x98765000+i*8,4));
 assert(caster.api.read<unsigned>((uintptr_t)selfData+0x4d0)==70);
 unsigned char savedFlat[sizeof(flatData)],savedSelf[sizeof(selfData)];memcpy(savedFlat,flatData,sizeof(flatData));memcpy(savedSelf,selfData,sizeof(selfData));
 for(unsigned i=0;i<100;++i){
  assert(!caster.api.connect((uintptr_t)flatParent,0x12345678+i*8,2));
  assert(!caster.api.connect((uintptr_t)selfParent,0x12345678+i*8,4));
 }
 assert(!memcmp(savedFlat,flatData,sizeof(flatData))&&!memcmp(savedSelf,selfData,sizeof(selfData)));
 // Existing links are reusable at capacity; a new caster cannot corrupt count.
 assert(caster.api.connect((uintptr_t)flatParent,(uintptr_t)groupObject,2));
 assert(caster.api.connect((uintptr_t)selfParent,(uintptr_t)object,4));
 auto bad=74u+1;memcpy(flatData+0x548,&bad,4);assert(!caster.api.registry((uintptr_t)flatParent,(uintptr_t)object,2).valid);memcpy(flatData,savedFlat,sizeof(flatData));
 bad=0xffffffffu;memcpy(flatData+0x548,&bad,4);assert(!caster.api.registry((uintptr_t)flatParent,(uintptr_t)object,2).valid);memcpy(flatData,savedFlat,sizeof(flatData));
 auto* nativeWriter=(unsigned char*)(image+0x44022e0);const auto originalByte=nativeWriter[0];nativeWriter[0]=0xcc;
 assert(!caster.api.registry((uintptr_t)selfParent,(uintptr_t)object,4).valid);nativeWriter[0]=originalByte;
 // Both real executable variants decode to the same bounded registry.
 registry(0x2217870,0x44022e0,selfParent,selfData,0x4d0,70,false);
 assert(caster.api.registry((uintptr_t)selfParent,(uintptr_t)object,4).valid);
 registry(0x2217870,0x44022e0,selfParent,selfData,0x4d0,70,true);
 nativeWriter[36]=0x08;assert(!caster.api.registry((uintptr_t)selfParent,(uintptr_t)object,4).valid);nativeWriter[36]=0x07;
 const unsigned stable=sets;for(unsigned frame=0;frame<500;++frame)assert(fieldshadow::update(caster,image,31,scope,"data/sceneassets/var_cabin/model.rx3","var_cabin_",&pose,1,true,nullptr));assert(sets==stable&&binds==1);
 assert(!fieldshadow::update(caster,image,31,scope,"data/sceneassets/var_cabin/model.rx3","var_cabin_",&pose,1,false,nullptr));assert(!shown[0]);
 registry(0x22063b0,0x436f080,nextFlatParent,nextFlatData,0x548,73);
 const auto beforeRace=caster.api.registry((uintptr_t)nextFlatParent,(uintptr_t)object,2);assert(beforeRace.valid&&beforeRace.count==73);
 bad=74;memcpy(nextFlatData+0x548,&bad,4);assert(!caster.api.append(beforeRace,(uintptr_t)object,2));
 bad=73;memcpy(nextFlatData+0x548,&bad,4);renderNodes[0].value.bits=(uintptr_t)nextFlatParent;
 assert(fieldshadow::update(caster,image,32,scope,"data/sceneassets/var_cabin/model.rx3","var_cabin_",&pose,1,true,nullptr));assert(creates==1&&binds==2);
 assert(caster.api.read<unsigned>((uintptr_t)nextFlatData+0x548)==74&&!memcmp(savedFlat,flatData,sizeof(flatData)));
 readyFlag=false;assert(!fieldshadow::update(caster,image,32,scope,"data/sceneassets/var_cabin/model.rx3","var_cabin_",&pose,1,true,nullptr));assert(!shown[0]);
 readyFlag=true;short absent=-1;memcpy(meshPart+16,&absent,2);assert(!caster.api.ready((uintptr_t)object));absent=0;memcpy(meshPart+16,&absent,2);meshPart[18]=0;assert(!caster.api.ready((uintptr_t)object));meshPart[18]=1;assert(caster.api.ready((uintptr_t)object));
 assert(!caster.api.set((uintptr_t)object,64,pose,true));
 const auto rendered=draws.size();memcpy(luaVm+0x80,&sets,4);render(groupObject,2,&context);assert(draws.size()==rendered);
 // FIFA may replace Lua globals while retaining its native renderer. Reuse
 // our own linked slot and drop the previous world's members, even at 74/74.
 memcpy(luaVm+0x80,&tag,4);memcpy(replacementGlobals,globalTable,sizeof globalTable);ptr(luaVm,0x78,(uintptr_t)replacementGlobals);
 auto reloaded=caster.api;reloaded.scope.globals=(uintptr_t)replacementGlobals;assert(fieldshadow::connectFlatGroup(reloaded,(uintptr_t)object));
 assert(groupCreates==1&&caster.api.read<unsigned>((uintptr_t)nextFlatData+0x548)==74);
 render(groupObject,2,&context);assert(draws.size()==rendered+1&&draws.back().first==(uintptr_t)object);
 caster.object=0;VirtualFree((void*)image,0,MEM_RELEASE);
 std::cout<<"PASS production native shadows: 4 modules in 1 flat slot, 28 unique instance IDs, native query/draw ordering, full owned bounds, missing geometry rejected, Lua-world replacement at 74/74, actual flat/self writer capacities and overflow guards; no FIFA attached\n";
}
