"""Bound generated visual files only after FIFA and its readers have exited.

No saves, SQL, receipts, calendar journals, source assets or recovery transactions
belong to this policy. Native paths stay immutable for the lifetime of FIFA.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import re
import stat
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


def plan(root,check=lambda:None):
    """Return exact allowlisted files. Never infer deletability from 'runtime'."""
    root = Path(root).absolute()
    if not game_root(root): return {}
    candidates = {};metadata={}
    def units(parent,pattern):return _units(root,parent,pattern,metadata,check)
    def walk(folder):return files(root,folder,metadata,check)
    def add(group, paths):
        for p in paths:
            if not FORBIDDEN.search(p.name): candidates[p] = group
    market = root/MARKET
    # Models/labels bound to a particular session are rebuilt from persistent SQL.
    for name in ('packages', 'render_jobs'):
        add('market_'+name, (p for p in walk(market/name)
                            if (name == 'render_jobs' and p.suffix in GENERATED_EXTENSIONS)
                            or (name == 'packages' and re.fullmatch(r'managers_[0-9a-f]{64}(?:\.building)?\.big', p.name))))
    add('market_artwork', _over_budget(units(market/'artwork_cache',
        re.compile(r'art_[0-9a-f]{64}\.zip$')), 256*MIB, 1))
    # A template and its metadata are one eviction unit.
    templates = []
    for modified, size, members in units(market/'native_templates', re.compile(r'template_[0-9a-f]{64}\.big$')):
        side = members[0].with_suffix('.json')
        if side.is_file() and safe(root, side):
            members = members+[side]; size += side.stat().st_size
        templates.append((modified, size, members))
    add('market_templates', _over_budget(templates, 64*MIB, 1))
    add('market_textures', _over_budget(units(market/'texture_cache',
        re.compile(r'[0-9a-f]{64}\.dds$')), 128*MIB))
    cache = root/'ModCarrerMode/cache/club_browser'
    prepared = []
    for name in ('xi/prepared', 'player/prepared', 'coach', 'coach_exports', 'mascot'):
        prepared.extend(units(cache/name, HEX))
    add('prepared_models', _over_budget(prepared, 768*MIB))
    add('model_materials', _over_budget(units(cache/'xi/materials',
        re.compile(r'[0-9a-f]{64}\.rx3$')), 256*MIB))
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
    add('frontend_stadiums', _over_budget(stadiums, 1536*MIB, 2))
    add('match_stadiums', [p for _,_,members in units(
        root/'data/sceneassets/server16_match', re.compile(r'[0-9a-f]{32}$')) for p in members if p.suffix=='.rx3'])
    for name in ('goalpost_texture_previews','kitmix_previews','kitmix_imports'):
        add('import_previews', walk(root/'runtime'/name))
    for _,_,members in units(root/'runtime', re.compile(r'server16_stad_[a-z0-9_]+$')):
        add('stadium_extractions', members)
    # Deliberately NOT server16_stadium_apply_*/previous, SQL or calendar receipts.
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
                # Conservatively block helpers even if their root is not visible.
                return True
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


def maintain(root, *, guard=None, dry_run=False, quarantine=True, record=True):
    root=Path(root).absolute();result=Result();cutoff=time.time_ns()
    if not game_root(root): return result
    def check():
        if (guard() if guard is not None else busy(root)): raise Busy('FIFA, helper or launch is active')
    removed=[]
    try:
        check()
        with RootLock(root):
            check();candidates=plan(root,check)
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
        with self.lock:self.roots.setdefault(root,dict(pending=True,was_busy=False))
        self.wake.set()
    def request(self,root,callback=None):
        self.bind(root)
        with self.lock:
            if Path(root).absolute() in self.roots:
                self.roots[Path(root).absolute()]['pending']=True
                if callback:self.callbacks[Path(root).absolute()]=callback
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
                    ready=(not active and state['pending'] and time.monotonic()>=self.launch_hold and not self.stop.is_set())
                    if ready:self.running=True
                if not ready:continue
                last_check=[0.,False]
                def guard():
                    if self.stop.is_set() or self.occupied() or time.monotonic()<self.launch_hold:return True
                    if time.monotonic()-last_check[0]>.1:last_check[:]=[time.monotonic(),self.checker(root)]
                    return last_check[1]
                try:
                    report=maintain(root,guard=guard)
                    if report.files or report.moved_bytes or report.failed:
                        self.log(f'Visual cache maintenance: {report.files} paths; {report.released_bytes/MIB:.1f} MiB released; {report.moved_bytes/MIB:.1f} MiB moved; {len(report.failed)} skipped errors')
                    with self.lock:
                        state['pending']=report.deferred
                        callback=self.callbacks.pop(root,None) if not report.deferred else None
                    if callback:callback(report)
                except Exception as error:
                    with self.lock:state['pending']=False
                    self.log('Visual cache maintenance deferred after error',error)
                finally:
                    with self.lock:self.running=False
    def close(self):
        self.stop.set();self.wake.set();self.thread.join(timeout=1.)
