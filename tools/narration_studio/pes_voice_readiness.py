from pathlib import Path
import json,sqlite3,collections
from generic_policy import blocked_reasons
from pes_extract_library import DEFAULT_ROOT,WORK
db=sqlite3.connect(DEFAULT_ROOT/'library.sqlite')
texts=dict(db.execute("SELECT sha,transcript FROM assets WHERE status='decoded' AND transcript IS NOT NULL"));db.close()
data=json.loads((WORK/'pes_unique_assets.json').read_text(encoding='utf8'))
counts=collections.defaultdict(collections.Counter)
for ref in data['unique']:
    text=texts.get(ref['sha256'])
    counts[ref['narrator']]['unique_total']+=1
    if text:
        counts[ref['narrator']]['transcribed']+=1
        if not blocked_reasons(dict(event='',transcript=text)):counts[ref['narrator']]['generic_candidates']+=1
print(json.dumps(counts,ensure_ascii=True,indent=2),flush=True)
