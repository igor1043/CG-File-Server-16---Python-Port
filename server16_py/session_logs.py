"""Bound diagnostic output without touching saves, SQL, settings or assets.

Only log suffixes inside owned runtime locations and timestamped diagnostic
bundles are managed. Directory links, file links and developer trees are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import queue
import re
import stat
import threading
import time
import json
import tempfile
import zipfile
from datetime import datetime

FILE_LIMIT = 2 * 1024 * 1024
TAIL_BYTES = 256 * 1024
TOTAL_LIMIT = 32 * 1024 * 1024
DIAGNOSTICS_LIMIT = 32 * 1024 * 1024
HISTORY_LIMIT = 4 * 1024 * 1024
HISTORY_COUNT = 2
HISTORY_TAIL = 64 * 1024
CAPTURE_LIMIT = 16 * 1024 * 1024
INTERVAL_SECONDS = 10
UI_LINES = 2000
LOG_NAME = re.compile(r'.*\.log(?:[._-](?:\d+|old|bak|previous))?$', re.I)
SESSION_NAME = re.compile(r'\d{8}_\d{6}_\d{6}_pid\d+(?:\.zip)?$')
SKIP_DIRS = frozenset(('.git', 'source', 'vendor', 'node_modules', 'build', 'dist',
                       'backups', 'local-review', 'code-release', 'test_dependencies',
                       'external', 'package', 'diagnostics', '__pycache__'))


def linked(path):
    s = path.lstat()
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)


def safe(root, path):
    """Check every existing ancestor; never traverse a junction/reparse point."""
    root, path = Path(root).absolute(), Path(path).absolute()
    if root == Path(root.anchor) or not path.is_relative_to(root):return False
    try:
        current = path
        while True:
            if linked(current):return False
            if current == root:break
            current = current.parent
        return path.resolve().is_relative_to(root.resolve())
    except OSError:return False


def walk(root, folder, predicate=None):
    if not safe(root, folder) or not folder.is_dir():return
    for parent, dirs, files in os.walk(folder, followlinks=False):
        base = Path(parent)
        kept=[]
        for name in dirs:
            if name.lower() in SKIP_DIRS:continue
            try:
                if not linked(base/name):kept.append(name)
            except OSError:continue
        dirs[:]=kept
        for name in files:
            if predicate is not None and not predicate(name):continue
            path = base/name
            try:
                if not linked(path):yield path
            except OSError:continue


def log_files(root):
    root = Path(root).absolute()
    if not safe(root, root):return []
    paths = set()
    # The installed mods directory can be an intentional development junction.
    # It is bound separately at its resolved root, never followed by os.walk.
    if root.name.casefold()=='mods' and root.parent.name.casefold()=='modcarrermode':
        paths.update(walk(root,root,LOG_NAME.fullmatch))
    for folder in (root,root/'ModCarrerMode',root/'bin'):
        if not safe(root,folder):continue
        try:
            paths.update(p for p in folder.iterdir() if p.is_file() and LOG_NAME.fullmatch(p.name) and safe(root,p))
        except OSError:pass
    for rel in ('runtime', 'logs', 'ModCarrerMode/logs', 'ModCarrerMode/runtime',
                'ModCarrerMode/data', 'ModCarrerMode/mods'):
        paths.update(walk(root,root/rel,LOG_NAME.fullmatch))
    # Diagnostics have their own whole-bundle lifecycle; don't truncate evidence
    # from a live capture or corrupt an archive that is being assembled.
    return sorted(p for p in paths if not p.is_relative_to(root/'runtime/diagnostics'))


def managed_roots(root):
    root=Path(root).absolute();result=[root]
    plugins=root/'ModCarrerMode/mods'
    try:
        if linked(plugins):
            target=plugins.resolve(strict=True)
            if (target.name.casefold()=='mods' and target.parent.name.casefold()=='modcarrermode'
                    and safe(target,target) and target.is_dir()):result.append(target)
    except OSError:pass
    return result


def history_snapshot(root, paths):
    """Retain bounded tails, not full dumps, saves, configuration or credentials."""
    folder=root/'runtime/session_history'
    from .cache_maintenance import safe as safe_destination
    if not safe_destination(root,folder):return
    # A resolved plugin root is managed for logs only, not a second history tree.
    if root.name.casefold()=='mods':return
    folder.mkdir(parents=True,exist_ok=True)
    if not safe(root,folder):return
    rows=[];remaining=HISTORY_LIMIT//HISTORY_COUNT-64*1024
    def modified(pair):
        try:return pair[1].stat().st_mtime
        except OSError:return 0
    for base,path in sorted(paths,key=modified,reverse=True):
        if remaining<=0:break
        try:
            if not safe(base,path) or path.stat().st_nlink!=1:continue
            with path.open('rb') as stream:
                stream.seek(max(0,path.stat().st_size-min(HISTORY_TAIL,remaining)))
                data=stream.read(min(HISTORY_TAIL,remaining))
            if data:rows.append((str(path),data));remaining-=len(data)
        except OSError:continue
    if rows:
        name=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_pid'+str(os.getpid())+'.zip'
        destination=folder/name;temporary=destination.with_suffix('.new')
        if temporary.exists() and not safe(root,temporary):return
        from .startup_diagnostics import crash_summary
        evidence=[]
        for path in root.glob('*.dmp'):
            if safe(root,path):
                try:evidence.append(dict(name=path.name,bytes=path.stat().st_size,**crash_summary(path)))
                except OSError:pass
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('summary.json',json.dumps(dict(schema=1,logs=[p for p,_ in rows],crashes=evidence),ensure_ascii=False))
            for index,(path,data) in enumerate(rows):archive.writestr(f'logs/{index:03d}_{Path(path).name}',data)
        os.replace(temporary,destination)
    entries=sorted((p for p in folder.glob('*.zip') if SESSION_NAME.fullmatch(p.name) and safe(root,p)),key=lambda p:p.stat().st_mtime,reverse=True)
    total=0
    for index,path in enumerate(entries):
        try:
            size=path.stat().st_size
            if index>=HISTORY_COUNT or total+size>HISTORY_LIMIT:
                if path.stat().st_nlink==1:path.unlink()
            else:total+=size
        except OSError:pass


@dataclass
class Result:
    files: int = 0
    freed: int = 0
    failed: list[str] = field(default_factory=list)


def trim(root, path, keep, result):
    if not safe(root,path):return
    try:
        with path.open('r+b') as stream:
            s = os.fstat(stream.fileno())
            # A hard-linked log must not modify an otherwise unrelated file.
            if s.st_nlink != 1 or not stat.S_ISREG(s.st_mode):return
            if s.st_size <= keep:return
            tail=b''
            if keep:
                stream.seek(max(0,s.st_size-keep));tail=stream.read(keep)
                split=tail.find(b'\n')
                if 0 <= split < len(tail)-1:tail=tail[split+1:]
            stream.seek(0);stream.write(tail);stream.truncate(len(tail))
            result.files+=1;result.freed+=s.st_size-len(tail)
    except OSError as exc:result.failed.append(f'{path}: {exc}')


def diagnostic_entries(root):
    folder = root/'runtime/diagnostics'
    if not safe(root,folder) or not folder.is_dir():return []
    entries=[]
    for path in folder.iterdir():
        if not SESSION_NAME.fullmatch(path.name) or not safe(root,path):continue
        # Each child is checked too, even if a bundle was tampered with.
        files=list(walk(root,path)) if path.is_dir() else [path]
        try:entries.append((path,files,sum(p.stat().st_size for p in files),path.stat().st_mtime))
        except OSError:continue
    return entries


def prune_diagnostics(root, result, reset=False, protected=(), cutoff=None,
                      limit=DIAGNOSTICS_LIMIT):
    protected={Path(p).absolute() for p in protected}
    entries=diagnostic_entries(root);total=sum(row[2] for row in entries)
    groups={}
    for row in entries:groups.setdefault(row[0].stem if row[0].suffix=='.zip' else row[0].name,[]).append(row)
    keep=set(sorted(groups,key=lambda key:max(row[3] for row in groups[key]),reverse=True)[:HISTORY_COUNT])
    for path,files,size,modified in sorted(entries,key=lambda row:row[3]):
        base=path.with_suffix('') if path.suffix=='.zip' else path
        if base in protected or path in protected:continue
        import psutil
        if psutil.pid_exists(int(base.name.rsplit('pid',1)[1])):continue
        # Only past diagnostic sessions, never captures created by this launch.
        if reset and cutoff is not None and modified>=cutoff:continue
        if base.name in keep and total<=limit:continue
        for item in files:
            if not safe(root,item):continue
            try:
                s=item.stat()
                if s.st_nlink!=1:continue
                item.unlink();result.files+=1;result.freed+=s.st_size;total-=s.st_size
            except OSError as exc:result.failed.append(f'{item}: {exc}')
        if path.is_dir():
            for parent,dirs,unused in os.walk(path,topdown=False,followlinks=False):
                candidate=Path(parent)
                if safe(root,candidate):
                    try:candidate.rmdir()
                    except OSError:pass


def limit_image_diagnostics(root,result):
    """Only explicitly requested native validation captures, never club art."""
    parent=root/'ModCarrerMode/runtime/club_browser'
    if not safe(root,parent):return
    captures=[]
    for session in parent.iterdir():
        folder=session/'validation'
        if not session.name.isdecimal() or not safe(root,folder) or not folder.is_dir():continue
        for path in folder.glob('*.pixels'):
            if not re.fullmatch(r'\d+_\d+\.pixels',path.name) or not safe(root,path):continue
            try:captures.append((path.stat().st_mtime,path,path.stat().st_size))
            except OSError:pass
    used=0;kept=0
    for modified,path,size in sorted(captures,reverse=True):
        if kept<2 and used+size<=CAPTURE_LIMIT:used+=size;kept+=1;continue
        for item in (path,path.with_suffix('.json')):
            if not safe(root,item):continue
            try:
                info=item.stat()
                if info.st_nlink==1:item.unlink();result.files+=1;result.freed+=info.st_size
            except OSError as error:result.failed.append(f'{item}: {error}')


def maintain(root, *, reset=False, exclude=(), protected=(), cutoff=None,
             file_limit=FILE_LIMIT, tail_bytes=TAIL_BYTES, total_limit=TOTAL_LIMIT,
             diagnostics_limit=DIAGNOSTICS_LIMIT):
    root=Path(root).absolute();result=Result();excluded={Path(p).absolute() for p in exclude}
    rows=[];roots=managed_roots(root)
    paths=[(base,path) for base in roots for path in log_files(base)]
    # The only native temporary log owned by these mods; never scan shared Temp.
    native=Path(tempfile.gettempdir())/'cgfs16_overlay.log'
    from .cache_maintenance import game_root
    if game_root(root) and native.is_file():paths.append((native.parent,native))
    if reset:history_snapshot(root,paths)
    for base,path in paths:
        if path in excluded:continue
        try:
            s=path.stat()
            if reset or s.st_size>file_limit:trim(base,path,0 if reset else tail_bytes,result)
            s=path.stat();rows.append((s.st_mtime,path,s.st_size,base))
        except OSError as exc:result.failed.append(f'{path}: {exc}')
    total=sum(row[2] for row in rows)
    if total>total_limit:
        for modified,path,size,base in sorted(rows):
            if total<=total_limit:break
            before=result.freed;trim(base,path,0,result);total-=result.freed-before
    prune_diagnostics(root,result,reset,protected,cutoff,diagnostics_limit)
    limit_image_diagnostics(root,result)
    return result


class SessionLogs:
    """One background worker: no recursive scan or disk cleanup on the UI thread."""
    def __init__(self, *, exclude=(), protected=lambda:(), interval=INTERVAL_SECONDS,startup_clear=True):
        self.exclude=tuple(exclude);self.protected=protected;self.interval=interval
        self.startup_clear=startup_clear
        self.roots=set();self.lock=threading.Lock();self.tasks=queue.Queue()
        self.stop=threading.Event();self.started=time.time()
        self.thread=threading.Thread(target=self._run,name='Server16LogMaintenance',daemon=True)
        self.thread.start()

    def bind(self,root):
        root=Path(root).absolute()
        if not safe(root,root):return
        with self.lock:
            if root in self.roots:return
            self.roots.add(root)
        self.tasks.put(('startup' if self.startup_clear else 'limit',root,None))

    def clear(self,callback):self.tasks.put(('manual',None,callback))

    def _run(self):
        while not self.stop.is_set():
            try:action,root,callback=self.tasks.get(timeout=self.interval)
            except queue.Empty:action,root,callback='limit',None,None
            if action=='stop':return
            with self.lock:roots=(root,) if root is not None else tuple(self.roots)
            combined=Result()
            for current in roots:
                try:
                    report=maintain(current,reset=action!='limit',exclude=self.exclude,
                                    protected=self.protected(),cutoff=self.started if action=='startup' else None)
                    combined.files+=report.files;combined.freed+=report.freed;combined.failed.extend(report.failed)
                except Exception as exc:combined.failed.append(f'{current}: {exc}')
            if callback:
                try:callback(combined)
                except Exception:pass

    def close(self):
        self.stop.set();self.tasks.put(('stop',None,None));self.thread.join(timeout=1)
