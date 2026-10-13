"""Context constrained mappings for player calls, formations and weather."""
from __future__ import annotations
import collections,json,re,unicodedata
from pathlib import Path
from core import connect,WORK
from generic_policy import plain,blocked_reasons,female_reference

NUMBER_WORDS={'um':'1','uma':'1','dois':'2','duas':'2','tres':'3','quatro':'4','cinco':'5','seis':'6'}
NUMBER_VALUES={**{word:int(value) for word,value in NUMBER_WORDS.items()},**{str(n):n for n in range(1,6)}}
STOP=set('o a os as um uma de do da dos das que e e no na nos nas para por como mais menos esse essa esta este time equipe vai jogar jogo hoje esquema tatica formacao tecnico treinador campo meio defesa ataque ofensivo ofensiva defensivo defensiva com jogadores jogador ali bem muito'.split())

def formations(text):
    value=plain(text or '')
    found=set()
    for m in re.finditer(r'(?<!\d)(\d{3,5})(?!\d)',value):
        raw=m.group(1);nums=tuple(int(c) for c in raw)
        if len(nums) in (3,4,5) and sum(nums)==10 and 3<=nums[0]<=5 and all(0<=n<=5 for n in nums[1:]):found.add('-'.join(map(str,nums)))
    for m in re.finditer(r'(?<!\d)([3-5])\s*[x/-]\s*([0-5])\s*[x/-]\s*([0-5])(?:\s*[x/-]\s*([0-5]))?(?:\s*[x/-]\s*([0-5]))?(?!\d)',value):
        nums=tuple(int(n) for n in m.groups() if n)
        if len(nums) in (3,4,5) and sum(nums)==10 and all(0<=n<=5 for n in nums[1:]):found.add('-'.join(map(str,nums)))
    tokens=re.findall(r'\d+|[a-z]+',value)
    nums=[NUMBER_WORDS.get(t,t if t.isdigit() else '') for t in tokens]
    for width in (3,4,5):
        for i in range(len(nums)-width+1):
            seq=nums[i:i+width]
            if not all(seq):continue
            values=tuple(int(n) for n in seq)
            if sum(values)==10 and 3<=values[0]<=5 and all(0<=n<=5 for n in values[1:]):found.add('-'.join(map(str,values)))
    if re.search(r'\bdiamante\b|\blosangos?\b|\blos\s+(?:angus|angulo|angulos)\b|\bdiamond\b',value):found.add('diamond')
    if re.search(r'\bfalso\s+(?:9|nove)\b|\bfalse\s+9\b',value):found.add('false-9')
    if re.search(r'\b(ofensiv[oa]s?|vai\s+(?:para|pra)\s+cima|promete\s+(?:para|pra)\s+cima)\b',value):found.add('offensive')
    if re.search(r'\b(defensiv[oa]s?|cautelos[oa]s?|conservador[oa]s?|retrancad[oa]s?|recuad[oa]s?)\b',value):found.add('defensive')
    return found

def front_line_count(text):
    value=plain(text or '')
    counts=set()
    count_pattern=r'(um|uma|dois|duas|tres|quatro|1|2|3|4)'
    player_pattern=r'(?:atacantes?|jogadores?|homens?|pontas?)'
    for match in re.finditer(r'\b'+count_pattern+r'\s+'+player_pattern+r'\b',value):
        counts.add(NUMBER_VALUES[match.group(1)])
    if re.search(r'\bdupla\s+de\s+atacantes?\b',value):counts.add(2)
    if re.search(r'\b(?:um|uma|1)\s+(?:unico\s+)?atacante\b',value):counts.add(1)
    if re.search(r'\b(?:um|uma|1)\s+atacante\b.{0,60}\bdois\s+(?:bem\s+)?abertos?\b',value):
        counts.discard(1);counts.add(3)
    # These source and FIFA lines describe a lone striker without always
    # repeating the word “atacante” (e.g. “só um jogador isolado na frente”).
    if re.search(r'\b(?:so|apenas|unico|isolado)\b.{0,32}\b(?:um|uma|1)\s+(?:jogador|homem|peca)\b.{0,48}\b(?:frente|ataque|isolado|sozinho)\b',value):counts.add(1)
    if re.search(r'\b(?:dois|duas|2)\b.{0,36}\b(?:na\s+frente|no\s+ataque|linha\s+de\s+frente)\b',value):counts.add(2)
    return next(iter(counts)) if len(counts)==1 else None

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
    e=(event or '').upper()
    t=plain(text or '')
    # Ignore common football idioms so “chuva de gols” or “banho de água fria”
    # cannot masquerade as weather and leak into condition-specific scenes.
    figurative=(
        r'\bchuva\s+de\s+(?:gol\w*|aplausos|criticas|comentarios|elogios|ofertas|propostas)\b',
        r'\b(?:vai\s+)?chover\s+(?:comentari\w*|critica\w*|elogio\w*|aplausos)\b',
        r'\bchover\s+no\s+molhado\b',r'\b(?:faca\s+)?chuva\s+ou\s+(?:faca\s+)?sol\b',
        r'\b(?:balde|banho|ducha)\s+de\s+agua\s+(?:fria|gelada)\b',
        r'\bfrio\s+na\s+barriga\b',r'\b(?:cabeca|sangue)\s+fria\b',
        r'\bfri[oa]\s+(?:na\s+hora\s+de|e\s+calculad[oa])\b',r'\bbola\s+de\s+neve\b'
    )
    for pattern in figurative:t=re.sub(pattern,' ',t)
    # Remove negated rain wording before detecting positive rain mentions:
    # “não vai chover” is a dry/no-rain line, not a rain line.
    negative_rain=(
        r'\bsem\s+chuva\b',r'\bnada\s+de\s+chuva\b',r'\bnao\s+(?:vai\s+)?chover\b',
        r'\bnao\s+(?:esta\s+)?chovendo(?!\s+(?:tanto|muito|pouco))\b',r'\bnao\s+chove\b',
        r'\bno\s+rain\b',r'\bnot\s+raining\b'
    )
    dry_patterns=(
        r'\bsem\s+(?:chuva|precipitacao|vento)\b',r'\bnada\s+de\s+(?:chuva|vento)\b',r'\bnao\s+(?:vai\s+)?chover\b',
        r'\bnao\s+(?:esta\s+)?chovendo(?!\s+(?:tanto|muito|pouco))\b',r'\bnao\s+chove\b',
        r'\btempo\s+(?:(?:esta|ta|tava|estava)\s+)?(?:seco|aberto|bom)\b',r'\bceu\s+(?:aberto|limpo)\b',
        r'\bclima\s+(?:perfeito|agradavel)\b',r'\btemperatura\s+agradavel\b',
        r'\b(?:nao\s+(?:esta|ta)\s+ventando|sem\s+vento)\b',
        r'\bdia\s+de\s+(?:muito\s+)?sol\b',r'\bmuito\s+sol\b',
        r'\bsol\s+(?:forte|intenso|d[aá])\b',r'\bnoite\s+estrelada\b',
        r'\bgram(?:ado|a)\s+seco\b',
        r'\bno\s+rain\b',r'\bnot\s+raining\b'
    )
    dry=any(re.search(pattern,t) for pattern in dry_patterns)
    rain_text=t
    for pattern in negative_rain:rain_text=re.sub(pattern,' ',rain_text)
    snow=bool(re.search(r'\b(neve|nevando|nevar|snow)\b|\b(?:gramado|campo)\s+branquinho\b|\b(?:gramado|campo|grama|tapete\s+verde)\b.{0,35}\bbranquinh[oa]\b|\bgeada\b',t))
    cold=bool(re.search(r'\b(frio|fria|gelado|gelada|friaca|congelad[oa]s?|temperatura\s+baixa)\b',t))
    wet_pitch=bool(re.search(r'\b(?:gramado|grama|campo)\s+(?:molhado|molhada|pesado|pesada|encharcado|encharcada|escorregadio|escorregadia)\b',t))
    # General remarks such as “rain affects ball control” do not change a
    # sunny/no-rain scene into a rainy scene. Require a direct, present-tense
    # rain cue when the same transcript also explicitly says it is dry.
    direct_rain=bool(re.search(r'\b(chovendo|chove|choveu|chovia|chover|chuvisco|temporal|chuvoso|chuvosa|rainy)\b|\bque\s+chuva\b|\bcair\s+o\s+mundo\b|\bgalochas\b|\braios\s+e\s+trovoes\b|\bchuva\b.{0,20}\b(forte|caindo|caiu|cai|intensa|desse\s+jeito|assim)\b',rain_text))
    general_rain=bool(re.search(r'\b(chuva|rain)\b',rain_text))
    rain=direct_rain or (general_rain and not dry)
    if snow and rain:spoken='conflict'
    elif snow:spoken='snow'
    elif dry and (rain or wet_pitch):spoken='conflict'
    elif dry:spoken='dry'
    elif rain:spoken='rain'
    elif wet_pitch:spoken='wet'
    elif cold:spoken='cold'
    else:spoken=''
    coded='dry' if any(x in e for x in ('NO_RAIN','DRY','CLEAR_SKY','SUNNY')) else 'snow' if 'SNOW' in e else 'cold' if 'COLD' in e else 'rain' if re.search(r'(?:^|_)RAIN(?:_|$)|(?:^|_)RAINY(?:_|$)',e) else ''
    if spoken=='conflict' or (spoken and coded and spoken!=coded and not (spoken=='wet' and coded in ('rain','snow'))):return 'conflict'
    if spoken=='wet' and coded in ('rain','snow'):return coded
    return spoken or coded

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
    # Rebuild this exact-text layer every run; names without a matching spoken
    # form remain the FIFA original.
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method='player_call_exact'",(narrator,))
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

def match_entity_mentions(db,narrator):
    topics=('Campeonatos e competições','Estádios e cidades','Comentários de clubes')
    marks=','.join('?' for _ in topics)
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method='entity_transcript_exact'",(narrator,))
    sources=collections.defaultdict(list)
    for r in db.execute(f"SELECT * FROM sources WHERE narrator=? AND topic IN ({marks}) AND transcript!='' AND error=''",(narrator,*topics)):
        if r['confidence'] is not None and r['confidence'] < -1.0:continue
        key=canon_name(r['transcript'])
        if key and len(key.replace(' ',''))>=4:sources[(r['topic'],key)].append(dict(r))
    preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
    report=[];mapped=0
    for c in physical_clips(db,f"c.topic IN ({marks}) AND c.transcript!=''",topics):
        key=canon_name(c['transcript'])
        pool=sources.get((c['topic'],key),[])
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
        if not pool or any(a['key'] in preserved for a in aliases):continue
        pool.sort(key=lambda source:(source['path'],source['key']))
        source=pool[0]
        mapped+=put_aliases(db,narrator,c,source['key'],'entity_transcript_exact',1.0)
        report.append(dict(topic=c['topic'],event=c['event'],text=c['transcript'],source=source['path']))
    return dict(occurrences=mapped,physical=len(report),report=report)

def debut_position(event,text=''):
    e=(event or '').upper()
    for token,position in (
        ('POSITION_CENTRAL_DEFENDER','central_defender'),('POSITION_DEF_MID_FIELD','defensive_midfield'),
        ('POSITION_FULL_BACK','full_back'),('POSITION_GK','goalkeeper'),('POSITION_MID_FIELD','midfield'),
        ('POSITION_WINGER','winger'),('POSITION_FORWARD','forward')
    ):
        if token in e:return position
    value=plain(text or '')
    if re.search(r'\b(goleir[oa]s?|guarda redes|goalkeepers?)\b',value):return 'goalkeeper'
    if re.search(r'\b(lateral|ala|full back)\b',value):return 'full_back'
    if re.search(r'\b(volante|meio campista defensiv[oa])\b',value):return 'defensive_midfield'
    if re.search(r'\b(meia|meias|meio campista|meio campo ofensivo)\b',value):return 'midfield'
    if re.search(r'\b(ponta|pontas|extremo|extremos|winger)\b',value):return 'winger'
    if re.search(r'\b(zaga|zagueir[oa]s?|defensor[ae]?s?|defesa central|central defender)\b',value):return 'central_defender'
    if re.search(r'\b(atacante|atacantes|centroavante|camisa 9|jogador de frente|na linha de frente)\b',value):return 'forward'
    return ''

def match_debut_milestones(db,narrator):
    targets=list(physical_clips(db,"(c.event LIKE 'bDEBUT_INTRO%' OR c.event IN ('bDEBUT_FT_SINGLE_GEN','bDEBUT_FT_LAST_DUAL'))"))
    source_events=('bPRE_INTRO_SCENE_FOCUS_SINGLE_PLAYER_DEBUT_STITCH','bPTW_INTRO_SINGLE_DEBUT_GEN','bPRE_INTRO_SCENE_FOCUS_DUAL_PLAYER_DEBUTANTS','bPTW_FT_SEQ2_PLAYER_PROGRESSION_POSITIVE_DEBUT','bPTW_FT_SEQ2_PLAYER_PROGRESSION_NEGATIVE_DEBUT')
    rows=db.execute("SELECT * FROM sources WHERE narrator=? AND transcript!='' AND error='' AND (event IN ("+','.join('?' for _ in source_events)+") OR event LIKE 'bPTW_INTRO_SEQ2_SINGLE_DEBUT_POSITION_%')",(narrator,*source_events)).fetchall()
    sources=[]
    for row in rows:
        source=dict(row)
        if blocked_reasons(source):continue
        sources.append(source)
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method NOT IN ('manual','gender_review') AND clip IN (SELECT c.key FROM clips c JOIN banks b ON b.key=c.bank WHERE b.active=1 AND (c.event LIKE 'bDEBUT_INTRO%' OR c.event IN ('bDEBUT_FT_SINGLE_GEN','bDEBUT_FT_LAST_DUAL')))",(narrator,))
    report=[];unmatched=[];used=collections.Counter();mapped=0
    preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
    for clip in targets:
        event=clip['event']
        both_players=bool(re.search(r'\b(?:duas?\s+(?:importantes\s+)?estreias?|dois\s+estreantes?|duas\s+estreantes?|dois\s+jogadores\s+estreantes?|duas\s+contratacoes?|uma\s+para\s+cada\s+(?:time|lado)|um\s+em\s+cada\s+(?:time|lado)|para\s+os\s+dois\s+lados|cada\s+(?:time|lado)\s+(?:tera|tem|vai\s+ter)\s+(?:um|uma)\s+estreante)\b',plain(clip['transcript'] or '')))
        position=debut_position('',clip['transcript'])
        if 'DUAL' in event and both_players:
            pool=[s for s in sources if s['event']=='bPRE_INTRO_SCENE_FOCUS_DUAL_PLAYER_DEBUTANTS'];method='debut_dual_intro'
        elif event=='bDEBUT_FT_LAST_DUAL':
            pool=[s for s in sources if s['event']=='bPTW_FT_SEQ2_PLAYER_PROGRESSION_NEGATIVE_DEBUT'];method='debut_negative_result'
        elif event=='bDEBUT_FT_SINGLE_GEN':
            pool=[s for s in sources if s['event']=='bPTW_FT_SEQ2_PLAYER_PROGRESSION_POSITIVE_DEBUT'];method='debut_positive_result'
        else:
            exact=[s for s in sources if position and s['event'].startswith('bPTW_INTRO_SEQ2_SINGLE_DEBUT_POSITION_') and debut_position(s['event'],s['transcript'])==position]
            generic=[s for s in sources if s['event'] in ('bPRE_INTRO_SCENE_FOCUS_SINGLE_PLAYER_DEBUT_STITCH','bPTW_INTRO_SINGLE_DEBUT_GEN')]
            pool=exact or generic
            method='debut_position_exact' if exact else 'debut_intro_generic'
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(clip['bank'],clip['offset'])).fetchall()
        if not pool or any(alias['key'] in preserved for alias in aliases):
            unmatched.append(dict(event=event,position=debut_position('',clip['transcript']),original=clip['transcript'],reason='no_safe_debut_source' if not pool else 'manual_mapping_preserved'))
            continue
        available=[source for source in pool if used[source['key']]<8]
        if not available:
            unmatched.append(dict(event=event,position=debut_position('',clip['transcript']),original=clip['transcript'],reason='source_reuse_limit'))
            continue
        available.sort(key=lambda source:(-overlap(clip['transcript'],source['transcript']),used[source['key']],source['path']))
        source=available[0];used[source['key']]+=1
        with db: mapped+=put_aliases(db,narrator,clip,source['key'],method,1.0-overlap(clip['transcript'],source['transcript'])*.25)
        report.append(dict(event=event,position=debut_position('',clip['transcript']),method=method,original=clip['transcript'],replacement=source['transcript'],source=source['path']))
    return dict(occurrences=mapped,physical=len(report),methods={method:sum(1 for row in report if row['method']==method) for method in ('debut_position_exact','debut_intro_generic','debut_dual_intro','debut_positive_result','debut_negative_result')},unmatched_physical=len(unmatched),unmatched=unmatched,report=report)

TACTIC_EVENT_THEMES={
    'COUNTER_ATTACK':'counter_attack','HIGH_PRESS':'high_press','LONG_BALL':'long_ball',
    'PARK_THE_BUS':'park_bus','TIKI_TAKA':'tiki_taka','USING_WIDTH_OF_PITCH':'width'
}

def tactic_themes(text):
    value=plain(text or '');themes=set()
    patterns={
        'counter_attack':r'\bcontra[\s-]?ataques?\b|\bcontragolpes?\b',
        'high_press':r'\bmarq\w*\s+(?:mais\s+)?a\s+saida\s+de\s+bola\b|\badiantar\s+a\s+marcacao\b|\bmarcacao\s+alta\b|\bpressao\s+alta\b|\bpressionar\s+(?:alto|a\s+saida)\b',
        'long_ball':r'\bbola\s+longa\b|\bligacao\s+direta\b|\blancamento\s+longo\b|\bpasse\s+longo\b',
        'park_bus':r'\b(?:estacionar\s+o\s+onibus|park\s+the\s+bus|bloco\s+baixo|linhas\s+baixas|retrancad[oa]s?)\b',
        'tiki_taka':r'\btiki[\s-]?taka\b|\bposse\s+de\s+bola\b|\btroca\s+de\s+passes\b|\btoque\s+de\s+bola\b',
        'width':r'\b(?:usar|explorar|aproveitar)\s+(?:bem\s+)?(?:a\s+)?(?:largura|amplitude|laterais)\b|\babrir\s+o\s+campo\b|\bjogar\s+pelos\s+lados\b',
        'offside_line':r'\blinha\s+(?:burra|de\s+impedimento)\b|\bforcar\s+o\s+impedimento\b',
        'winger_switch':r'\b(?:pontas?|pontos?)\b.{0,60}\binvert\w*\b|\binvert\w*.{0,60}\b(?:pontas?|pontos?)\b',
        'defender_forward':r'\bzagueir\w*.{0,80}\b(?:area|ataque|frente)\b|\b(?:sobe|subir|avancar|avanca)\w*.{0,50}\bzagueir\w*\b'
    }
    for theme,pattern in patterns.items():
        if re.search(pattern,value):themes.add(theme)
    return themes

def source_tactic_themes(source):
    event=source['event'].upper()
    for marker,theme in TACTIC_EVENT_THEMES.items():
        if marker in event:return {theme}
    return tactic_themes(source['transcript'])

def match_tactics(db,narrator):
    targets=list(physical_clips(db,"c.event='bKINECT_TACTICS_GEN'"))
    rows=db.execute("SELECT * FROM sources WHERE narrator=? AND event LIKE 'bTACTICS_CHANGED%' AND transcript!='' AND error=''",(narrator,)).fetchall()
    sources=[]
    for row in rows:
        source=dict(row)
        if blocked_reasons(source):continue
        themes=source_tactic_themes(source)
        if themes:source['themes']=themes;sources.append(source)
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method NOT IN ('manual','gender_review') AND clip IN (SELECT c.key FROM clips c JOIN banks b ON b.key=c.bank WHERE b.active=1 AND c.event='bKINECT_TACTICS_GEN')",(narrator,))
    report=[];unmatched=[];used=collections.Counter();mapped=0
    preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
    for clip in targets:
        themes=tactic_themes(clip['transcript'])
        pool=[source for source in sources if source['themes'] and source['themes'].issubset(themes)]
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(clip['bank'],clip['offset'])).fetchall()
        if not pool or any(alias['key'] in preserved for alias in aliases):
            unmatched.append(dict(event=clip['event'],themes=sorted(themes),original=clip['transcript'],reason='no_exact_tactic_source' if not pool else 'manual_mapping_preserved'))
            continue
        available=[source for source in pool if used[source['key']]<8]
        if not available:
            unmatched.append(dict(event=clip['event'],themes=sorted(themes),original=clip['transcript'],reason='source_reuse_limit'))
            continue
        available.sort(key=lambda source:(source['themes']!=themes,-overlap(clip['transcript'],source['transcript']),used[source['key']],source['path']))
        source=available[0];used[source['key']]+=1
        with db:mapped+=put_aliases(db,narrator,clip,source['key'],'tactic_same_strategy',.95)
        report.append(dict(event=clip['event'],themes=sorted(themes),match_level='exact' if source['themes']==themes else 'same_theme_subset',original=clip['transcript'],replacement=source['transcript'],source=source['path']))
    return dict(occurrences=mapped,physical=len(report),themes=dict(collections.Counter(theme for row in report for theme in row['themes'])),unmatched_physical=len(unmatched),unmatched=unmatched,report=report)

FORMATION_EVENTS=('bTS_FORMATION','bTS_FORMATION_REPEAT','bTS_FORMATION_FRONT')

def match_formations(db,narrator):
    marks=','.join('?' for _ in FORMATION_EVENTS)
    clips=list(physical_clips(db,f'c.event IN ({marks})',FORMATION_EVENTS))
    sources=collections.defaultdict(list);front_fallbacks=collections.defaultdict(list)
    for r in db.execute(f"SELECT * FROM sources WHERE narrator=? AND event IN ({marks}) AND transcript!='' AND error=''",(narrator,*FORMATION_EVENTS)):
        source=dict(r);source['female_reference']=female_reference(source['transcript'])
        if r['event']=='bTS_FORMATION_FRONT':
            count=front_line_count(r['transcript'])
            if count is None:front_fallbacks[r['event']].append(source)
            else:sources[r['event']].append((source,{f'front:{count}'}))
            continue
        signature=formations(r['transcript'])
        if signature:sources[r['event']].append((source,signature))
    prepared=[];unmatched=[]
    for c in clips:
        if c['event']=='bTS_FORMATION_FRONT':
            target_count=front_line_count(c['transcript'])
            if target_count is None:
                unmatched.append(dict(event=c['event'],original=c['transcript'],reason='front_line_count_not_clear'))
                continue
            target_female=female_reference(c['transcript'])
            exact=[source for source,signature in sources.get(c['event'],[]) if source['female_reference']==target_female and signature=={f'front:{target_count}'}]
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
            gender_safe_fallbacks=[source for source in front_fallbacks.get(c['event'],[]) if source['female_reference']==target_female]
            prepared.append((len(exact)+len(gender_safe_fallbacks),c,{f'front:{target_count}'},exact,gender_safe_fallbacks,aliases))
            continue
        target=formations(c['transcript'])
        if not target:
            unmatched.append(dict(event=c['event'],original=c['transcript'],reason='formation_signature_not_recognized'))
            continue
        target_shapes={x for x in target if '-' in x and x[0].isdigit()}
        target_tags=target-target_shapes
        target_female=female_reference(c['transcript'])
        exact=[];fallback=[]
        for source,signature in sources.get(c['event'],[]):
            if source['female_reference']!=target_female:continue
            source_shapes={x for x in signature if '-' in x and x[0].isdigit()}
            source_tags=signature-source_shapes
            if target_shapes and source_shapes!=target_shapes:continue
            if not target_shapes and source_shapes and not (target_tags & {'diamond','false-9'}):continue
            target_special=target_tags & {'diamond','false-9'}
            source_special=source_tags & {'diamond','false-9'}
            target_styles=target_tags & {'offensive','defensive'}
            source_styles=source_tags & {'offensive','defensive'}
            # False nine is a distinct tactical role, not a harmless omission.
            if 'false-9' in target_special and 'false-9' not in source_special:continue
            if target_shapes==source_shapes and target_special==source_special and target_styles==source_styles:
                exact.append(source)
            elif source_special.issubset(target_special) and source_styles.issubset(target_styles):
                # Safe fallback may omit a detail from the Tiago line, but it
                # cannot add an unsupported diamond/false nine or a contrary
                # offensive/defensive description.
                fallback.append(source)
        aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
        prepared.append((len(exact)+len(fallback),c,target,exact,fallback,aliases))
    report=[];mapped=0;fallback_count=0;exact_count=0
    with db:
        db.execute(f"DELETE FROM mappings WHERE profile=? AND method NOT IN ('manual','gender_review') AND clip IN (SELECT c.key FROM clips c JOIN banks b ON b.key=c.bank WHERE b.active=1 AND c.event IN ({marks}))",(narrator,*FORMATION_EVENTS))
        used=collections.Counter()
        preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
        # Assign the rarest exact formation signatures first so broad/common
        # variations do not consume recordings needed by a less common shape.
        for _,c,target,exact,fallback,aliases in sorted(prepared,key=lambda item:(item[0],item[1]['event'],item[1]['bank'],item[1]['offset'])):
            pool=[source for source in exact if used[source['key']]<8]
            match_level='exact'
            if not pool:
                pool=[source for source in fallback if used[source['key']]<8]
                match_level='context_fallback'
            if not pool or any(a['key'] in preserved for a in aliases):
                unmatched.append(dict(event=c['event'],formation=sorted(target),original=c['transcript'],reason='no_source_with_same_context' if not pool else 'manual_mapping_preserved'))
                continue
            pool.sort(key=lambda src:(-overlap(c['transcript'],src['transcript']),used[src['key']],src['path']))
            ranked=pool[:5];source=ranked[0];used[source['key']]+=1
            score=1.0-overlap(c['transcript'],source['transcript'])*.25
            method='formation_same_context' if match_level=='exact' else 'formation_context_fallback'
            mapped+=put_aliases(db,narrator,c,source['key'],method,score)
            exact_count+=match_level=='exact';fallback_count+=match_level!='exact'
            report.append(dict(event=c['event'],formation=sorted(target),match_level=match_level,original=c['transcript'],replacement=source['transcript'],source=source['path'],alternatives=[dict(text=s['transcript'],path=s['path'],lexical_overlap=round(overlap(c['transcript'],s['transcript']),3)) for s in ranked]))
    return dict(occurrences=mapped,physical=len(report),exact_physical=exact_count,context_fallback_physical=fallback_count,source_formation_variants=sum(len(v)+len(front_fallbacks.get(k,[])) for k,v in sources.items()),unmatched_physical=len(unmatched),unmatched=unmatched,report=report)

def weather_scene(event):
    e=(event or '').upper()
    if 'RAINBOW' in e:return False
    # These named gameplay variants carry explicit rain/snow commentary too.
    return 'WEATHER' in e or 'RAIN' in e or 'SNOW' in e

def weather_role(event):
    """Keep weather wording attached to the play/commentary moment it describes."""
    e=(event or '').upper()
    if 'INTRO' in e or 'PRES_' in e:return 'presentation'
    if 'GOAL' in e:return 'goal'
    if 'MISS' in e:return 'miss'
    if 'FOUL' in e:return 'foul'
    if 'TCKL' in e or 'SLIDE' in e:return 'tackle'
    if 'KICKOFF' in e:return 'kickoff'
    if 'HT_' in e or 'HALFTIME' in e:return 'halftime'
    if 'FT_' in e or 'FULLTIME' in e:return 'fulltime'
    return e if weather_scene(e) else ''

def weather_scene_compatible(target,source):
    target_event=target['event'];source_event=source['event']
    if target_event==source_event:return True
    target_role=weather_role(target_event);source_role=weather_role(source_event)
    return bool(target_role and target_role==source_role)

def match_weather(db,narrator):
    clips=list(physical_clips(db,"(c.event LIKE '%WEATHER%' OR c.event LIKE '%RAIN%' OR c.event LIKE '%SNOW%') AND c.event NOT LIKE '%RAINBOW%'") )
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method='weather_same_condition'",(narrator,))
        preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
        for c in clips:
            expected=weather_kind(c['event'],c['transcript']) or 'general'
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
            for alias in aliases:
                if alias['key'] in preserved:continue
                current=db.execute('SELECT m.source,m.method,s.event,s.transcript FROM mappings m JOIN sources s ON s.key=m.source WHERE m.profile=? AND m.clip=?',(narrator,alias['key'])).fetchone()
                if current:
                    spoken=weather_kind(current['event'],current['transcript'])
                    source_role=weather_role(current['event'])
                    target_role=weather_role(c['event'])
                    incompatible_role=bool(source_role and target_role and source_role!=target_role)
                    if spoken=='conflict' or (spoken in ('rain','snow','dry','cold','wet') and spoken!=expected) or (expected=='general' and spoken in ('rain','snow','dry','cold','wet')) or incompatible_role:
                        db.execute('DELETE FROM mappings WHERE profile=? AND clip=?',(narrator,alias['key']))
    sources=collections.defaultdict(list)
    for r in db.execute("SELECT * FROM sources WHERE narrator=? AND transcript!='' AND error=''",(narrator,)):
        if 'RAINBOW' in r['event'].upper():continue
        kind=weather_kind(r['event'],r['transcript'])
        if kind in ('rain','snow','dry','cold','wet') and weather_role(r['event']):sources[(r['event'],kind)].append(dict(r))
    report=[];unmatched=[];mapped=0;used=collections.Counter()
    with db:
        preserved={r['clip'] for r in db.execute("SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','gender_review')",(narrator,))}
        for c in clips:
            if not weather_scene(c['event']):continue
            kind=weather_kind(c['event'],c['transcript']) or 'general'
            if kind=='conflict':
                unmatched.append(dict(event=c['event'],original=c['transcript'],reason='weather_condition_conflict'))
                continue
            pool=[]
            for (event,state),rows in sources.items():
                if state!=kind:continue
                same_scene=event==c['event']
                if same_scene or (kind!='general' and weather_scene_compatible(c,rows[0])):pool.extend(rows)
            # Weather-specific intro variants outnumber the compatible target
            # slots; keep each selected recording unique across the profile.
            pool=[s for s in pool if used[s['key']]==0]
            aliases=db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',(c['bank'],c['offset'])).fetchall()
            if not pool or any(a['key'] in preserved for a in aliases):
                unmatched.append(dict(event=c['event'],condition=kind,original=c['transcript'],reason='no_source_with_same_weather_scene' if not pool else 'manual_mapping_preserved'))
                continue
            pool.sort(key=lambda s:(-overlap(c['transcript'],s['transcript']),used[s['key']],s['path']))
            source=pool[0];used[source['key']]+=1
            mapped+=put_aliases(db,narrator,c,source['key'],'weather_same_condition',.95)
            report.append(dict(event=c['event'],condition=kind,original=c['transcript'],replacement=source['transcript'],source=source['path']))
        return dict(occurrences=mapped,physical=len(report),unmatched_physical=len(unmatched),conditions={k:sum(1 for r in report if r['condition']==k) for k in ('rain','snow','dry','cold','wet','general')},unmatched=unmatched,report=report)

def run(narrator):
    db=connect()
    result=dict(narrator=narrator,player_calls=match_player_calls(db,narrator),entity_mentions=match_entity_mentions(db,narrator),debut_milestones=match_debut_milestones(db,narrator),tactics=match_tactics(db,narrator),formations=match_formations(db,narrator),weather=match_weather(db,narrator))
    dest=WORK/'transcriptions';dest.mkdir(exist_ok=True)
    (dest/(narrator+'_contextual_associations.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    db.close();print(json.dumps({k:(v if k=='narrator' else {key:val for key,val in v.items() if key not in ('report','unmatched')}) for k,v in result.items()},ensure_ascii=False),flush=True)
    return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('narrator');run(p.parse_args().narrator)
