"""Bounded, read-only DB v8 projection for the career panel.

The editor remains isolated in the x86 worker. Only uncompressed strings and
integers needed by the panel are decoded here, using the installed metadata.
Unsupported layouts fall back to the existing editor inspection.
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from .career_save_worker import Save, blocks, catalog, fingerprint, job_offer_seed, read_job_offer


@lru_cache(maxsize=4)
def _metadata(path, size, modified):
    root = ET.parse(path).getroot()
    return {t.attrib['shortname'].encode('ascii'): (
        t.attrib['name'], {f.attrib['shortname'].encode('ascii'): f.attrib
                           for f in t.findall('fields/field')}) for t in root.findall('table')}


class Record:
    def __init__(self, data, start, fields):
        self.data, self.start, self.fields = data, start, fields

    def GetIntField(self, name):
        kind, bit, depth, low = self.fields[name]
        if kind != 3 or not 0 < depth <= 32:
            raise ValueError('Campo inteiro não reconhecido: '+name)
        byte, shift = divmod(bit, 8)
        word = int.from_bytes(self.data[self.start+byte:self.start+byte+(shift+depth+7)//8], 'little')
        return ((word >> shift) & ((1 << depth)-1)) + low

    def GetStringField(self, name):
        kind, bit, depth, _ = self.fields[name]
        if kind != 0 or bit % 8 or depth % 8:
            raise ValueError('Campo de texto não reconhecido: '+name)
        start = self.start+bit//8
        return self.data[start:start+depth//8].split(b'\0', 1)[0].decode('utf-8', errors='replace')


class Database:
    def __init__(self, data, offset, size, metadata):
        if data[offset:offset+4] != b'DB\0\x08':
            raise ValueError('Versão de banco não reconhecida.')
        count = struct.unpack_from('<I', data, offset+16)[0]
        directory_end = offset+24+count*8+4
        if not 0 < count < 512 or directory_end > offset+size:
            raise ValueError('Diretório de tabelas inválido.')
        self.tables = {}
        for index in range(count):
            short, relative = struct.unpack_from('<4sI', data, offset+24+index*8)
            if short not in metadata:
                continue
            name, definitions = metadata[short]
            if name not in ('nations', 'teams', 'leagues', 'leagueteamlinks', 'career_users',
                            'career_playasplayer', 'career_managerpref', 'career_managerinfo', 'career_calendar'):
                continue
            start = directory_end+relative
            if start < directory_end or start+36 > offset+size:
                raise ValueError('Tabela fora do banco.')
            record_size = struct.unpack_from('<I', data, start+4)[0]
            allocated, valid = struct.unpack_from('<HH', data, start+16)
            field_count = data[start+24]
            records = start+36+field_count*16
            if (not record_size or not field_count or valid > allocated
                    or records+allocated*record_size > offset+size):
                raise ValueError('Registros fora do banco.')
            fields = {}
            for column in range(field_count):
                kind, bit, short_field, depth = struct.unpack_from('<II4sI', data, start+36+column*16)
                definition = definitions.get(short_field)
                if definition is None:
                    continue
                if bit+depth > record_size*8:
                    raise ValueError('Campo fora do registro.')
                fields[definition['name']] = (kind, bit, depth, int(definition.get('rangelow', 0)))
            self.tables[name] = [Record(data, records+i*record_size, fields) for i in range(valid)]


class CareerRead:
    context = Save.context
    one = Save.one

    def __init__(self, data, meta):
        self.data = data
        stat = meta.stat()
        metadata = _metadata(str(meta), stat.st_size, stat.st_mtime_ns)
        self.databases = [Database(data, offset, size, metadata) for offset, size in blocks(data)]

    def rows(self, name):
        matches = [db.tables[name] for db in self.databases if name in db.tables]
        if len(matches) > 1:
            raise ValueError('Tabela ambígua: '+name)
        return matches[0] if matches else []


def _catalog(databases, nations, codes=None):
    # Adapter keeps the catalog's filtering identical to the editing worker.
    from types import SimpleNamespace
    adapted = [SimpleNamespace(Table=[SimpleNamespace(
        TableDescriptor=SimpleNamespace(TableName=name), Records=rows, NValidRecords=len(rows))
        for name, rows in db.tables.items()]) for db in databases]
    return catalog(adapted, nations, codes)


def read(game, request):
    game = Path(game)
    meta = game/'data/db/fifa_ng_db-meta.xml'
    if request['op'] == 'catalog':
        data = (game/'data/db/fifa_ng_db.db').read_bytes()
        stat = meta.stat()
        db = Database(data, 0, len(data), _metadata(str(meta), stat.st_size, stat.st_mtime_ns))
        nations = db.tables['nations']
        countries = {str(r.GetIntField('nationid')): r.GetStringField('nationname') for r in nations}
        codes = {str(r.GetIntField('nationid')): r.GetStringField('isocountrycode').lower() for r in nations}
        return {'ok': True, **_catalog([db], countries, codes)}
    if request['op'] != 'inspect':
        raise ValueError('O leitor não permite alterações.')
    save = CareerRead(Path(request['path']).read_bytes(), meta)
    result = {'ok': True, 'context': save.context(), 'fingerprint': fingerprint(save.data),
              'catalog': _catalog(save.databases, {})}
    if result['context']['player_id'] is None:
        result.update(job_offer=read_job_offer(save.data), job_offer_seed=job_offer_seed(save))
    return result
