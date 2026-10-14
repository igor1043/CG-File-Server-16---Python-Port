from __future__ import annotations
import sys, json, sqlite3, subprocess, os, hashlib, struct, wave, zlib, shutil
from pathlib import Path, PureWindowsPath
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
import unicodedata
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server16_py.narration_bank import BigArchive, HarmonyBank, sps_size
from server16_py.narration_paths import narration_root
from portable_setup import configuration_path

APP_ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',APP_ROOT))
CODE_ROOT=Path(__file__).resolve().parent
CONFIG_PATH=configuration_path(APP_ROOT)
CONFIG=json.loads(CONFIG_PATH.read_text(encoding='utf8')) if CONFIG_PATH.exists() else {}

def configured_path(key, default):
    value=CONFIG.get(key)
    if value in (None,''): value=default
    path=Path(value)
    if not path.is_absolute(): path=(APP_ROOT if getattr(sys,'frozen',False) else CONFIG_PATH.parent)/path
    return path.resolve()

GAME=configured_path('game',str(APP_ROOT))
LOCAL_GAME=(GAME/'fifa16.exe').is_file()
TOOL=configured_path('audio_tool',str(APP_ROOT/'FIFA16AudioTool'))
NARRATIONS=narration_root(GAME)
WORK=configured_path('catalog_root',str(APP_ROOT/'Dados FIFA 16/Catálogo editável/.studio'))
PROJECTS=configured_path('projects',str(APP_ROOT/'Projetos'))
SOURCE_ROOT=configured_path('source_root',str(APP_ROOT.parent/'Áudios Originais dos Narradores/01 - Acervos originais'))
USER_AUDIO_ROOT=configured_path('user_audio_root',str(APP_ROOT.parent/'Áudios Originais dos Narradores/02 - Áudios adicionados pelo usuário'))
WHISPER_MODEL=configured_path('whisper_model',str(RESOURCE_ROOT/'models/faster-whisper-small'))
DB = WORK/'catalog.sqlite'
VGM = RESOURCE_ROOT/'bin/vgmstream-cli.exe' if (RESOURCE_ROOT/'bin/vgmstream-cli.exe').exists() else APP_ROOT/'bin/vgmstream-cli.exe' if (APP_ROOT/'bin/vgmstream-cli.exe').exists() else TOOL/'vgmstream-cli.exe'
SX = next((path for path in (RESOURCE_ROOT/'bin/encoder/sx.exe',APP_ROOT/'bin/encoder/sx.exe',RESOURCE_ROOT/'bin/sx.exe',APP_ROOT/'bin/sx.exe') if path.exists()),TOOL/'tools/ea_soundexchange/sx_6.00.00/sx/sx.exe')
FFMPEG = str(RESOURCE_ROOT/'bin/ffmpeg.exe') if (RESOURCE_ROOT/'bin/ffmpeg.exe').exists() else str(APP_ROOT/'bin/ffmpeg.exe') if (APP_ROOT/'bin/ffmpeg.exe').exists() else 'ffmpeg'

def _relative_path(value, root):
    """Return a Windows path relative to root, even when drive-letter case differs."""
    path_parts=PureWindowsPath(str(value)).parts
    root_parts=PureWindowsPath(str(root)).parts
    if len(path_parts)<len(root_parts) or tuple(p.casefold() for p in path_parts[:len(root_parts)])!=tuple(p.casefold() for p in root_parts):
        return None
    return path_parts[len(root_parts):]

def relocate_catalog_paths(db):
    """Rebase absolute paths saved by this PC when a prepared catalogue moves."""
    manifest_path=WORK/'portable_catalog.json'
    if not manifest_path.is_file(): return
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    old=manifest.get('resolved_roots',{})
    if not old: old={k:manifest.get(k,'') for k in ('game_root','work_root','source_root')}
    current={'game_root':str(GAME),'work_root':str(WORK),'source_root':str(SOURCE_ROOT)}
    if all(not old.get(name) or os.path.normcase(os.path.normpath(str(old[name])))==os.path.normcase(os.path.normpath(str(current[name]))) for name in current):
        return
    changes=(('banks','source',('game_root',)),('banks','sbr',('work_root','game_root')),
             ('banks','body',('game_root',)),('clips','wav',('work_root','game_root')),
             ('sources','path',('source_root','work_root','game_root')))
    for table,column,order in changes:
        key='key'
        rows=db.execute(f'SELECT {key},{column} FROM {table} WHERE {column} IS NOT NULL AND {column}!=""').fetchall()
        updates=[]
        for row in rows:
            value=row[1]
            for root_name in order:
                before=old.get(root_name)
                if not before: continue
                relative=_relative_path(value,before)
                if relative is not None:
                    value=str(Path(current[root_name]).joinpath(*relative))
                    break
            if value!=row[1]: updates.append((value,row[0]))
        if updates: db.executemany(f'UPDATE {table} SET {column}=? WHERE {key}=?',updates)
    db.commit()
    manifest['resolved_roots']=current
    from atomic_io import write_json
    write_json(manifest_path,manifest)

def connect(path=DB):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path, timeout=60)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA cache_size=-65536')
    db.execute('PRAGMA mmap_size=134217728')
    db.execute('PRAGMA temp_store=MEMORY')
    db.create_function('fold',1,lambda value:''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c)))
    if db.execute('PRAGMA journal_mode').fetchone()[0]!='wal':db.execute('PRAGMA journal_mode=WAL')
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'banks','clips','sources','mappings'}.issubset(tables):db.executescript('''
    CREATE TABLE IF NOT EXISTS banks (key TEXT PRIMARY KEY, name TEXT, source TEXT, sbr TEXT, body TEXT, body_base INTEGER, body_size INTEGER, active INTEGER, sbr_hash TEXT);
    CREATE TABLE IF NOT EXISTS clips (key TEXT PRIMARY KEY, bank TEXT, group_id INTEGER, dataset_id INTEGER, event TEXT, row INTEGER, sound_id INTEGER, offset INTEGER, size INTEGER, capacity INTEGER, wav TEXT, status TEXT DEFAULT 'pending', error TEXT DEFAULT '', transcript TEXT DEFAULT '', duration REAL DEFAULT 0, category TEXT);
    CREATE TABLE IF NOT EXISTS sources (key TEXT PRIMARY KEY, narrator TEXT, path TEXT, event TEXT, variant INTEGER, transcript TEXT DEFAULT '', confidence REAL, duration REAL, error TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS mappings (profile TEXT, clip TEXT, source TEXT, method TEXT, score REAL, PRIMARY KEY(profile,clip));
    CREATE TABLE IF NOT EXISTS narration_reviews (profile TEXT, clip TEXT, reviewed INTEGER NOT NULL DEFAULT 1, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(profile,clip));
    CREATE INDEX IF NOT EXISTS clips_bank_offset ON clips(bank,offset);
    CREATE INDEX IF NOT EXISTS clips_event ON clips(event,row);
    CREATE INDEX IF NOT EXISTS clips_bank_group ON clips(bank,group_id);
    CREATE INDEX IF NOT EXISTS sources_event ON sources(narrator,event,variant);
    ''')
    db.execute('CREATE TABLE IF NOT EXISTS narration_reviews (profile TEXT, clip TEXT, reviewed INTEGER NOT NULL DEFAULT 1, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(profile,clip))')
    db.execute('CREATE INDEX IF NOT EXISTS narration_reviews_profile_state ON narration_reviews(profile,reviewed)')
    db.execute('CREATE INDEX IF NOT EXISTS sources_narrator_path ON sources(narrator,path)')
    source_columns={row[1] for row in db.execute('PRAGMA table_info(sources)')}
    for column,definition in (('topic_manual','INTEGER NOT NULL DEFAULT 0'),('origin_path',"TEXT DEFAULT ''")):
        if column not in source_columns:db.execute('ALTER TABLE sources ADD COLUMN '+column+' '+definition)
    db.commit()
    db.execute('CREATE INDEX IF NOT EXISTS sources_narrator_origin ON sources(narrator,origin_path)')
    from topics import update_topics
    ready=('topic_metadata' in tables and db.execute('SELECT 1 FROM topic_metadata WHERE version=4').fetchone()
           and all('topic' in {row[1] for row in db.execute('PRAGMA table_info('+table+')')} for table in ('clips','sources')))
    if not ready:update_topics(db)
    relocate_catalog_paths(db)
    return db

def decompress(b):
    if b[:8]!=b'chunkzip': return b
    version, full, chunk, count=struct.unpack_from('>IIII',b,8)
    if version!=2: raise ValueError('chunkzip versão não suportada')
    pos=40; parts=[]
    for _ in range(count):
        pos=(pos+7)//8*8
        if pos%16!=8: pos+=8
        size,flag=struct.unpack_from('>II',b,pos)
        payload=b[pos+8:pos+8+size]
        parts.append(payload if flag==4 else zlib.decompress(payload,-15))
        pos+=8+size
    out=b''.join(parts)
    if len(out)!=full: raise ValueError('chunkzip tamanho divergente')
    return out

def metadata(game):
    # Patch > archive, and loose files take precedence over both.
    files={}
    for name in ('data_audio3.big','data_audio3_extra.big','data_patch.big'):
        p=game/name
        if not p.exists(): continue
        big=BigArchive(p)
        for e in big.entries:
            if e.name.lower()=='audiodata/speechdata/por_br/por_br.xml': files[e.name]=decompress(big.read(e))
    loose=game/'audiodata/speechdata/por_br/por_br.xml'
    if loose.exists(): files['loose']=decompress(loose.read_bytes())
    if not files: raise ValueError('XML brasileiro de eventos não localizado')
    data=list(files.values())[-1]
    (WORK/'metadata').mkdir(exist_ok=True)
    (WORK/'metadata/por_br.xml').write_bytes(data)
    root=ET.fromstring(data)
    return {int(g.attrib['SampleGroupKey'],16):g.attrib['Name'] for g in root.iter('SampleGroup')}

def inventory(game=GAME):
    db=connect(); names=metadata(game)
    bank_dir=WORK/'banks'; bank_dir.mkdir(exist_ok=True)
    found=[]
    # Include all Brazilian banks present in mounted root archives, including patches.
    for path in sorted(game.glob('*.big')):
        big=BigArchive(path)
        byname={e.name.lower():e for e in big.entries}
        for e in big.entries:
            if '/por_br/' not in e.name.lower() or not e.name.lower().endswith('.sbr'): continue
            other=byname.get(e.name.lower()[:-4]+'.sbs')
            data=big.read(e)
            key=path.stem+'__'+Path(e.name).stem
            sbr=bank_dir/(key+'.sbr'); sbr.write_bytes(data)
            loose=game/e.name
            active=not loose.exists()
            found.append((key,Path(e.name).stem,str(path),str(sbr),str(path),other.offset if other else 0,other.size if other else len(data),int(active),data))
    for path in sorted((game/'audiodata/speechdata/por_br').glob('*.sbr')):
        body=path.with_suffix('.sbs')
        key='loose__'+path.stem
        data=path.read_bytes(); sbr=bank_dir/(key+'.sbr'); sbr.write_bytes(data)
        found.append((key,path.stem,str(path),str(sbr),str(body),0,body.stat().st_size if body.exists() else len(data),1,data))
    report=[]
    for key,name,source,sbr,body,base,size,active,data in found:
        bank=HarmonyBank(data)
        db.execute('INSERT OR REPLACE INTO banks VALUES (?,?,?,?,?,?,?,?,?)',(key,name,source,sbr,body,base,size,active,hashlib.sha256(data).hexdigest()))
        offsets=sorted(set(r['offset'] for r in bank.rows if r['storage']=='sbs' and r['offset']))
        ends={o:(offsets[i+1] if i+1<len(offsets) else size) for i,o in enumerate(offsets)}
        errors=[]
        with Path(body).open('rb') as f:
            payloads={}
            for row in bank.rows:
                off=row['offset']
                if not off: continue
                if row['storage']!='sbs': raise ValueError('Banco com áudio RAM requer extração interna')
                if off not in payloads:
                    capacity=ends[off]-off
                    f.seek(base+off)
                    b=f.read(capacity)
                    try:
                        skip,length=sps_size(b)
                        payloads[off]=(skip,length,capacity-skip,'')
                    except Exception as exc:
                        payloads[off]=(0,capacity,capacity,str(exc)); errors.append(dict(offset=off,error=str(exc)))
                skip,length,capacity,error=payloads[off]
                event=names.get(row['group_id'],f"UNKNOWN_{row['group_id']:08x}")
                clip_key=f"{key}:{row['group_id']:08x}:{row['row']:05d}:{row['sound_id']:08x}"
                wav=str(WORK/'original_wav'/key/f'{off:08x}.wav')
                category='callname' if event in ('pPLAYER_NAMES','pSIMPLE_SURNAME') else 'special' if any(t in event for t in ('LEGEND','PLAYER','BANT','CAREER')) else 'commentary'
                from topics import topic
                db.execute('''INSERT INTO clips (key,bank,group_id,dataset_id,event,row,sound_id,offset,size,capacity,wav,error,category,topic)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET event=excluded.event,offset=excluded.offset,size=excluded.size,capacity=excluded.capacity,error=excluded.error''',
                    (clip_key,key,row['group_id'],row['dataset_id'],event,row['row'],row['sound_id'],off+skip,length,capacity,wav,error,category,topic(event)))
        db.commit()
        item=dict(bank=key,active=bool(active),datasets=len(bank.datasets),occurrences=len(bank.rows),physical=len(offsets),errors=errors)
        report.append(item); print(json.dumps({k:v for k,v in item.items() if k!='errors'}),flush=True)
    (WORK/'inventory_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    db.close(); return report

def decode_all(workers=4):
    db=connect()
    clips=db.execute('''SELECT c.*,b.body,b.body_base FROM clips c JOIN banks b ON b.key=c.bank GROUP BY c.bank,c.offset ORDER BY c.bank,c.offset''').fetchall()
    def decode_batch(batch):
        # One decoder process for many streams avoids loading its DLLs tens of
        # thousands of times. Inputs stay in the same bank directory.
        directory=Path(batch[0]['wav']).parent
        directory.mkdir(parents=True,exist_ok=True)
        pending=[]; error=''
        try:
            with Path(batch[0]['body']).open('rb') as f:
                for c in batch:
                    dest=Path(c['wav'])
                    if dest.exists() and dest.stat().st_size>=44: continue
                    raw=dest.with_suffix('.sps')
                    f.seek(c['body_base']+c['offset']);raw.write_bytes(f.read(c['size']))
                    pending.append(raw)
            if pending:
                run=subprocess.run([str(VGM),'-i']+[p.name for p in pending],cwd=directory,capture_output=True,timeout=600,creationflags=0x08000000)
                error=run.stderr.decode(errors='replace')[-1600:]
                for raw in pending:
                    output=raw.with_name(raw.name+'.wav')
                    if output.exists(): output.replace(raw.with_suffix('.wav'))
                    raw.unlink(missing_ok=True)
        except Exception as exc: error=str(exc)
        result=[]
        for c in batch:
            try:
                with wave.open(c['wav']) as w:
                    duration=w.getnframes()/w.getframerate()
                    if not w.getnframes(): raise ValueError('WAV vazio')
                result.append((c,'decoded','',duration))
            except Exception as exc: result.append((c,'failed',error or str(exc),0))
        return result
    batches=[]
    for c in clips:
        if not batches or len(batches[-1])>=128 or batches[-1][0]['bank']!=c['bank']: batches.append([])
        batches[-1].append(c)
    good=bad=0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed(pool.submit(decode_batch,b) for b in batches):
            for c,status,error,duration in future.result():
                if status!=c['status'] or error!=c['error'] or duration!=c['duration']:
                    db.execute('UPDATE clips SET status=?,error=?,duration=? WHERE bank=? AND offset=?',(status,error,duration,c['bank'],c['offset']))
                good+=status=='decoded'; bad+=status=='failed'
            db.commit(); print(f'decode {good+bad}/{len(clips)} good={good} failed={bad}',flush=True)
    result=dict(total=len(clips),decoded=good,failed=bad)
    (WORK/'decode_report.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    db.close(); return result

SOURCE_AUDIO_EXTENSIONS={'.wav','.mp3','.flac','.ogg','.m4a'}

def iter_source_audio(root):
    """Yield supported recordings from a folder and every nested folder."""
    root=Path(root).expanduser()
    if root.is_file():
        if root.suffix.lower() in SOURCE_AUDIO_EXTENSIONS: yield root.resolve()
        return
    if not root.is_dir(): raise FileNotFoundError('Pasta de áudios não encontrada: '+str(root))
    def walk_error(error): raise error
    for folder,subfolders,filenames in os.walk(root,topdown=True,onerror=walk_error,followlinks=False):
        subfolders.sort(key=str.casefold)
        for filename in sorted(filenames,key=str.casefold):
            path=Path(folder)/filename
            if path.suffix.lower() in SOURCE_AUDIO_EXTENSIONS and path.is_file(): yield path.resolve()

def safe_audio_folder_name(value):
    """Make a readable Windows folder name for an imported audio collection."""
    name=''.join('_' if char in '<>:"/\\|?*' or ord(char)<32 else char for char in str(value or '').strip())
    name=name.rstrip('. ')
    if not name or name.upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        name='Coleção de áudios'
    return name

def _inside_directory(path, root):
    try:Path(path).resolve().relative_to(Path(root).resolve());return True
    except (ValueError,OSError):return False

def copy_audio_collection(source_root, destination_parent, progress=None):
    """Copy a selected audio tree into the managed narrator library.

    Folder structure and adjacent TXT transcripts are kept. Re-attaching a
    folder already in the managed library indexes it in place instead of
    making another copy.
    """
    source=Path(source_root).expanduser().resolve()
    parent=Path(destination_parent).expanduser().resolve()
    if not source.is_dir():raise NotADirectoryError('Selecione uma pasta de áudios válida: '+str(source))
    if _inside_directory(source,parent):
        count=sum(1 for _ in iter_source_audio(source))
        return source,count
    parent.mkdir(parents=True,exist_ok=True)
    base=safe_audio_folder_name(source.name)
    target=parent/base
    index=2
    while target.exists():
        marker=target/'.narration-library.json'
        try:
            if json.loads(marker.read_text(encoding='utf8')).get('source')==str(source):
                return target,sum(1 for _ in iter_source_audio(target))
        except (OSError,ValueError,AttributeError):pass
        target=parent/f'{base} ({index})';index+=1
    total=sum(1 for _ in iter_source_audio(source))
    copied=0
    target.mkdir(parents=True)
    try:
        for path in iter_source_audio(source):
            relative=path.relative_to(source)
            destination=target/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination)
            for sidecar in (Path(str(path)+'.txt'),path.with_suffix('.txt')):
                if sidecar.is_file():
                    side_relative=sidecar.relative_to(source)
                    side_destination=target/side_relative
                    side_destination.parent.mkdir(parents=True,exist_ok=True)
                    if not side_destination.exists():shutil.copy2(sidecar,side_destination)
            copied+=1
            if progress and (copied==total or copied%25==0):progress(copied,total)
        (target/'.narration-library.json').write_text(
            json.dumps({'source':str(source),'audio_files':copied},ensure_ascii=False,indent=2),encoding='utf8')
    except Exception:
        # Leave the partial import visible for recovery instead of deleting user data.
        (target/'.import_incomplete').write_text(f'Origem: {source}\nCopiados: {copied}/{total}\n',encoding='utf8')
        raise
    return target,copied

def import_sources(narrator, root):
    import re
    db=connect(); count=0
    try:
        for p in iter_source_audio(root):
            match=re.match(r'(.+)_(\d+)_(\d+)$',p.stem)
            event,variant=(match[1],int(match[2])) if match else ('',-1)
            duration=0
            existing=db.execute('SELECT key,transcript FROM sources WHERE narrator=? AND path=? UNION ALL SELECT key,transcript FROM sources WHERE narrator=? AND origin_path=? LIMIT 1',(narrator,str(p),narrator,str(p))).fetchone()
            transcript=''
            for text_path in (p.with_suffix(p.suffix+'.txt'),p.with_suffix('.txt')):
                if text_path.is_file():
                    transcript=text_path.read_text(encoding='utf-8-sig').strip();break
            if existing:
                if transcript and not existing['transcript']:
                    db.execute('UPDATE sources SET transcript=? WHERE key=?',(transcript,existing['key']))
                count+=1
                continue
            key=narrator+':'+hashlib.sha256(str(p).encode()).hexdigest()[:20]
            from topics import topic
            db.execute('INSERT OR IGNORE INTO sources (key,narrator,path,event,variant,duration,topic,transcript) VALUES (?,?,?,?,?,?,?,?)',(key,narrator,str(p),event,variant,duration,topic(event,str(p),transcript),transcript)); count+=1
            if count%200==0: db.commit()
        db.commit()
    finally: db.close()
    print('sources',narrator,count,flush=True)
    return count

def remove_source_asset(narrator, key, managed_root):
    """Remove one narrator asset and its mappings; only delete managed audio files."""
    db=connect()
    try:
        row=db.execute('SELECT path FROM sources WHERE key=? AND narrator=?',(key,narrator)).fetchone()
        if row is None:raise ValueError('Este áudio não está na biblioteca do narrador ativo.')
        path=Path(row['path']).expanduser().resolve()
        profiles=[item['profile'] for item in db.execute('SELECT DISTINCT profile FROM mappings WHERE source=?',(key,))]
        changes={profile:[item['clip'] for item in db.execute('SELECT clip FROM mappings WHERE source=? AND profile=?',(key,profile))] for profile in profiles}
        db.execute('DELETE FROM mappings WHERE source=?',(key,))
        db.execute('DELETE FROM sources WHERE key=? AND narrator=?',(key,narrator))
        db.commit()
    finally:db.close()
    deleted_file=False;delete_error=''
    if _inside_directory(path,managed_root):
        deleted_file=True
        for candidate in {path,Path(str(path)+'.txt'),path.with_suffix('.txt')}:
            try:candidate.unlink(missing_ok=True)
            except OSError as exc:delete_error=str(exc)
    return dict(path=path,profiles=profiles,changes=changes,deleted_file=deleted_file,delete_error=delete_error)

def stage_source_asset(narrator, key, managed_root):
    """Keep the same asset identity while copying its complete recording into the game."""
    from atomic_io import write_text
    db=connect()
    try:
        row=db.execute('SELECT * FROM sources WHERE key=? AND narrator=?',(key,narrator)).fetchone()
        if row is None:raise ValueError('Áudio não encontrado na base deste narrador.')
        source=Path(row['path']).expanduser().resolve();root=Path(managed_root).resolve()
        if not source.is_file():raise FileNotFoundError('Áudio não encontrado: '+str(source))
        if _inside_directory(source,root):return source
        target=root/'Utilizados'/(hashlib.sha256(key.encode()).hexdigest()[:12]+'_'+source.name)
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or (target.stat().st_size,target.stat().st_mtime_ns)!=(source.stat().st_size,source.stat().st_mtime_ns):shutil.copy2(source,target)
        if row['transcript']:write_text(Path(str(target)+'.txt'),row['transcript'])
        db.execute('UPDATE sources SET path=?,origin_path=CASE WHEN coalesce(origin_path,\'\')=\'\' THEN ? ELSE origin_path END WHERE key=?',(str(target),str(source),key))
        db.commit();return target
    finally:db.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['inventory','decode','import']); args=parser.parse_args()
    if args.action=='inventory': inventory()
    elif args.action=='decode': print(decode_all())
    else:
        import_sources('Vilani',r'J:\mods\fifa 16\03_Recursos\VILANI')
        import_sources('Luiz Roberto',r'J:\mods\fifa 16\03_Recursos\narrations\Luiz Roberto')
