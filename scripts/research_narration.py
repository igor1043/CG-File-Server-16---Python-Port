"""Read-only evidence capture for FIFA 16 commentary investigation."""
from pathlib import Path
import json, struct, re, sys, ctypes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(r'U:\fifa 16')
OUT = Path(__file__).resolve().parents[1] / 'artifacts' / 'narration_research'
OUT.mkdir(parents=True, exist_ok=True)

def big_entries(path):
    with path.open('rb') as f:
        h = f.read(16)
        if h[:4] not in (b'BIGF', b'BIG4'): return []
        count, size = struct.unpack_from('>II', h, 8)
        data = h + f.read(size - 16)
    pos, entries = 16, []
    for _ in range(count):
        offset, length = struct.unpack_from('>II', data, pos)
        end = data.index(0, pos + 8)
        name = data[pos+8:end].decode('latin1')
        entries.append(dict(name=name, offset=offset, size=length))
        pos = end + 1
    return entries

def main():
    archives = []
    for p in sorted(ROOT.glob('*.big')):
        try:
            entries = big_entries(p)
            matches = [e for e in entries if any(t in e['name'].lower() for t in ('por_br', 'speech', '.dbi', '.hdr', '.dat', '.sbr', '.sbs'))]
            archives.append(dict(path=str(p), count=len(entries), matches=matches))
            print(p.name, len(entries), len(matches), flush=True)
        except Exception as e: print(p.name, e)
    (OUT/'archives.json').write_text(json.dumps(archives, indent=2), encoding='utf8')
    from server16_py.memory_access import Memory
    from server16_py.windows_file_handles import find_exact_open_disk_path
    m = Memory()
    if m.attack('fifa16'):
        candidates = list(ROOT.glob('*.big')) + list((ROOT/'audiodata'/'speechdata').rglob('*.sbs'))
        paths = [str(p) for p in candidates if find_exact_open_disk_path(m.process_id, [p])]
        (OUT/'open_files.json').write_text(json.dumps(sorted(paths), indent=2), encoding='utf8')
        print('PID', m.process_id, 'BASE', hex(m.base_module), 'OPEN_FILES', len(paths), flush=True)
        print('\n'.join(p for p in paths if any(t in p.lower() for t in ('por_br','speech','.dbi','.big'))), flush=True)
        data = m.read_process_memory(m.base_module, 4096)
        peoff = struct.unpack_from('<I', data, 0x3c)[0]
        image_size = struct.unpack_from('<I', data, peoff + 0x50)[0]
        data = m.read_process_memory(m.base_module, image_size)
        strings = []
        for match in re.finditer(rb'[\x20-\x7e]{5,}', data):
            s = match.group().decode('ascii')
            if any(t in s.lower() for t in ('speech', 'commentary', 'por_br', '.dbi', '.sbs', '.sbr')):
                strings.append(dict(address=hex(m.base_module+match.start()), text=s))
        (OUT/'module_strings.json').write_text(json.dumps(strings, indent=2), encoding='utf8')
        print('AUDIO_STRINGS', len(strings), 'IMAGE_SIZE', image_size, flush=True)
        m.close()

if __name__ == '__main__': main()
