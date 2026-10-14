"""Build one preliminary playable profile without waiting for the entire ASR batch."""
from pathlib import Path
import os,json,sys
game=Path(r'U:\fifa 16');work=game/'Narrations/.studio'
config=work/'pipeline_config.json'
config.write_text(json.dumps(dict(game=str(game),catalog_root=str(work),projects=str(game/'Narrations'))),encoding='utf8')
os.environ['F16_NARRATION_CONFIG']=str(config)
from ingest_pes_library import run
from base_matching import seed
from profiles import compile_profile
from core import connect
name=' '.join(sys.argv[1:])
run()
result=seed(name)
if not result['mapped_occurrences']:raise ValueError('Nenhuma associação segura disponível para '+name)
db=connect();count=db.execute('SELECT count(DISTINCT source) FROM mappings WHERE profile=?',(name,)).fetchone()[0];db.close()
if count<3:raise ValueError('Biblioteca ainda insuficiente: menos de três gravações associadas')
package=compile_profile(name)
metadata=package.parent/'profile.json';data=json.loads(metadata.read_text(encoding='utf8'))
data.update(preliminary=True,review_required=True,notes='Versão inicial com gravações já transcritas; as demais falas usam o original enquanto a biblioteca completa é processada.')
metadata.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(dict(package=str(package),summary=data),ensure_ascii=True),flush=True)
