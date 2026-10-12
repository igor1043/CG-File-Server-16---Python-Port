"""Match club call names by equal spoken text, never by PES/FIFA numeric IDs."""
import collections,json
from core import connect
from generic_policy import plain

def canonical(text):
    text=plain(text or '')
    if not text or text=='sem fala detectada' or len(text)>80 or len(text.split())>6:return ''
    return text.replace(' ','')

def run(name):
    db=connect();sources=collections.defaultdict(list)
    for row in db.execute("SELECT * FROM sources WHERE narrator=? AND topic=? AND transcript!='' AND error=''",(name,'Nomes de clubes')):
        key=canonical(row['transcript'])
        if key:sources[key].append(dict(row))
    preserved={row['clip'] for row in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','boundary_cleanup','gender_review')",(name,))}
    updates=[];seen=set();used=collections.Counter()
    for row in db.execute('SELECT c.* FROM clips c JOIN banks b ON c.bank=b.key WHERE b.active=1 AND c.topic=? ORDER BY c.bank,c.offset',('Nomes de clubes',)):
        identity=(row['bank'],row['offset'])
        if identity in seen:continue
        seen.add(identity);pool=sources.get(canonical(row['transcript']),[])
        if not pool:continue
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',identity).fetchall()
        if any(alias['key'] in preserved for alias in aliases):continue
        source=min(pool,key=lambda candidate:(used[candidate['key']],candidate['path']))
        used[source['key']]+=1
        updates.extend((name,alias['key'],source['key'],'club_transcript_exact',1) for alias in aliases)
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method='club_transcript_exact'",(name,))
        db.executemany('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',updates)
    db.close();report=dict(narrator=name,club_occurrences=len(updates),unique_recordings=len(used),review_required=True)
    print(json.dumps(report,ensure_ascii=True),flush=True);return report

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('narrator');run(parser.parse_args().narrator)
