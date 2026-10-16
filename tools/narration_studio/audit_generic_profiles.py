"""Validate reviewed associations and export before/after evidence."""
from pathlib import Path
import collections,json,sqlite3
from core import connect,GAME,WORK
from generic_policy import blocked_reasons,intro_role,reviewed_pools

def audit():
    current=connect()
    backup=Path((WORK/'generic_backup_path.txt').read_text(encoding='utf8'))
    old=sqlite3.connect(str(backup/'catalog.sqlite'));old.row_factory=sqlite3.Row
    for narrator in ('Vilani','Luiz Roberto'):
        rows=current.execute('''SELECT c.key,c.event,c.bank,c.offset,s.key source_key,s.event source_event,
            s.path,s.transcript,s.confidence,m.method FROM mappings m JOIN clips c ON m.clip=c.key
            JOIN sources s ON m.source=s.key WHERE m.profile=? ORDER BY c.event,c.row''',(narrator,)).fetchall()
        previous={r['key']:dict(r) for r in old.execute('''SELECT c.key,c.event,s.path,s.transcript
            FROM mappings m JOIN clips c ON m.clip=c.key JOIN sources s ON m.source=s.key WHERE m.profile=?''',(narrator,))}
        issues=[];seen={};changes=[];roles=collections.Counter()
        for row in rows:
            r=dict(row);source=dict(event=r['source_event'],transcript=r['transcript'])
            reasons=blocked_reasons(source)
            if reasons:issues.append(dict(clip=r['key'],reasons=reasons,path=r['path']))
            identity=(r['bank'],r['offset'])
            if identity in seen and seen[identity]!=r['source_key']:issues.append(dict(clip=r['key'],reasons=['alias com associação diferente']))
            seen[identity]=r['source_key']
            role=intro_role(r['event'])
            if role:
                roles[role]+=1
                if r['path'] not in reviewed_pools()[narrator][role]:issues.append(dict(clip=r['key'],reasons=['abertura fora da biblioteca aprovada'],path=r['path']))
            before=previous.get(r['key'])
            if before is None or before['path']!=r['path']:
                changes.append(dict(clip=r['key'],event=r['event'],role=role,old_transcript=before['transcript'] if before else '[sem associação]',new_transcript=r['transcript'],new_source=r['path'],method=r['method']))
        summary=dict(narrator=narrator,before=len(previous),after=len(rows),physical=len(seen),changed=len(changes),intro_roles=dict(roles),issues=len(issues),policy='generic_base_v1',backup=str(backup))
        destination=GAME/'Narrations'/narrator/'generic_review.json'
        destination.write_text(json.dumps(dict(summary=summary,issues=issues,changes=changes),ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(summary,ensure_ascii=False),flush=True)
        assert not issues,json.dumps(issues[:5],ensure_ascii=False)
    old.close();current.close()

if __name__=='__main__':audit()
