#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <tlhelp32.h>
#include <initializer_list>
#include <wchar.h>
#include "mascot_single_core.h"
#include "native_guards.h"
#include "mascot_package_guard.h"
#include "mascot_memory_reader.h"
#include "mascot_pose_policy.h"
#include "mascot_placement_policy.h"
#include "match_presentation.h"

static uintptr_t image;
static char logPath[MAX_PATH];
static volatile LONG started;
static void (__fastcall* originalSelect)(void*);
static uintptr_t lastRenderer, lastRecords;
static size_t lastCount, selectedSlot;
static unsigned int lastAppearanceType=23;
static float targetPosition[3];
static bool repositionMascot;
static bool currentClubAnimated;
static MascotPlacementChoice matchPlacement;
static float originalPosition[3];
static float originalYaw;
static int lastHome = -1, lastStadium = -1, lastLight = -1, lastCold = -1;
static DWORD lastIdentityCheck, lastDirectionCheck;
static MatchPresentationConfig presentationConfig;
static bool lastMascotAllowed=true;
static int lastAttackDirection;
struct PriorPlacement { unsigned int magic, index; uintptr_t renderer, records; float original[3], target[3]; };
static PriorPlacement priorPlacement;
static bool priorPlacementPending;
static wchar_t gameDirectory[MAX_PATH];
static volatile LONG packageStatus;
static LONG lastPackageStatus = -1;
static unsigned int mascotPlacementGeneration;
// Validated once by placement. Animation consumes this snapshot in the same
// hook, rather than scanning the same vectors and Lua tables a second time.
struct MascotFrameContext {
    uintptr_t renderer, records;
    size_t count, selected;
    int home, stadium, light, cold;
    LONG packages;
    unsigned int generation;
    bool mascotActive;
    bool packageAnimated;
    unsigned int appearanceType;
};

static void log_event(const char* format, ...)
{
    FILE* file = nullptr;
    if (!logPath[0] || fopen_s(&file, logPath, "ab") || !file) return;
    fprintf(file, "%lu thread=%lu ", GetTickCount(), GetCurrentThreadId());
    va_list args; va_start(args, format); vfprintf(file, format, args); va_end(args);
    fputs("\r\n", file); fclose(file);
}

struct ClubPackage { unsigned int club; bool animated; };
static ClubPackage clubPackages[128]{};
static size_t clubPackageCount;
static SRWLOCK clubPackageLock=SRWLOCK_INIT;
static bool mascot_club_ready(int club,bool animated) {
    bool ready=false;AcquireSRWLockShared(&clubPackageLock);
    for(size_t i=0;i<clubPackageCount;++i) if(clubPackages[i].club==(unsigned int)club) {ready=!animated||clubPackages[i].animated;break;}
    ReleaseSRWLockShared(&clubPackageLock);return ready;
}
static void update_packages()
{
    ClubPackage next[128]{};size_t count=0;
    wchar_t pattern[MAX_PATH];_snwprintf_s(pattern,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\*",gameDirectory);
    WIN32_FIND_DATAW entry{};HANDLE search=FindFirstFileW(pattern,&entry);
    if(search!=INVALID_HANDLE_VALUE) {
        do {
            if(!(entry.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY))continue;
            wchar_t* end=nullptr;unsigned long id=wcstoul(entry.cFileName,&end,10);
            if(!id||id>1000000||!end||*end||count>=128)continue;
            wchar_t model[MAX_PATH],texture[MAX_PATH],animated[MAX_PATH];
            _snwprintf_s(model,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%lu\\model.rx3",gameDirectory,id);
            _snwprintf_s(texture,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%lu\\textures.rx3",gameDirectory,id);
            _snwprintf_s(animated,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%lu\\model_animated.rx3",gameDirectory,id);
            if(mascot_rx3_file_valid(model,false)&&mascot_rx3_file_valid(texture,true))next[count++]={(unsigned int)id,mascot_rx3_file_valid(animated,false)};
        }while(FindNextFileW(search,&entry));FindClose(search);
    }
    for(size_t i=0;i<count;++i)for(size_t j=i+1;j<count;++j)if(next[j].club<next[i].club){ClubPackage temp=next[i];next[i]=next[j];next[j]=temp;}
    AcquireSRWLockExclusive(&clubPackageLock);
    bool changed=count!=clubPackageCount;
    for(size_t i=0;!changed && i<count;++i)changed=next[i].club!=clubPackages[i].club || next[i].animated!=clubPackages[i].animated;
    if(changed){memcpy(clubPackages,next,sizeof(next));clubPackageCount=count;InterlockedIncrement(&packageStatus);}
    ReleaseSRWLockExclusive(&clubPackageLock);
    if(changed)for(size_t i=0;i<count;++i)log_event("package_ready club=%u animated=%u",next[i].club,(unsigned int)next[i].animated);
}

static DWORD WINAPI package_worker(void*)
{
    for (;;) { update_packages(); Sleep(1000); }
}

static bool readable(uintptr_t address, size_t length)
{
    MEMORY_BASIC_INFORMATION info{};
    if (address < 0x10000 || !length || address + length < address ||
        !VirtualQuery((void*)address, &info, sizeof(info)) || info.State != MEM_COMMIT ||
        (info.Protect & (PAGE_NOACCESS | PAGE_GUARD))) return false;
    return address + length <= (uintptr_t)info.BaseAddress + info.RegionSize;
}

template<typename T> static bool get(uintptr_t address, T& value)
{
    if (!readable(address, sizeof(value))) return false;
    __try { value = *(T*)address; return true; }
    __except(EXCEPTION_EXECUTE_HANDLER) { return false; }
}

static bool vector_bounds(uintptr_t address, size_t stride, uintptr_t& begin, size_t& count)
{
    uintptr_t end, capacity;
    if (!get(address, begin) || !get(address + 8, end) || !get(address + 16, capacity)) return false;
    if (!begin && !end && !capacity) { count = 0; return true; }
    if (begin < 0x10000 || end < begin || capacity < end || (end - begin) % stride ||
        (capacity - begin) % stride || (capacity - begin) / stride > 1024) return false;
    count = (end - begin) / stride;
    return count <= 256 && readable(begin, capacity - begin ? capacity - begin : 1);
}

static bool code_ready()
{
    for (const NativeGuard& guard : nativeGuards) {
        /* The first CALL can already belong to our v3 diagnostic plugin. */
        const size_t skip = guard.rva == 0x43ac0f1 ? 5 : 0;
        if (!readable(image + guard.rva, guard.size) ||
            memcmp((void*)(image + guard.rva + skip), guard.bytes + skip, guard.size - skip)) return false;
    }
    return true;
}

static bool refresh_lua(unsigned int rnaIndex)
{
    char ready[4096]{},animated[4096]{};size_t rp=0,ap=0;
    AcquireSRWLockShared(&clubPackageLock);
    for(size_t i=0;i<clubPackageCount;++i){
        rp+=(size_t)snprintf(ready+rp,sizeof(ready)-rp,"[%u]=true,",clubPackages[i].club);
        if(clubPackages[i].animated)ap+=(size_t)snprintf(animated+ap,sizeof(animated)-ap,"[%u]=true,",clubPackages[i].club);
    }
    ReleaseSRWLockShared(&clubPackageLock);
    char script[12288];
    const int size=snprintf(script,sizeof(script),
        "FIFA16_MASCOT_SINGLE_INSTANCE_READY=true; FIFA16_MASCOT_PACKAGE_STATUS={%s}; FIFA16_MASCOT_ANIMATION_MODEL_READY={%s}; "
        "if not FIFA16_MASCOT_BASE_SLEUPDATE then FIFA16_MASCOT_BASE_SLEUPDATE=SleUpdate end; "
        "SleUpdate=function(i) FIFA16_MASCOT_BASE_SLEUPDATE(i);local s=db.sle[i]; "
        "if s.isMascot==1 and FIFA16_MASCOT_PACKAGE_STATUS[s.teamid]~=true then s.isMascot=0;s.slename='photographer' end end; "
        "if not FIFA16_MASCOT_BASE_RMSLE then FIFA16_MASCOT_BASE_RMSLE=GetRMSle end; "
        "GetRMSle=function(i,m)local s=db.sle[i]; "
        "if (s.sletype==5 or s.sletype==12) and FIFA16_MASCOT_PACKAGE_STATUS[s.teamid] then return '' end; "
        "if s.isMascot==1 and m==0 and FIFA16_MASCOT_ANIMATION_MODEL_READY[s.teamid] then return 'data/sceneassets/mascot/'..s.teamid..'/model_animated.rx3;' end; "
        "return FIFA16_MASCOT_BASE_RMSLE(i,m) end;SleUpdate(%u);local s=db.sle[%u]; "
        "FIFA16_MASCOT_CORNER_AUDIT={rnaIndex=%u,homeTeam=s.teamid,isMascot=s.isMascot,name=s.slename,model=GetRMSle(%u,0),texture=GetTexture(%u)};",
        ready,animated,rnaIndex,rnaIndex,rnaIndex,rnaIndex,rnaIndex);
    if (size < 0 || size >= sizeof(script)) return false;
    __try {
        /* Engine-owned critical section; runs on native BatchSLE scene thread. */
        ((void (__fastcall*)(const char*, size_t, const char*))(image + 0x4ac35e0))(
            script, (size_t)size, "mascot_corner_refresh");
        return true;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        log_event("lua_refresh_fault"); return false;
    }
}

/* Read the already verified Lua 5.1 table layout on its scene thread.
 * Placement changes require this exact prototype's isMascot=1. */
static uintptr_t lua_table_field(uintptr_t table, const char* key)
{
    MascotScopedMemoryReader reader;
    unsigned char type, power; uintptr_t nodes;
    if (!reader.get(table + 8, type) || type != 5 || !reader.get(table + 11, power) || power > 16 ||
        !reader.get(table + 32, nodes)) return 0;
    const size_t length = strlen(key), count = (size_t)1 << power;
    for (size_t i = 0; i < count; ++i) {
        const uintptr_t node = nodes + i * 40;
        int tag; uintptr_t text; size_t textLength;
        if (!reader.get(node + 24, tag)) return 0;
        if (tag != 4 || !reader.get(node + 16, text) || !reader.get(text + 16, textLength) ||
            textLength != length || !reader.readable(text + 24, length)) continue;
        if (memcmp((void*)(text + 24), key, length) == 0) return node;
    }
    return 0;
}

static uintptr_t prototype_lua_table(unsigned int index)
{
    uintptr_t lua, globals, dbValue, dbTable, sleValue, sleTable, array, item;
    int tag, size;
    if (!get(image + 0x3613fd0, lua) || !get(lua + 0x80, tag) || tag != 5 ||
        !get(lua + 0x78, globals) || !(dbValue = lua_table_field(globals, "db")) ||
        !get(dbValue + 8, tag) || tag != 5 || !get(dbValue, dbTable) ||
        !(sleValue = lua_table_field(dbTable, "sle")) || !get(sleValue + 8, tag) || tag != 5 ||
        !get(sleValue, sleTable) || !get(sleTable + 56, size) || index < 1 || index > (unsigned int)size ||
        !get(sleTable + 24, array) || !get(array + (index - 1) * 16 + 8, tag) || tag != 5 ||
        !get(array + (index - 1) * 16, item)) return 0;
    return item;
}

static int lua_number(uintptr_t table, const char* key)
{
    uintptr_t value = lua_table_field(table, key); int tag; double number;
    if (!value || !get(value + 8, tag) || tag != 3 || !get(value, number) ||
        !isfinite(number) || number < -1 || number > 1000000) return -1;
    return (int)number;
}

#include "mascot_attack_side.h"
#include "mascot_native_animation.h"

static bool same_position(const float* a, const float* b)
{
    return fabsf(a[0]-b[0]) < 0.2f && fabsf(a[1]-b[1]) < 0.2f && fabsf(a[2]-b[2]) < 0.2f;
}

static void reload_legacy_ballboys(uintptr_t renderer)
{
    for (unsigned int type : {5u, 12u}) {
        uintptr_t begin; size_t count;
        if (!vector_bounds(renderer + 0x30 * (type + 1), 8, begin, count)) continue;
        for (size_t i = 0; i < count; ++i) {
            uintptr_t prototype, state; unsigned int rnaIndex; uint16_t nativeType;
            if (!get(begin+i*8, prototype) || !get(prototype+12,nativeType) || nativeType != type ||
                !get(prototype+16,state) || !get(state+0x4c,rnaIndex)) continue;
            char script[80];
            int size = snprintf(script,sizeof(script),"SleUpdate(%u);",rnaIndex);
            ((void (__fastcall*)(const char*,size_t,const char*))(image+0x4ac35e0))(
                script,(size_t)size,"mascot_normal_ballboys");
            ((void (__fastcall*)(void*,unsigned char))(image+0x43b4530))((void*)prototype,1);
            log_event("legacy_ballboy_reload type=%u rna_index=%u policy=normal_ballboy",type,rnaIndex);
        }
    }
}

static void prepare_prototypes(uintptr_t begin,size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        uintptr_t prototype = *(uintptr_t*)(begin + i * 8);
        if (!((bool (__fastcall*)(void*))(image + 0x43b4500))((void*)prototype)) {
            alignas(16) int parameters[5] = {-1, -1, -1, 0, -1};
            ((void (__fastcall*)(void*, const int*))(image + 0x43b4640))((void*)prototype, parameters);
            ((void (__fastcall*)(void*, unsigned char))(image + 0x43b4530))((void*)prototype, 0);
        }
    }
}

static bool assign_mascot_placement(void* object, MascotFrameContext& frame)
{
    const uintptr_t renderer = (uintptr_t)object;
    size_t placementCounts[mascotPlacementTypeCount]{};
    uintptr_t placementRecords[mascotPlacementTypeCount]{};
    for(unsigned int i=0;i<mascotPlacementTypeCount;++i)
        if(!vector_bounds(renderer+0x30*(mascotPlacementTypes[i]+0x2f),0x50,placementRecords[i],placementCounts[i]))return false;
    const unsigned int appearanceType=mascot_choose_placement_type(placementCounts);
    if(appearanceType>=23) {
        static DWORD lastMissingLog=0;const DWORD tick=GetTickCount();
        if(!lastMissingLog || tick-lastMissingLog>=5000) { lastMissingLog=tick;log_event("placement_unavailable photographers=0 choreo_photographers=0 stewards=0 choreo_stewards=0"); }
        lastRecords=0;repositionMascot=false;mascot_set_animation_active(false,-1);return false;
    }
    uintptr_t prototypes, records; size_t prototypeCount, count;
    const unsigned char reservedAppearance=(unsigned char)mascot_reserved_appearance(appearanceType);
    if (!vector_bounds(renderer + 0x30*(appearanceType+1), 8, prototypes, prototypeCount) || prototypeCount != (size_t)reservedAppearance+1 ||
        !vector_bounds(renderer + 0x30*(appearanceType+0x2f), 0x50, records, count)) return false;
    if (!count) { lastRecords = 0; repositionMascot = false; mascot_set_animation_active(false,-1); return false; }
    for (size_t i = 0; i < prototypeCount; ++i) {
        uintptr_t prototype, state; uint16_t type, variation;
        if (!get(prototypes + i * 8, prototype) || !get(prototype + 12, type) || type != appearanceType ||
            !get(prototype + 14, variation) || variation != i || !get(prototype + 16, state) ||
            !readable(state, 0x50)) return false;
    }
    uintptr_t prototype = *(uintptr_t*)(prototypes + (size_t)reservedAppearance*8);
    uintptr_t state = *(uintptr_t*)(prototype + 16);
    const unsigned int rnaIndex = *(unsigned int*)(state + 0x4c);
    const bool newGeometry = renderer != lastRenderer || records != lastRecords || count != lastCount || appearanceType!=lastAppearanceType;
    if(renderer==lastRenderer && appearanceType!=lastAppearanceType && lastAppearanceType<23) {
        uintptr_t previous;size_t previousCount;
        if(vector_bounds(renderer+0x30*(lastAppearanceType+0x2f),0x50,previous,previousCount) && previous==lastRecords) {
            mascot_walk_restore_live(renderer,previous,previousCount);
            mascot_unbind_pose(renderer,previous,previousCount);
        }
    }
    // Clean the reserved appearances in the other validated actor categories.
    // No previous vector or scene pointer is used after an ownership change.
    for(unsigned int i=0;i<mascotPlacementTypeCount;++i)if(mascotPlacementTypes[i]!=appearanceType)
        mascot_assign_none((unsigned char*)placementRecords[i],placementCounts[i],(unsigned char)mascot_reserved_appearance(mascotPlacementTypes[i]));
    int home = lastHome, stadium = lastStadium, light = lastLight, cold = lastCold;
    const DWORD tick = GetTickCount();
    const bool mascotAllowed=presentationConfig.read(tick).mascots;
    const bool optionsChanged=mascotAllowed!=lastMascotAllowed;
    if (newGeometry || tick - lastIdentityCheck >= 250) {
        lastIdentityCheck = tick;
        const uintptr_t luaTable = prototype_lua_table(rnaIndex);
        home = lua_number(luaTable,"teamid"); stadium = lua_number(luaTable,"stadiumID");
        light = lua_number(luaTable,"stadiumLightID"); cold = lua_number(luaTable,"cold");
    }
    const bool newIdentity = home != lastHome || stadium != lastStadium || light != lastLight || cold != lastCold;
    const LONG packages=InterlockedCompareExchange(&packageStatus,0,0);
    const bool packagesChanged=packages!=lastPackageStatus;
    if (newGeometry || newIdentity || packagesChanged || optionsChanged) {
        ++mascotPlacementGeneration;
        if (!newGeometry && mascotWalkRuntime.ready) mascot_walk_restore_live(renderer,records,count);
        if (!newGeometry && repositionMascot && selectedSlot < count) {
            float current[3]; memcpy(current,(void*)(records+selectedSlot*0x50+0x20),sizeof(current));
            if (same_position(current,targetPosition)) memcpy((void*)(records+selectedSlot*0x50+0x20),originalPosition,sizeof(originalPosition));
        }
        if (priorPlacementPending) {
            if (renderer == priorPlacement.renderer && records == priorPlacement.records && priorPlacement.index < count) {
                float current[3]; memcpy(current,(void*)(records+priorPlacement.index*0x50+0x20),sizeof(current));
                if (same_position(current,priorPlacement.target)) {
                    memcpy((void*)(records+priorPlacement.index*0x50+0x20),priorPlacement.original,sizeof(priorPlacement.original));
                    log_event("prior_plugin_placement_restored number=%u",priorPlacement.index+1);
                }
            }
            priorPlacementPending = false;
        }
        lastRenderer = renderer; lastRecords = records; lastCount = count;
        lastAppearanceType=appearanceType;
        lastHome=home; lastStadium=stadium; lastLight=light; lastCold=cold;
        lastPackageStatus=packages;
        lastMascotAllowed=mascotAllowed;
        selectedSlot = mascot_choose_corner((const unsigned char*)records, count);
        float p[3]; memcpy(p, (void*)(records + selectedSlot * 0x50 + 0x20), sizeof(p));
        log_event("scene renderer=%p placement_type=%u actors=%zu photographers=%zu choreo_photographers=%zu stewards=%zu choreo_stewards=%zu mascot_slots=1 number=%zu runtime_index=%zu position=%g,%g,%g",
            object,appearanceType,count,placementCounts[0],placementCounts[1],placementCounts[2],placementCounts[3],selectedSlot+1,selectedSlot,p[0],p[1],p[2]);
        if (refresh_lua(rnaIndex)) {
            /* v2/v3 had already configured this resource as a photographer.
             * Force its native callback/path/material reload on the scene thread. */
            ((void (__fastcall*)(void*, unsigned char))(image + 0x43b4530))((void*)prototype, 1);
            log_event("reserved_resource_reload requested rna_index=%u audit=FIFA16_MASCOT_CORNER_AUDIT", rnaIndex);
        }
        repositionMascot = mascotAllowed && lua_number(prototype_lua_table(rnaIndex),"isMascot") == 1;
        currentClubAnimated=mascot_club_ready(home,true);
        mascot_set_animation_active(repositionMascot && currentClubAnimated,home);
        memcpy(originalPosition,p,sizeof(originalPosition));
        if(!get(records+selectedSlot*0x50+0x1c,originalYaw))originalYaw=0;
        mascot_position_by_goal_line(p, targetPosition);
        lastAttackDirection=0;lastDirectionCheck=0;
        reload_legacy_ballboys(renderer);
        log_event("match_identity home=%d stadium=%d mascot_active=%u",home,stadium,(unsigned int)repositionMascot);
        log_event("goal_line_position active=%u number=%zu original=%g,%g,%g target=%g,%g,%g",
            (unsigned int)repositionMascot, selectedSlot + 1, p[0], p[1], p[2],
            targetPosition[0], targetPosition[1], targetPosition[2]);
    }
    if(repositionMascot){
        const uintptr_t session=(uintptr_t)(unsigned int)InterlockedCompareExchange(&mascotPlacementSession,0,0);
        const uint64_t tickSeed=GetTickCount64();
        const uint32_t seed=(uint32_t)tickSeed^(uint32_t)(tickSeed>>32)^(unsigned int)home^(uint32_t)session;
        if(matchPlacement.update(session,home,stadium,seed))
            log_event("match_position_chosen club=%d session=%llu lateral=%g behind_boards_x=5850 preferred=%u",home,(unsigned long long)session,matchPlacement.lateral,(unsigned int)(matchPlacement.lateral==3150.0f));
        targetPosition[2]=matchPlacement.lateral;
    }
    if (repositionMascot && (!lastDirectionCheck || tick-lastDirectionCheck>=250)) {
        lastDirectionCheck=tick;
        const int direction=mascot_home_native_orientation(home);
        if (direction && direction!=lastAttackDirection) {
            lastAttackDirection=direction;
            targetPosition[0]=mascot_attack_goal_x(direction);
            targetPosition[2]=matchPlacement.lateral;
            log_event("attack_side home=%d direction=%d goal_x=%g target=%g,%g,%g",home,direction,
                targetPosition[0],targetPosition[0],targetPosition[1],targetPosition[2]);
        }
    }
    prepare_prototypes(prototypes,prototypeCount);
    const size_t changes = repositionMascot ? mascot_assign_one((unsigned char*)records,count,selectedSlot,reservedAppearance) :
        mascot_assign_none((unsigned char*)records,count,reservedAppearance);
    if (repositionMascot) memcpy((void*)(records + selectedSlot * 0x50 + 0x20), targetPosition, sizeof(targetPosition));
    if (changes) log_event("appearance_assignment mode=corner mascot_slots=1 normal_slots=%zu changed=%zu",
        count - 1, changes);
    frame = {renderer, records, count, selectedSlot, home, stadium, light, cold,
        packages, mascotPlacementGeneration, repositionMascot, currentClubAnimated,appearanceType};
    return true;
}

static void __fastcall selection_hook(void* renderer)
{
    originalSelect(renderer);
    /* BEFORE 43a8bf0 resolves prototypes and builds its GPU draw list. */
    MascotFrameContext frame{};
    __try {
        if (assign_mascot_placement(renderer, frame)) mascot_animate_instance(frame);
        else { mascotWalkRuntime={};mascotNativeClock={};mascot_unbind_pose(0,0,0); mascot_set_animation_active(false,-1); }
    }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        // A failed scene lookup supplies no ownership proof for old pointers.
        // Forget them; never write through them during exception recovery.
        mascotWalkRuntime={};mascotNativeClock={};mascot_unbind_pose(0,0,0); mascot_set_animation_active(false,-1);
        static DWORD lastFaultLog; const DWORD tick=GetTickCount();
        if (!lastFaultLog || tick-lastFaultLog>=1000) {
            lastFaultLog=tick; log_event("assignment_fault; no further writes this frame");
        }
    }
}

static void* allocate_near(uintptr_t origin)
{
    SYSTEM_INFO info; GetSystemInfo(&info);
    const uintptr_t step = info.dwAllocationGranularity;
    const uintptr_t aligned = origin & ~(step - 1);
    for (uintptr_t distance = step; distance < 0x70000000; distance += step) {
        for (int side = 0; side < 2; ++side) {
            if (side && aligned < distance + 0x10000) continue;
            uintptr_t candidate = side ? aligned - distance : aligned + distance;
            void* memory = VirtualAlloc((void*)candidate, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
            if (memory) return memory;
        }
    }
    return nullptr;
}

static bool known_call_site(unsigned char* site)
{
    if (memcmp(site, nativeGuards[0].bytes, 5) == 0) return true;
    if (site[0] != 0xe8) return false;
    int32_t relative; memcpy(&relative, site + 1, 4);
    const uintptr_t relay = (uintptr_t)site + 5 + relative;
    const unsigned char jump[6] = {0xff,0x25,0,0,0,0};
    uintptr_t destination;
    if (!readable(relay, 14) || memcmp((void*)relay, jump, 6) || !get(relay + 6, destination)) return false;
    HMODULE previous = GetModuleHandleW(L"mascot_goal_line_v12.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v11.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v10.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v9.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v8.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v7.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line_v6.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_goal_line.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_corner.dll");
    if (!previous) previous = GetModuleHandleW(L"mascot_single.dll");
    if (!previous) return false;
    const uintptr_t base = (uintptr_t)previous;
    IMAGE_DOS_HEADER dos; IMAGE_NT_HEADERS64 nt;
    return get(base, dos) && dos.e_magic == IMAGE_DOS_SIGNATURE && dos.e_lfanew > 0 && dos.e_lfanew < 4096 &&
        get(base + (uintptr_t)dos.e_lfanew, nt) && nt.Signature == IMAGE_NT_SIGNATURE &&
        destination >= base && destination < base + nt.OptionalHeader.SizeOfImage;
}

static bool install_call(unsigned char* site, int32_t relative)
{
    /* Briefly stop other game threads only while replacing the native CALL.
     * All handles and buffers are acquired beforehand; no heap/log/Lua work
     * is done while threads are stopped. Their prior suspend counts remain. */
    HANDLE handles[256]{}; size_t count = 0, suspended = 0;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return false;
    THREADENTRY32 entry{}; entry.dwSize = sizeof(entry);
    bool valid = true; DWORD failure = 0; const char* stage = "none";
    for (BOOL found = Thread32First(snapshot, &entry); found; found = Thread32Next(snapshot, &entry)) {
        if (entry.th32OwnerProcessID != GetCurrentProcessId() || entry.th32ThreadID == GetCurrentThreadId()) continue;
        if (count == 256) { valid = false; failure = ERROR_INSUFFICIENT_BUFFER; stage = "thread_capacity"; break; }
        HANDLE thread = OpenThread(THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION, FALSE, entry.th32ThreadID);
        if (!thread) {
            failure = GetLastError();
            /* A snapshot can contain a startup thread that has already exited. */
            if (failure == ERROR_INVALID_PARAMETER) continue;
            valid = false; stage = "open_thread"; break;
        }
        handles[count++] = thread;
    }
    CloseHandle(snapshot);
    unsigned char expected[5]; memcpy(expected, site, 5);
    DWORD old;
    if (!valid || !VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old)) {
        if (valid) { failure = GetLastError(); stage = "protect_call"; }
        for (size_t i = 0; i < count; ++i) CloseHandle(handles[i]);
        log_event("handoff_retry stage=%s error=%lu", stage, failure);
        return false;
    }
    for (; suspended < count; ++suspended) {
        if (SuspendThread(handles[suspended]) == (DWORD)-1) {
            failure = GetLastError(); stage = "suspend_thread"; valid = false; break;
        }
    }
    if (valid && memcmp(site, expected, 5) == 0) {
        memcpy(site + 1, &relative, 4);
        FlushInstructionCache(GetCurrentProcess(), site, 5);
    } else if (valid) { valid = false; failure = ERROR_RETRY; stage = "call_changed"; }
    while (suspended) ResumeThread(handles[--suspended]);
    DWORD ignored; VirtualProtect(site, 5, old, &ignored);
    for (size_t i = 0; i < count; ++i) CloseHandle(handles[i]);
    if (!valid) log_event("handoff_retry stage=%s error=%lu", stage, failure);
    return valid;
}

static DWORD WINAPI worker(void*)
{
    for (unsigned attempt = 0; attempt < 600; ++attempt) {
        if (!code_ready()) { Sleep(200); continue; }
        unsigned char* site = (unsigned char*)(image + 0x43ac0f1);
        if (!known_call_site(site)) { log_event("not_installed unknown_existing_hook"); return 5; }
        unsigned char* relay = (unsigned char*)allocate_near((uintptr_t)site);
        if (!relay) { log_event("not_installed near_relay_allocation_failed"); return 1; }
        /* FF25 RIP+0 jumps without changing any argument register. */
        const unsigned char jump[6] = {0xff, 0x25, 0, 0, 0, 0};
        memcpy(relay, jump, 6);
        const uintptr_t destination = (uintptr_t)&selection_hook;
        memcpy(relay + 6, &destination, 8);
        DWORD old;
        if (!VirtualProtect(relay, 4096, PAGE_EXECUTE_READ, &old)) {
            VirtualFree(relay, 0, MEM_RELEASE); return 2;
        }
        FlushInstructionCache(GetCurrentProcess(), relay, 14);
        originalSelect = (void (__fastcall*)(void*))(image + 0x43a8900);
        const int64_t distance = (int64_t)(uintptr_t)relay - (int64_t)((uintptr_t)site + 5);
        if (distance < INT32_MIN || distance > INT32_MAX || !code_ready() || !known_call_site(site)) {
            VirtualFree(relay, 0, MEM_RELEASE); return 3;
        }
        const int32_t relative = (int32_t)distance;
        if (!install_call(site, relative)) {
            VirtualFree(relay, 0, MEM_RELEASE);
            /* Startup thread churn is transient. Keep the guarded worker alive. */
            Sleep(200); continue;
        }
        HANDLE animationThread=CreateThread(nullptr,0,mascot_animation_worker,nullptr,0,nullptr);
        if (animationThread) CloseHandle(animationThread);
        else log_event("animation_score_watcher not_started thread_creation_failed");
        log_event("installed version=26 mode=contact_driven_locomotion hook=43ac0f1 crowd_hook=0 placement_types=1,18,0,22 resource_refresh=1 startup_retry=1 legacy_ballboys=normal missing_package_guard=1 celebration_engine_ms=15000 performance_revision=2 identity_poll_ms=250 lua_scan_per_frame=0 dynamic_club_packages=1 seated_pose_guard=1 approved_clips_only=1 turn_before_walk=1 yaw_private_palette=1 idle_blend_ms=450 ground_smoothing_ms=80 restart_session_worker=1 no_consecutive_position_repeat=1 stale_scene_restore=0 waypoint_dwell_seconds=30 waypoint_policy=local_least_recent waypoint_max_travel_cm=600 waypoint_interaction_seconds=15 goal_variants=6 support_variants=3 replay_clock=GameStateInterface replay_history_frames=8192 waypoint_applause_separate=1");
        return 0;
    }
    log_event("not_installed unsupported_or_conflicting_native_code"); return 4;
}

extern "C" __declspec(dllexport) unsigned int WINAPI Fifa16ModGetApiVersion() { return 1; }
extern "C" __declspec(dllexport) unsigned int WINAPI Fifa16ModMatchPresentationVersion() { return 1; }
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModSetPriorPlacement(const void* input)
{
    PriorPlacement value;
    if (started || !input || !get((uintptr_t)input,value) || value.magic != 0x4d534c37 || value.index >= 256) return FALSE;
    for (size_t i=0;i<3;++i) if (!isfinite(value.original[i]) || !isfinite(value.target[i]) ||
        fabsf(value.original[i]) > 20000 || fabsf(value.target[i]) > 20000) return FALSE;
    priorPlacement = value; priorPlacementPending = true; return TRUE;
}
extern "C" __declspec(dllexport) BOOL WINAPI Fifa16ModStart(const char* modsRoot)
{
    if (!modsRoot || !modsRoot[0]) return FALSE;
    if (InterlockedCompareExchange(&started, 1, 0)) return TRUE;
    char logsDirectory[MAX_PATH];
    _snprintf_s(logsDirectory, sizeof(logsDirectory), _TRUNCATE, "%s\\..\\logs", modsRoot);
    CreateDirectoryA(logsDirectory, nullptr);
    _snprintf_s(logPath, sizeof(logPath), _TRUNCATE, "%s\\mascot_goal_line.log", logsDirectory);
    if (!GetModuleFileNameW(nullptr,gameDirectory,MAX_PATH)) return FALSE;
    wchar_t* separator=wcsrchr(gameDirectory,L'\\');
    if (!separator) return FALSE;
    *separator=0;
    if (!presentationConfig.initialize()) return FALSE;
    log_event("match_presentation_config mascots=%u poll_ms=250",(unsigned int)presentationConfig.read(GetTickCount()).mascots);
    update_packages();
    image = (uintptr_t)GetModuleHandleW(nullptr);
    HMODULE pinned;
    if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
        (LPCSTR)&started, &pinned)) return FALSE;
    HANDLE thread = CreateThread(nullptr, 0, worker, nullptr, 0, nullptr);
    if (!thread) return FALSE;
    CloseHandle(thread);
    HANDLE guardThread=CreateThread(nullptr,0,package_worker,nullptr,0,nullptr);
    if (guardThread) CloseHandle(guardThread);
    return TRUE;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}
