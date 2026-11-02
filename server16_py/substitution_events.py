"""Read-only match roster observations and one-shot substitution events.

No address scans, native calls, hooks, save edits or changes to match rules.
The registry and all objects are resolved anew for each match.
"""
from dataclasses import dataclass
import struct
import time
from .match_state import outside_match_page,pause_page,read_native_match_scene
from .offsets import Offsets


@dataclass(frozen=True)
class Player:
    id:int
    club:int
    side:int
    role:int


@dataclass(frozen=True)
class Snapshot:
    identity:tuple
    clock:int
    phase:int
    replay:bool
    page:str
    clubs:tuple
    players:tuple
    presentation:str=''

    @property
    def substitution_scene(self):
        return self.presentation.startswith('package_sub_')

    @property
    def paused(self):
        # StadiumPan is shared by pause and an interrupted cinematic. Its
        # label alone cannot override a validated substitution or live phase.
        stadium_pan=self.page.lower().rsplit('/',1)[-1]=='stadiumpan'
        return pause_page(self.page) and not (stadium_pan and (self.substitution_scene or self.phase==15))

    @property
    def playable(self):
        return (self.phase in (4,6,14,15) or self.substitution_scene) and not self.replay and not self.paused and not outside_match_page(self.page)


@dataclass(frozen=True)
class Substitution:
    identity:tuple
    club:int
    side:int
    incoming:tuple
    outgoing:tuple
    clock:int


class MatchReader:
    def __init__(self,memory):self.memory=memory;self.offsets=Offsets();self.presentation_reader=NativePresentationReader(memory)

    def read(self):
        m=self.memory;b=m.base_module;u=m.read_int64;i=m.read_uint32
        def owned(at,rva):return at>=0x10000 and u(at)==b+rva
        try:
            scene=read_native_match_scene(m)
            if scene is None:return None
            manager=u(b+0x3517420)
            if not owned(manager,0x2226730):return None
            world=u(manager+8)
            if not owned(world,0x2225d90):return None
            game=u(world+0x10)
            if not owned(game,0x2309370):return None
            registry=u(game+0x20)
            if registry<0x10000:return None
            def collection(slot,minimum,maximum):
                at=registry+8+slot*32;kind=i(at);count=i(at+16);pairs=u(at+24)
                if kind!=slot or not minimum<=count<=maximum or pairs<0x10000:raise ValueError('Invalid match registry')
                raw=m.read_process_memory(pairs,count*16)
                return pairs,count,tuple(struct.unpack_from('<Q',raw,j*16+8)[0] for j in range(count))
            team_pairs,_,teams=collection(15,2,2);clubs=[0,0];team_by_side=[0,0]
            for team in teams:
                if not owned(team,0x22fe9f0) or u(team+0x30)!=registry:return None
                side=i(team+0x58);stats=u(team+0x50)
                if side>1 or team_by_side[side] or stats<0x10000:return None
                club=i(stats+0x80)
                if not 0<club<1000000:return None
                clubs[side]=club;team_by_side[side]=team
            pairs,count,objects=collection(12,22,128);players=[];seen=set()
            for obj in objects:
                if not owned(obj,0x22fe740) or u(obj+0x38)!=registry:return None
                info=u(obj+0xa0)
                if info<0x10000:return None
                _,ident,club,side,role=struct.unpack('<5i',m.read_process_memory(info,20))
                if side not in (0,1) or club!=clubs[side] or not 0<ident<10000000 or not 0<=role<=32 or (side,ident) in seen or u(obj+0x88)!=team_by_side[side]:return None
                seen.add((side,ident));players.append(Player(ident,club,side,role))
            page=m.get_string(self.offsets.ORIPGBASE,self.offsets.PG1,128)
            clock=m.get_int(self.offsets.GAMESTATSBASE,self.offsets.GAMERANTIME)
            if clock>1000000:return None
            # Avoid mixing a roster from one match with a new scene/registry.
            if (u(b+0x3517420)!=manager or u(manager+8)!=world or u(world+0x10)!=game or u(game+0x20)!=registry or read_native_match_scene(m)!=scene or u(registry+8+12*32+24)!=pairs or i(registry+8+12*32+16)!=count):return None
            identity=(manager,world,game,registry,team_pairs,scene.source,*team_by_side,*clubs)
            return Snapshot(identity,clock,scene.phase,scene.replay,page,tuple(clubs),tuple(players),self.presentation_reader.read())
        except (OSError,ValueError,struct.error,RuntimeError):return None


class NativePresentationReader:
    """Read the selected MUSE graph; never invoke, queue or modify a graph.

    ExtraScenes publishes the camera engine even when its optional cuts are
    disabled. If unavailable, roster detection still resumes in live play.
    Layout checks mirror extra_scenes/native_muse.h, including queue ownership.
    """
    def __init__(self,memory):self.memory=memory;self.bc=0;self.engine_export=0;self.retry=0
    def read(self):
        m=self.memory;u=m.read_int64;i=m.read_uint32
        try:
            if not self.engine_export:
                if time.monotonic()<self.retry:return ''
                self.retry=time.monotonic()+5
                bc=m._get_base_address('BCEnginezf.dll');extra=m._get_base_address('extra_scenes.dll')
                if not bc or not extra:return ''
                from .career_context import _export
                pe=i(extra+0x3c)
                if not 0<pe<4096:return ''
                size=i(extra+pe+24+56)
                if not 4096<size<0x10000000:return ''
                published=_export(m,extra,size,b'ExtraScenesEngine')
                if not published:return ''
                self.bc=bc;self.engine_export=published
            bc=self.bc;engine=u(self.engine_export);scene=u(engine+0x68);services=u(scene+0x10)
            if u(services)!=bc+0x1165b0:return ''
            adapter=u(services+0x50)
            if u(adapter)!=bc+0x1166d0:return ''
            impl=u(adapter+0x58)
            if u(impl)!=bc+0x12c890:return ''
            manager=u(impl+0xa0)
            if u(manager)!=bc+0x12c300:return ''
            processor=u(manager+0xb0);selected=u(processor+0x60);first=u(processor+0x28);end=u(processor+0x30)
            if not selected or first<0x10000 or not 0<end-first<=4096 or (end-first)%8:return ''
            tasks=struct.unpack('<'+'Q'*((end-first)//8),m.read_process_memory(first,end-first))
            if selected not in tasks:return ''
            graph=u(selected+8)
            if u(graph)!=bc+0x12eff0:return ''
            raw=m.read_process_memory(graph+0x18,95)
            if b'\0' not in raw:return ''
            name=raw.split(b'\0',1)[0].decode('ascii')
            if (u(self.engine_export)!=engine or u(engine+0x68)!=scene or u(scene+0x10)!=services
                    or u(services+0x50)!=adapter or u(adapter+0x58)!=impl or u(impl+0xa0)!=manager
                    or u(manager+0xb0)!=processor or u(processor+0x60)!=selected
                    or u(processor+0x28)!=first or u(processor+0x30)!=end or u(selected+8)!=graph):return ''
            return name
        except (OSError,ValueError,struct.error,RuntimeError,UnicodeError):
            self.engine_export=0
            return ''


class SubstitutionTracker:
    """Compare committed player identities, ignoring mere formation changes."""
    def __init__(self,settle_samples=2):self.settle_samples=max(2,settle_samples);self.reset()
    def reset(self):self.identity=None;self.clock=-1;self.roster=None;self.candidate=None;self.hits=0;self.seen=set();self.participated=[set(),set()]
    @staticmethod
    def active_rosters(snapshot):return tuple(tuple(sorted(p.id for p in snapshot.players if p.side==side and p.role<28)) for side in (0,1))
    def observe(self,snapshot):
        if snapshot is None:return []
        if outside_match_page(snapshot.page):self.reset();return []
        roster=self.active_rosters(snapshot)
        if not all(1<=len(team)<=11 for team in roster):return []
        if snapshot.identity!=self.identity or (not snapshot.replay and snapshot.clock+5<self.clock):
            self.reset();self.identity=snapshot.identity;self.clock=snapshot.clock;self.roster=roster;self.participated=[set(v) for v in roster];return []
        if snapshot.replay:return []
        self.clock=max(self.clock,snapshot.clock)
        if not snapshot.playable:self.candidate=None;self.hits=0;return []
        if roster==self.roster:self.candidate=None;self.hits=0;return []
        if roster!=self.candidate:self.candidate=roster;self.hits=1;return []
        self.hits+=1
        if self.hits<self.settle_samples:return []
        events=[]
        for side in (0,1):
            incoming=tuple(sorted(set(roster[side])-self.participated[side]));outgoing=tuple(sorted(set(self.roster[side])-set(roster[side])))
            key=(side,incoming,outgoing)
            if incoming and key not in self.seen:
                self.seen.add(key);events.append(Substitution(snapshot.identity,snapshot.clubs[side],side,incoming,outgoing,snapshot.clock))
            self.participated[side].update(roster[side])
        self.roster=roster;self.candidate=None;self.hits=0;return events
