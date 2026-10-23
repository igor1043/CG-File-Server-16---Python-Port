"""Activate only shipped career/panorama UI entries in each installation's BH.

Do not distribute BH indexes: their ordering depends on the local BIG files.
The hash release uses the same ViV4 contract as the birthyear UI installer.
"""
from pathlib import Path
import hashlib,json,os,struct,time

PANORAMA_TARGETS={
 'data/ui/game/background/backgroundfifa.big',
 'data/ui/game/screens/misc/stadiumpan.big',
 'data/ui/nav/mainfeflow.nav',
 'data/ui/nav/careermode/mainmenuhubflow.nav',
}
TARGETS=PANORAMA_TARGETS|{'data/ui/layout/careermanagerhubcfg.xml'}

def plans(game,targets=None):
    game=Path(game);result=[];targets=TARGETS if targets is None else frozenset(targets)
    for stem in ('data_patch','data_front_end_extra','data_front_end','data_startup'):
        archive=game/(stem+'.big')
        if not archive.exists():continue
        with archive.open('rb') as handle:
            head=handle.read(16)
            if len(head)!=16 or head[:4] not in (b'BIG4',b'BIGF'):raise ValueError('Unknown BIG: '+str(archive))
            count,end=struct.unpack_from('>II',head,8)
            if count>1_000_000 or not 16<=end<=min(134217728,archive.stat().st_size):raise ValueError('Invalid BIG directory')
            table=handle.read(end-16)
        records=[];matches=[];at=0
        for i in range(count):
            offset,size=struct.unpack_from('>II',table,at);z=table.index(0,at+8)
            name=table[at+8:z].decode('ascii').replace('\\','/').casefold();at=z+1
            records.append((offset,size))
            if name in targets and (game/name).is_file():matches.append((i,name))
        if not matches:continue
        index=archive.with_suffix('.bh');before=index.read_bytes();expected=16+20*count
        if len(before)!=expected or before[:4]!=b'ViV4' or struct.unpack_from('<I',before,4)[0]!=expected or struct.unpack_from('>II',before,8)!=(count,expected):raise ValueError('Incompatible BH: '+str(index))
        for i,(offset,size) in enumerate(records):
            if struct.unpack_from('>II',before,16+i*20)!=(offset,size) or offset+size>archive.stat().st_size:raise ValueError('BIG/BH order mismatch: '+str(index))
        after=bytearray(before)
        for i,name in matches:after[28+i*20:36+i*20]=bytes(8)
        result.append((index,before,bytes(after),matches))
    return result

def activate(game,verify_only=False,targets=None):
    import psutil
    game=Path(game).resolve();plan=plans(game,targets);pending=[p for p in plan if p[1]!=p[2]]
    if pending and not verify_only:
        for task in psutil.process_iter(['name','exe']):
            try:
                if (task.info['name'] or '').casefold()=='fifa16.exe' and task.info['exe'] and Path(task.info['exe']).resolve().parent==game:
                    return {'status':'restart_required','changed':0,'pending':len(pending)}
            except (psutil.NoSuchProcess,psutil.AccessDenied):continue
        backup=game/'ModCarrerMode/backups'/('club_ui_'+time.strftime('%Y%m%d_%H%M%S')+'_'+str(os.getpid()))
        backup.mkdir(parents=True,exist_ok=False)
        completed=[]
        try:
            for index,before,after,matches in pending:
                if index.read_bytes()!=before:raise RuntimeError('BH changed during activation')
                (backup/index.name).write_bytes(before)
                if (backup/index.name).read_bytes()!=before:raise RuntimeError('BH backup verification failed')
                with index.open('r+b') as handle:
                    if handle.read()!=before:raise RuntimeError('BH changed during activation')
                    completed.append((index,before))
                    handle.seek(0);handle.write(after);handle.flush();os.fsync(handle.fileno())
                if index.read_bytes()!=after:raise RuntimeError('BH verification failed')
        except Exception:
            for index,before in reversed(completed):index.write_bytes(before)
            raise
    return {'status':'activation_required' if verify_only and pending else 'ready','changed':0 if verify_only else len(pending),'entries':sum(len(p[3]) for p in plan)}
