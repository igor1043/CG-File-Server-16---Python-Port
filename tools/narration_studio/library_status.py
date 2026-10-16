from pathlib import Path
import sqlite3,json
import psutil
root=Path(r'J:\mods\fifa 16\audios narradores')
db=sqlite3.connect(root/'library.sqlite',timeout=2)
print(json.dumps(dict(states=db.execute('SELECT status,count(*) FROM assets GROUP BY status').fetchall(),transcribed=db.execute('SELECT count(*) FROM assets WHERE transcript IS NOT NULL').fetchone()[0],errors=db.execute("SELECT error,count(*) FROM assets WHERE error!='' GROUP BY error LIMIT 5").fetchall())),flush=True)
for process in psutil.process_iter(['pid','name','cmdline','cpu_times']):
    command=process.info['cmdline'] or []
    if any('pes_extract_library.py' in part for part in command):
        print(json.dumps(dict(pid=process.pid,cpu=list(process.info['cpu_times']),command=command)),flush=True)
