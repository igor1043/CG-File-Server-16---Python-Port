"""Bounded inventory of user-provided PES narration sources and free space."""
from pathlib import Path
import os,json,collections,shutil

roots=[Path(r'J:\mods\pes\audio pes\content\Multinarrador'),Path(r'J:\mods\pes\vgmtoolbox_bin_r1040')]
result=dict(disks={},narrators=[],tools=[],instructions=[])
for path in (Path('U:/'),Path('J:/')):
    usage=shutil.disk_usage(path)
    result['disks'][str(path)]=dict(total=usage.total,free=usage.free)
for ancestor in (Path(r'J:\AGENTS.md'),Path(r'J:\mods\AGENTS.md'),Path(r'J:\mods\pes\AGENTS.md'),Path(r'J:\mods\pes\audio pes\AGENTS.md'),Path(r'J:\mods\pes\audio pes\content\AGENTS.md'),Path(r'J:\mods\pes\audio pes\content\Multinarrador\AGENTS.md'),Path(r'J:\mods\fifa 16\AGENTS.md')):
    if ancestor.is_file():result['instructions'].append(dict(path=str(ancestor),text=ancestor.read_text(encoding='utf8',errors='replace')))
for folder in sorted(roots[0].iterdir()):
    if not folder.is_dir():continue
    extensions=collections.Counter();sizes=collections.Counter();examples=[];count=0
    for directory,_,files in os.walk(folder):
        for name in files:
            path=Path(directory)/name
            extension=path.suffix.lower();size=path.stat().st_size
            count+=1;extensions[extension]+=1;sizes[extension]+=size
            if len(examples)<6:
                with path.open('rb') as file:head=file.read(32)
                examples.append(dict(path=str(path),size=size,header=head.hex()))
    result['narrators'].append(dict(name=folder.name,files=count,bytes=sum(sizes.values()),extensions=dict(extensions),sizes=dict(sizes),examples=examples))
for tool_root in roots[1:]+[Path(r'J:\mods\pes\audio pes')]:
    result['tools'].extend(str(path) for path in tool_root.iterdir() if path.is_file() and path.suffix.lower() in ('.exe','.py','.bat','.cmd','.txt'))
destination=Path(__file__).parent/'pes_inventory.json'
destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
for narrator in result['narrators']:print(json.dumps({k:v for k,v in narrator.items() if k!='examples'},ensure_ascii=True),flush=True)
print(json.dumps(dict(disks=result['disks'],instructions=result['instructions'],report=str(destination)),ensure_ascii=True),flush=True)
