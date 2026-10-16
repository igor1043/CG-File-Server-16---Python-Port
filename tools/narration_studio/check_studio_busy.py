"""Verify the actual frozen editor can open while a writer holds the catalogue."""
from pathlib import Path
import os,json,subprocess,time
from core import connect,DB

root=Path(__file__).resolve().parents[2];built=root/'build/portable_editor/NarrationStudio.exe'
writer=connect();writer.execute('BEGIN IMMEDIATE')
writer.execute("UPDATE sources SET transcript=transcript WHERE key=(SELECT key FROM sources LIMIT 1)")
try:
    started=time.monotonic()
    result=subprocess.run([str(built),'--smoke'],env=dict(os.environ,F16_NARRATION_CONFIG=r'J:\mods\fifa 16\NarrationStudio\studio_config.json'),timeout=30,creationflags=0x08000000)
    assert result.returncode==0
    report=json.loads((built.parent/'studio_smoke.json').read_text(encoding='utf8'))
    assert report['status']=='ok' and report['paired_rows']
    print(json.dumps(dict(status='opened_while_writer_busy',seconds=round(time.monotonic()-started,2),rows=report['original_rows'])),flush=True)
finally:writer.rollback();writer.close()
