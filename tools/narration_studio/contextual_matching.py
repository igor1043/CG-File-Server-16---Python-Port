"""Context constrained mappings for player calls, formations and weather."""
from __future__ import annotations
import collections,json,re,unicodedata
from pathlib import Path
from core import connect,WORK
from generic_policy import plain

NUMBER_WORDS={'um':'1','uma':'1','dois':'2','duas':'2','tres':'3','quatro':'4','cinco':'5','seis':'6'}
STOP=set('o a os as um uma de do da dos das que e e no na nos nas para por como mais menos esse essa esta este time equipe vai jogar jogo hoje esquema tatica formacao tecnico treinador campo meio defesa ataque ofensivo ofensiva defensivo defensiva com jogadores jogador ali bem muito'.split())

def formations(text):
    value=plain(text or '')
    found=set()
    for m in re.finditer(r'(?<!\d)(\d{3,4})(?!\d)',value):
        raw=m.group(1);nums=tuple(int(c) for c in raw)
        if len(nums) in (3,4) and sum(nums)==10 and 3<=nums[0]<=5 and all(1<=n<=5 for n in nums[1:]):found.add('-'.join(map(str,nums)))
    tokens=re.findall(r'\d+|[a-z]+',value)
    nums=[NUMBER_WORDS.get(t,t if t.isdigit() else '') for t in tokens]
    for width in (3,4):
        for i in range(len(nums)-width+1):
            seq=nums[i:i+width]
            if not all(seq):continue
            values=tuple(int(n) for n in seq)
            if sum(values)==10 and 3<=values[0]<=5 and all(1<=n<=5 for n in values[1:]):found.add('-'.join(map(str,values)))
    return found

def words(text):
    return {w for w in plain(text or '').split() if len(w)>2 and w not in STOP and not w.isdigit()}

def overlap(left,right):
    a,b=words(left),words(right)
    return len(a&b)/max(1,len(a|b))

def canon_name(text):
    value=plain(text or '')
    value=' '.join(value.split())
    if not value or value=='sem fala detectada' or len(value)>72 or len(value.split())>6:return ''
    return value

def weather_kind(event,text):
    e=(event or '').upper();t=plain(text or '')
    if any(x in e for x in ('RAIN','RAINY')):return 'rain'
    if 'SNOW' in e:return 'snow'
    if any(x in e for x in ('NO_RAIN','DRY','CLEAR_SKY','SUNNY')):return 'dry'
    if re.search(r'\b(sem chuva|nao chove|nao vai chover|tempo seco|sol forte|ceu aberto)\b',t):return 'dry'
    if re.search(r'\b(neve|nevando|nevar|snow)\b',t):return 'snow'
    if re.search(r'\b(chuva|chuvoso|chovendo|chove|chuvisco|temporal|rain)\b',t):return 'rain'
    return ''

def physical_clips(db,where,args=()):
    rows=db.execute('SELECT c.*,b.name bank_name FROM clips c JOIN banks b ON b.key=c.bank WHERE b.active=1 AND '+where+' ORDER BY c.bank,c.offset,c.key',args).fetchall()
    seen=set()
    for row in rows:
        identity=(row['bank'],row['offset'])
        if identity in seen:continue
        seen.add(identity);yield dict(row)

def put_aliases(db,narrator,clip,source,method,score):
    aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(clip['bank'],clip['offset'])).fetchall()
    db.executemany('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',[(narrator,a['key'],source,method,score) for a in aliases])
    return len(aliases)

def match_player_calls(db,narrator):
    sources=collections.defaultdict(list)
    for r in db.execute("SELECT * FROM sources WHERE narrator=? AND topic='Call names de jogadores' AND transcript!='' AND error='' AND event LIKE 'pPLAYER_NAMES%'",(narrator,)):
        if r['confidence'] is not None and r['confidence'] < -1.0:continue
        key=canon_name(r['transcript'])
        if key:sources[key].append(dict(r))
    rows=[];mapped=0
    preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
    for c in physical_clips(db,"c.topic='Call names de jogadores' AND c.transcript!='' AND c.event LIKE 'pPLAYER_NAMES%'"):
        key=canon_name(c['transcript']);pool=sources.get(key,[])
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
        if not pool or any(a['key'] in preserved for a in aliases):continue
        pool.sort(key=lambda s:(0 if 'SIMPLE' in s['event'] else 1 if 'HIGH' in s['event'] else 2,s['path']))
        source=pool[0];mapped+=put_aliases(db,narrator,c,source['key'],'player_call_exact',1.0)
        rows.append(dict(event=c['event'],original=c['transcript'],replacement=source['transcript'],source=source['path']))
    return dict(occurrences=mapped,physical=len(rows),unique_sources=len(sources),report=rows)

def match_formations(db,narrator):
    clips=list(physical_clips(db,"c.event IN ('bTS_FORMATION','bTS_FORMATION_REPEAT')"))
    sources=collections.defaultdict(list)
    for r in db.execute("SELECT * FROM sources WHERE narrator=? AND event IN ('bTS_FORMATION','bTS_FORMATION_REPEAT') AND transcript!='' AND error=''",(narrator,)):
        codes=tuple(sorted(formations(r['transcript'])))
        if 1<=len(codes)<=2:sources[(r['event'],codes)].append(dict(r))
    report=[];mapped=0
    # Delete numeric formation proposals first: only an identical spoken
    # formation set may replace the FIFA recording.
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method NOT IN ('manual','gender_review') AND clip IN (SELECT c.key FROM clips c JOIN banks b ON b.key=c.bank WHERE b.active=1 AND c.event IN ('bTS_FORMATION','bTS_FORMATION_REPEAT'))",(narrator,))
        used=collections.Counter()
        preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
        for c in clips:
            codes=tuple(sorted(formations(c['transcript'])))
            if not 1<=len(codes)<=2:continue
            pool=[s for s in sources.get((c['event'],codes),[]) if used[s['key']]<8]
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
            if not pool or any(a['key'] in preserved for a in aliases):continue
            pool.sort(key=lambda s:(-overlap(c['transcript'],s['transcript']),used[s['key']],s['path']))
            ranked=pool[:5];source=ranked[0];used[source['key']]+=1
            score=1.0-overlap(c['transcript'],source['transcript'])*.25
            mapped+=put_aliases(db,narrator,c,source['key'],'formation_same_shape',score)
            report.append(dict(event=c['event'],formation=list(codes),original=c['transcript'],replacement=source['transcript'],source=source['path'],alternatives=[dict(text=s['transcript'],path=s['path'],lexical_overlap=round(overlap(c['transcript'],s['transcript']),3)) for s in ranked]))
    return dict(occurrences=mapped,physical=len(report),source_formation_variants=len(sources),report=report)

def weather_scene(event):
    e=(event or '').upper()
    if any(x in e for x in ('RAINBOW','GOAL','MISS','FOUL','TCKL','REPLAY')):return False
    return 'WEATHER' in e or e.startswith('BINTRO') and any(x in e for x in ('RAIN','SNOW','DRY','CLEAR','SUNNY'))

def match_weather(db,narrator):
    clips=list(physical_clips(db,"(c.event LIKE '%WEATHER%' OR c.event LIKE '%RAIN%' OR c.event LIKE '%SNOW%') AND c.event NOT LIKE '%RAINBOW%'") )
    sources=collections.defaultdict(list)
    for r in db.execute("SELECT * FROM sources WHERE narrator=? AND (event LIKE '%WEATHER%' OR event LIKE '%RAIN%' OR event LIKE '%SNOW%') AND event NOT LIKE '%RAINBOW%' AND transcript!='' AND error=''",(narrator,)):
        if not weather_scene(r['event']):continue
        kind=weather_kind(r['event'],r['transcript']) or ('general' if 'WEATHER' in r['event'].upper() else '')
        if kind:sources[(r['event'],kind)].append(dict(r))
    report=[];mapped=0;used=collections.Counter()
    with db:
        preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
        for c in clips:
            if not weather_scene(c['event']):continue
            kind=weather_kind(c['event'],c['transcript']) or ('general' if 'WEATHER' in c['event'].upper() else '')
            if not kind:continue
            pool=[]
            for (event,state),rows in sources.items():
                if state!=kind:continue
                if event==c['event'] or (kind!='general' and 'WEATHER' in event.upper()):pool.extend(rows)
            pool=[s for s in pool if used[s['key']]<4]
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
            if not pool or any(a['key'] in preserved for a in aliases):continue
            pool.sort(key=lambda s:(-overlap(c['transcript'],s['transcript']),used[s['key']],s['path']))
            source=pool[0];used[source['key']]+=1
            mapped+=put_aliases(db,narrator,c,source['key'],'weather_same_condition',.95)
            report.append(dict(event=c['event'],condition=kind,original=c['transcript'],replacement=source['transcript'],source=source['path']))
    return dict(occurrences=mapped,physical=len(report),conditions={k:sum(1 for r in report if r['condition']==k) for k in ('rain','snow','dry','general')},report=report)

def run(narrator):
    db=connect()
    result=dict(narrator=narrator,player_calls=match_player_calls(db,narrator),formations=match_formations(db,narrator),weather=match_weather(db,narrator))
    dest=WORK/'transcriptions';dest.mkdir(exist_ok=True)
    (dest/(narrator+'_contextual_associations.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    db.close();print(json.dumps({k:(v if k=='narrator' else {key:val for key,val in v.items() if key!='report'}) for k,v in result.items()},ensure_ascii=False),flush=True)
    return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('narrator');run(p.parse_args().narrator)
