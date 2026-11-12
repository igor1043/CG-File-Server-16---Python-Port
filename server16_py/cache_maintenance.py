"""Bound generated visual files only after FIFA and its readers have exited.

Saves, SQL, receipts, source assets and recovery transactions remain outside
this policy. Only closed, unpinned calendar scopes join the visual sweep.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import stat
import sys
import threading
import time

import psutil

MIB = 1024 * 1024
ROOM = 'data/sceneassets/server16_dressing_room_v3/'
MARKET = 'ModCarrerMode/runtime/manager_market/'
POLICY = Path(__file__).with_name('assets') / 'cache_protected_assets.json'
FORBIDDEN = re.compile(r'\.(?:sqlite3?|db)(?:-wal|-shm|-journal)?$|^(?:DATA|INDEX)$', re.I)
SHARED = re.compile(r'(?:coach_[a-z_]+_\d+_[0-9a-f]{18}_r76|medical_[a-z_]+_\d+_[0-9a-f]{18}_r77|next_match_\d+_[0-9a-f]{14}_r64|live_name_\d+_\d+_[0-9a-f]{10}|locker_plate_\d+_\d+_[0-9a-f]{12}_r56|theme_\d+_[0-9a-f]{12}_r48|neutral_[0-9a-f]{12}_r62|interior_[a-z_]+_\d+_[0-9a-f]{16}_r72)\.rx3$')
DERIVED = re.compile(r'(?:board_atlas|board_image|board|fascia|image_fascia|fascia_fullres|feature_wall|custom|joinery_cabinet|acoustic_ceiling|scenery_atlas_[01]|floor|wood|niche|accent|joinery_[a-z_]+|ceiling_details_[a-z_]+|table_wood|image_panels|lettering|furniture_[a-z_]+|cushion|metal|linen|light)_[0-9a-f]{14}\.rx3$')
HEX = re.compile(r'[0-9a-f]{24,64}$')
GENERATED_EXTENSIONS = frozenset(('.rx3', '.ff3d', '.bin', '.json', '.tsv', '.log', '.new', '.tmp'))
LIMITS_MIB = dict(prepared_models=384,model_materials=128,market_artwork=224,
                 market_templates=48,market_textures=64,frontend_stadiums=1024,
                 trophy_appearance=32,trophy_thumbnails=16,preview_art=16,
                 extracted_assets=64,stadium_previews=16)


class Busy(RuntimeError):
    pass


def safe(root, path):
    """Validate existing ancestors too; allow missing owned destinations."""
    root,path=Path(root).absolute(),Path(path).absolute()
    if root==Path(root.anchor) or not path.is_relative_to(root):return False
    try:
        current=path
        while True:
            try:
                s=current.lstat()
                if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:return False
            except FileNotFoundError:pass
            if current==root:break
            current=current.parent
        return path.resolve().is_relative_to(root.resolve())
    except (OSError,ValueError,RuntimeError):return False


@dataclass
class Result:
    files: int = 0
    logical_bytes: int = 0
    released_bytes: int = 0
    moved_bytes: int = 0
    skipped: int = 0
    deferred: bool = False
    failed: list[str] = field(default_factory=list)
    groups: dict[str, int] = field(default_factory=dict)


def game_root(root):
    root = Path(root).absolute()
    return (safe(root, root) and safe(root, root/'ModCarrerMode/data') and
            safe(root, root/'data/sceneassets') and (root/'ModCarrerMode/data').is_dir()
            and (root/'data/sceneassets').is_dir())


def files(root, folder, metadata=None, check=lambda:None):
    if not safe(root, folder) or not folder.is_dir():
        return []
    found = []
    for parent, dirs, names in os.walk(folder, followlinks=False):
        check()
        base = Path(parent)
        if not safe(root,base):dirs[:]=[];continue
        kept=[]
        for n in dirs:
            try:
                s=(base/n).lstat()
                if not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400:kept.append(n)
            except OSError:pass
        dirs[:]=kept
        for name in names:
            path = base/name
            if FORBIDDEN.search(name):continue
            try:
                s=path.lstat()
                if stat.S_ISREG(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400:
                    found.append(path)
                    if metadata is not None:metadata[path]=s
            except OSError:pass
    return found


def policy_assets():
    try:
        data = json.loads(POLICY.read_bytes())
        paths = data['room_assets']
        if data.get('schema') != 1 or not 50 <= len(paths) <= 4096:
            return None
        if any(not p.startswith(ROOM) or '..' in PurePosixPath(p).parts or '\\' in p for p in paths):
            return None
        return set(paths)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def room_protected(root):
    protected = policy_assets()
    if protected is None: return None  # Missing policy must never expose shipped art.
    descriptor = root/'ModCarrerMode/runtime/club_environment/room/runtime/native_components_v2.txt'
    manifest = root/(ROOM+'manifest.json')
    try:
        if not safe(root, descriptor) or not safe(root, manifest): return None
        if descriptor.stat().st_size > 2*MIB or manifest.stat().st_size > 2*MIB: return None
        text = descriptor.read_text(encoding='utf8')
        if not text.startswith('S16NATIVE '): return None
        protected.update(re.findall(r'"(data/[^"\r\n]+)"', text))
        model_files = json.loads(manifest.read_bytes())['model_files']
        for name in model_files.values():
            if PurePosixPath(name).name != name or not name.endswith('.rx3'): return None
            protected.add(ROOM+name)
        return protected
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _units(root, parent, pattern, metadata=None, check=lambda:None):
    if not safe(root, parent) or not parent.is_dir(): return []
    result = []
    for path in parent.iterdir():
        check()
        if not pattern.fullmatch(path.name):continue
        try:
            s=path.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:continue
            if metadata is not None:metadata[path]=s
        except OSError:continue
        members = files(root, path,metadata,check) if stat.S_ISDIR(s.st_mode) else [path]
        if not members: continue
        try:
            stats=[metadata[p] if metadata is not None and p in metadata else p.stat() for p in members]
            result.append((max(s.st_mtime_ns for s in stats),sum(s.st_size for s in stats),members))
        except OSError: continue
    return result


def _over_budget(units, budget, max_units=None):
    used = 0; kept = 0; discard = []
    for modified, size, members in sorted(units, key=lambda u:u[0], reverse=True):
        if used+size <= budget and (max_units is None or kept < max_units):
            used += size; kept += 1
        else: discard.extend(members)
    return discard


def identical(root,left,right,check):
    if not safe(root,left) or not safe(root,right) or not right.is_file():return False
    try:
        if left.stat().st_size!=right.stat().st_size:return False
        with left.open('rb') as a,right.open('rb') as b:
            while True:
                check();chunk=a.read(MIB)
                if chunk!=b.read(MIB):return False
                if not chunk:return True
    except OSError:return False


def plan(root,check=lambda:None,*,journals_only=False,purge=False):
    """Return exact allowlisted files. Never infer deletability from 'runtime'."""
    root = Path(root).absolute()
    if not game_root(root): return {}
    candidates = {};metadata={}
    def units(parent,pattern):return _units(root,parent,pattern,metadata,check)
    def walk(folder):return files(root,folder,metadata,check)
    def budget(name):return 0 if purge else LIMITS_MIB[name]*MIB
    def add(group, paths):
        for p in paths:
            if not FORBIDDEN.search(p.name): candidates[p] = group
    from .session_storage import finished_calendar_files
    add('finished_calendar', finished_calendar_files(root,check))
    if journals_only:
        return candidates
    market = root/MARKET
    # Models/labels bound to a particular session are rebuilt from persistent SQL.
    for name in ('packages', 'render_jobs'):
        add('market_'+name, (p for p in walk(market/name)
                            if (name == 'render_jobs' and p.suffix in GENERATED_EXTENSIONS)
                            or (name == 'packages' and re.fullmatch(r'managers_[0-9a-f]{64}(?:\.building)?\.big', p.name))))
    add('market_artwork', _over_budget(units(market/'artwork_cache',
        re.compile(r'art_[0-9a-f]{64}\.zip$')), budget('market_artwork'), 1))
    # A template and its metadata are one eviction unit.
    templates = []
    for modified, size, members in units(market/'native_templates', re.compile(r'template_[0-9a-f]{64}\.big$')):
        side = members[0].with_suffix('.json')
        if side.is_file() and safe(root, side):
            members = members+[side]; size += side.stat().st_size
        templates.append((modified, size, members))
    add('market_templates', _over_budget(templates, budget('market_templates'), 1))
    add('market_textures', _over_budget(units(market/'texture_cache',
        re.compile(r'[0-9a-f]{64}\.dds$')), budget('market_textures')))
    cache = root/'ModCarrerMode/cache/club_browser'
    prepared = []
    for name in ('xi/prepared', 'player/prepared', 'coach', 'coach_exports', 'mascot'):
        prepared.extend(units(cache/name, HEX))
    add('prepared_models', _over_budget(prepared, budget('prepared_models')))
    add('model_materials', _over_budget(units(cache/'xi/materials',
        re.compile(r'[0-9a-f]{64}\.rx3$')), budget('model_materials')))
    add('published_models', [p for _,_,members in units(
        root/'data/sceneassets/server16_club_xi', re.compile(r'\d+$')) for p in members
        if p.suffix in GENERATED_EXTENSIONS])
    # Only evict frontend copies with an existing original library package.
    stadiums = []
    for unit in units(root/'data/sceneassets/server16_frontend', re.compile(r'[0-9a-f]{24}$')):
        try:
            folder = unit[2][0].parent
            # ready.json is at the immutable stadium directory's root.
            while folder.parent != root/'data/sceneassets/server16_frontend': folder = folder.parent
            record = folder/'ready.json'
            if not safe(root, record) or record.stat().st_size > MIB: continue
            source = Path(json.loads(record.read_bytes())['source'])
            if source.exists(): stadiums.append(unit)
        except (OSError, ValueError, KeyError): continue
    add('frontend_stadiums', _over_budget(stadiums, budget('frontend_stadiums'), 1))
    add('match_stadiums', [p for _,_,members in units(
        root/'data/sceneassets/server16_match', re.compile(r'[0-9a-f]{32}$')) for p in members if p.suffix=='.rx3'])
    for name in ('goalpost_texture_previews','kitmix_previews','kitmix_imports'):
        add('import_previews', walk(root/'runtime'/name))
    for _,_,members in units(root/'runtime', re.compile(r'server16_stad_[a-z0-9_]+$')):
        add('stadium_extractions', members)
    # Per-process scene publications are disposable only after the global
    # FIFA/helper guard releases the installation. SQL and receipts stay out.
    for folder in ('ModCarrerMode/runtime/club_browser','data/sceneassets/server16_trophy_room'):
        add('ended_scene_sessions',[p for _,_,members in units(root/folder,re.compile(r'[1-9]\d*$'))
                                    for p in members if p.suffix.lower() in GENERATED_EXTENSIONS|{'.png','.dds','.big','.txt','.pixels'}])
    trophy=root/'data/sceneassets/server16_trophy_room'
    add('trophy_appearance',_over_budget(units(trophy/'appearance',re.compile(r'[0-9a-f]{16}$')),budget('trophy_appearance')))
    thumbnails=[(metadata[p].st_mtime_ns,metadata[p].st_size,[p]) for p in walk(trophy/'thumbnails')
                if re.fullmatch(r't\d+_[0-9a-f]{12}\.png',p.name)]
    add('trophy_thumbnails',_over_budget(thumbnails,budget('trophy_thumbnails')))
    art=root/'ModCarrerMode/runtime/club_environment/preview/runtime/art_cache'
    previews=[(metadata[p].st_mtime_ns,metadata[p].st_size,[p]) for p in walk(art)
              if p.suffix.lower() in ('.png','.dds','.rx3','.big','.json')]
    add('preview_art',_over_budget(previews,budget('preview_art')))
    extracted=root/'ModCarrerMode/runtime/club_environment/asset_cache'
    add('extracted_assets',_over_budget(units(extracted,re.compile(r'[0-9a-f]{20}$')),budget('extracted_assets')))
    selector=root/'runtime/stadium_selector'
    previews=[(metadata[p].st_mtime_ns,metadata[p].st_size,[p]) for p in walk(selector)
              if re.fullmatch(r'[a-z_]+_[01]\.png',p.name)]
    add('stadium_previews',_over_budget(previews,budget('stadium_previews')))
    # _prepare_runtime formerly copied the editable source artwork into runtime.
    # All readers use the canonical data paths; never delete those source files.
    for relative,source in [('current_dressing_room','current_dressing_room'),('room/clubs','room/clubs')]:
        canonical=root/'ModCarrerMode/data/club_environment'/source
        if safe(root,canonical) and canonical.is_dir():
            mirror=root/'ModCarrerMode/runtime/club_environment'/relative
            add('redundant_art_mirrors',[p for p in walk(mirror)
                if p.suffix.lower() in ('.png','.dds','.rx3','.json') and identical(root,p,canonical/p.relative_to(mirror),check)])
    # Deliberately exclude server16_stadium_apply_*/previous, SQL and save receipts.
    protected = room_protected(root)
    if protected is not None:
        for p in walk(root/ROOM):
            rel = p.relative_to(root).as_posix()
            if rel in protected: continue
            tail = rel[len(ROOM):]
            generated = SHARED.fullmatch(tail[7:]) if tail.startswith('shared/') else DERIVED.fullmatch(tail)
            if generated: add('room_old_generated', [p])
    return candidates


def busy(root):
    """FIFA anywhere, or an owning visual helper, prevents disk eviction."""
    root = Path(root).absolute()
    try:
        for process in psutil.process_iter(['pid','name','cmdline','exe']):
            if process.pid == os.getpid(): continue
            name = (process.info['name'] or '').casefold()
            if name in ('fifa16.exe','fifa 16.exe'): return True
            if name not in ('server16python.exe','server16.exe','python.exe','pythonw.exe','python3.exe'): continue
            args = ' '.join(process.info['cmdline'] or []).casefold()
            if any(token in args for token in ('--club-environment','--club-browser-worker')):
                argv=process.info['cmdline'] or []
                # A crashed FIFA can leave an old worker behind indefinitely.
                # Only a worker's live FIFA owner can pin the visual cache.
                try:
                    owner=psutil.Process(int(argv[argv.index('--pid')+1]))
                    if owner.name().casefold() in ('fifa16.exe','fifa 16.exe'):return True
                except (ValueError,IndexError):return True
                except (psutil.NoSuchProcess,psutil.ZombieProcess):continue
    except (psutil.AccessDenied, OSError): return True
    return False


class RootLock:
    def __init__(self, root): self.root=root; self.stream=None
    def __enter__(self):
        path=self.root/'runtime/cache_maintenance/cleanup.lock'
        if not safe(self.root, path.parent.parent): raise Busy('Unsafe maintenance directory')
        path.parent.mkdir(parents=True,exist_ok=True)
        if not safe(self.root,path): raise Busy('Unsafe maintenance lock')
        self.stream=path.open('a+b');self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                if not path.stat().st_size:self.stream.write(b'0');self.stream.flush();self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close();self.stream=None;raise Busy('Another cache maintenance is running')
        return self
    def __exit__(self,*unused):
        if self.stream is not None:
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
            self.stream.close()


def maintain(root, *, guard=None, dry_run=False, quarantine=False, record=True, journals_only=False,purge=False):
    root=Path(root).absolute();result=Result();cutoff=time.time_ns()
    if not game_root(root): return result
    checked=[0.,False]
    def check():
        if guard is not None:active=guard()
        else:
            # Do not enumerate every Windows process once per cached file.
            # The same 100 ms guard is used by the background UI service.
            now=time.monotonic()
            if now-checked[0]>=.1:checked[:]=[now,busy(root)]
            active=checked[1]
        if active:raise Busy('FIFA, helper or launch is active')
    removed=[]
    try:
        check()
        with RootLock(root):
            check();candidates=plan(root,check,journals_only=journals_only,purge=purge)
            # Clear only stale match routes, before deleting their resources.
            if not dry_run and any(g=='match_stadiums' for g in candidates.values()):
                from .stadium_match_assets import clear_match_routes
                for slot in (176,261):
                    route=root/f'data/fifarna/lua/assets/server16_match_{slot}.lua'
                    if not safe(root,route) or not safe(root,route.with_suffix('.lua.tmp')):
                        raise Busy('Unsafe match route')
                check();clear_match_routes(root)
            parents=set()
            for path,group in candidates.items():
                check()
                if not safe(root,path): result.skipped+=1;continue
                try:
                    s=path.stat()
                    if s.st_mtime_ns>=cutoff:result.skipped+=1;continue
                    relative=path.relative_to(root).as_posix()
                    if dry_run:
                        result.files+=1;result.logical_bytes+=s.st_size;result.groups[group]=result.groups.get(group,0)+s.st_size
                        continue
                    try:
                        path.unlink()
                        result.files+=1;result.logical_bytes+=s.st_size
                        # Count the content once, when its last hardlink disappears.
                        if s.st_nlink==1:result.released_bytes+=s.st_size
                        result.groups[group]=result.groups.get(group,0)+s.st_size
                        removed.append(relative);parents.add(path.parent)
                    except PermissionError:
                        if not quarantine:raise
                        base=root.parent/('FIFA16-cache-descartavel-'+root.name)
                        target=base/relative
                        if not safe(base,target) or target.resolve().is_relative_to(root.resolve()):raise
                        target.parent.mkdir(parents=True,exist_ok=True)
                        check();os.replace(path,target);result.moved_bytes+=s.st_size;removed.append(relative+' -> '+str(target))
                except OSError as error:result.failed.append(str(path)+': '+str(error))
            if not dry_run:
                for directory in sorted(parents,key=lambda p:len(p.parts),reverse=True):
                    while directory!=root and safe(root,directory):
                        check()
                        try:directory.rmdir()
                        except OSError:break
                        directory=directory.parent
    except Busy:
        result.deferred=True
    if record and not dry_run:
        directory=root/'runtime/cache_maintenance'
        if safe(root,directory):
            directory.mkdir(exist_ok=True)
            payload=dict(schema=1,at=time.time(),**asdict(result),removed=removed)
            tmp=directory/('last-'+str(os.getpid())+'.new')
            tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,directory/'last.json')
    return result


class SessionCaches:
    """Startup + end-of-game housekeeping; never runs a sweep on the Tk thread."""
    def __init__(self, log, *, occupied=lambda:False, interval=2., checker=busy):
        self.log=log;self.occupied=occupied;self.interval=interval;self.checker=checker
        self.roots={};self.lock=threading.Lock();self.wake=threading.Event();self.stop=threading.Event()
        self.running=False;self.launch_hold=0.;self.callbacks={}
        self.thread=threading.Thread(target=self._run,name='Server16VisualCacheMaintenance',daemon=True);self.thread.start()
    def bind(self,root):
        root=Path(root).absolute()
        if not game_root(root): return
        queued=False
        pending=root/'runtime/cache_maintenance/pending.json'
        try:
            if safe(root,pending):
                value=json.loads(pending.read_bytes());queued=isinstance(value,dict) and value.get('purge') is True
        except (OSError,ValueError,TypeError):pass
        with self.lock:self.roots.setdefault(root,dict(pending=True,was_busy=False,purge=queued,retry_at=0.,revision=0))
        self.wake.set()
    def request(self,root,callback=None,*,purge=False):
        root=Path(root).absolute()
        self.bind(root)
        with self.lock:
            if Path(root).absolute() in self.roots:
                self.roots[Path(root).absolute()]['pending']=True
                self.roots[root]['revision']+=1
                self.roots[Path(root).absolute()]['purge']|=purge
                if callback:self.callbacks[Path(root).absolute()]=callback
                if purge:
                    pending=Path(root)/'runtime/cache_maintenance/pending.json'
                    if safe(Path(root),pending):
                        pending.parent.mkdir(parents=True,exist_ok=True)
                        tmp=pending.with_suffix('.new')
                        if not safe(root,tmp):raise Busy('Unsafe pending cleanup file')
                        tmp.write_text('{"schema":1,"purge":true}',encoding='utf8');os.replace(tmp,pending)
        self.wake.set()
    def reserve_launch(self):
        with self.lock:
            self.launch_hold=time.monotonic()+20
            return not self.running
    def _run(self):
        while not self.stop.is_set():
            self.wake.wait(self.interval);self.wake.clear()
            with self.lock:roots=list(self.roots.items())
            for root,state in roots:
                active=self.checker(root) or self.occupied()
                with self.lock:
                    if state['was_busy'] and not active:state['pending']=True
                    state['was_busy']=active
                    ready=(not active and state['pending'] and time.monotonic()>=max(self.launch_hold,state['retry_at']) and not self.stop.is_set())
                    if ready:self.running=True;revision=state['revision'];purge=state['purge']
                if not ready:continue
                last_check=[0.,False]
                def guard():
                    if self.stop.is_set() or self.occupied() or time.monotonic()<self.launch_hold:return True
                    if time.monotonic()-last_check[0]>.1:last_check[:]=[time.monotonic(),self.checker(root)]
                    return last_check[1]
                try:
                    report=maintain(root,guard=guard,purge=purge)
                    if not report.deferred and getattr(sys,'frozen',False):
                        from .session_storage import sweep_extractions
                        extracted=sweep_extractions()
                        if extracted.released_bytes:
                            self.log(f'Server16 temporary files: {extracted.released_bytes/MIB:.1f} MiB released')
                    if report.files or report.moved_bytes or report.failed:
                        self.log(f'Session cache maintenance: {report.files} paths; {report.released_bytes/MIB:.1f} MiB released; {report.moved_bytes/MIB:.1f} MiB moved; {len(report.failed)} skipped errors')
                    with self.lock:
                        changed=state['revision']!=revision
                        state['pending']=changed or report.deferred or bool(report.failed)
                        state['retry_at']=time.monotonic()+30 if report.failed else 0.
                        if not changed and not report.deferred and not report.failed:
                            state['purge']=False
                            pending=root/'runtime/cache_maintenance/pending.json'
                            if safe(root,pending):pending.unlink(missing_ok=True)
                        callback=self.callbacks.pop(root,None) if not changed and not report.deferred else None
                    if callback:callback(report)
                except Exception as error:
                    with self.lock:state['pending']=True;state['retry_at']=time.monotonic()+30
                    self.log('Visual cache maintenance deferred after error',error)
                finally:
                    with self.lock:self.running=False
    def close(self):
        self.stop.set();self.wake.set();self.thread.join(timeout=1.)
