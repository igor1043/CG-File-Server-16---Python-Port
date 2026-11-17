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
TARGETS=PANORAMA_TARGETS|{'data/ui/layout/careermanagerhubcfg.xml',
                       'data/ui/game/screens/playnow/kickoffhub.big',
                       'data/ui/game/screens/settings/gamesettings.big',
                       'data/ui/nav/settingsflow.nav',
                       'data/ui/game/screens/fluxhub/fluxhub.big',
                       'data/ui/game/screens/career/managerpreferences.big',
                       'data/ui/game/screens/career/setup.big',
                       'data/ui/game/background/backgroundbootflow.big'}

def bh_hash(name):
    value=5381
    for byte in name.replace('\\','/').lower().encode('ascii'):
        value=(value*33+byte)&0xffffffffffffffff
    return value

def _align_index(index,before,records):
    """Repair stale offsets/order only when the entire file identity set agrees.

    Zero hashes are intentional loose-file releases. Recover that complete set
    by subtracting the visible names; never re-enable them during a repair.
    Different archives/file sets still require an explicit regeneration.
    """
    expected=16+20*len(records)
    if (len(before)!=expected or before[:4]!=b'ViV4' or
        struct.unpack_from('<I',before,4)[0]!=expected or
        struct.unpack_from('>II',before,8)!=(len(records),expected)):
        raise ValueError('O indice BH precisa ser regenerado para o BIG desta instalacao: '+str(index))
    names={bh_hash(name) for offset,size,name in records}
    if 0 in names or len(names)!=len(records):raise ValueError('Ambiguous BIG filenames: '+str(index))
    old=[struct.unpack_from('>IIIQ',before,16+i*20) for i in range(len(records))]
    visible={entry[3]:entry for entry in old if entry[3]}
    if len(visible)!=sum(bool(entry[3]) for entry in old) or not visible.keys()<=names:
        raise ValueError('O BH pertence a outro conjunto de arquivos; regenere os indices locais: '+str(index))
    after=bytearray(before)
    for i,(offset,size,name) in enumerate(records):
        key=bh_hash(name);previous=visible.get(key)
        # A nonzero uncompressed size is archive-specific. Do not guess when
        # its compressed payload also changed.
        if previous and previous[2] and previous[1]!=size:
            raise ValueError('Compressed BH entry requires regeneration: '+str(index))
        uncompressed=previous[2] if previous else 0
        # Preserve hidden records verbatim when they are already aligned.
        if old[i][:2]==(offset,size) and old[i][3]==0:uncompressed=old[i][2]
        struct.pack_into('>IIIQ',after,16+i*20,offset,size,uncompressed,key if previous else 0)
    return after

def plans(game,targets=None):
    game=Path(game);result=[];targets=TARGETS if targets is None else frozenset(targets)
    for stem in ('data_patch','data_front_end_extra','data_front_end','data_startup'):
        archive=game/(stem+'.big')
        if not archive.exists():continue
        archive_size=archive.stat().st_size
        with archive.open('rb') as handle:
            head=handle.read(16)
            if len(head)!=16 or head[:4] not in (b'BIG4',b'BIGF'):raise ValueError('Unknown BIG: '+str(archive))
            count,end=struct.unpack_from('>II',head,8)
            if count>1_000_000 or not 16<=end<=min(134217728,archive_size):raise ValueError('Invalid BIG directory')
            table=handle.read(end-16)
        records=[];matches=[];at=0
        for i in range(count):
            if at+8>=len(table):raise ValueError('Truncated BIG directory: '+str(archive))
            offset,size=struct.unpack_from('>II',table,at);z=table.index(0,at+8)
            name=table[at+8:z].decode('ascii').replace('\\','/').casefold();at=z+1
            if offset<end or offset+size>archive_size:raise ValueError('Invalid BIG payload: '+str(archive))
            records.append((offset,size,name))
            if name in targets and (game/name).is_file():matches.append((i,name))
        if not matches:continue
        index=archive.with_suffix('.bh');before=index.read_bytes()
        after=_align_index(index,before,records)
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
