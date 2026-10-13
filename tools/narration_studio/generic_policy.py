"""Content checks and reviewed pools for reusable football commentary."""
from pathlib import Path
import functools,json,re,unicodedata

from core import WORK

def female_reference(text):
    text=plain(text)
    if re.search(r'\b(jogadora|jogadoras|goleira|goleiras|atacante feminina|juiza|arbitra)\b',text):return True
    if re.search(r'\b(she (shoots|shot|scores|scored|passes|passed|dribbles|dribbled|takes|hits|runs|plays|saves|saved)|her (shot|goal|pass|save))\b',text):return True
    if re.search(r'\bela (recuperou|perdeu|ganhou|empatou|driblou|chutou|bateu|finalizou|meteu|recebeu|dominou|pegou|tocou|passou|cruzou|cabeceou|correu|arrancou|marcou|carregou|conseguiu)\b',text):return True
    if re.search(r'\bela\s+(?:atua|fica|e|vai|joga|tem|forma|faz)\b.{0,72}\b(?:sozinha|referencia|dupla|trio|tridente|ataque|frente|titular|estreia)\b',text):return True
    if re.search(r'\bela\b.{0,48}\b(?:merece|destaque|jogadora|artilheira|goleira|capita|estrela|heroina|parece|pareceu|perdida|jogou|atua|esteve)\b',text):return True
    if re.search(r'\bela (?:foi|e|era|ficou|esta|estava|sera) (?:a |uma )?(?:titular|jogadora|artilheira|goleira|capita|estrela)\b',text):return True
    if re.search(r'\b(?:gostando|gostei|vendo|marcando|acompanhando|ajudando)\s+dela\b|\bela\s+me\s+(?:parece|pareceu)\b',text):return True
    if re.search(r'\b(?:dela|jogadora|artilheira|goleira)\b.{0,48}\b(?:perdida|apagada|bem|mal|boa|ruim|estreia|destaque)\b',text):return True
    if re.search(r'\b(?:jogadora|artilheira|goleira|capita|atacante feminina)\b|\bdela\s+(?:no|na)\s+(?:ataque|defesa)\b',text):return True
    if re.search(r'\belas\s+(?:fazem|formam|ficam|atuam|jogam|sao|estao|vao)\b.{0,80}\b(?:dupla|trio|tridente|ataque|frente|titulares|estreia)\b',text):return True
    if re.search(r'\bas\s+duas\b(?!\s+equipes?)\s+.{0,48}\b(?:ataque|frente|jogadoras?|atacantes?)\b',text):return True
    # 'ela' may refer to the ball. Reject only player actions and possession.
    return bool(re.search(r'\b(ela (recupera|perde|ganha|empata|dribla|chuta|bate|finaliza|faz|mete|recebe|domina|pega|toca|passa|cruza|cabeceia|corre|arranca|marca|carrega|nao conseguiu)|e dela|gol dela|segundo dela|ela era a ultima|elas (jogam|atacam))\b',text))

def plain(text):
    text=''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+',' ',text).strip()

def weather_condition(event,text):
    """Return a specific playing condition when a line clearly identifies one."""
    event=(event or '').upper();value=' '+plain(text or '')+' '
    if any(token in event for token in ('SNOW','SNOWY')) or re.search(r'\b(?:neve|nevando|nevou|snow|snowing|snowy)\b',value):return 'snow'
    if any(token in event for token in ('NO_RAIN','DRY','CLEAR','SUNNY')):return 'dry'
    if any(token in event for token in ('RAIN','RAINY','WET')):return 'rain'
    dry_context=bool(re.search(r'\b(?:sem chuva|nada de chuva|nao chove|tempo (?:esta |ta |ficou )?aberto|ceu aberto|ceu limpo|dia de sol|muito sol|tempo seco|grama seca|gramado seco|tempo ta bom|tempo bom|clima perfeito|tempo agradavel|sem vento|nao esta ventando|nao ta ventando)\b',value))
    if dry_context:return 'dry'
    if re.search(r'\b(?:chov\w*|chuva(?! de gols?)|molhad\w*|rain\w*|wet|storm|tempestade|trovao|trov[oõ]es|cair o mundo)\b',value):return 'rain'
    if re.search(r'\b(?:branquinh\w*|campo branco|gramado branco|congela o pe|congela os pes)\b',value):return 'snow'
    if re.search(r'\b(?:dry|clear skies|sunny|no rain)\b',value):return 'dry'
    return ''

@functools.lru_cache(maxsize=1)
def named_references():
    references=set()
    path=WORK/'metadata/game_names.json'
    if path.exists():
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        for table in ('teams','stadiums','leagues'):
            for name in data.get(table,{}).values():
                value=plain(name)
                if len(value)>=5:references.add(value)
                short=re.sub(r'\b(fc|cf|sc|afc|ac|ss|ud|cd|rc|se|cr|ec|clube|club|futebol|football)\b',' ',value)
                short=' '.join(short.split())
                if len(short)>=5 and short not in ('united','sporting','athletic','national','nacional','internacional','all stars'):references.add(short)
    references.update(plain(s) for s in (
        'Juve','Juventus','Torino','Chelsea','Arsenal','Manchester','United','City',
        'Barcelona','Real Madrid','PSG','Paris Saint Germain','Marseille','Flamengo',
        'Vasco','Fluminense','Corinthians','Palmeiras','São Paulo','Botafogo','Santos',
        'Grêmio','Cruzeiro','Galo','Bayern','Dortmund','Hamburgo','Werder Bremen',
        'Inter de Milão','Maracanã','Old Trafford','Etihad','Allianz','Stamford Bridge',
        'Neymar','Messi','Cristiano','Ronaldo','Ronaldinho','Marcelinho','Pedrinho',
        'Ben Johnson','Usain Bolt','Wilson Boat','Didier','Agostinho','Faustão',
        'Roger','Professor Raimundo','Libertadores','Champions League','Europa League',
        'Copa do Mundo','Brasileirão','Premier League','Liga dos Campeões'))
    # Short generic words in game table labels are not reliable names.
    references.difference_update(('futebol','football','league','liga','calcio','stadium','estadio','stars','classic','rest of world',
        'confianca','decisao','forte','ao vivo','central','capital','barra','feira','altos','treze','nacional','internacional'))
    return tuple(sorted(references,key=len,reverse=True))

def blocked_reasons(source,require_text=True):
    return list(_blocked_reasons(source.get('event',''),source.get('transcript',''),require_text))

@functools.lru_cache(maxsize=50000)
def _blocked_reasons(event,transcript,require_text):
    reasons=[];event=event.upper();text=plain(transcript)
    if female_reference(transcript):reasons.append('referência a jogadora em perfil masculino')
    if any(token in event for token in ('SPECIFIC','PLAYER_NAMES','SIMPLE_SURNAME','CLUB_NAME','TEAM_NAME','BANTER_STADIUM','FINAL_STADIUM')) or event.startswith(('SINTRO','RINTRO','LINTRO')):
        reasons.append('evento específico')
    if not text or text=='sem fala detectada':
        if require_text:reasons.append('fala ainda não verificada')
        return tuple(reasons)
    # An audience greeting is harmless even though Brazil is a team name.
    checked=re.sub(r'\balo(?: alo)? brasil\b','alo publico',text)
    checked=re.sub(r'\bligado na globo\b','ligado na transmissao',checked)
    padded=' '+checked+' '
    for name in named_references():
        if ' '+name+' ' in padded:reasons.append('referência: '+name);break
    if any(' '+plain(term)+' ' in padded for term in (
        'cartola','hashtag','você comenta','QR Code','votação','novela','Fantástico',
        'tela quente','domingo maior','filme','meme','grande família','craque do jogo',
        'árbitro de vídeo','hábito de vídeo','VAR','27 graus','199 passes','164 certos',
        'Domingão','Luciano Huck','Vivo Fibra','oferecimento','patrocínio','Itaú','Brahma',
        'brought to you by','sponsored by','commercial break')):
        reasons.append('publicidade, conversa externa ou informação fixa')
    return tuple(reasons)

def intro_role(event):
    e=event.upper()
    if e.startswith('TINTRO'):return None # Raw club call names stay original.
    if 'INTRO' not in e and not any(t in e for t in ('HELLO','WELCOME','LINEUP','FORMATION')):return None
    if any(t in e for t in ('PLAYER_NAMES','SURNAME','WEATHER','RAIN','SNOW','REF')):return None
    if 'TS_TEAM_INTRO' in e or 'LINEUP' in e or 'FORMATION' in e:return 'lineup'
    if any(t in e for t in ('HELLO','WELCOME','COMMENTATORS','PRE_STITCH')):return 'welcome'
    return 'expectation'

@functools.lru_cache(maxsize=1)
def reviewed_pools():
    path=WORK/'generic_curated.json'
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else {}

def approved_pool(narrator,role,sources):
    wanted=set(reviewed_pools().get(narrator,{}).get(role,[]))
    return [s for s in sources if s['path'] in wanted and not blocked_reasons(s)]

def proposed_opening_pool(role,sources):
    """Conservative text proposals for new libraries, always marked for review."""
    patterns={
        'welcome':r'\b(bem vind[oa]s?|boa (tarde|noite)|alo (voce|publico)|comeca (a nossa|mais uma) transmissao|welcome|good (afternoon|evening)|hello everyone)\b',
        'lineup':r'\b(escalacao|escalacoes|formacao (das|da|dos)|equipes na (sua )?tela|line ?ups|starting eleven|formations)\b',
        'expectation':r'\b(bom jogo|grande jogo|boa partida|partida emocionante|jogo emocionante|great match|good game|exciting match)\b'}
    # A keyword can occur inside an unrelated long call (for example, a goal
    # recap that also says "escalação"). Don't use that as a lineup.
    match_cues=re.compile(r'\b(gol|gols|empata|empatou|chute|chutou|finaliza|finalizou|goleiro|defendeu|defesa|escanteio|impedimento|cartao|falta|penalti|rebote|trave|placar|vitoria|derrota|contra ataque|drible|cruzamento|marcou|bateu|rede)\b')
    result=[]
    for source in sources:
        text=plain(source['transcript'])
        if blocked_reasons(source) or not re.search(patterns[role],text):continue
        if match_cues.search(text):continue
        result.append(source)
    return result

def event_pair_compatible(target_event,source_event,target_text='',source_text=''):
    """Reject semantic matches that cross a clearly different game scene."""
    target=(target_event or '').upper();source=(source_event or '').upper()
    target_weather=weather_condition(target,target_text)
    source_weather=weather_condition(source,source_text)
    if (target_weather or source_weather) and target_weather!=source_weather:return False
    if not source:
        if any(token in target for token in ('TRANSFER','TR_C_','TR_M_','STORYLINE','DEBUT','REF','PREV','PSO','PENALTIES','SHOOTOUT','TUTORIAL','SUB')):return False
        return True
    # These are player-name/transfer-name slots, not ordinary commentary.
    if target.startswith(('PTR_','PPLAYER_NAMES','PSIMPLE_SURNAME')):return False
    if any(token in source for token in ('FOCUS_PASSER','PLAYER_NAMES','CALL_NAME','SIMPLE_SURNAME')):return False
    # Keep special career and transfer scenarios within their own source pool.
    # Similar wording alone is not enough to replace a debut, storyline or fee.
    def has_transfer(value):return any(token in value for token in ('TRANSFER','TR_C_','TR_M_','TR_'))
    if has_transfer(target)!=has_transfer(source):return False
    target_debut=target.startswith('PDEBUT') or 'DEBUT' in target
    source_debut='DEBUT' in source or 'PLAYER_PROGRESSION' in source or 'PTW_' in source
    if target_debut and not source_debut:return False
    if 'DEBUT' in source and not target_debut:return False
    if 'STORYLINE' in target and 'STORYLINE' not in source:return False
    target_ref='REF' in target or 'REFEREE' in target
    source_ref='REF' in source or 'REFEREE' in source
    if target_ref!=source_ref:return False
    if 'JOSTLE' in target and 'JOSTLE' not in source:return False
    # Previous-match summaries and current-play events are separate scenes.
    if any(token in target for token in ('PREV','LOOKING_BACK','LAST_MATCH')) and not any(token in source for token in ('PREV','LOOKING_BACK','LAST_MATCH')):return False
    # A goal cannot be replaced by a miss (or an own goal by an ordinary one).
    goal=lambda value:('GOAL' in value and not any(token in value for token in ('NO_GOAL','GOALKEEPER','GOAL_KICK','GOALKICK','TOWARDS_GOAL')))
    miss=lambda value:any(token in value for token in ('MISS','NO_GOAL','SHOTWIDE','OFF_BAR','OFF_POST'))
    if (goal(target) and miss(source)) or (miss(target) and goal(source)):return False
    if goal(target)!=goal(source) and (goal(target) or goal(source)):return False
    if miss(target)!=miss(source) and (miss(target) or miss(source)):return False
    own_goal=lambda value:any(token in value for token in ('OWNGOAL','OWN_GOAL'))
    if own_goal(target)!=own_goal(source) and (own_goal(target) or own_goal(source)):return False
    if ('MANAGER_REACT' in target)!=('MANAGER_REACT' in source):return False
    target_card=any(token in target for token in ('RED_CARD','YELLOW_CARD','CARD')) or bool(re.search(r'(?:^|_)RED(?:_|$)',target))
    source_card=any(token in source for token in ('RED_CARD','YELLOW_CARD','CARD','FOUL_RESULT_RED','RED_WINNING','YELLOW')) or bool(re.search(r'(?:^|_)RED(?:_|$)',source))
    if target_card!=source_card:return False
    if ('TUTORIAL' in target)!=('TUTORIAL' in source):return False
    if (any(token in target for token in ('KEEPER','GOALKEEPER','KPR')) and any(token in source for token in ('STRIKER','FORWARD'))) :return False
    if (any(token in source for token in ('KEEPER','GOALKEEPER','KPR')) and any(token in target for token in ('STRIKER','FORWARD'))):return False
    # Shoot-out attempts need the same outcome: a converted kick cannot be
    # replaced by a miss, and a miss cannot be replaced by a save.
    if 'PSO' in target or 'PSO' in source:
        if ('PSO' in target)!=('PSO' in source):return False
        def pso_outcome(value):
            if any(token in value for token in ('GOAL','SCORE')) and not any(token in value for token in ('MISS','NO_GOAL')):return 'goal'
            if any(token in value for token in ('MISS','WIDE','OFF_BAR','OFF_POST')):return 'miss'
            if any(token in value for token in ('SAVE','STOP')):return 'save'
            if any(token in value for token in ('SETUP','RUN_UP','ANTICIPATION')):return 'setup'
            return ''
        target_outcome=pso_outcome(target);source_outcome=pso_outcome(source)
        if target_outcome and source_outcome and target_outcome!=source_outcome:return False
    # Injury-time announcements are unrelated to injuries and substitutions.
    target_injury_time='INJURY_TIME' in target
    source_injury_time='INJURY_TIME' in source
    if target_injury_time!=source_injury_time and ('INJURY' in target or 'INJURY' in source):return False
    # Goalkeeper substitutions have a different meaning from an outfield change.
    target_sub='SUB' in target or 'SUBSTIT' in target
    source_sub='SUB' in source or 'SUBSTIT' in source
    if target_sub:
        if not source_sub:return False
        if source_sub and ('KEEPER' in target)!=('KEEPER' in source):return False
    elif source_sub:return False
    target_shootout=any(token in target for token in ('PSO','PENALTIES','SHOOTOUT'))
    source_shootout=any(token in source for token in ('PSO','PENALTIES','SHOOTOUT'))
    if target_shootout!=source_shootout:return False
    target_penalty_goal='PEN_GOAL' in target or 'PENALTY_GOAL' in target
    source_penalty_goal='PEN_GOAL' in source or 'PENALTY_GOAL' in source
    if target_penalty_goal!=source_penalty_goal:return False
    target_handball_penalty='PK_FROM_HANDBALL' in target
    source_handball_penalty='PK_FROM_HANDBALL' in source
    if target_handball_penalty!=source_handball_penalty:return False
    target_throw=any(token in target for token in ('THROW_IN','THROWIN'))
    source_throw=any(token in source for token in ('THROW_IN','THROWIN'))
    if target_throw and not source_throw:return False
    # Separate-game score/penalty overlays must not replace the current match.
    if 'ELSEWHERE' in source and 'ELSEWHERE' not in target:return False
    if 'SCORELINE' in source and 'ELSEWHERE' in source and not any(t in target for t in ('SCORELINE','ELSEWHERE','SC2_')):return False
    # Keep explicit match stages together (half-time, full-time, kick-off and extra time).
    def phase(event):
        value=event[1:] if event[:1] in 'BCMPLRST' else event
        if 'EXTRA' in value and ('HALF' in value or 'TIME' in value):return 'extra_time'
        if re.search(r'(?:^|_)(?:HT|HALFTIME|HALF_TIME)(?:_|$)',value):return 'halftime'
        if re.search(r'(?:^|_)(?:FT|FULLTIME|FINAL_WHISTLE)(?:_|$)',value):return 'fulltime'
        if 'KICKOFF' in value or 'KICK_OFF' in value:return 'kickoff'
        if 'FIRST_HALF' in value:return 'first_half'
        if 'SECOND_HALF' in value or '2ND_HALF' in value:return 'second_half'
        return ''
    target_phase=phase(target);source_phase=phase(source)
    if (target_phase or source_phase) and target_phase!=source_phase:return False
    # Keep amount/price calls factually consistent when ASR preserves numeric values.
    quantity_event=any(token in target or token in source for token in ('AMOUNT','TRANSFER_FEE','TRANSFER_VALUE'))
    if quantity_event:
        # A fee/amount line cannot be replaced with an unrelated event that
        # happens to mention the same generic ideas (pressure, expectation).
        if has_transfer(target) and not has_transfer(source):return False
        target_numbers=set(re.findall(r'\b\d+(?:[.,]\d+)?\b',plain(target_text or '')))
        source_numbers=set(re.findall(r'\b\d+(?:[.,]\d+)?\b',plain(source_text or '')))
        if target_numbers and source_numbers and target_numbers!=source_numbers:return False
        currencies=lambda text:set(re.findall(r'\b(?:dolar(?:es)?|euros?|libras?|pounds?)\b',plain(text or '')))
        target_currency=currencies(target_text);source_currency=currencies(source_text)
        if target_currency and source_currency and target_currency!=source_currency:return False
    return True

def candidate_allowed(original,source):
    if blocked_reasons(source):return False
    # Openings have curated pools; ordinary football speech cannot stand in
    # for a welcome or team presentation simply because it scores similarly.
    if intro_role(original['event']):return False
    role=intro_role(source.get('event',''))
    if role or source.get('event','').startswith('GENERIC_'):return False
    e=original['event'].upper();text=plain(source['transcript'])
    if not event_pair_compatible(e,source.get('event',''),original.get('transcript',''),source.get('transcript','')):return False
    # Preserve named competition references. A line about Ligue 1 is not a
    # safe substitute for the Champions Cup or a group-stage fixture.
    competitions=(
        'champions league','champions cup','champions league','euro league','euroleague','europa league',
        'premier league','barclays premier league','bundesliga','serie a','serie b','la liga',
        'fa cup','league cup','copa da liga inglesa','copa do mundo','libertadores','brasileirao','eurocopa','copa continental sul americana','copa continental','copa europa','uefa super cup','efa super cup','ea sports fc super cup','emirates cup','all stars cup','dfb pokal','dfb pocal','copa da alemanha',
        'campeonato brasileiro','ligue 1','ligue one','championship','copa america','copa américa','womens europa cup','women europa cup','women s europa cup',
    )
    target_text=plain(original.get('transcript','')); source_text=plain(source.get('transcript',''))
    target_comp={term for term in competitions if re.search(r'\b'+re.escape(plain(term))+r'\b',target_text)}
    source_comp={term for term in competitions if re.search(r'\b'+re.escape(plain(term))+r'\b',source_text)}
    if source_comp and target_comp and not (target_comp & source_comp):return False
    if source_comp and not target_comp:return False
    # Do not inject a result that the original scene does not state.
    target_event=original.get('event','').upper();source_event=source.get('event','').upper()
    result_tokens=('EQUALISER','EQUALIZER','HATTRICK','HAT_TRICK','TEAM_WON','TEAM_LOST','WINNING_BY','LOSING_BY','LOST_BY','DRAW_','DREW','LOSE','LOST','WON')
    source_result=next((token for token in result_tokens if token in source_event),None)
    target_result=next((token for token in result_tokens if token in target_event),None)
    if source_result and source_result!=target_result:return False
    stage_terms=(
        ('group_stage',('group stage','fase de grupos','fase de grupo')),
        ('quarterfinal',('quarter final','quarter-final','quartas de final','quarta de final')),
        ('semifinal',('semi final','semi-final','semifinal','semifinais')),
        ('final',('final da','grande final','finalissima','decisao do titulo')),
        ('first_round',('first round','primeira rodada','primeira fase')),
    )
    def competition_stage(value):
        folded=plain(value)
        for stage,phrases in stage_terms:
            if any(plain(phrase) in folded for phrase in phrases):return stage
        return ''
    target_stage=competition_stage(original.get('transcript',''));source_stage=competition_stage(source.get('transcript',''))
    if (source_stage or target_stage) and source_stage!=target_stage and any(token in target_event for token in ('LAE','COMPETITION','CUP_FINAL')):return False
    def debut_tone(event,text):
        value=plain(text)
        if any(token in event for token in ('NEGATIVE_DEBUT','RATING_POOR','RATING_BAD')) or re.search(r'\b(?:estreia ruim|jogou mal|nao jogou bem|abaixo da expectativa|atuacao apagada|partida apagada|foi mal hoje|decepcionante)\b',value):return 'negative'
        if any(token in event for token in ('POSITIVE_DEBUT','RATING_GOOD','RATING_EXCELLENT','RATING_EXCEPTIONAL')) or re.search(r'\b(?:otima estreia|grande estreia|bela apresentacao|comecou muito bem|estreia excelente|jogou muito|mandou bem|bom jogo|grande jogo|excelente partida|grande apresentacao)\b',value):return 'positive'
        if any(token in event for token in ('NEUTRAL_DEBUT','RATING_AVERAGE')) or re.search(r'\b(?:estreia discreta|na media|atuacao mediana|poderia ter sido melhor)\b',value):return 'neutral'
        return ''
    target_tone=debut_tone(target_event,original.get('transcript',''));source_tone=debut_tone(source_event,source.get('transcript',''))
    if target_tone and source_tone and target_tone!=source_tone:return False
    def match_result(text):
        value=plain(text)
        if re.search(r'\b(?:empatou|empate|igualou|draw|drew|equalizou|equaliser|equalizer)\b',value):return 'draw'
        if re.search(r'\b(?:perdeu|perder|derrota|foi derrotad[oa]|lost|losing|defeated)\b',value):return 'loss'
        if re.search(r'\b(?:venceu|vit[oó]ria|ganhou|levou a melhor|won|winner)\b',value):return 'win'
        return ''
    target_result_text=match_result(original.get('transcript',''));source_result_text=match_result(source.get('transcript',''))
    if source_result_text and target_result_text and source_result_text!=target_result_text:return False
    def event_result(event):
        if any(token in event for token in ('INCREASING_LEAD','EXTEND_THE_LEAD','WINNING_BY','TEAM_WON','WON_')):return 'win'
        if any(token in event for token in ('LEVEL','DRAW','EQUALISER','EQUALIZER','DREW')):return 'draw'
        if any(token in event for token in ('LOSING','LOST','DEFEAT','TEAM_LOST','BEHIND')):return 'loss'
        return ''
    target_event_result=event_result(target_event);source_event_result=event_result(source_event)
    if target_event_result and source_result_text and target_event_result!=source_result_text:return False
    if source_event_result and target_result_text and source_event_result!=target_result_text:return False
    if source_result_text and any(token in target_event for token in ('PREV','STORYLINE','SCORELINE')) and not target_result_text:return False
    score_pattern=r'\b(?:zero|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|\d{1,2})\s+a\s+(?:zero|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|\d{1,2})\b'
    target_score=set(re.findall(score_pattern,target_text));source_score=set(re.findall(score_pattern,source_text))
    if source_score and target_score!=source_score:return False
    # Shot type is material: a volley, header, chip and penalty are not
    # interchangeable merely because both end with a goal.
    shot_types=(
        ('header',('HEADER','HEADED','CABECEIO','CABECEOU')),
        ('volley',('VOLLEY','VOLEIO','VOLEOU')),
        ('penalty',('PEN_GOAL','PENALTY_GOAL','PENALTY_SCORED','PENALTY','PENALTI','PEN_PANENKA','PANENKA')),
        ('chip',('CHIP','CAVADINHA','COBERTURA')),
        ('finesse',('FINESSE','PLACED_SHOT','CHUTE_COLOCADO')),
        ('free_kick',('FREEKICK','FREE_KICK','FALTA')),
    )
    def shot_type(event,text):
        value=(event+' '+plain(text)).upper()
        return next((name for name,tokens in shot_types if any(token in value for token in tokens)), '')
    target_shot=shot_type(target_event,original.get('transcript',''));source_shot=shot_type(source_event,source.get('transcript',''))
    if target_shot and source_shot and target_shot!=source_shot:return False
    if 'GOAL_LOCATION' in target_event and 'BUILDUP' in source_event:return False
    target_card=any(token in target_event for token in ('RED_CARD','YELLOW_CARD','CARD'))
    if target_card and not any(token in source_text for token in ('cartao','vermelho','amarelo','expulso','expulsao')):return False
    if not source.get('event'):
        if any(token in e for token in ('OWN_GOAL','OWNGOAL')) and not any(term in text for term in ('gol contra','own goal')):return False
        for tokens,terms in ((('OFFSIDE','OS_CALL'),('impedimento','offside')), (('CORNER',),('escanteio','corner')), (('THROW_IN','THROWIN'),('lateral','throw in'))):
            if any(token in e for token in tokens) and not any(term in text for term in terms):return False
    if any(t in e for t in ('GOAL_SCORED','C_GOAL_','REPLAY_GOAL','CONSOLATION_GOAL')):
        if any(t in text for t in ('quase','nao entrou','nao foi gol','nao saindo','se entra','se der o replay','pode entrar','nao sai','pedindo para tomar','pedindo pra tomar','almost','nearly','not a goal','did not score','no goal','would have been')):return False
        if not source.get('event') and not any(t in text for t in ('golaco','gol maravilhoso','belo gol','lindo gol','belissimo gol','fundo da rede','estufar a rede','fez o gol','marcou o gol','faz um gol','gol de centro','what a goal','back of the net','he scores','he scored')) and not re.fullmatch(r'(?:g[o]+a?l+\s*)+',text):return False
    # Neutral replacements must not assert a fixed score, time or earlier
    # result that the target does not provide.
    if not source.get('event'):
        if any(t in text for t in ('primeiro gol foi','ja saiu um gol','hoje fez tres gols','22 agora','vinte minutos','cinco a um','27 5','15 9')):return False
    return True

def reference(event):
    e=event.upper();role=intro_role(event)
    if role=='welcome':return 'Boas-vindas à transmissão de futebol, apresentação do narrador e comentarista.'
    if role=='lineup':return 'Veja a escalação e a disposição tática das equipes na tela.'
    if role=='expectation':return 'Expectativa de uma boa partida de futebol entre as duas equipes.'
    for words,text in (
        (('OWN_GOAL','OWNGOAL'),'Gol contra: o jogador colocou a bola no próprio gol.'),
        (('GOAL_SCORED','C_GOAL_','REPLAY_GOAL','CONSOLATION_GOAL'),'Gol! A bola foi para o fundo da rede. Belo gol, comemoração.'),
        (('WOODWORK','HIT_POST'),'A bola acertou a trave ou o travessão; o gol não saiu.'),
        (('MISS','SHOTWIDE','NO_GOAL'),'Perdeu a chance de gol. Chutou para fora, a bola não entrou.'),
        (('SAVE','STOPPER'),'O goleiro fez uma grande defesa e impediu o gol.'),
        (('INTERCEPT','CLEARED','CLEARANCE','BLOCK','TCKL'),'A defesa interceptou, cortou a bola e recuperou a posse.'),
        (('PASS','CROSS'),'Passe, troca de passes e construção da jogada ofensiva.'),
        (('OFFSIDE','OS_CALL'),'Impedimento marcado pelo assistente.'),
        (('CORNER',),'Escanteio: bola parada para cobrança na área.'),
        (('RED','YELLOW','CARD'),'O árbitro mostrou cartão por uma falta.'),
        (('FOUL',),'O árbitro marcou a falta na disputa de bola.'),
        (('SHOT','ATTACK','CHANCE'),'O time ataca, cria uma chance e tenta finalizar em gol.'),
        (('FULLTIME','FT_'),'O jogo terminou. Apito final e avaliação da partida.'),
        (('HALFTIME','HT_'),'Fim do primeiro tempo. Intervalo da partida.'),
    ):
        if any(w in e for w in words):return text
    return ''
