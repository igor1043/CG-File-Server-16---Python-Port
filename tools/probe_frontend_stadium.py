"""Read-only FIFA 16 front-end stadium investigation. Never writes game memory."""
from __future__ import annotations

import argparse
import bisect
import ctypes
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'runtime/dev_deps')]


def main():
    import pefile
    import psutil
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from server16_py.memory_access import Memory
    from server16_py.offsets import Offsets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--function', action='append', default=[], help='RVA in hex')
    parser.add_argument('--calls-to', action='append', default=[], help='RVA in hex')
    parser.add_argument('--references-to', action='append', default=[], help='RIP-relative global RVA in hex')
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--offline', type=Path, help='Read a captured code/constant image instead of the process')
    parser.add_argument('--term', help='Additional string expression for the reference scan')
    parser.add_argument('--vtable-global', action='append', default=[], help='RVA of pointer to object')
    parser.add_argument('--read', action='append', default=[], help='Absolute address:size in hex')
    parser.add_argument('--range', action='append', default=[], help='RVA begin:end in hex')
    args = parser.parse_args()
    proc = None if args.offline else next(p for p in psutil.process_iter(['name', 'exe'])
                if (p.info['name'] or '').lower() == 'fifa16.exe')
    image_path = Path('U:/fifa 16/fifa16.exe') if args.offline else Path(proc.info['exe'])
    pe = pefile.PE(str(image_path), fast_load=True)
    if args.offline:
        class Snapshot:
            base_module = 0x140000000
            def __init__(self):self.data=args.offline.read_bytes()
            def read_process_memory(self,address,size):
                offset=address-self.base_module
                if offset<0 or offset+size>len(self.data):raise RuntimeError('Not captured')
                return self.data[offset:offset+size]
            def read_int64(self,address):return struct.unpack('<Q',self.read_process_memory(address,8))[0]
            def get_string(self,*args):return 'offline'
            def get_int(self,*args):return 0
            def close(self):pass
        memory=Snapshot()
    else:
        memory = Memory()
        memory.process_id = proc.pid
        memory.process_handle = memory.kernel32.OpenProcess(0x410, False, proc.pid)
        if not memory.process_handle:
            raise OSError('Read-only OpenProcess failed')
        memory.base_module = memory._get_base_address(str(image_path))
    base = memory.base_module
    out = ROOT / 'artifacts/frontend_stadium_research'
    out.mkdir(parents=True, exist_ok=True)
    pdata = next(s for s in pe.sections if s.Name.startswith(b'.pdata')).get_data()
    functions = sorted((a, b) for a, b, _ in struct.iter_unpack('<III', pdata[:len(pdata)//12*12])
                       if 0 < a < b < pe.OPTIONAL_HEADER.SizeOfImage)
    starts = [a for a, _ in functions]
    report = {'pid': proc.pid if proc else None, 'base': hex(base), 'ram_write_access': False}
    for value in args.vtable_global:
        pointer = memory.read_int64(base + int(value, 16))
        vtable = memory.read_int64(pointer)
        entries = list(struct.unpack('<32Q', memory.read_process_memory(vtable, 256)))
        report['vtable_' + value] = {'object': hex(pointer), 'vtable_rva': hex(vtable-base),
                                   'entries': [hex(v-base) for v in entries]}
    for value in args.read:
        address, size = (int(part, 16) for part in value.split(':'))
        raw = memory.read_process_memory(address, size)
        report['read_' + value] = {'hex': raw.hex(), 'int32': list(struct.unpack('<' + 'i'*(size//4), raw[:size//4*4]))}
    offsets = Offsets()
    for label, root, chain in [('page', offsets.ORIPGBASE, offsets.PG1),
                               ('match_stadium', offsets.ORISTADIDBASE, offsets.S)]:
        try:
            report[label] = memory.get_string(root, chain, 96) if label == 'page' else memory.get_int(root, chain)
        except Exception as error:
            report[label] = str(error)

    def read_chunks(section):
        for offset in range(0, section.Misc_VirtualSize, 1 << 20):
            rva = section.VirtualAddress + offset
            size = min((1 << 20) + 256, section.Misc_VirtualSize - offset)
            try:
                yield rva, memory.read_process_memory(base + rva, size)
            except RuntimeError:
                pass

    refs = []
    if args.references_to:
        targets = {int(value,16) for value in args.references_to}
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:continue
            for rva,data in read_chunks(section):
                for match in re.finditer(rb'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....',data,re.S):
                    source=rva+match.start()
                    target=source+7+struct.unpack_from('<i',match[0],3)[0]
                    if target in targets:refs.append((source,'global_'+hex(target)))
    if args.scan:
        targets = {}
        term = re.compile((args.term or 'favorit|favourit|festadium|front.?end.?stadium|backgroundstadium|backgrounddp|stadiumbackground|reload.*stadium|(?:start|change).*stadium|stadium.*(?:change|background)|FE_STADIUM').encode(), re.I)
        for section in pe.sections:
            if section.Characteristics & 0x20000000:
                continue
            for rva, data in read_chunks(section):
                for match in re.finditer(rb'[\x20-\x7e]{5,300}', data):
                    if term.search(match[0]):
                        targets[rva + match.start()] = match[0].decode('ascii')
        (out / 'strings.json').write_text(json.dumps({hex(k):v for k,v in targets.items()}, indent=2), encoding='utf8')
        pattern = re.compile(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....', re.S)
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            for rva, data in read_chunks(section):
                for match in pattern.finditer(data):
                    source = rva + match.start()
                    target = source + 7 + struct.unpack_from('<i', match[0], 3)[0]
                    if target in targets:
                        refs.append((source, targets[target]))
        report['strings'] = len(targets)
        report['references'] = len(refs)
    if args.calls_to:
        targets = {int(v, 16) for v in args.calls_to}
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            for rva, data in read_chunks(section):
                for match in re.finditer(rb'\xe8....', data, re.S):
                    source = rva + match.start()
                    target = source + 5 + struct.unpack_from('<i', match[0], 1)[0]
                    if target in targets:
                        refs.append((source, 'call_' + hex(target)))
    refs.extend((int(value, 16), 'manual') for value in args.function)
    refs.extend((int(value.split(':')[0], 16), 'range:' + value) for value in args.range)
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    decoder.skipdata = True
    def describe(instruction):
        line = f'{instruction.address:08x} {instruction.mnemonic:8} {instruction.op_str}'
        match = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', instruction.op_str)
        if match:
            disp = int(match[2], 16) * (1 if match[1] == '+' else -1)
            target = instruction.address + instruction.size + disp
            line += f' ; RVA {target:x}'
            try:
                raw = memory.read_process_memory(base + target, 128).split(b'\0', 1)[0]
                if len(raw) >= 3 and all(32 <= b < 127 for b in raw):
                    line += ' ' + repr(raw.decode('ascii'))
            except RuntimeError:
                pass
        return line
    results = []
    for source, label in refs:
        index = bisect.bisect_right(starts, source) - 1
        begin, end = functions[index] if index >= 0 else (source, source + 512)
        if not begin <= source < end or end - begin > 100000:
            begin, end = source, source + 512
        if label.startswith('range:'):
            begin, end = (int(part, 16) for part in label[6:].split(':'))
        filename = f'{begin:08x}.asm'
        try:
            code = memory.read_process_memory(base + begin, end - begin)
            (out / filename).write_text('\n'.join(describe(i) for i in decoder.disasm(code, begin)), encoding='utf8')
            results.append({'label': label, 'xref': hex(source), 'function': hex(begin), 'end': hex(end), 'file': filename})
        except Exception as error:
            results.append({'label': label, 'error': str(error)})
    report['functions'] = results
    name = 'scan.json' if args.scan else 'followup.json'
    (out / name).write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))
    memory.close()


if __name__ == '__main__':
    main()
