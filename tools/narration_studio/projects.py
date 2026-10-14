"""Editable projects separate from deployed game packages."""
from pathlib import Path
import collections,concurrent.futures,hashlib,json,os,shutil,struct,subprocess,wave
from core import connect,GAME,WORK,PROJECTS,VGM,USER_AUDIO_ROOT,import_sources,stage_source_asset
from server16_py.narration_paths import narration_root, profile_directory, profile_directories
from profiles import compile_profile,assign
from atomic_io import write_bytes,write_json,write_text

def safe_name(name):
    name=name.strip()
    if not name or name in ('.','..') or any(c in name for c in '\\/:*?"<>|') or name.endswith(('.', ' ')):
        raise ValueError('Use um nome de narrador válido.')
    return name

def folder(name):return PROJECTS/safe_name(name)

def game_project_folder(name,game_root=None):
    """Editable sidecar saved beside the installed narrator profile."""
    return profile_directory(Path(game_root or GAME),safe_name(name))/'Studio'

def assets_folder(name):return game_project_folder(name)/'assets'

def metadata(name):
    for path in (folder(name)/'project.json',game_project_folder(name)/'project.json',profile_directory(GAME,name)/'profile.json'):
        if path.exists():return json.loads(path.read_text(encoding='utf8'))
    return dict(name=name,commentator='',competitions=[])

def _mirror_editable_project(name,dest):
    target=game_project_folder(name);target.mkdir(parents=True,exist_ok=True)
    for relative in ('project.json','narrator.txt','portrait.png','library_folders.json','transcriptions/audio.json','transcriptions/audio.txt','transcriptions/original.txt','transcriptions/library.json'):
        source=dest/relative
        if not source.is_file():continue
        output=target/relative;output.parent.mkdir(parents=True,exist_ok=True)
        write_bytes(output,source.read_bytes())

def save(name,commentator=None,competitions=None,portrait=None):
    dest=folder(name);dest.mkdir(parents=True,exist_ok=True)
    if name!='Tiago Leifert':assets_folder(name).mkdir(parents=True,exist_ok=True)
    data=metadata(name);data.update(name=name,format='FIFA16NarrationProject',version=1)
    data.setdefault('template','Tiago Leifert')
    data.setdefault('template_commentator','Caio Ribeiro')
    for key,value in (('commentator',commentator),('competitions',competitions),('portrait',portrait)):
        if value is not None:data[key]=value
    db=connect()
    rows=db.execute('''SELECT m.*,c.event,c.bank,c.offset,c.wav,s.path,s.transcript,s.confidence,s.duration,s.event source_event,s.variant
        FROM mappings m JOIN clips c ON m.clip=c.key JOIN sources s ON m.source=s.key WHERE profile=?''',(name,)).fetchall()
    data['mappings']=[dict(r) for r in rows]
    data['reviewed']=[r['clip'] for r in db.execute('SELECT clip FROM narration_reviews WHERE profile=? AND reviewed=1 ORDER BY clip',(name,))]
    texts=dest/'transcriptions';texts.mkdir(exist_ok=True)
    sources=db.execute('SELECT key,path,origin_path,event,variant,transcript,confidence,duration,topic,topic_manual FROM sources WHERE narrator=?',(name,)).fetchall()
    data['assets']=[dict(r) for r in sources]
    write_json(dest/'project.json',data)
    write_json(texts/'audio.json',data['assets'])
    (texts/'audio.txt').write_text('\n'.join(f"{r['path']}\t{r['transcript'] or '[pendente]'}" for r in sources),encoding='utf8')
    if name=='Tiago Leifert':
        originals=db.execute('SELECT key,event,wav,transcript FROM clips ORDER BY event,row').fetchall()
        (texts/'original.txt').write_text('\n'.join(f"{r['key']}\t{r['event']}\t{r['wav']}\t{r['transcript'] or '[pendente]'}" for r in originals),encoding='utf8')
    (dest/'narrator.txt').write_text(f"Narrador={name}\nComentarista={data.get('commentator','')}\nCompeticoes={','.join(data.get('competitions',[]))}\n",encoding='utf8')
    db.close();_mirror_editable_project(name,dest);return dest

def apply_changes(name, clips):
    """Install only changed sound slots while preserving the existing package."""
    from profiles import encoded,package_bytes
    clips=set(clips)
    if not clips:return profile_directory(GAME,name)
    db=connect()
    try:
        aliases=set()
        for key in clips:
            row=db.execute('SELECT bank,offset FROM clips WHERE key=?',(key,)).fetchone()
            if row:aliases.update(r['key'] for r in db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',tuple(row)))
        if not aliases:return profile_directory(GAME,name)
        rows=[dict(row) for row in db.execute('''SELECT c.*,b.name bank_name,s.path,s.transcript source_transcript
            FROM clips c JOIN banks b ON b.key=c.bank
            LEFT JOIN mappings m ON m.clip=c.key AND m.profile=? LEFT JOIN sources s ON s.key=m.source
            WHERE b.active=1 AND c.key IN ('''+','.join('?' for _ in aliases)+')',[name,*aliases])]
    finally:db.close()
    dest=profile_directory(GAME,name);dest.mkdir(parents=True,exist_ok=True)
    banks=collections.defaultdict(dict)
    package=dest/'profile.npack'
    if package.exists():
        for bank,offset,payload in unpack(package):banks[bank][offset]=payload
    cache=folder(name)/'build'/'encoded'
    payloads={path:encoded(path,cache) for path in {row['path'] for row in rows if row['path']}}
    reports=[]
    report_paths=[dest/'build_report.json',folder(name)/'build'/'build_report.json']
    existing=[path for path in report_paths if path.is_file()]
    if existing:
        reports=json.loads(max(existing,key=lambda path:path.stat().st_mtime_ns).read_text(encoding='utf8'))
    reports=[item for item in reports if item.get('clip') not in aliases]
    for row in rows:
        bank='audiodata/speechdata/por_br/'+row['bank_name'].lower()+'.sbs'
        offset=int(Path(row['wav']).stem,16)
        banks[bank].pop(offset,None)
        if row['path']:
            payload=payloads[row['path']];banks[bank][offset]=payload
            stat=Path(row['path']).stat()
            reports.append(dict(clip=row['key'],event=row['event'],source=row['path'],source_signature=dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns),transcript=row['source_transcript'],mode='resident_sps',bytes=len(payload)))
    out,unique=package_bytes(banks)
    meta=json.loads((dest/'profile.json').read_text(encoding='utf8')) if (dest/'profile.json').exists() else {}
    info=metadata(name)
    meta.update({key:info[key] for key in ('commentator','competitions','portrait') if key in info})
    meta.update(name=name,version=3,package='profile.npack',mapped=sum('error' not in item for item in reports),physical=sum(len(items) for items in banks.values()),unique_audio=unique,failed=0,original_fallback=True)
    write_bytes(package,out)
    write_json(dest/'build_report.json',reports);write_json(dest/'profile.json',meta)
    write_text(dest/'narrator.txt',f'Narrador={name}\nComentarista={meta.get("commentator","")}\nPacote=profile.npack\nVersao=3\n')
    return dest

def assign_audio(name, clips, source):
    clips=[clips] if isinstance(clips,str) else list(clips)
    stage_source_asset(name,source,assets_folder(name))
    db=connect();before=[dict(row) for row in db.execute('SELECT * FROM mappings WHERE profile=?',(name,))];reviews=[dict(row) for row in db.execute('SELECT * FROM narration_reviews WHERE profile=?',(name,))];db.close()
    try:
        for clip in clips:assign(name,clip,source)
        apply_changes(name,clips)
    except Exception:
        db=connect();db.execute('DELETE FROM mappings WHERE profile=?',(name,));db.execute('DELETE FROM narration_reviews WHERE profile=?',(name,))
        db.executemany('INSERT INTO mappings VALUES (?,?,?,?,?)',[(row['profile'],row['clip'],row['source'],row['method'],row['score']) for row in before])
        db.executemany('INSERT INTO narration_reviews(profile,clip,reviewed,updated_at) VALUES (?,?,?,?)',[(row['profile'],row['clip'],row['reviewed'],row['updated_at']) for row in reviews])
        db.commit();db.close();raise
    save(name)
    return f'Áudio salvo e aplicado em Narrations\\{name}. A alteração será usada na próxima aplicação deste narrador na prévia.'

def new(name,commentator='',competitions=None):
    dest=folder(name)
    if (dest/'project.json').exists():raise ValueError('Já existe um projeto com esse nome. Abra-o para editar.')
    return save(name,commentator,competitions or [])

def names():
    result={'Tiago Leifert','Vilani','Luiz Roberto'}
    if PROJECTS.exists():result.update(p.name for p in PROJECTS.iterdir() if p.is_dir() and (p/'project.json').exists())
    result.update(path.name for path in profile_directories(narration_root(GAME)))
    return sorted(result,key=lambda n:({'Tiago Leifert':0,'Vilani':1,'Luiz Roberto':2}.get(n,3),n))

def clone(original,name):
    name=safe_name(name)
    if name in names():raise ValueError('Já existe um projeto com esse nome.')
    save(original);data=metadata(original);db=connect();sources={}
    for r in db.execute('SELECT * FROM sources WHERE narrator=?',(original,)).fetchall():
        key=name+':'+hashlib.sha256(r['path'].encode()).hexdigest()[:20];sources[r['key']]=key
        db.execute('INSERT OR IGNORE INTO sources (key,narrator,path,event,variant,transcript,confidence,duration,error,topic) VALUES (?,?,?,?,?,?,?,?,?,?)',(key,name,r['path'],r['event'],r['variant'],r['transcript'],r['confidence'],r['duration'],r['error'],r['topic']))
        db.execute('UPDATE sources SET topic_manual=?,origin_path=? WHERE key=?',(r['topic_manual'],r['origin_path'],key))
    for r in db.execute('SELECT * FROM mappings WHERE profile=?',(original,)).fetchall():db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',(name,r['clip'],sources[r['source']],r['method'],r['score']))
    for r in db.execute('SELECT clip,reviewed FROM narration_reviews WHERE profile=?',(original,)).fetchall():
        db.execute('INSERT OR REPLACE INTO narration_reviews(profile,clip,reviewed) VALUES (?,?,?)',(name,r['clip'],r['reviewed']))
    db.commit();db.close();return save(name,data.get('commentator',''),data.get('competitions',[]))

def build(name):
    project=save(name);data=metadata(name);export=project/'build';export.mkdir(exist_ok=True)
    portrait=data.get('portrait','')
    if portrait and (project/portrait).is_file():shutil.copy2(project/portrait,export/'portrait.png')
    (export/'profile.json').write_text(json.dumps({k:v for k,v in data.items() if k not in ('mappings','format')},ensure_ascii=False,indent=2),encoding='utf8')
    compile_profile(name,destination=export)
    if json.loads((export/'profile.json').read_text(encoding='utf8'))['failed']:raise ValueError('A geração encontrou falhas. Confira build_report.json; o pacote instalado foi preservado.')
    deployed=install_profile(export,name,GAME)
    return f'Pacote criado e instalado: {deployed}. Aplique o narrador na prévia.'

def install_profile(export,name,game_root):
    """Install only assets consumed by the game; keep editing data in Studio."""
    export=Path(export)
    deployed=profile_directory(game_root,name)
    deployed.mkdir(parents=True,exist_ok=True)
    for filename in ('profile.npack','profile.json','narrator.txt','portrait.png'):
        source=export/filename
        if source.is_file():
            temporary=deployed/(filename+'.new')
            shutil.copy2(source,temporary)
            temporary.replace(deployed/filename)
    return deployed

def unpack(package):
    """Streaming reader: preserve complete SPS, validate before extraction."""
    with Path(package).open('rb') as f:
        def read(size):
            data=f.read(size)
            if len(data)!=size:raise ValueError('Pacote truncado.')
            return data
        def u32():return struct.unpack('<I',read(4))[0]
        magic=read(8)
        if magic not in (b'F16NPK2\0',b'F16NPK3\0'):raise ValueError('Formato de pacote não suportado.')
        pooled=magic==b'F16NPK3\0';pool=[]
        if pooled:
            count=u32()
            if count>100000:raise ValueError('Pacote inválido: áudios demais.')
            for _ in range(count):
                size=u32()
                if size>64*1024*1024 or size<12:raise ValueError('Áudio inválido.')
                pool.append(read(size))
        banks=u32()
        if banks>64:raise ValueError('Pacote inválido: bancos demais.')
        for _ in range(banks):
            length=u32()
            if length>1024:raise ValueError('Caminho inválido no pacote.')
            bank=read(length*2).decode('utf-16le').replace('\\','/').lower()
            if not bank.startswith('audiodata/speechdata/por_br/') or '..' in bank:raise ValueError('Banco inválido.')
            count=u32()
            if count>100000:raise ValueError('Pacote inválido: áudios demais.')
            for _ in range(count):
                offset=struct.unpack('<Q',read(8))[0];size=u32()
                if pooled:
                    if size>=len(pool):raise ValueError('Referência de áudio inválida.')
                    data=pool[size]
                else:
                    if size>64*1024*1024 or size<12:raise ValueError('Áudio inválido.')
                    data=read(size)
                if data[0]!=0x48:raise ValueError('Cabeçalho SPS inválido.')
                yield bank,offset,data
        if f.read(1):raise ValueError('Dados adicionais inesperados no pacote.')

def open_project(path):
    src=Path(path);src=src.parent if src.is_file() else src
    if (src/'Studio'/'project.json').is_file():src=src/'Studio'
    manifest=src/'project.json';meta=src/'profile.json'
    data=json.loads((manifest if manifest.exists() else meta).read_text(encoding='utf8'))
    name=safe_name(data['name']);dest=folder(name);dest.mkdir(parents=True,exist_ok=True)
    def relocated(value):
        if Path(value).exists():return value
        normalized=str(value).replace('\\','/');marker='/Narrations/'+name+'/Studio/assets/'
        if marker.casefold() in normalized.casefold():
            start=normalized.casefold().index(marker.casefold())+len(marker)
            candidate=assets_folder(name)/normalized[start:]
            if candidate.exists():return str(candidate)
        return value
    for row in data.get('mappings',[]):row['path']=relocated(row['path'])
    db=connect()
    for asset in data.get('assets',[]):
        asset['path']=relocated(asset['path'])
        if not Path(asset['path']).is_file():continue
        db.execute('INSERT OR IGNORE INTO sources(key,narrator,path,event,variant,transcript,confidence,duration,topic,topic_manual,origin_path) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (asset['key'],name,asset['path'],asset.get('event',''),asset.get('variant',-1),asset.get('transcript',''),asset.get('confidence'),asset.get('duration',0),asset.get('topic',''),asset.get('topic_manual',0),asset.get('origin_path','')))
        if asset.get('topic_manual'):db.execute('UPDATE sources SET topic=?,topic_manual=1 WHERE key=?',(asset['topic'],asset['key']))
    db.commit();db.close()
    folder_index=src/'library_folders.json'
    if folder_index.is_file():shutil.copy2(folder_index,dest/'library_folders.json')
    if manifest.exists() and all(Path(r['path']).exists() for r in data.get('mappings',[])):
        db=connect()
        for r in data.get('mappings',[]):
            db.execute('INSERT OR IGNORE INTO sources (key,narrator,path,event,variant,transcript,confidence,duration) VALUES (?,?,?,?,?,?,?,?)',(r['source'],name,r['path'],r.get('source_event',''),r.get('variant',-1),r.get('transcript',''),r.get('confidence'),r.get('duration',0)))
            if db.execute('SELECT 1 FROM clips WHERE key=?',(r['clip'],)).fetchone():db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',(name,r['clip'],r['source'],r.get('method','manual'),r.get('score',1)))
        db.commit();db.close()
    else:
        package=src/data.get('package','profile.npack')
        if not Path(package).is_absolute():package=src/package
        if not Path(package).is_file() and (src.parent/'profile.npack').is_file():package=src.parent/'profile.npack'
        media=assets_folder(name)/'Recuperados';media.mkdir(parents=True,exist_ok=True)
        entries=[];unique={}
        for bank,offset,payload in unpack(package):
            token=hashlib.sha256(payload).hexdigest()[:24];sps=media/(token+'.sps');wav=sps.with_suffix('.wav')
            if token not in unique:
                sps.write_bytes(payload);unique[token]=(sps,wav)
            entries.append((bank,offset,str(wav)))
        def decode(item):
            sps,wav=item
            if not wav.exists():subprocess.run([str(VGM),'-i','-o',str(wav),str(sps)],check=True,capture_output=True,creationflags=0x08000000)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(decode,unique.values()))
        import_sources(name,media);db=connect()
        lookup=collections.defaultdict(list)
        for r in db.execute('SELECT c.key,c.wav,b.name FROM clips c JOIN banks b ON c.bank=b.key WHERE b.active=1'):
            lookup[(r['name'].lower(),int(Path(r['wav']).stem,16))].append(r['key'])
        for bank,offset,wav in entries:
            source=db.execute('SELECT key FROM sources WHERE narrator=? AND path=?',(name,wav)).fetchone()
            for clip in lookup[(Path(bank).stem,offset)]:db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',(name,clip,source['key'],'manual',1))
        db.commit();db.close()
    if data.get('reviewed'):
        db=connect()
        for clip in data['reviewed']:
            if db.execute('SELECT 1 FROM clips WHERE key=?',(clip,)).fetchone():
                db.execute('INSERT OR REPLACE INTO narration_reviews(profile,clip,reviewed) VALUES (?,?,1)',(name,clip))
        db.commit();db.close()
    portrait=data.get('portrait','portrait.png')
    if (src/portrait).is_file():
        if (src/portrait).resolve()!=(dest/'portrait.png').resolve():shutil.copy2(src/portrait,dest/'portrait.png')
        data['portrait']='portrait.png'
    (dest/'project.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    save(name);return name
