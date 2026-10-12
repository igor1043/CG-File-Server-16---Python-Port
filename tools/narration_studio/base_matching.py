"""Exhaustive base-event matching, with physical aliases and names kept safe."""
from pathlib import Path
import collections,hashlib,json,re
from core import connect,WORK
from matching import model,MODEL as MATCHING_MODEL
from topics import topic as classify
from generic_policy import approved_pool,proposed_opening_pool,blocked_reasons,candidate_allowed,intro_role,reference
MAX_SOURCE_REUSE=8

EXCLUDED=('Call names de jogadores','Nomes de clubes')
def eligible(row):
    e=row['event'].upper()
    return row['topic'] not in EXCLUDED and not (e.startswith('P') and any(t in e for t in ('PLAYER','SPECIFIC','SURNAME','NAMES')))

def normalized(event):
    return re.sub('[^A-Z0-9]','',event.upper().replace('GENERIC','GEN').replace('ATTACKING','ATTACK'))

def description(event):
    text=event[1:].replace('_',' ').lower()
    return re.sub(r'\b(seq\d+|gen|c|m|pb|hr|ptw)\b',' ',text).strip()

def compatible(left,right):
    a=left.upper();b=right.upper()
    # A goal must never become a miss, or an own goal an ordinary score.
    goal=lambda e:any(t in e for t in ('GOAL_SCORED','C_GOAL_','REPLAY_GOAL','CONSOLATION_GOAL'))
    miss=lambda e:any(t in e for t in ('MISS','NO_GOAL','SHOTWIDE'))
    if goal(a) and miss(b) or miss(a) and goal(b):return False
    if ('OWNGOAL' in a or 'OWN_GOAL' in a)!=('OWNGOAL' in b or 'OWN_GOAL' in b):return False
    halftime=lambda e:e.startswith(('BHT_','PHT_','MHT_')) or 'HALFTIME' in e or '_HT_' in e
    fulltime=lambda e:e.startswith(('BFT_','PFT_','MFT_')) or 'FULLTIME' in e or '_FT_' in e
    if halftime(a) and fulltime(b) or fulltime(a) and halftime(b):return False
    champion=lambda e:any(t in e for t in ('CHAMPION','CUP_FINAL','LEAGUE_TITLE'))
    if champion(b) and not champion(a):return False
    positive=lambda e:bool(re.search(r'(?:^|_)(WIN|WON|WINNING|LEADING)(?:_|$)',e))
    negative=lambda e:bool(re.search(r'(?:^|_)(LOSS|LOST|LOSING)(?:_|$)',e))
    if positive(a) and not negative(a) and negative(b) and not positive(b):return False
    if negative(a) and not positive(a) and positive(b) and not negative(b):return False
    return True

def seed(narrator,threshold=.64):
    print('Preparing association model',narrator,flush=True)
    import torch
    from threadpoolctl import threadpool_limits
    import numpy as np
    torch.set_num_threads(4)
    # Small repeated matrix products must not start dozens of BLAS threads.
    blas_limit=threadpool_limits(limits=4,user_api='blas')
    db=connect()
    originals=[dict(r) for r in db.execute('''SELECT c.*,b.name AS bank_name FROM clips c JOIN banks b ON b.key=c.bank
        WHERE b.active=1 ORDER BY c.bank,c.offset,c.key''') if eligible(r) or intro_role(r['event'])]
    sources=[dict(r) for r in db.execute('SELECT * FROM sources WHERE narrator=? AND error=\'\' ORDER BY event,variant,path',(narrator,)) if eligible(r) and Path(r['path']).stat().st_size>=45]
    for r in originals+sources:r['topic']=classify(r['event'],r.get('path',''),r['transcript'])
    rejected=[dict(source=s['path'],event=s['event'],transcript=s['transcript'],reasons=blocked_reasons(s)) for s in sources if blocked_reasons(s)]
    sources=[s for s in sources if not blocked_reasons(s)]
    opening_pools={role:approved_pool(narrator,role,sources) for role in ('welcome','lineup','expectation')}
    proposed_roles=set()
    for role,pool in opening_pools.items():
        if not pool:
            opening_pools[role]=proposed_opening_pool(role,sources);proposed_roles.add(role)
    by_event=collections.defaultdict(list)
    for s in sources:
        if s['event']:by_event[s['event']].append(s)
    canonical={normalized(e):e for e in by_event}
    original_events={r['event']:r for r in originals}
    event_matches={}
    encoder=model()
    print('Matching event references',narrator,len(original_events),flush=True)
    for topic in sorted({r['topic'] for r in originals}):
        left=[e for e,r in original_events.items() if r['topic']==topic]
        right=[e for e,rows in by_event.items() if rows[0]['topic']==topic]
        if not left or not right:continue
        lv=encoder.encode([description(e) for e in left],normalize_embeddings=True,show_progress_bar=False)
        rv=encoder.encode([description(e) for e in right],normalize_embeddings=True,show_progress_bar=False)
        scores=lv@rv.T
        for i,e in enumerate(left):
            for j in scores[i].argsort()[::-1][:12]:
                score=float(scores[i,j]);target=right[j]
                if score<threshold:break
                if compatible(e,target):event_matches[e]=(target,score);break
    # PES recordings have no event names. Match their reviewed transcripts
    # against original speech, or against the event meaning when pending.
    spoken=[s for s in sources if s['transcript'] and s['transcript']!='[sem fala detectada]' and (s['confidence'] is None or s['confidence']>-.8)]
    spoken_vectors=encoder.encode([s['transcript'] for s in spoken],normalize_embeddings=True,show_progress_bar=False) if spoken else None
    queries=[r['transcript'] if r['transcript'] and r['transcript']!='[sem fala detectada]' else reference(r['event']) or description(r['event']) for r in originals]
    scene_queries=[reference(r['event']) for r in originals]
    unique_queries=list(dict.fromkeys(queries+[query for query in scene_queries if query]))
    print('Encoding speech references',narrator,len(unique_queries),'sources',len(spoken),flush=True)
    encoded_queries=None
    if spoken:
        # FIFA-side references are shared by every narrator. Cache their
        # normalized vectors so a batch build encodes the 20k+ queries once.
        cache_dir=WORK/'embedding_cache';cache_dir.mkdir(parents=True,exist_ok=True)
        cache_path=cache_dir/(hashlib.sha1(MATCHING_MODEL.encode('utf8')).hexdigest()[:12]+'.npz')
        cached_queries=[];cached_vectors=np.empty((0,0),dtype='float32')
        if cache_path.is_file():
            try:
                with np.load(cache_path,allow_pickle=False) as cache:
                    cached_queries=cache['queries'].astype(str).tolist()
                    cached_vectors=cache['vectors'].astype('float32',copy=False)
            except (OSError,ValueError,KeyError):
                cached_queries=[];cached_vectors=np.empty((0,0),dtype='float32')
        cached={query:index for index,query in enumerate(cached_queries)}
        missing=[query for query in unique_queries if query not in cached]
        if missing:
            new_vectors=encoder.encode(missing,normalize_embeddings=True,batch_size=128,show_progress_bar=False)
            if cached_vectors.size:
                cached_vectors=np.vstack((cached_vectors,new_vectors))
            else:
                cached_vectors=new_vectors
            cached_queries.extend(missing)
            cached={query:index for index,query in enumerate(cached_queries)}
            temporary=cache_path.with_suffix('.tmp')
            with temporary.open('wb') as stream:
                np.savez(stream,queries=np.asarray(cached_queries,dtype=str),vectors=cached_vectors)
            temporary.replace(cache_path)
        encoded_queries=np.stack([cached_vectors[cached[query]] for query in unique_queries])
    rankings={}
    if encoded_queries is not None:
        # Rank each distinct reference once, in bounded matrix batches.
        # Many game variants use the same reference; avoid a BLAS call for
        # every physical sound and keep the temporary matrix under 2 MiB.
        for start in range(0,len(unique_queries),128):
            values=encoded_queries[start:start+128]@spoken_vectors.T
            for query,similarities in zip(unique_queries[start:start+128],values):
                indices=np.argsort(similarities)[::-1][:30]
                rankings[query]=[(int(j),float(similarities[j])) for j in indices if similarities[j]>=.60]
    print('Selecting compatible recordings',narrator,flush=True)
    preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
    source_uses=collections.Counter()
    for row in db.execute('''SELECT m.source,COUNT(DISTINCT c.bank||':'||c.offset) AS uses
        FROM mappings m JOIN clips c ON c.key=m.clip
        WHERE m.profile=? AND m.method IN ('manual','gender_review')
        GROUP BY m.source''',(narrator,)):
        source_uses[row['source']]=row['uses']
    seen=set();report=[];updates=[]
    for i,c in enumerate(originals):
        identity=(c['bank'],c['offset'])
        if identity in seen:continue
        seen.add(identity)
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',identity).fetchall()
        if any(a['key'] in preserved for a in aliases):continue
        event=c['event'];role=intro_role(event);target=canonical.get(normalized(event));score=1.;method='event_variation'
        if not target and event in event_matches:target,score=event_matches[event];method='event_semantic'
        source=None
        if role:
            pool=opening_pools[role]
            if not pool:continue
            if narrator=='Vilani' and 'HELLO' in event.upper():
                pool=[s for s in pool if s['event']=='bINTRO_SEQ1_COMMENTATORS_STITCH'] or pool
            elif narrator=='Vilani' and role=='expectation':
                preferred=[s for s in pool if s['event']==('bINTRO_SEQ2_GENERIC' if 'CNOTES' in event.upper() else 'bINTRO_SEQ1_GENERIC')]
                pool=preferred or pool
            available=[s for s in pool if source_uses[s['key']]<MAX_SOURCE_REUSE]
            if available:
                source=min(available,key=lambda s:(source_uses[s['key']],s['path']))
                method='speech_intro_suggestion' if role in proposed_roles else 'generic_intro'
        elif target:
            pool=[s for s in by_event[target] if candidate_allowed(c,s)]
            demo='demo' in c['bank_name'].lower()
            preferred=[s for s in pool if ('por_br_DEMO' in s['path'])==demo]
            pool=preferred or pool
            available=[s for s in pool if source_uses[s['key']]<MAX_SOURCE_REUSE]
            if available:
                source=next((s for s in available if s['variant']==c['row']),None)
                if source is None:source=min(available,key=lambda s:(source_uses[s['key']],s['path']))
        if not source and not role and rankings:
            # A generic recording can fit the scene even when the original
            # sentence names a particular team or player. Keep that proposal
            # slightly below a direct transcript match, with the same guards.
            candidates=dict(rankings[queries[i]])
            for j,value in rankings.get(scene_queries[i],[]):candidates[j]=max(candidates.get(j,0),value*.97)
            for j,value in sorted(candidates.items(),key=lambda item:item[1],reverse=True):
                candidate=spoken[j]
                if source_uses[candidate['key']]>=MAX_SOURCE_REUSE:continue
                if candidate['confidence'] is None and value<.72:continue
                if not candidate_allowed(c,candidate):continue
                if candidate['topic']!=c['topic'] and not (candidate['topic']=='Outros comentários' and c['topic'] in ('Abertura e apresentação','Intervalo e resultado','Outros comentários')):continue
                lower=candidate['transcript'].casefold()
                if c['topic']=='Gols' and any(t in lower for t in ('não entrou','quase entrou','não foi gol')):continue
                source=candidate;score=value;method='speech_semantic';break
        if not source:continue
        source_uses[source['key']]+=1
        updates.extend((narrator,a['key'],source['key'],method,score) for a in aliases)
        report.append(dict(clip=c['key'],event=event,reference=reference(event),original=c['transcript'],replacement=source['transcript'],source_event=source['event'],source=source['path'],method=method,score=score,review=method not in ('event_variation','generic_intro')))
    # Keep the previous usable project available during model inference.
    # Replace automatic associations together, preserving manual edits.
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method IN ('boundary_cleanup','event_semantic','event_variation','speech_semantic','speech_intro_suggestion','event_variant','intro_test','curated_test','semantic_test','generic_intro')",(narrator,))
        db.executemany('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',updates)
    total=db.execute('SELECT count(*) FROM mappings WHERE profile=?',(narrator,)).fetchone()[0]
    summary=dict(narrator=narrator,new_physical=len(report),mapped_occurrences=total,eligible_physical=len(seen),generic_intro=sum(r['method']=='generic_intro' for r in report),rejected_sources=len(rejected),max_source_reuse=MAX_SOURCE_REUSE,review_required=True)
    out=WORK/'transcriptions';out.mkdir(exist_ok=True)
    (out/(narrator+'_base_associations.json')).write_text(json.dumps(dict(summary=summary,associations=report,rejected_sources=rejected),ensure_ascii=False,indent=2),encoding='utf8')
    db.close();blas_limit.restore_original_limits();print(json.dumps(summary,ensure_ascii=False),flush=True);return summary

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('narrator');p.add_argument('--threshold',type=float,default=.64);a=p.parse_args();seed(a.narrator,a.threshold)
