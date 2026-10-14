"""Atomic editor writes that tolerate brief Windows reader locks."""
from pathlib import Path
import json, os, tempfile, time

def write_bytes(path, data, best_effort=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    temporary=Path(temporary)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(data)
        for attempt in range(10):
            try:temporary.replace(path);return True
            except PermissionError:
                if attempt==9:
                    if best_effort:return False
                    raise
                time.sleep(.03*(attempt+1))
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass

def write_json(path, data, best_effort=False):
    return write_bytes(path,json.dumps(data,ensure_ascii=False,indent=2).encode('utf8'),best_effort)

def write_text(path, text):
    return write_bytes(path,text.encode('utf8'))
