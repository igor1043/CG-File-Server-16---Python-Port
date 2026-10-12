"""Bounded BIG reader and EA Harmony SBR field decoder.

SBR fields are arrays, not one audio per DSET. Every logical row is retained;
audio blobs shared by rows are deduplicated only during decoding.
"""
from __future__ import annotations
from pathlib import Path
import struct
from dataclasses import dataclass

@dataclass(frozen=True)
class BigEntry:
    name: str
    offset: int
    size: int

class BigArchive:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as f:
            h = f.read(16)
            if h[:4] not in (b'BIGF', b'BIG4'):
                raise ValueError(f'BIG inválido: {self.path}')
            count, length = struct.unpack_from('>II', h, 8)
            if not 16 <= length <= min(self.path.stat().st_size, 64*1024*1024):
                raise ValueError('Diretório BIG fora dos limites')
            data = h + f.read(length-16)
        self.entries = []
        pos = 16
        for _ in range(count):
            offset, size = struct.unpack_from('>II', data, pos)
            end = data.index(0, pos+8)
            name = data[pos+8:end].decode('latin1').replace('\\', '/')
            if offset + size > self.path.stat().st_size:
                raise ValueError(f'Entrada BIG truncada: {name}')
            self.entries.append(BigEntry(name, offset, size))
            pos = end+1

    def read(self, entry):
        with self.path.open('rb') as f:
            f.seek(entry.offset)
            data = f.read(entry.size)
        if len(data) != entry.size:
            raise ValueError('Leitura BIG incompleta')
        return data

class HarmonyBank:
    def __init__(self, data: bytes):
        if data[:4] not in (b'SBle', b'SBbe'):
            raise ValueError('SBR Harmony inválido')
        self.data = data
        self.endian = '<' if data[:4] == b'SBle' else '>'
        self.data_offset = self.u32(0x20)
        count, table = self.u16(0x0a), self.u32(0x18)
        self.rows = []
        self.datasets = []
        for i in range(count):
            off = self.u32(table+8*i)
            if data[off:off+4] not in (b'TESD', b'DSET'):
                raise ValueError(f'DSET inválido em {off:x}')
            dataset_id = self.u32(off+8)
            group_id = self.u32(off+12)
            values, fields = self.u32(off+0x38), self.u16(off+0x3c)
            if values > 1000000 or fields > 256:
                raise ValueError('Contagem SBR fora dos limites')
            columns = {}
            for j in range(fields):
                p = off+0x48+j*0x18
                tag = data[p:p+4]
                columns[tag] = self.field(p, values)
            audio_tag = b'FFO.' if b'FFO.' in columns else b'MAR.'
            if audio_tag not in columns:
                raise ValueError(f'DSET sem OFF/RAM: {dataset_id:x}')
            ds = dict(id=dataset_id, index=i, count=values, fields=[t.decode('ascii', errors='replace') for t in columns])
            self.datasets.append(ds)
            unique_index, previous = -1, None
            for j, sound_offset in enumerate(columns[audio_tag]):
                # vgmstream indexes physical sounds; our catalog also retains aliases.
                if sound_offset != previous:
                    unique_index += 1
                previous = sound_offset
                self.rows.append(dict(dataset_id=dataset_id, group_id=group_id, dataset_index=i,
                    row=j, variant=unique_index, sound_id=columns.get(b'DIS.', [0]*values)[j],
                    offset=sound_offset, storage='sbs' if audio_tag==b'FFO.' else 'sbr',
                    sbs_id=columns.get(b'SBS.', [0]*values)[j]))

    def number(self, pos, fmt):
        return struct.unpack_from(self.endian+fmt, self.data, pos)[0]
    def u16(self, pos): return self.number(pos,'H')
    def u32(self, pos): return self.number(pos,'I')
    def u64(self, pos): return self.number(pos,'Q')

    def field(self, p, count):
        kind, flags, base, table = self.data[p+5], self.u16(p+6), self.u64(p+8), self.u32(p+16)
        width, shift = flags >> 8, flags & 255
        if kind == 0:
            return [base]*count
        if kind == 1:
            step = self.number(p+6,'h')
            return [base+step*i for i in range(count)]
        if kind in (2,3):
            if width not in (1,2,4,8):
                raise ValueError(f'Largura de campo desconhecida: {width}')
            n = count if kind==2 else base
            if kind==3 and not 1<=n<=count:
                raise ValueError('Contagem de valores distintos SBR inválida')
            if table+n*width>len(self.data):
                raise ValueError('Tabela SBR truncada')
            fmt = {1:'B',2:'H',4:'I',8:'Q'}[width]
            vals = [self.number(table+i*width,fmt) for i in range(n)]
            if kind==2:
                return [base+(v << shift) for v in vals]
            if not 1 <= shift <= 32:
                raise ValueError('Largura de índice SBR inválida')
            index_start = table + n*width
            if index_start+(count*shift+7)//8>len(self.data):
                raise ValueError('Índices SBR truncados')
            packed = int.from_bytes(self.data[index_start:index_start+(count*shift+7)//8], 'little')
            indices = [(packed >> (j*shift)) & ((1<<shift)-1) for j in range(count)]
            if any(i>=n for i in indices):
                raise ValueError('Índice SBR fora da tabela')
            return [vals[i] for i in indices]
        if kind == 4:
            return [self.u64(table+i*8) for i in range(count)]
        raise ValueError(f'Tipo de campo SBR desconhecido: {kind}')

def sps_size(data: bytes, start=0):
    """Walk SPS blocks to the end marker; never include the following sound."""
    p = start
    if data[p:p+4] == b'slot': p += 0x30
    audio_start = p
    if p+4 > len(data) or data[p] != 0x48:
        raise ValueError(f'SPS sem cabeçalho em {p:x}')
    while p+4 <= len(data):
        block = int.from_bytes(data[p:p+4], 'big')
        kind, size = block >> 24, block & 0xffffff
        if kind == 0x45:
            end=p+max(4,size)
            if end>len(data):raise ValueError('Final SPS truncado')
            return audio_start, end-audio_start
        if size < 4 or p+size > len(data):
            raise ValueError(f'Bloco SPS inválido em {p:x}: {block:x}')
        p += size
    raise ValueError('SPS sem marcador final')
