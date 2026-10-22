"""Rebuild camera resources while preserving unrelated frozen Server16 members."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter
import pefile
from build_frontend_server_update import build as build_python


def build(server, camera, output):
    server, camera, output = map(lambda p: Path(p).resolve(), (server, camera, output))
    if server == output:
        raise ValueError('Build separately before replacing the installed Server.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='server16_camera_build_') as folder:
        intermediate = Path(folder) / 'Server16Python.exe'
        python_report = build_python(server, intermediate, ('server16_py', 'server16_py.first_person_runtime',
            'server16_py.app', 'server16_py.startup_diagnostics'), allow_new=True)
        original = CArchiveReader(str(server))
        archive = CArchiveReader(str(intermediate))
        raw = intermediate.read_bytes()
        writer = CArchiveWriter.__new__(CArchiveWriter)
        payload = io.BytesIO()
        toc = []
        renamed = []
        baseline_name = 'server16_py/assets/startup_baseline.json'
        baseline_path = Path(__file__).resolve().parents[1]/baseline_name
        baseline_entry = next((name for name in archive.toc if name.replace('\\', '/') == baseline_name), None)
        for name, (offset, length, size, compressed, kind) in archive.toc.items():
            if name.replace('\\', '/') == 'bin/server16_first_person_v13.dll':
                new_name = name.replace('server16_first_person_v13.dll', 'server16_first_person_v14.dll')
                entry = writer._write_blob(payload, camera.read_bytes(), new_name, kind, bool(compressed))
                renamed.append((name, new_name))
            elif name == baseline_entry:
                entry = writer._write_blob(payload, baseline_path.read_bytes(), name, kind, bool(compressed))
            else:
                entry = (payload.tell(), length, size, compressed, kind, name)
                payload.write(raw[archive._start_offset+offset:archive._start_offset+offset+length])
            toc.append(entry)
        if not baseline_entry:
            toc.append(writer._write_blob(payload, baseline_path.read_bytes(), baseline_name, 'x', True))
        if len(renamed) != 1:
            raise ValueError('Expected exactly one v13 camera DLL in the current release.')
        for option in archive.options:
            toc.append((0, 0, 0, 0, 'o', option))
        pos = payload.tell()
        table = writer._serialize_toc(toc)
        payload.write(table)
        cookie = list(struct.unpack(writer._COOKIE_FORMAT, raw[-writer._COOKIE_LENGTH:]))
        cookie[1:4] = [pos+len(table)+writer._COOKIE_LENGTH, pos, len(table)]
        payload.write(struct.pack(writer._COOKIE_FORMAT, *cookie))
        output.write_bytes(raw[:archive._start_offset]+payload.getvalue())
    pe = pefile.PE(str(output))
    checksum = pe.generate_checksum()
    with output.open('r+b') as stream:
        stream.seek(pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'))
        stream.write(struct.pack('<I', checksum))
    updated = CArchiveReader(str(output))
    old_name, new_name = renamed[0]
    assert len(original.toc)+(0 if baseline_entry else 1) == len(updated.toc)
    assert updated.options == original.options
    for name in original.toc:
        if name not in ('PYZ.pyz', old_name, baseline_entry):
            assert original.extract(name) == updated.extract(name), name
    assert updated.extract(new_name) == camera.read_bytes()
    assert updated.extract(baseline_name) == baseline_path.read_bytes()
    report = {'version': '0.2.13', 'output': str(output), 'bytes': output.stat().st_size,
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256(server.read_bytes()).hexdigest(),
              'camera_resource': new_name, 'camera_sha256': hashlib.sha256(camera.read_bytes()).hexdigest(),
              'preserved_archive_members': len(original.toc)-(3 if baseline_entry else 2),
              'preserved_python_modules': python_report['preserved_python_modules'],
              'python_modules': python_report['modules']}
    report['startup_baseline_sha256'] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--camera', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.server, args.camera, args.output), indent=2))
