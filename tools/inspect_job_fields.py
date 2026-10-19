import sys,tempfile,json
from pathlib import Path
root=Path.cwd();sys.path[:0]=[str(root),str(root/'server16_py'),str(root/'bin')]
from db_worker import _prefer_bundled_site_packages
_prefer_bundled_site_packages()
import clr
clr.AddReference(str(root/'bin/FifaLibrary16.dll'))
from FifaLibrary import DbFile
from server16_py.career_save_worker import Save
with tempfile.TemporaryDirectory() as tmp:
 s=Save((root/'artifacts/career_transfer_check_20261019T110006_662621Z/snapshot/DATA').read_bytes(),Path('U:/fifa 16/data/db/fifa_ng_db-meta.xml'),tmp,DbFile)
 out={}
 for name in ('teams','career_calendar','career_managerinfo','career_users'):
  t=s.table(name);fields=[(str(f.FieldName),str(f.FieldType)) for f in t.TableDescriptor.FieldDescriptors]
  rows=[r for r in s.rows(name) if name!='teams' or r.GetIntField('teamid') in (1043,383,598,111042)]
  out[name]=[{n:(str(r.GetStringField(n)) if ty=='String' else r.GetIntField(n)) for n,ty in fields} for r in rows[:6]]
 print(json.dumps(out))
