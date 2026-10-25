"""Runtime-only x86 bridge files; pip/build caches are not shipped to players."""
from pathlib import Path,PurePosixPath

BUILD_ONLY={'pip','setuptools','wheel','_distutils_hack'}
def include_bridge_path(name):
    parts=PurePosixPath(str(name).replace('\\','/')).parts
    if '__pycache__' in parts or any(p.endswith(('.pyc','.pyo')) for p in parts):return False
    if parts[:2]==('Lib','site-packages') and len(parts)>2:
        package=parts[2].casefold()
        if package in BUILD_ONLY or package.endswith(('.dist-info','.egg-info')):return False
        if package=='distutils-precedence.pth':return False
    if parts and parts[0].casefold()=='scripts':return False
    return True

def bridge_files(root):
    root=Path(root)
    return [(str(path),'bin/python32/'+str(path.relative_to(root).parent).replace('\\','/'))
            for path in sorted(root.rglob('*')) if path.is_file() and include_bridge_path(path.relative_to(root))]
