"""Create sentence-complete neutral excerpts and explicit opening pools."""
from pathlib import Path
import hashlib,json,subprocess,wave
from core import connect,GAME,WORK,import_sources
from generic_policy import blocked_reasons

def prepare():
    # These boundaries lie in pauses between complete sentences, checked
    # against luiz_generic_word_times.json. Full recordings remain intact.
    root=Path(r'J:\mods\fifa 16\03_Recursos\narrations\Luiz Roberto\source_wav')
    dest=GAME/'Narrations/Luiz Roberto/source/generic_curated';dest.mkdir(parents=True,exist_ok=True)
    recipes=(
        ('GENERIC_WELCOME','30_MAIN.awb.00020.wav',0,4.24,'Você ligado na Globo a partir de agora, entra no clima do jogão!'),
        ('GENERIC_LINEUP','30_MAIN.awb.00269.wav',0,4.78,'E nós temos a disposição tática do time desta forma. Taticamente o time é esse.'),
        ('GENERIC_EXPECTATION_1','30_MAIN.awb.00269.wav',6.29,9.14,'Jogo recheado de craques dos dois lados.'),
        ('GENERIC_EXPECTATION_2','30_MAIN.awb.00269.wav',9.30,14.02,'Então a gente fica naquela expectativa. E quem pode se destacar num jogo como esse?'),
    )
    report=[]
    for name,source,start,end,text in recipes:
        target=dest/(name+'.wav')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(root/source),'-ss',str(start),'-t',str(end-start),'-ac','1','-ar','32000','-c:a','pcm_s16le',str(target)],check=True,capture_output=True,creationflags=0x08000000)
        with wave.open(str(target)) as w:duration=w.getnframes()/w.getframerate()
        assert abs(duration-(end-start))<.002
        report.append(dict(path=str(target),original=str(root/source),start=start,end=end,transcript=text,duration=duration,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    import_sources('Luiz Roberto',dest)
    db=connect()
    for r in report:db.execute('UPDATE sources SET event=?,transcript=?,confidence=0,duration=?,topic=? WHERE path=?',(Path(r['path']).stem,r['transcript'],r['duration'],'Abertura e apresentação',r['path']))
    db.commit()
    pools={'Vilani':dict(welcome=[],lineup=[],expectation=[]),'Luiz Roberto':dict(welcome=[report[0]['path']],lineup=[report[1]['path']],expectation=[r['path'] for r in report[2:]])}
    for row in db.execute("SELECT * FROM sources WHERE narrator='Vilani' ORDER BY event,variant,path"):
        s=dict(row);e=s['event']
        if blocked_reasons(s):continue
        if e=='bINTRO_SEQ1_COMMENTATORS_STITCH' and 'caio' in s['transcript'].casefold():pools['Vilani']['welcome'].append(s['path'])
        elif e=='bINTRO_SEQ1_WELCOME_STITCH':pools['Vilani']['welcome'].append(s['path'])
        elif e=='bTS_TEAM_INTRO' and s['variant'] in (13,14,15,16,17):pools['Vilani']['lineup'].append(s['path'])
        elif e in ('bINTRO_SEQ1_GENERIC','bINTRO_SEQ2_GENERIC'):pools['Vilani']['expectation'].append(s['path'])
    for narrator,roles in pools.items():
        for role,paths in roles.items():assert paths,(narrator,role)
    (WORK/'generic_curated.json').write_text(json.dumps(pools,ensure_ascii=False,indent=2),encoding='utf8')
    (dest/'segment_origins.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({n:{k:len(v) for k,v in p.items()} for n,p in pools.items()},ensure_ascii=False))
    db.close()

if __name__=='__main__':prepare()
