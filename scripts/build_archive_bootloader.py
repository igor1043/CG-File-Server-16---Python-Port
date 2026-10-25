"""Build the pinned PyInstaller 6.20.0 bootloader with bounded archive reopen.

Run from an MSVC x64 developer shell. This is a developer build step, not an
installer. Downloaded upstream source and outputs stay under ignored build/.
"""
from pathlib import Path
import argparse,hashlib,os,shutil,subprocess,sys,urllib.request,zipfile

VERSION='6.20.0'
SHA256='c81004088c7bebdb07223a7d599bd087e2decaca05400363ae428ef132f40296'
URL=f'https://github.com/pyinstaller/pyinstaller/archive/refs/tags/v{VERSION}.zip'

def patch(source,header):
    path=source/'bootloader/src/pyi_archive.c'
    original=path.read_text(encoding='utf8')
    marker='archive_fp = pyi_path_fopen(archive->filename, "rb");'
    if original.count(marker)!=2:raise RuntimeError('Unexpected upstream archive implementation')
    at=original.index('\n/*',original.index('#include "pyi_path.h"'))
    updated=original[:at]+'\n#include "server16_archive_retry.h"\n'+original[at:]
    updated=updated.replace(marker,'archive_fp = server16_open_archive(archive->filename);')
    initial='archive_fp = pyi_path_fopen(filename, "rb");'
    if updated.count(initial)!=1:raise RuntimeError('Unexpected initial archive open')
    updated=updated.replace(initial,'archive_fp = server16_open_archive(filename);')
    path.write_text(updated,encoding='utf8')
    shutil.copy2(header,path.with_name(header.name))

def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path);p.add_argument('--archive',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];work=(a.work or root/'build/archive-bootloader').resolve();work.mkdir(parents=True,exist_ok=True)
    archive=a.archive or work/f'pyinstaller-v{VERSION}.zip'
    if not archive.is_file():urllib.request.urlretrieve(URL,archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('Upstream source checksum mismatch')
    source=work/f'pyinstaller-{VERSION}'
    if source.exists():raise FileExistsError(f'Choose an unused build directory: {source}')
    with zipfile.ZipFile(archive) as z:z.extractall(work)
    patch(source,root/'tools/server16_archive_retry.h')
    env=dict(os.environ,PYTHONIOENCODING='utf-8')
    subprocess.run([sys.executable,'waf','all','--target-arch=64bit'],cwd=source/'bootloader',env=env,check=True)
    print(source/'PyInstaller/bootloader/Windows-64bit-intel/runw.exe')

if __name__=='__main__':main()
