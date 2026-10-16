import psutil,json
for process in psutil.process_iter(['pid','name','cmdline','cpu_times']):
    parts=process.info['cmdline'] or []
    if any(any(word in part for word in ('prepare_portable','PyInstaller','TranscriptionWorker','NarrationStudio.exe','pes_extract')) for part in parts):
        print(json.dumps(dict(pid=process.pid,name=process.info['name'],cpu=list(process.info['cpu_times']),command=parts)),flush=True)
