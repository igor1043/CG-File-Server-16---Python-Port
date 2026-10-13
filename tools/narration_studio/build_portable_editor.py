"""Bundle decoders and the local ASR companion into one game-root editor EXE."""
from pathlib import Path
import subprocess,sys,argparse
root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--tools',type=Path,default=root.parent/'NarrationStudio')
parser.add_argument('--worker',type=Path,default=root.parent/'build/portable_worker/TranscriptionWorker.exe')
parser.add_argument('--distpath',type=Path,default=root/'build/portable_editor')
parser.add_argument('--workpath',type=Path,default=root/'build/portable_editor_work')
options=parser.parse_args();installed=options.tools;worker=options.worker
if not worker.exists():raise FileNotFoundError('Compile primeiro o TranscriptionWorker atualizado e informe --worker: '+str(worker))
assets=[(installed/'bin','bin'),(worker,'AI')]
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','NarrationStudio',
      '--distpath',str(options.distpath),'--workpath',str(options.workpath),
      '--specpath',str(root/'tools/narration_studio'),'--paths',str(root/'tools/narration_studio')]
for name in ('faster_whisper','torch','transformers','sentence_transformers','numpy'):args.extend(('--exclude-module',name))
for source,destination in assets:
    if not source.exists():raise FileNotFoundError(source)
    args.extend(('--add-data',str(source)+';'+destination))
args.append(str(root/'tools/narration_studio/studio.py'))
with (root/'tools/narration_studio/build_portable_editor.log').open('wb') as log:
    subprocess.run(args,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
