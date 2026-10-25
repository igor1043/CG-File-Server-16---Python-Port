"""Replace only the frozen loader and remove x86 development-only payloads.

All retained CArchive members, including every frozen Python module, are copied
byte for byte and checked afterwards. Preserve PE icon/manifest/version resources.
"""
from pathlib import Path
import argparse,ctypes,hashlib,json,shutil,struct,sys
import pefile
from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter
from PyInstaller.utils.win32.winutils import update_exe_pe_checksum
from frozen_payload import include_bridge_path

def copy_resources(source,target):
    pe=pefile.PE(str(source));kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.BeginUpdateResourceW.argtypes=[ctypes.c_wchar_p,ctypes.c_int];kernel.BeginUpdateResourceW.restype=ctypes.c_void_p
    kernel.UpdateResourceW.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ushort,ctypes.c_void_p,ctypes.c_uint]
    kernel.EndUpdateResourceW.argtypes=[ctypes.c_void_p,ctypes.c_int]
    def key(entry):
        if entry.name is not None:return ctypes.cast(ctypes.c_wchar_p(str(entry.name)),ctypes.c_void_p)
        return ctypes.c_void_p(entry.id)
    handle=kernel.BeginUpdateResourceW(str(target),True)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            for name in kind.directory.entries:
                for lang in name.directory.entries:
                    row=lang.data.struct;data=ctypes.create_string_buffer(pe.get_data(row.OffsetToData,row.Size))
                    if not kernel.UpdateResourceW(handle,key(kind),key(name),lang.id,data,row.Size):raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel.EndUpdateResourceW(handle,True);raise
    if not kernel.EndUpdateResourceW(handle,False):raise ctypes.WinError(ctypes.get_last_error())
    pe.close()

def repack(source,loader,output):
    if source.resolve()==output.resolve():raise ValueError('Do not overwrite the input bundle')
    old=source.read_bytes();archive=CArchiveReader(str(source))
    cookie=struct.unpack(CArchiveWriter._COOKIE_FORMAT,old[-CArchiveWriter._COOKIE_LENGTH:])
    if cookie[4]!=sys.version_info.major*100+sys.version_info.minor:raise RuntimeError('Use the original Python minor version')
    output.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(loader,output);copy_resources(source,output)
    packed=bytearray();members=[];removed=[]
    for name,(offset,size,unpacked,compressed,kind) in archive.toc.items():
        normalized=name.replace('\\','/')
        if normalized.startswith('bin/python32/') and not include_bridge_path(normalized[len('bin/python32/'):]):
            removed.append(name);continue
        data=old[archive._start_offset+offset:archive._start_offset+offset+size]
        members.append((len(packed),len(data),unpacked,compressed,kind,name));packed.extend(data)
    for option in archive.options:members.append((0,0,0,0,'o',option))
    toc=CArchiveWriter._serialize_toc(members)
    tail=struct.pack(CArchiveWriter._COOKIE_FORMAT,cookie[0],len(packed)+len(toc)+CArchiveWriter._COOKIE_LENGTH,len(packed),len(toc),cookie[4],cookie[5])
    with output.open('ab') as stream:stream.write(packed);stream.write(toc);stream.write(tail)
    update_exe_pe_checksum(str(output))
    updated=CArchiveReader(str(output));assert updated.options==archive.options
    for name in updated.toc:assert updated.extract(name)==archive.extract(name),name
    assert updated.extract('PYZ.pyz')==archive.extract('PYZ.pyz')
    report=dict(archive_reopen_retry_ms=5000,original_entries=len(archive.toc),retained_entries=len(updated.toc),
                removed_development_entries=removed,all_retained_payloads_unchanged=True,
                bytes=output.stat().st_size,old_sha256=hashlib.sha256(old).hexdigest(),sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    output.with_suffix('.build.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('loader',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=repack(a.source,a.loader,a.output);result.pop('removed_development_entries');print(json.dumps(result,indent=2))
