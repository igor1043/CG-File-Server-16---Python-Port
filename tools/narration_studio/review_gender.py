"""Correct known feminine variants without recomputing the full project."""
from pathlib import Path
import collections,json
from core import connect,GAME
from generic_policy import female_reference,blocked_reasons

def review(name='Vilani'):
    db=connect();sources=[dict(r) for r in db.execute('SELECT * FROM sources WHERE narrator=?',(name,))];pool=collections.defaultdict(list)
    for s in sources:
        if not blocked_reasons(s) and Path(s['path']).exists():pool[s['event']].append(s)
    rows=db.execute('''SELECT c.bank,c.offset,c.key,c.event,c.row,s.key source,s.event source_event,s.transcript,s.path
        FROM mappings m JOIN clips c ON m.clip=c.key JOIN sources s ON m.source=s.key WHERE profile=?''',(name,)).fetchall()
    seen=set();report=[]
    with db:
        for row in rows:
            r=dict(row);identity=(r['bank'],r['offset'])
            if identity in seen or not female_reference(r['transcript']):continue
            seen.add(identity);candidates=pool[r['source_event']]
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',identity).fetchall()
            source=candidates[r['row']%len(candidates)] if candidates else None
            for alias in aliases:
                if source:db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',(name,alias['key'],source['key'],'gender_review',1))
                else:db.execute('DELETE FROM mappings WHERE profile=? AND clip=?',(name,alias['key']))
            report.append(dict(event=r['event'],old=r['transcript'],replacement=source['transcript'] if source else '[original do FIFA]',count=len(aliases)))
    remaining=db.execute('''SELECT s.transcript FROM mappings m JOIN sources s ON m.source=s.key WHERE profile=?''',(name,)).fetchall()
    assert not any(female_reference(r[0]) for r in remaining)
    summary=dict(narrator=name,reviewed=len(seen),changed=sum(r['count'] for r in report),remaining_female_references=0)
    (GAME/'Narrations'/name/'gender_review.json').write_text(json.dumps(dict(summary=summary,changes=report),ensure_ascii=False,indent=2),encoding='utf8');print(summary,flush=True);db.close();return report

if __name__=='__main__':review()
