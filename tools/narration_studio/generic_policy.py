"""Content checks and reviewed pools for reusable football commentary."""
from pathlib import Path
import functools,json,re,unicodedata

from core import WORK

def female_reference(text):
    text=plain(text)
    if re.search(r'\b(jogadora|jogadoras|goleira|goleiras|atacante feminina|juiza|arbitra)\b',text):return True
    if re.search(r'\b(she (shoots|scores|passes|dribbles|takes|hits|runs|plays|saves)|her (shot|goal|pass|save))\b',text):return True
    # 'ela' may refer to the ball. Reject only player actions and possession.
    return bool(re.search(r'\b(ela (recupera|perde|ganha|empata|dribla|chuta|bate|finaliza|faz|mete|recebe|domina|pega|toca|passa|cruza|cabeceia|corre|arranca|marca|carrega|nao conseguiu)|e dela|gol dela|segundo dela|ela era a ultima|elas (jogam|atacam))\b',text))

def plain(text):
    text=''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+',' ',text).strip()

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
    return [s for s in sources if not blocked_reasons(s) and re.search(patterns[role],plain(s['transcript']))]

def candidate_allowed(original,source):
    if blocked_reasons(source):return False
    # Openings have curated pools; ordinary football speech cannot stand in
    # for a welcome or team presentation simply because it scores similarly.
    if intro_role(original['event']):return False
    role=intro_role(source.get('event',''))
    if role or source.get('event','').startswith('GENERIC_'):return False
    e=original['event'].upper();text=plain(source['transcript'])
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
