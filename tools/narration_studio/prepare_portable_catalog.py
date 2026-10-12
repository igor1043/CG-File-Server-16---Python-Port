"""Copy an editable catalogue into the game without altering original assets."""
from pathlib import Path
import sqlite3,shutil,json,os
from core import connect,WORK,GAME

def main():
    dest=GAME/'Narrations/.studio';dest.mkdir(parents=True,exist_ok=True)
    print('Opening source catalogue',flush=True)
    source=connect();db=sqlite3.connect(dest/'catalog.sqlite')
    print('Backing up catalogue',flush=True)
    source.backup(db,pages=256,progress=lambda status,remaining,total:print('Backup pages remaining:',remaining,flush=True) if remaining%1024==0 else None);source.close();db.close()
    db=sqlite3.connect(dest/'catalog.sqlite');db.row_factory=sqlite3.Row
    paths={r['wav'] for r in db.execute("SELECT wav FROM clips WHERE status='decoded'")}
    print('Listing original files:',len(paths),flush=True)
    existing={str(Path(base)/name) for base,dirs,files in os.walk(dest/'original_wav') for name in files}
    missing=[]
    for old in paths:
        original=Path(old);target=dest/'original_wav'/original.parent.name/original.name
        if str(target) not in existing:missing.append((original,target))
    print('Computing copy size:',len(missing),flush=True)
    sizes={}
    for directory in {p.parent for p,t in missing}:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file():sizes[str(directory/entry.name)]=entry.stat().st_size
    needed=sum(sizes[str(p)] for p,t in missing)
    free=shutil.disk_usage(dest).free
    print(json.dumps(dict(original_files=len(paths),copy_files=len(missing),needed=needed,free=free)),flush=True)
    if free<needed+2*1024**3:raise RuntimeError('Espaço insuficiente para o catálogo editável; nenhuma cópia iniciada.')
    folders=set()
    for index,(original,target) in enumerate(missing):
        if target.parent not in folders:target.parent.mkdir(parents=True,exist_ok=True);folders.add(target.parent)
        shutil.copy2(original,target)
        if index%1000==0:print('Originals copied:',index,flush=True)
    db.execute('CREATE TEMP TABLE relocated_wavs(old TEXT PRIMARY KEY,new TEXT)')
    db.executemany('INSERT INTO relocated_wavs VALUES (?,?)',[(old,str(dest/'original_wav'/Path(old).parent.name/Path(old).name)) for old in paths])
    db.execute('UPDATE clips SET wav=(SELECT new FROM relocated_wavs WHERE old=clips.wav) WHERE wav IN (SELECT old FROM relocated_wavs)')
    for folder in ('banks','metadata','transcriptions'):
        if (WORK/folder).is_dir():shutil.copytree(WORK/folder,dest/folder,dirs_exist_ok=True)
    if (WORK/'generic_curated.json').exists():shutil.copy2(WORK/'generic_curated.json',dest/'generic_curated.json')
    for row in db.execute('SELECT key,sbr FROM banks').fetchall():
        db.execute('UPDATE banks SET sbr=? WHERE key=?',(str(dest/'banks'/Path(row['sbr']).name),row['key']))
    db.commit();db.close()
    # Existing compiled narrators also retain editing project metadata.
    projects=Path(r'J:\mods\fifa 16\NarrationStudio\Projects')
    for folder in projects.iterdir():
        if folder.is_dir():
            for filename in ('project.json','portrait.png','library_folders.json'):
                if (folder/filename).exists():shutil.copy2(folder/filename,GAME/'Narrations'/folder.name/filename)
    (dest/'catalog_ready.json').write_text(json.dumps(dict(original_files=len(paths),state='complete')),encoding='utf8')
    print('Portable catalogue ready:',str(dest),flush=True)

if __name__=='__main__':main()
