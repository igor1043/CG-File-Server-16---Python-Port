"""Launch the built smoke helper without opening an interactive editor."""
from pathlib import Path
import os,subprocess,json

root=Path(__file__).resolve().parents[2]
folder=root/'build/narration_studio_release'
env=dict(os.environ,F16_NARRATION_CONFIG=r'J:\mods\fifa 16\NarrationStudio\studio_config.json')
report=folder/'studio_smoke.json'
if report.exists():report.replace(folder/'studio_smoke.previous.json')
result=subprocess.run([str(folder/'NarrationStudio.exe'),'--smoke'],env=env,cwd=folder,timeout=45,creationflags=0x08000000)
assert result.returncode==0,result.returncode
data=json.loads(report.read_text(encoding='utf8'))
assert data['status']=='ok' and data['paired_rows'] and data['counts']['total']==47440
assert (folder/'studio_startup.log').exists()
print(json.dumps(dict(status='verified',rows=data['original_rows'],paired=data['paired_rows'],transcribed=data['counts']['transcribed'])))
