"""Run portable career UI helpers with Server16's bundled Python runtime.

Worker mode is dispatched before splash/UI initialization. Only the bank
worker processes budget changes, after its existing scoped UI validations.
"""
from pathlib import Path
import argparse,contextlib,ctypes,hashlib,json,os,runpy,shutil,subprocess,sys,time,traceback

ENTRIES={'room':'prepare_native_room_components_r46_20261022.py','bank':'watch_r57.py','preview':'prepare.py'}

def atomic_copy(source,target):
    data=source.read_bytes()
    if target.exists() and target.read_bytes()==data:return
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+str(os.getpid())+'.new')
    temporary.write_bytes(data);os.replace(temporary,target)

def prepare_runtime(game):
    source=game/'ModCarrerMode/source/club_environment'
    runtime=game/'ModCarrerMode/runtime/club_environment'
    for group,entry in ENTRIES.items():
        if not (source/group/entry).is_file():raise FileNotFoundError(source/group/entry)
        for file in (source/group).glob('*'):
            if file.is_file() and file.suffix in ('.py','.big'):atomic_copy(file,runtime/group/file.name)
        (runtime/group/'runtime').mkdir(parents=True,exist_ok=True)
    # The separate 32-bit DB bridge also uses the shipped helper source.
    atomic_copy(Path(__file__).with_name('db_worker.py'),runtime/'preview/db_worker.py')
    seeds=game/'ModCarrerMode/data/club_environment'
    for file in seeds.rglob('*'):
        if file.is_file():atomic_copy(file,runtime/file.relative_to(seeds))
    # Preserve already-contracted loans on machines upgraded from the prototype.
    previous=game/'ModCarrerMode/experiments/career_bank_20261021/runtime'
    for folder in previous.glob('*'):
        if folder.is_dir() and len(folder.name)==20 and all(c in '0123456789abcdef' for c in folder.name):
            target=runtime/'bank/runtime'/folder.name
            if not target.exists():shutil.copytree(folder,target)
    return source,runtime

def worker(game,kind,pid):
    os.environ['SERVER16_GAME_ROOT']=str(game)
    # A native plugin can start a worker before the supervisor, including on a
    # clean installation. Never assume its generated runtime already exists.
    source,runtime=prepare_runtime(game)
    sys.path[:0]=[str(source),str(source/'vendor'),str(runtime/'room'),str(runtime/'preview'),str(runtime/'bank')]
    sys.argv=[str(runtime/kind/ENTRIES[kind]),'--watch','--pid',str(pid)]
    # A windowed frozen process can expose an invalid inherited stdout handle.
    # Diagnostic prints must never abort a financial or asset operation.
    log=runtime/kind/'runtime/service.log'
    if os.environ.get('SERVER16_CLUB_BROWSER_WORKER')=='1':log=game/'ModCarrerMode/runtime/club_browser'/str(pid)/'service.log'
    elif os.environ.get('SERVER16_TRANSFER_MARKET_WORKER')=='1':log=runtime/'market/service.log'
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('a',encoding='utf8',buffering=1) as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        print('WORKER_START',json.dumps(dict(kind=kind,game=str(game),game_pid=pid,helper_pid=os.getpid()),ensure_ascii=True))
        try:runpy.run_path(sys.argv[0],run_name='__main__')
        except BaseException:
            traceback.print_exc();raise

def supervise(game,pid):
    import psutil
    process=psutil.Process(pid)
    if process.name().casefold()!='fifa16.exe' or Path(process.exe()).resolve().parent!=game:
        raise ValueError('FIFA session does not belong to this installation')
    created=process.create_time()
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    lock=kernel.CreateMutexW(None,False,'Local\\Server16ClubEnvironment_'+str(pid))
    if not lock:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:kernel.CloseHandle(lock);return
    children={};streams={};next_start={}
    try:
        source,runtime=prepare_runtime(game)
        log=runtime/'supervisor.log'
        with log.open('a',encoding='utf8') as stream:stream.write(f'game_pid={pid} portable workers enabled\n')
        while process.is_running() and process.create_time()==created:
            for kind in ENTRIES:
                child=children.get(kind)
                if child is not None and child.poll() is None:continue
                if time.monotonic()<next_start.get(kind,0):continue
                next_start[kind]=time.monotonic()+15
                if kind in streams:streams[kind].close()
                streams[kind]=(runtime/kind/'runtime/worker.log').open('ab')
                command=[sys.executable]
                if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve().parents[1]/'main.py'))
                command+=['--club-environment-worker',kind,'--game-root',str(game),'--pid',str(pid)]
                children[kind]=subprocess.Popen(command,cwd=game,stdout=streams[kind],stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
    except psutil.NoSuchProcess:pass
    finally:
        for child in children.values():
            if child.poll() is None:child.terminate()
        for child in children.values():
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill()
        for stream in streams.values():stream.close()
        kernel.CloseHandle(lock)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--club-environment',action='store_true')
    parser.add_argument('--club-environment-worker',choices=ENTRIES)
    parser.add_argument('--club-environment-check',action='store_true')
    parser.add_argument('--club-environment-install',action='store_true')
    parser.add_argument('--game-root',type=Path,required=True)
    parser.add_argument('--pid',type=int,default=0)
    args=parser.parse_args(argv);game=args.game_root.resolve()
    if args.club_environment_check or args.club_environment_install:
        source,runtime=prepare_runtime(game)
        os.environ['SERVER16_GAME_ROOT']=str(game)
        sys.path[:0]=[str(source),str(source/'vendor'),str(runtime/'room'),str(runtime/'preview'),str(runtime/'bank')]
        import portable_paths,build_preview,room_native_hanging_20261022,loans,bank_ui_r60
        for kind in (0,2):room_native_hanging_20261022.source_shirt(kind)
        if args.club_environment_install:
            import psutil
            if any((task.info['name'] or '').casefold()=='fifa16.exe' for task in psutil.process_iter(['name'])):raise RuntimeError('Close FIFA before installing UI')
            from bootstrap_ui import generate
            generate()
            from .loose_ui import activate
            activate(game)
        import sqlite3,save_sidecar,bank_art
        db=sqlite3.connect(':memory:')
        try:assert db.execute('SELECT 1').fetchone()==(1,)
        finally:db.close()
        result={'ready':True,'workers':list(ENTRIES),'game':str(game),'numpy':__import__('numpy').__version__,'sqlite':sqlite3.sqlite_version,'bank_icons':bank_art.validate_assets()}
        (runtime/'check.json').write_text(json.dumps(result),encoding='utf8')
        print(json.dumps(result));return 0
    if args.pid<=0:parser.error('--pid is required')
    if args.club_environment_worker:worker(game,args.club_environment_worker,args.pid)
    else:supervise(game,args.pid)
    return 0
