"""Complete editable reference indexes, including special player speech."""
import csv,json,collections
from core import connect,GAME,PROJECTS

def export():
    db=connect();dest=PROJECTS/'Original/indexes';dest.mkdir(parents=True,exist_ok=True)
    rows=[dict(r) for r in db.execute('SELECT key,event,bank,group_id,dataset_id,row,sound_id,offset,wav,duration,topic,transcript,status FROM clips ORDER BY topic,event,row')]
    groups={'all_occurrences':rows,'club_names':[r for r in rows if r['topic']=='Nomes de clubes'],'club_comments':[r for r in rows if r['topic']=='Comentários de clubes'],'competitions':[r for r in rows if r['topic']=='Campeonatos e competições'],'venues':[r for r in rows if r['topic']=='Estádios e cidades'],'player_call_names':[r for r in rows if r['topic']=='Call names de jogadores'],'special_player_comments':[r for r in rows if r['topic']=='Comentários de jogadores' or r['event'].upper().startswith(('PDEBUT','PSTORY','PRETIR','PLEGEND'))]}
    for name,items in groups.items():
        with (dest/(name+'.tsv')).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');writer.writeheader();writer.writerows(items)
    summary=dict(occurrences=len(rows),physical=len({r['wav'] for r in rows}),transcribed=sum(bool(r['transcript']) for r in rows),topics=dict(collections.Counter(r['topic'] for r in rows)),special_ronaldinho=sum('ronaldinho' in r['transcript'].casefold() for r in rows),scope='Bancos brasileiros encontrados na instalação U:\\fifa 16; referências lógicas do SBR, incluindo arquivos loose e bancos sobrepostos. Transcrição automática não prova o vínculo com um ID de jogador.')
    (dest/'coverage.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True);db.close();return dest

if __name__=='__main__':export()
