from pathlib import Path
import psutil,json,sys
root=Path(r'J:\mods\fifa 16\NarrationStudio')
for name in ('studio_error.log','studio_startup.log','studio_config.json'):
    path=root/name
    print(name,flush=True)
    if path.exists():print(path.read_text(encoding='utf8',errors='replace')[-3500:],flush=True)
for process in psutil.process_iter(['pid','name']):
    if process.info['name'].lower() in ('narrationstudio.exe','fifa16.exe','server16python.exe'):
        try:print(json.dumps(dict(pid=process.pid,name=process.name(),exe=process.exe(),args=process.cmdline()),ensure_ascii=True),flush=True)
        except psutil.Error:print(process.info,flush=True)
print('paths',json.dumps({name:(root/name).exists() for name in ('NarrationStudio.exe','bin/ffmpeg.exe','AI/TranscriptionWorker.exe','Projects')}),flush=True)
