"""Export source/configuration/docs only; never edits the game or Git index."""
from pathlib import Path
import argparse,hashlib,json,subprocess,zipfile

SOURCE_EXT={'.py','.c','.cpp','.h','.hpp','.inc','.cs','.asm','.s','.lua','.ps1','.cmd','.bat',
            '.js','.ts','.jsx','.tsx','.sql','.spec','.cmake','.sh','.ini','.toml','.yaml','.yml',
            '.md','.json','.xml','.nav','.cfg','.csproj','.vcxproj','.sln'}
ASSET_EXT={'.rx3','.fmdl','.ftex','.dds','.fbx','.obj','.blend','.png','.jpg','.jpeg','.gif',
           '.mp3','.wav','.ogg','.flac','.mp4','.avi','.dll','.exe','.pyd','.bin','.db','.big','.lnx','.ico'}
def candidates(root):
    raw=subprocess.check_output(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z'])
    for name in sorted(set(raw.decode('utf8').split('\0'))):
        path=Path(name);parts=[p.lower() for p in path.parts]
        if not name or not (root/path).is_file():continue
        if any(p in parts for p in ('.git','__pycache__','.venv','venv','runtime','backups','artifacts','fixtures','extracted','historico_carregado','test_dependencies','code-release')):continue
        if parts[0]=='bin' or any(p.startswith('dist') for p in parts):continue
        if any(p=='build' and (i==0 or parts[i-1]!='scripts') for i,p in enumerate(parts)):continue
        if 'sceneassets' in parts or 'source/mascot_photographer/assets/' in name.replace('\\','/').lower():continue
        if path.suffix.lower() in ASSET_EXT:continue
        if path.suffix.lower() in SOURCE_EXT or path.name in ('.gitignore','.gitattributes','requirements.txt','CMakeLists.txt'):
            yield path
        elif path.suffix.lower()=='.txt' and ('compdata' in parts or path.name in ('enabled.txt','LEIA-ME.txt')):yield path

def export(root,output):
    root=root.resolve();output=output.resolve()
    if output.is_relative_to(root):raise ValueError('Choose an output outside the repository.')
    files=list(candidates(root));output.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for relative in files:
            data=(root/relative).read_bytes();records.append({'path':relative.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            package.writestr(relative.as_posix(),data)
        package.writestr('CODE_MANIFEST.json',json.dumps({'schema':1,'scope':'source_config_docs_only','files':records},ensure_ascii=False,indent=2))
    with zipfile.ZipFile(output) as package:
        assert package.testzip() is None
        assert all(Path(name).suffix.lower() not in ASSET_EXT for name in package.namelist())
    result={'output':str(output),'files':len(records),'uncompressed_bytes':sum(r['bytes'] for r in records),'zip_bytes':output.stat().st_size,'assets_included':False}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(export(args.root,args.output),ensure_ascii=False,indent=2))
