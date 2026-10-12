from __future__ import annotations
import sys, json, sqlite3, subprocess, os, hashlib, struct, wave, zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
import unicodedata
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server16_py.narration_bank import BigArchive, HarmonyBank, sps_size

APP_ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
RESOURCE_ROOT=Path(getattr(sys,'_MEIPASS',APP_ROOT))
CODE_ROOT=Path(__file__).resolve().parent
LOCAL_GAME=(APP_ROOT/'fifa16.exe').is_file() if getattr(sys,'frozen',False) else False
CONFIG_PATH=Path(os.environ.get('F16_NARRATION_CONFIG',str(APP_ROOT/'studio_config.json')))
CONFIG=json.loads(CONFIG_PATH.read_text(encoding='utf8')) if CONFIG_PATH.exists() else {}
GAME = Path(CONFIG.get('game',str(APP_ROOT) if LOCAL_GAME else r'U:\fifa 16'))
TOOL = Path(CONFIG.get('audio_tool',r'J:\mods\fifa 16\02_Ferramentas\FIFA16AudioTool\FIFA16AudioTool'))
WORK = Path(CONFIG.get('catalog_root',str(GAME/'Narrations/.studio') if LOCAL_GAME else str(CODE_ROOT)))
PROJECTS = Path(CONFIG.get('projects',str(GAME/'Narrations') if LOCAL_GAME else str(APP_ROOT/'Projects')))
DB = WORK/'catalog.sqlite'
VGM = RESOURCE_ROOT/'bin/vgmstream-cli.exe' if (RESOURCE_ROOT/'bin/vgmstream-cli.exe').exists() else APP_ROOT/'bin/vgmstream-cli.exe' if (APP_ROOT/'bin/vgmstream-cli.exe').exists() else TOOL/'vgmstream-cli.exe'
SX = RESOURCE_ROOT/'bin/sx.exe' if (RESOURCE_ROOT/'bin/sx.exe').exists() else APP_ROOT/'bin/sx.exe' if (APP_ROOT/'bin/sx.exe').exists() else TOOL/'tools/ea_soundexchange/sx_6.00.00/sx/sx.exe'
FFMPEG = str(RESOURCE_ROOT/'bin/ffmpeg.exe') if (RESOURCE_ROOT/'bin/ffmpeg.exe').exists() else str(APP_ROOT/'bin/ffmpeg.exe') if (APP_ROOT/'bin/ffmpeg.exe').exists() else 'ffmpeg'

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
    CREATE INDEX IF NOT EXISTS clips_bank_offset ON clips(bank,offset);
    CREATE INDEX IF NOT EXISTS clips_event ON clips(event,row);
    CREATE INDEX IF NOT EXISTS clips_bank_group ON clips(bank,group_id);
    CREATE INDEX IF NOT EXISTS sources_event ON sources(narrator,event,variant);
    ''')
    from topics import update_topics
    ready=('topic_metadata' in tables and db.execute('SELECT 1 FROM topic_metadata WHERE version=2').fetchone()
           and all('topic' in {row[1] for row in db.execute('PRAGMA table_info('+table+')')} for table in ('clips','sources')))
    if not ready:update_topics(db)
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

def import_sources(narrator, root):
    import re
    db=connect(); count=0
    for p in Path(root).rglob('*'):
        if p.suffix.lower() not in ('.wav','.mp3','.flac','.ogg','.m4a'): continue
        match=re.match(r'(.+)_(\d+)_(\d+)$',p.stem)
        event,variant=(match[1],int(match[2])) if match else ('',-1)
        duration=0
        key=narrator+':'+hashlib.sha256(str(p).encode()).hexdigest()[:20]
        from topics import topic
        db.execute('INSERT OR IGNORE INTO sources (key,narrator,path,event,variant,duration,topic) VALUES (?,?,?,?,?,?,?)',(key,narrator,str(p),event,variant,duration,topic(event,str(p)))); count+=1
        if count%200==0: db.commit()
    db.commit(); db.close(); print('sources',narrator,count,flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['inventory','decode','import']); args=parser.parse_args()
    if args.action=='inventory': inventory()
    elif args.action=='decode': print(decode_all())
    else:
        import_sources('Vilani',r'J:\mods\fifa 16\03_Recursos\VILANI')
        import_sources('Luiz Roberto',r'J:\mods\fifa 16\03_Recursos\narrations\Luiz Roberto')
