"""Index every supplied PES waveform; deduplicate identical encoded assets."""
from pathlib import Path
import json,hashlib,time,collections,shutil,os
from pes_archives import awb_entries,audio_header

SOURCE=Path(r'J:\mods\pes\audio pes\content\Multinarrador')
DEST=Path(r'J:\mods\fifa 16\narrações fifa')
WORK=Path(__file__).parent
ALIASES={'Gustavo Villani':'Vilani','Luis Roberto':'Luiz Roberto'}

def run():
    DEST.mkdir(parents=True,exist_ok=True);unique={};summaries=[];started=time.time();done=0
    for folder in sorted(SOURCE.iterdir()):
        if not folder.is_dir() or not list(folder.rglob('*.awb')):continue
        name=ALIASES.get(folder.name,folder.name);dest=DEST/name;dest.mkdir(exist_ok=True);(dest/'indexes').mkdir(exist_ok=True)
        cached=dest/'indexes/pes_references.json'
        if cached.is_file():
            references=json.loads(cached.read_text(encoding='utf8'))
            for ref in references:
                if ref['codec']=='hca' and ref.get('duration') is None:
                    with Path(ref['archive']).open('rb') as file:
                        file.seek(ref['offset']);ref.update(audio_header(file.read(min(128,ref['size']))))
                unique.setdefault(ref['sha256'],ref)
            summary=dict(narrator=name,source=str(folder),references=len(references),unique=len({r['sha256'] for r in references}),total_duration=sum(r['duration'] or 0 for r in references),empty=sum(r.get('duration')==0 for r in references))
            summaries.append(summary);done+=len(references);print(json.dumps(summary,ensure_ascii=True),flush=True)
            cached.write_text(json.dumps(references,ensure_ascii=False,separators=(',',':')),encoding='utf8')
            continue
        references=[];local=set();duration=0;empty=0
        for awb in sorted(folder.rglob('*.awb')):
            bank=awb.stem
            for entry in awb_entries(awb):
                data=entry.pop('data');token=hashlib.sha256(data).hexdigest();header=audio_header(data)
                ref=dict(narrator=name,bank=bank,archive=str(awb),sha256=token,**entry,**header)
                references.append(ref);local.add(token)
                duration+=header['duration'] or 0;empty+=header['duration']==0
                if token not in unique:unique[token]=ref
                done+=1
            (WORK/'pes_index_progress.json').write_text(json.dumps(dict(state='indexing',narrator=name,references=done,unique=len(unique),elapsed=round(time.time()-started))),encoding='utf8')
        path=dest/'indexes/pes_references.json';path.write_text(json.dumps(references,ensure_ascii=False,separators=(',',':')),encoding='utf8')
        summary=dict(narrator=name,source=str(folder),references=len(references),unique=len(local),total_duration=duration,empty=empty)
        summaries.append(summary);print(json.dumps(summary,ensure_ascii=True),flush=True)
        # The ACB metadata is small and retains cue/sequence information.
        for acb in folder.rglob('*.acb'):
            target=dest/'indexes/acb'/acb.name;target.parent.mkdir(exist_ok=True);shutil.copy2(acb,target)
    output=dict(state='indexed',voices=summaries,unique=list(unique.values()),references=done,elapsed=round(time.time()-started),free_bytes=shutil.disk_usage(DEST).free)
    (WORK/'pes_unique_assets.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    (WORK/'pes_index_progress.json').write_text(json.dumps({k:v for k,v in output.items() if k!='unique'},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(unique=len(unique),unique_bytes=sum(r['size'] for r in unique.values()),unique_duration=sum(r['duration'] or 0 for r in unique.values()),references=done,elapsed=output['elapsed'],free_bytes=output['free_bytes'])),flush=True)

if __name__=='__main__':run()
