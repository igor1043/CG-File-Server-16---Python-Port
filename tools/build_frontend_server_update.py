"""Update selected Python modules while preserving an existing frozen Server16."""
import argparse
import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import sys
import zlib

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter

ROOT=Path(__file__).resolve().parents[1]
MODULES=('server16_py.frontend_stadium_panel','server16_py.frontend_stadium_selection')


def module_source(name, kind):
    path=ROOT/Path(*name.split('.'))
    return path/'__init__.py' if kind==1 else path.with_suffix('.py')


def build(server,output,modules=MODULES,allow_new=False):
    modules=tuple(modules)
    if not modules or any((name!='server16_py' and not name.startswith('server16_py.')) or
                          not all(part.isidentifier() for part in name.split('.')) for name in modules):
        raise ValueError('Select existing server16_py modules')
    server=Path(server).resolve();output=Path(output).resolve()
    if server==output:raise ValueError('Build to a separate file before installation')
    archive=CArchiveReader(str(server))
    original=server.read_bytes()
    if archive._end_offset!=len(original):raise ValueError('Signed or trailing data is not supported')
    cookie=struct.unpack(CArchiveWriter._COOKIE_FORMAT,original[-CArchiveWriter._COOKIE_LENGTH:])
    if cookie[4]!=sys.version_info.major*100+sys.version_info.minor:
        raise ValueError('Use the same Python version as the installed Server16')
    pyz=archive.open_embedded_archive('PYZ.pyz')
    previous=archive.extract('PYZ.pyz')
    if previous[4:8]!=importlib.util.MAGIC_NUMBER:raise ValueError('Python bytecode version changed')
    payload=bytearray(previous[:17]);pyz_toc=[]
    sources={}
    for name,(kind,offset,length) in pyz.toc.items():
        chunk=previous[offset:offset+length]
        if name in modules:
            source=module_source(name,kind)
            raw=source.read_bytes();sources[name]=hashlib.sha256(raw).hexdigest()
            code=compile(raw,pyz.extract(name).co_filename,'exec')
            chunk=zlib.compress(marshal.dumps(code),6)
        pyz_toc.append((name,(kind,len(payload),len(chunk))))
        payload.extend(chunk)
    for name in modules:
        if name in sources:
            continue
        if not allow_new:
            raise ValueError('Installed Server16 lacks requested modules')
        source=module_source(name,0)
        raw=source.read_bytes();sources[name]=hashlib.sha256(raw).hexdigest()
        code=compile(raw,name.replace('.', '/')+'.py','exec')
        chunk=zlib.compress(marshal.dumps(code),6)
        pyz_toc.append((name,(0,len(payload),len(chunk))))
        payload.extend(chunk)
    if set(sources)!=set(modules):raise ValueError('Installed Server16 lacks requested modules')
    toc_offset=len(payload)
    payload.extend(marshal.dumps(pyz_toc));payload[8:12]=struct.pack('!i',toc_offset)
    packed=bytearray();toc=[]
    for name,(offset,length,unpacked,compressed,kind) in archive.toc.items():
        chunk=original[archive._start_offset+offset:archive._start_offset+offset+length]
        if name=='PYZ.pyz':
            unpacked=len(payload)
            chunk=zlib.compress(payload,9) if compressed else payload
        toc.append((len(packed),len(chunk),unpacked,compressed,kind,name))
        packed.extend(chunk)
    for option in archive.options:toc.append((0,0,0,0,'o',option))
    toc_data=CArchiveWriter._serialize_toc(toc)
    cookie_data=struct.pack(CArchiveWriter._COOKIE_FORMAT,cookie[0],
        len(packed)+len(toc_data)+CArchiveWriter._COOKIE_LENGTH,len(packed),len(toc_data),cookie[4],cookie[5])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(original[:archive._start_offset]+packed+toc_data+cookie_data)
    updated=CArchiveReader(str(output));updated_pyz=updated.open_embedded_archive('PYZ.pyz')
    assert updated.options==archive.options and updated.toc.keys()==archive.toc.keys()
    assert set(updated_pyz.toc)==set(pyz.toc)|set(modules)
    for name in archive.toc:
        if name!='PYZ.pyz':assert updated.extract(name)==archive.extract(name),name
    for name,(kind,offset,length) in pyz.toc.items():
        new_kind,new_offset,new_length=updated_pyz.toc[name]
        assert kind==new_kind
        if name not in modules:
            assert previous[offset:offset+length]==payload[new_offset:new_offset+new_length],name
        else:
            source=module_source(name,kind)
            expected=compile(source.read_bytes(),pyz.extract(name).co_filename,'exec')
            assert updated_pyz.extract(name)==expected,name
    for name in set(modules)-set(pyz.toc):
        expected=compile(module_source(name,0).read_bytes(),name.replace('.', '/')+'.py','exec')
        assert updated_pyz.extract(name)==expected,name
    report={'server':str(server),'output':str(output),'modules':sources,
            'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'preserved_archive_members':len(archive.toc)-1,
            'preserved_python_modules':len(set(pyz.toc)-set(modules))}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--module',action='append',dest='modules')
    args=parser.parse_args();build(args.server,args.output,args.modules or MODULES)
