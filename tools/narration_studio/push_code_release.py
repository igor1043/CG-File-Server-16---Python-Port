import subprocess,json,re
from pathlib import Path
from urllib.parse import urlsplit
root=Path(__file__).resolve().parents[2]
url=subprocess.check_output(['git','remote','get-url','origin'],cwd=root,text=True).strip()
result=subprocess.run(['git','push','origin','fifa-friends'],cwd=root,capture_output=True,text=True)
def safe(text):
    text=text.replace(url,'[origin]')
    return re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@',r'\1[credentials]@',text)
if result.returncode:raise RuntimeError(safe(result.stderr))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
parsed=urlsplit(url)
web=('https://'+parsed.hostname+parsed.path.removesuffix('.git')) if parsed.hostname else ''
print(json.dumps(dict(status='pushed',branch='fifa-friends',commit=commit,repository=web,output=safe(result.stderr))),flush=True)
