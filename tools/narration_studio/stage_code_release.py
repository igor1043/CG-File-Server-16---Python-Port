"""Stage reviewed code only, never recordings, catalogues or executable builds."""
from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parents[2]
allowed={'.py','.cpp','.h','.hpp','.c','.ps1','.bat','.cmd','.md','.rc'}
names=['.gitignore','Server16Python.spec','build_exe.bat']
for base in ('server16_py','tests','native_mods','scripts'):
    for p in (root/base).rglob('*'):
        if p.is_file() and p.suffix in allowed and '__pycache__' not in p.parts:names.append(p.relative_to(root).as_posix())
names += ['server16_py/locales/'+lang+'.json' for lang in ('pt','en','es')]
modules=('audio_playback audio_quality_audit base_matching build_portable_editor core editor_catalog export_catalog_indexes export_existing_library finalize_pes_profiles generic_policy ingest_pes_library inventory_pes_sources library_panel match_club_names matching pes_archives pes_extract_library pes_index_all prepare_portable_catalog profiles projects studio topics transcribe transcribe_batch transcription_worker update_catalog_indexes').split()
names += ['tools/narration_studio/'+name+'.py' for name in modules]
names += ['tools/narration_studio/README.md','tools/narration_studio/TranscriptionWorker.spec','tests/test_narration_library.py']
names=sorted(set(name for name in names if (root/name).is_file()))
for name in names:
    if (root/name).stat().st_size>1024*1024:raise ValueError('Unexpected large code file: '+name)
subprocess.run(['git','add','--']+names,cwd=root,check=True,capture_output=True)
staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=root,text=True).splitlines()
for name in staged:
    if name not in names:raise ValueError('Preexisting unrelated staged file; preserve and review: '+name)
    if Path(name).suffix in ('.exe','.dll','.wav','.mp3','.flac','.sqlite','.big','.npack'):raise ValueError('Binary staged: '+name)
print(json.dumps(dict(files=len(staged),bytes=sum((root/name).stat().st_size for name in staged))),flush=True)
