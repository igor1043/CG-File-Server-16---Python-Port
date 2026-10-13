"""Human-readable navigation over the game's commentary event names."""
import re
TOPICS=('Abertura e apresentação','Clima e gramado','Ataque e chances','Defesa e goleiro','Gols','Faltas e cartões','Bola parada e laterais','Formações e táticas','Comentários de jogadores','Call names de jogadores','Nomes de clubes','Comentários de clubes','Campeonatos e competições','Estádios e cidades','Intervalo e resultado','Outros comentários')

def topic(event, path='', transcript=''):
    e=event.upper();p=path.upper();t=transcript.casefold()
    if e.startswith(('PPLAYER_NAMES','PSIMPLE_SURNAME')) or 'CALLNAME' in e or '10_PLAYER' in p:return 'Call names de jogadores'
    if 'RAINBOW' not in e and any(x in e for x in ('WEATHER','RAIN','SNOW')):return 'Clima e gramado'
    if e.startswith(('SBANTER_STADIUM','SINTROSEQ1_STADIUM')) or any(x in e for x in ('STADIUM','VENUE','CITY_NAME')):return 'Estádios e cidades'
    # c/l events are named competition/league variants, unlike generic b events.
    if event.startswith(('c','l')) and any(x in e for x in ('CUP','LEAGUE','COMPETITION','TOURNAMENT','CHAMPIONSHIP')):return 'Campeonatos e competições'
    if event.startswith('t') and any(x in e for x in ('BANTER','COMP_TEAM','TS_TEAM','LAE','LAL')):
        return 'Campeonatos e competições' if 'CUP' in e and 'TEAM' not in e else 'Comentários de clubes'
    if event.startswith('t') or '00_TEAM' in p:return 'Nomes de clubes'
    if e.startswith(('TINTRO','TTEAM','TTR_','TCLUB')) or any(x in e for x in ('TEAM_NAME','CLUB_NAME')) or '00_TEAM' in p:return 'Nomes de clubes'
    if 'FORMATION' in e or 'TACTIC' in e:return 'Formações e táticas'
    if any(x in e for x in ('GOAL_SCORED','C_GOAL_','REPLAY_GOAL','CONSOLATION_GOAL','GOLDEN_GOAL')):return 'Gols'
    if any(x in e for x in ('SAVE','BLOCK','KEEPER','CLEAN_SHEET','CLEARED','CLEARANCE','INTERCEPT','DEFEND','DEFENCE','DEFENSE','GOALKICK','GOAL_KICK')):return 'Defesa e goleiro'
    if any(x in e for x in ('MISS','SHOTWIDE','WOODWORK','NO_GOAL')):return 'Ataque e chances'
    if 'GOAL' in e and not any(x in e for x in ('TOWARDS_GOAL','GOAL_LINE','GOAL_DIFFERENTIAL')):return 'Gols'
    if any(x in e for x in ('FOUL','CARD','PENALTY','PENALTIES','DIRECT_FK','FREEKICK','FREE_KICK')):return 'Faltas e cartões'
    if any(x in e for x in ('CORNER','OFFSIDE','THROW_IN','THROWIN')):return 'Bola parada e laterais'
    if any(x in e for x in ('PLAYER','DEBUT','LEGEND','PTW','BIRTHDAY','SUBSTIT','INJUR')):return 'Comentários de jogadores'
    if any(x in e for x in ('INTRO','HELLO','KICKOFF','WEATHER','STADIUM')):return 'Abertura e apresentação'
    if any(x in e for x in ('FULLTIME','HALFTIME','FT_','HT_','FINAL_WHISTLE','RESULT','WINNER','LEAGUE_TABLE')):return 'Intervalo e resultado'
    if any(x in e for x in ('ATTACK','SHOT','CHANCE','DRIBBL','FINISH','BREAKAWAY','CROSS','PASS','HIT_POST')):return 'Ataque e chances'
    if any(x in t for x in ('não entrou','na trave','quase entrou','contra-ataque')):return 'Ataque e chances'
    if any(x in t for x in ('você ligado','boa noite','boa tarde','bem-vindo','estamos prontos','decisão de campeonato')):return 'Abertura e apresentação'
    if any(x in t for x in ('goleiro','defendeu','defesa','marcação')):return 'Defesa e goleiro'
    if any(x in t for x in ('levou o gol','belo gol','golaço','marcou o gol','fez o gol')) or re.fullmatch(r'(?:g[o]+a?l+[\s!,.]*)+',t.strip()):return 'Gols'
    if any(x in t for x in ('falta','cartão','pênalti')):return 'Faltas e cartões'
    if any(x in t for x in ('escanteio','lateral','impedimento')):return 'Bola parada e laterais'
    # The supplied library also contains English commentary. Preserve the
    # same scene groups before multilingual semantic matching.
    if any(x in t for x in ('off target','missed the chance','almost a goal','not a goal','wide of','crossbar','counter attack')):return 'Ataque e chances'
    if any(x in t for x in ('what a goal','back of the net','he scores','he scored')) or t.strip().rstrip('!.')=='goal':return 'Gols'
    if any(x in t for x in ('goalkeeper','great save','good save','defence','defense','tackle')):return 'Defesa e goleiro'
    if any(x in t for x in ('yellow card','red card','foul','penalty')):return 'Faltas e cartões'
    if any(x in t for x in ('corner kick','throw in','throw-in','offside')):return 'Bola parada e laterais'
    if any(x in t for x in ('welcome','good evening','good afternoon','starting eleven','line-ups','lineups')):return 'Abertura e apresentação'
    if any(x in t for x in ('full time','half time','final whistle')):return 'Intervalo e resultado'
    return 'Outros comentários'

def update_topics(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='topic_metadata'").fetchone():
        db.execute('CREATE TABLE topic_metadata (version INTEGER PRIMARY KEY)')
    rebuild=not db.execute('SELECT 1 FROM topic_metadata WHERE version=4').fetchone()
    for table in ('clips','sources'):
        columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        if 'topic' not in columns:db.execute('ALTER TABLE '+table+" ADD COLUMN topic TEXT DEFAULT ''")
        rows=db.execute('SELECT key,event,transcript,'+('wav' if table=='clips' else 'path')+' AS path FROM '+table+('' if rebuild else " WHERE topic='' OR topic IS NULL")).fetchall()
        db.executemany('UPDATE '+table+' SET topic=? WHERE key=?',[(topic(r['event'],r['path'],r['transcript']),r['key']) for r in rows])
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",(table+'_topic',)).fetchone():
            db.execute('CREATE INDEX '+table+'_topic ON '+table+'(topic)')
    if rebuild:db.execute('INSERT OR IGNORE INTO topic_metadata VALUES (4)')
    db.commit()
