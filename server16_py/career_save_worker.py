"""Isolated x86 save editor. Never receives permission to publish a live save.

Reads the DATA container, edits fixed-size DB blocks using FifaLibrary16 and
rebuilds its payload CRC. The main process owns backup and publication.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

MAX_MONEY = 2_000_000_000
JOB_OFFER_MARKER = -16416


def job_offer_offset(data):
    """jo002 is the native JobOfferManager's 11-int serializer (50 bytes)."""
    offsets = []
    start = 160
    while True:
        start = data.find(b'jo002\0', start)
        if start < 0:
            break
        offsets.append(start)
        start += 6
    if len(offsets) != 1:
        raise ValueError('Bloco nativo de proposta ausente ou ambíguo.')
    offset = offsets[0]
    if data[offset+50:offset+56] != b'pj001\0' or any(
            offset < a+n and offset+50 > a for a,n in blocks(data)):
        raise ValueError('Layout da proposta nativa não reconhecido.')
    return offset


def read_job_offer(data):
    values = struct.unpack_from('<11i', data, job_offer_offset(data)+6)
    return {'team_id':values[0], 'league_id':values[1], 'date':values[6],
            'wage':values[7], 'source_club':values[8],
            'dispatch_pending':values[9]==JOB_OFFER_MARKER and values[10]==-1}


def job_offer_seed(save):
    dates={r.GetIntField('currdate') for r in save.rows('career_calendar')}
    if len(dates)!=1:
        raise ValueError('Data da carreira ausente ou ambígua.')
    return {'date':next(iter(dates)),
            'wage':save.one('career_managerinfo','userid',save.context()['userid']).GetIntField('wage')}


def stage_job_offer(data, request, seed):
    """Fixed-size patch after the DB inspection's fingerprint was revalidated."""
    if fingerprint(data)!=request['fingerprint']:
        raise ValueError('O save mudou. Reabra o painel e confirme o pedido novamente.')
    before=request['context']
    target,league=request['team_id'],request['league_id']
    if (before['player_id'] is not None or type(target) is not int or type(league) is not int
            or not 0<target<2_000_000 or not 0<league<2_000_000
            or not 0<before['club_id']<2_000_000 or target==before['club_id']):
        raise ValueError('Clube ou contexto da proposta inválido.')
    offset=job_offer_offset(data)
    existing=struct.unpack_from('<11i',data,offset+6)
    if existing[0]!=-1 or existing[8:]!=(-1,-1,-1):
        raise ValueError('Há uma proposta ou candidatura em andamento. Resolva-a no FIFA antes de pedir outra.')
    date,wage=seed['date'],seed['wage']
    from datetime import datetime
    if type(date) is not int or not 20000101<=date<=20991231:
        raise ValueError('Data da carreira não reconhecida.')
    datetime.strptime(str(date),'%Y%m%d')
    if type(wage) is not int or not 0<wage<=MAX_MONEY:
        raise ValueError('Salário do treinador não reconhecido.')
    payload=bytearray(data)
    struct.pack_into('<11i',payload,offset+6,target,league,0,0,0,0,date,wage,
                     before['club_id'],JOB_OFFER_MARKER,-1)
    struct.pack_into('<I',payload,132,zlib.crc32(payload[160:]))
    blocks(payload)
    return bytes(payload)


def prepare_job_offer(save, request):
    before = save.context()
    if before['player_id'] is not None:
        raise ValueError('Proposta de emprego disponível na carreira de treinador.')
    if any(before[k] != request['context'][k] for k in ('userid','club_id','player_id')):
        raise ValueError('O contexto da carreira mudou. Reabra o painel.')
    target, league = request['team_id'], request['league_id']
    if type(target) is not int or type(league) is not int or target <= 0 or target == before['club_id']:
        raise ValueError('Escolha outro clube para solicitar uma proposta.')
    save.one('teams','teamid',target)
    division = save.one('leagues','leagueid',league)
    if division.GetIntField('level') <= 0 or not any(
            r.GetIntField('teamid')==target and r.GetIntField('leagueid')==league
            and r.GetIntField('secondarytable')==0 for r in save.rows('leagueteamlinks')):
        raise ValueError('O clube não pertence à divisão selecionada neste save.')
    # The native adapter consumes this marker on the provider's owner thread.
    # It obtains the club's real standings/wage, adds the native offer and
    # calls InformOfJobOffer (email + event 0x82). No club is changed here.
    return stage_job_offer(save.data,request,job_offer_seed(save))


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def fifa_crc32(data):
    """DB v8's non-reflected CRC, identical to the native retirement engine."""
    table = []
    for byte in range(256):
        value = byte << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(value)
    crc = 0xFFFFFFFF
    for byte in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[((crc >> 24) ^ byte) & 255]
    return crc


def retirement_table_crc(payload, table):
    """Preserve the native sentinel and every unrelated table/index checksum."""
    header = int(table.CrcTableHeaderPosition)-32
    start = header+36
    record_size = struct.unpack_from('<I', payload, header+4)[0]
    valid = struct.unpack_from('<H', payload, header+18)[0]
    compressed = struct.unpack_from('<I', payload, header+12)[0]
    end = start+int(table.TableDescriptor.NFields)*16+record_size*valid+((compressed+7)&~7)
    if not 0 <= header < start <= end <= len(payload)-4:
        raise ValueError('Layout do CRC da aposentadoria não reconhecido.')
    if struct.unpack_from('<I', payload, end)[0] != 0xCDCDCDCD:
        struct.pack_into('<I', payload, end, fifa_crc32(memoryview(payload)[start:end]))


def blocks(data):
    if len(data) < 180 or struct.unpack_from('<I', data, 136)[0] != 56:
        raise ValueError('Formato de save não compatível com esta versão.')
    if struct.unpack_from('<I', data, 132)[0] != zlib.crc32(data[160:]):
        raise ValueError('O save não passou na verificação de integridade.')
    result, offset = [], 160
    while True:
        offset = data.find(b'DB\x00\x08', offset)
        if offset < 0:
            break
        size = struct.unpack_from('<I', data, offset+8)[0]
        count = struct.unpack_from('<I', data, offset+16)[0]
        if 24 <= size <= len(data)-offset and 0 < count < 512:
            result.append((offset, size))
            offset += size
        else:
            offset += 4
    if len(result) != 3:
        raise ValueError('Esperados três bancos no save. Operação cancelada.')
    return result


class Save:
    def __init__(self, data, meta, temporary, DbFile):
        self.data, self.meta = data, str(meta)
        self.databases, self.paths = [], []
        self._rows, self._record_owner, self._table_owner = {}, {}, {}
        self.dirty = set()
        self.changes = {}
        self.ranges = blocks(data)
        self.DbFile = DbFile
        for index, (offset, size) in enumerate(self.ranges):
            path = Path(temporary)/('block_%d.db' % index)
            path.write_bytes(data[offset:offset+size])
            database = DbFile(str(path), self.meta)
            if not database.Load():
                raise ValueError('Não foi possível abrir o banco do save.')
            self.paths.append(path)
            self.databases.append(database)
            for table in database.Table:
                self._table_owner[str(table.TableDescriptor.TableName)] = index

    def table(self, name, required=True):
        matches = [t for d in self.databases for t in d.Table
                   if str(t.TableDescriptor.TableName) == name]
        if len(matches) == 1:
            return matches[0]
        if required:
            raise ValueError('Tabela ausente ou ambígua: '+name)
        return None

    def rows(self, name):
        if name in self._rows:
            return self._rows[name]
        table = self.table(name, False)
        rows = [] if table is None else list(table.Records)[:table.NValidRecords]
        self._rows[name] = rows
        for index, row in enumerate(rows):
            self._record_owner[id(row)] = (self._table_owner[name], name, table, index)
        return rows

    def change(self, record, field, value):
        owner, name, table, index = self._record_owner[id(record)]
        key = (owner, name, index, field)
        old = self.changes[key][1] if key in self.changes else record.GetIntField(field)
        set_int(record, field, value)
        self.changes[key] = (table, old, value)
        self.dirty.add(owner)

    def one(self, name, field, value):
        rows = [r for r in self.rows(name) if r.GetIntField(field) == value]
        if len(rows) != 1:
            raise ValueError('Registro ausente ou ambíguo em '+name)
        return rows[0]

    def context(self):
        users = self.rows('career_users')
        if len(users) != 1:
            raise ValueError('Esta versão exige uma carreira com um único usuário.')
        user = users[0]
        uid, club = user.GetIntField('userid'), user.GetIntField('clubteamid')
        if club <= 0:
            raise ValueError('O usuário não está vinculado a um clube.')
        player = [r for r in self.rows('career_playasplayer') if r.GetIntField('userid') == uid]
        if len(player) > 1:
            raise ValueError('Jogador de carreira ambíguo.')
        pref = self.one('career_managerpref', 'managerprefid', uid)
        team = self.one('teams', 'teamid', club)
        return {'userid': uid, 'club_id': club, 'club': str(team.GetStringField('teamname')),
                'player_id': player[0].GetIntField('playerid') if player else None,
                'budget': pref.GetIntField('transferbudget'), 'currency': pref.GetIntField('currency')}

    def serialize(self):
        data = bytearray(self.data)
        for index, (database, path, (offset, size)) in enumerate(zip(self.databases, self.paths, self.ranges)):
            if index not in self.dirty:
                continue
            output = path.with_name(path.stem+'_out.db')
            payload = bytearray(self.data[offset:offset+size])
            layouts = {}
            for (owner, name, row_index, field), (table, old, value) in self.changes.items():
                if owner != index:
                    continue
                key = (name,field)
                if key not in layouts:
                    descriptor = table.TableDescriptor
                    column = next(f for f in descriptor.FieldDescriptors if str(f.FieldName)==field)
                    if str(column.FieldType) != 'Integer' or not 0 < column.Depth <= 31:
                        raise ValueError('Campo inteiro incompatível: '+field)
                    layouts[key] = (int(table.CrcTableHeaderPosition)+4+int(descriptor.NFields)*16,
                                    int(descriptor.RecordSize),int(column.BitOffset),int(column.Depth),int(column.RangeLow))
                start,record_size,bit_offset,depth,low = layouts[key]
                # DB v8 stores 16-byte field descriptors after the table CRC.
                # Validate the original encoded value before touching its bits.
                bit = (start+row_index*record_size)*8+bit_offset
                byte, shift = divmod(bit,8)
                width = (shift+depth+7)//8
                if byte < 0 or byte+width > len(payload):
                    raise ValueError('Campo fora do banco: '+field)
                word = int.from_bytes(payload[byte:byte+width], 'little')
                mask = (1<<depth)-1
                if ((word>>shift)&mask)+low != old:
                    raise ValueError('O layout do campo não foi validado: '+name+'.'+field)
                encoded = value-low
                if not 0 <= encoded <= mask:
                    raise ValueError('Valor fora da capacidade do campo: '+field)
                word = (word & ~(mask<<shift)) | (encoded<<shift)
                payload[byte:byte+width] = word.to_bytes(width,'little')
            if hasattr(self, 'retirement_summary'):
                tables = {name:table for (owner,name,_,_), (table,_,_) in self.changes.items() if owner==index}
                if set(tables) != {'players'}:
                    raise ValueError('A aposentadoria não pode alterar outras tabelas.')
                retirement_table_crc(payload, tables['players'])
            output.write_bytes(payload)
            # Recompute only the DB checksums; all other bytes stay identical.
            if not hasattr(self, 'retirement_summary'):
                reread = self.DbFile(str(output), self.meta)
                if not reread.Load() or not reread.ComputeAllCrc():
                    raise ValueError('Falha ao recalcular integridade do banco.')
            payload = output.read_bytes()
            if len(payload) != size:
                raise ValueError('A edição mudou o tamanho do banco %d (%d / %d). Operação cancelada.' % (index, len(payload), size))
            check = self.DbFile(str(output), self.meta)
            if not check.Load():
                raise ValueError('Falha na releitura do banco alterado.')
            verified_records = {}
            for (owner,name,row_index,field), (table,old,value) in self.changes.items():
                if owner!=index:continue
                if name not in verified_records:verified_records[name]=check.GetTable(name).Records
                if verified_records[name][row_index].GetIntField(field)!=value:
                    raise ValueError('A releitura não confirmou o campo '+field)
            data[offset:offset+size] = payload
        struct.pack_into('<I', data, 132, zlib.crc32(data[160:]))
        blocks(data)
        return bytes(data)


def set_int(record, field, value):
    if not record.SetField(field, int(value)) or record.GetIntField(field) != value:
        raise ValueError('Valor não aceito pelo save: '+field)


def catalog(databases, nations, nation_codes=None):
    tables = {str(t.TableDescriptor.TableName): t for db in databases for t in db.Table}
    def rows(name):
        t = tables.get(name)
        return [] if t is None else list(t.Records)[:t.NValidRecords]
    leagues = {r.GetIntField('leagueid'): {
        'id': r.GetIntField('leagueid'), 'name': str(r.GetStringField('leaguename')),
        'country_id': r.GetIntField('countryid'), 'level': r.GetIntField('level')}
        for r in rows('leagues') if r.GetIntField('level') > 0}
    teams = {r.GetIntField('teamid'): {'id': r.GetIntField('teamid'),
             'name': str(r.GetStringField('teamname')), 'asset_id': r.GetIntField('assetid')}
             for r in rows('teams')}
    links = {(r.GetIntField('leagueid'), r.GetIntField('teamid')) for r in rows('leagueteamlinks')
             if r.GetIntField('leagueid') in leagues and r.GetIntField('teamid') in teams
             and r.GetIntField('secondarytable') == 0}
    return {'nations': nations, 'nation_codes': nation_codes or {}, 'leagues': list(leagues.values()),
            'teams': list(teams.values()), 'links': sorted(links)}


def edit(save, request):
    change = save.change
    before = save.context()
    expected = request['context']
    for key in ('userid', 'club_id', 'player_id'):
        if before[key] != expected[key]:
            raise ValueError('O contexto da carreira mudou. Abra novamente a overlay.')
    if request['action'] in ('remove_retirement', 'remove_and_rejuvenate'):
        from datetime import date, timedelta
        from calendar import monthrange
        rejuvenate = request['action'] == 'remove_and_rejuvenate'
        age = request.get('target_age', 18)
        if type(age) is not int or not 12 <= age <= 50:
            raise ValueError('Idade-alvo fora do intervalo seguro de 12 a 50 anos.')
        if rejuvenate:
            dates = {row.GetIntField('currdate') for row in save.rows('career_calendar')}
            if len(dates) != 1:
                raise ValueError('Data da carreira ausente ou ambígua.')
            stamp = str(next(iter(dates)))
            current = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
        epoch = date(1582, 10, 14)
        players = save.rows('players')
        retiring = [row for row in players if row.GetIntField('isretiring') == 1]
        for row in retiring:
            change(row, 'isretiring', 0)
            if rejuvenate:
                birthday = epoch + timedelta(days=row.GetIntField('birthdate'))
                year = current.year-age-((current.month, current.day) < (birthday.month, birthday.day))
                birthday = date(year, birthday.month, min(birthday.day, monthrange(year, birthday.month)[1]))
                change(row, 'birthdate', (birthday-epoch).days)
        save.retirement_summary = {'mode': request['action'], 'target_age': age,
            'players_seen': len(players), 'players_retiring': len(retiring), 'players_changed': len(retiring)}
        return before
    uid, old = before['userid'], before['club_id']
    pref = save.one('career_managerpref', 'managerprefid', uid)
    if request['action'] == 'funds':
        amount = request['amount']
        if type(amount) is not int or not 0 < amount <= MAX_MONEY:
            raise ValueError('Valor de verba inválido.')
        if before['player_id'] is not None:
            raise ValueError('A verba está disponível na carreira de treinador.')
        total = before['budget'] + amount
        if total > MAX_MONEY:
            raise ValueError('O orçamento ultrapassaria o limite permitido.')
        change(pref, 'transferbudget', total)
        return dict(before, budget=total)
    if request['action'] != 'transfer':
        raise ValueError('Operação desconhecida.')
    target, league = request['team_id'], request['league_id']
    if type(target) is not int or type(league) is not int or target == old:
        raise ValueError('Escolha um clube diferente do atual.')
    target_team = save.one('teams', 'teamid', target)
    league_row = save.one('leagues', 'leagueid', league)
    if league_row.GetIntField('level') <= 0 or not any(
            r.GetIntField('teamid') == target and r.GetIntField('leagueid') == league
            and r.GetIntField('secondarytable') == 0 for r in save.rows('leagueteamlinks')):
        raise ValueError('O clube não pertence à divisão selecionada neste save.')
    player_id = before['player_id']
    if player_id is not None:
        if any(r.GetIntField('playerid') == player_id for r in save.rows('playerloans')):
            raise ValueError('Encerre o empréstimo do jogador antes de transferir.')
        links = [r for r in save.rows('teamplayerlinks') if r.GetIntField('playerid') == player_id]
        owned = [r for r in links if r.GetIntField('teamid') == old]
        if len(owned) != 1 or any(r.GetIntField('teamid') == target for r in links):
            raise ValueError('Vínculo de elenco ausente ou ambíguo.')
        roster = [r for r in save.rows('teamplayerlinks') if r.GetIntField('teamid') == target]
        if len(roster) >= 52:
            raise ValueError('O elenco de destino está cheio.')
        used = {r.GetIntField('jerseynumber') for r in roster}
        number = next((n for n in range(1,100) if n not in used), None)
        if number is None:
            raise ValueError('Não há número de camisa disponível no clube.')
        # Remove the departing player from saved lineups using a member of the
        # old squad that is not already in that particular lineup.
        old_roster = {r.GetIntField('playerid') for r in save.rows('teamplayerlinks')
                      if r.GetIntField('teamid') == old and r.GetIntField('playerid') != player_id}
        positions={r.GetIntField('playerid'):r.GetIntField('preferredposition1') for r in save.rows('players')
                   if r.GetIntField('playerid') in old_roster or r.GetIntField('playerid')==player_id}
        for name in ('teamsheets', 'default_teamsheets'):
            table = save.table(name, False)
            if table is None:
                continue
            fields = [str(f.FieldName) for f in table.TableDescriptor.FieldDescriptors]
            player_fields = [f for f in fields if f.startswith('playerid')]
            for row in save.rows(name):
                if 'teamid' not in fields or row.GetIntField('teamid') != old:
                    continue
                player_fields.sort(key=lambda f:int(f[8:]))
                for field in player_fields:
                    if row.GetIntField(field) == player_id:
                        if int(field[8:]) < 11:
                            reserve = next((f for f in player_fields if int(f[8:])>=11
                                            and row.GetIntField(f) in old_roster
                                            and (positions.get(row.GetIntField(f))==0)==(positions.get(player_id)==0)), None)
                            if reserve is None:
                                raise ValueError('Não há reserva para substituir o jogador no clube anterior.')
                            change(row, field, row.GetIntField(reserve))
                            change(row, reserve, -1)
                        else:
                            change(row, field, -1)
                replacement = next((row.GetIntField(f) for f in player_fields
                                    if row.GetIntField(f) in old_roster), None)
                for field in ('captainid','penaltytakerid','freekicktakerid','leftfreekicktakerid',
                              'rightfreekicktakerid','leftcornerkicktakerid','rightcornerkicktakerid','longkicktakerid'):
                    if field in fields and row.GetIntField(field)==player_id:
                        if replacement is None:
                            raise ValueError('Capitão ou cobrador do clube anterior indisponível.')
                        change(row,field,replacement)
            # Keep the transferred player available on the destination bench.
            for row in save.rows(name):
                if 'teamid' not in fields or row.GetIntField('teamid') != target:
                    continue
                if any(row.GetIntField(f)==player_id for f in player_fields):
                    continue
                empty=next((f for f in player_fields if int(f[8:])>=11 and row.GetIntField(f)<=0),None)
                if empty is None:
                    raise ValueError('A escalação de destino não tem uma vaga livre.')
                change(row,empty,player_id)
        change(owned[0], 'teamid', target)
        change(owned[0], 'jerseynumber', number)
        for row in save.rows('career_playercontract'):
            if row.GetIntField('playerid') == player_id:
                change(row, 'teamid', target)
        for row in save.rows('previousteam'):
            if row.GetIntField('playerid') == player_id:
                change(row, 'previousteamid', old)
        old_team=save.one('teams','teamid',old)
        team_table=save.table('teams')
        fields={str(f.FieldName) for f in team_table.TableDescriptor.FieldDescriptors}
        for field in ('captainid','penaltytakerid','freekicktakerid'):
            if field in fields and old_team.GetIntField(field)==player_id:
                change(old_team,field,next(iter(sorted(old_roster))))
    else:
        manager = save.one('career_managerinfo', 'userid', uid)
        change(manager, 'clubteamid', target)
        # The manager takes the destination club's budget rather than carrying
        # the previous club's finances to the new job.
        change(pref, 'transferbudget', target_team.GetIntField('transferbudget'))
    user = save.one('career_users', 'userid', uid)
    change(user, 'clubteamid', target)
    change(user, 'leagueid', league)
    # primarycompobjid is a CompData object, not a league database ID.
    primary = request.get('primarycompobjid')
    if type(primary) is not int or not 0 < primary <= 2000:
        raise ValueError('Competição principal do destino não identificada nos dados do jogo.')
    change(user, 'primarycompobjid', primary)
    stadiums = [r for r in save.rows('teamstadiumlinks') if r.GetIntField('teamid') == target]
    if len(stadiums) == 1:
        change(pref, 'stadiumid', stadiums[0].GetIntField('stadiumid'))
    return save.context()


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from db_worker import _prefer_bundled_site_packages
    _prefer_bundled_site_packages()
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    dll, game = Path(request['dll']).resolve(), Path(request['game']).resolve()
    sys.path.insert(0, str(dll.parent))
    import clr
    clr.AddReference(str(dll))
    from FifaLibrary import DbFile
    meta = game/'data/db/fifa_ng_db-meta.xml'
    with tempfile.TemporaryDirectory(prefix='server16-career-') as temporary:
        if request['op'] == 'catalog':
            base = DbFile(str(game/'data/db/fifa_ng_db.db'), str(meta))
            if not base.Load():
                raise ValueError('Não foi possível ler os clubes instalados.')
            nations = base.GetTable('nations')
            countries = {str(r.GetIntField('nationid')): str(r.GetStringField('nationname'))
                         for r in list(nations.Records)[:nations.NValidRecords]}
            country_codes = {str(r.GetIntField('nationid')): str(r.GetStringField('isocountrycode')).lower()
                             for r in list(nations.Records)[:nations.NValidRecords]}
            result = catalog([base], countries, country_codes)
        else:
            data = Path(request['path']).read_bytes()
            save = Save(data, meta, temporary, DbFile)
            result = {'context': save.context(), 'fingerprint': fingerprint(data)}
            if request['op'] == 'inspect':
                result['catalog'] = catalog(save.databases, {})
                if request.get('retirement_audit'):
                    result['players'] = [[r.GetIntField(f) for f in ('playerid', 'isretiring', 'birthdate')]
                                         for r in save.rows('players')]
                    result['date'] = save.rows('career_calendar')[0].GetIntField('currdate')
                if result['context']['player_id'] is None:
                    result['job_offer'] = read_job_offer(data)
                    result['job_offer_seed'] = job_offer_seed(save)
            elif request['op'] == 'prepare':
                if fingerprint(data) != request['fingerprint']:
                    raise ValueError('O save foi salvo novamente. Reabra a overlay e confirme o pedido.')
                if request['action']=='job_offer':
                    expected=save.context()
                    payload=prepare_job_offer(save,request)
                    result['job_offer']=read_job_offer(payload)
                else:
                    expected = edit(save, request)
                    payload = save.serialize()
                    if hasattr(save, 'retirement_summary'):
                        result['retirement'] = save.retirement_summary
                # Full reload and semantic verification before any publication.
                verify_dir = Path(temporary)/'verify'
                verify_dir.mkdir()
                verify = Save(payload, meta, verify_dir, DbFile)
                if verify.context() != expected:
                    raise ValueError('A releitura do save não confirmou a alteração.')
                if 'retirement' in result and (len(verify.rows('players')) != result['retirement']['players_seen']
                        or any(r.GetIntField('isretiring') == 1 for r in verify.rows('players'))):
                    raise ValueError('A releitura não confirmou a remoção da aposentadoria.')
                if request['action']=='job_offer' and read_job_offer(verify.data)!=result['job_offer']:
                    raise ValueError('A releitura não confirmou a proposta de emprego.')
                Path(request['output']).write_bytes(payload)
                result.update(context=expected, output_sha256=fingerprint(payload))
            else:
                raise ValueError('Comando inválido.')
        print(json.dumps({'ok': True, **result}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=True))
        raise SystemExit(1)
