from pathlib import Path
import shutil,subprocess,json
root=Path(__file__).resolve().parents[1];source=Path(r'U:\fifa 16\ModCarrerMode\source\career_ui_assets');dest=root/'native_mods/career_ui_assets';dest.mkdir(exist_ok=True)
files=('career_ui_assets.c','path_hooks.inc','asset_catalog.inc','compat_aliases.inc','test_ui_assets.c','README.md','prepare_calendar_icons.py')
for name in files:shutil.copy2(source/name,dest/name)
(dest/'CRASH_FIX.md').write_text('Abertura do FIFA 16: o writer nativo em exe+0x3c9a720 consulta o byte +0x18 da estrutura sink. O hook deve inicializar o campo truncated com zero. Uma estrutura de apenas três campos deixa o byte fora do objeto e pode produzir nomes vazios, incluindo data/loc/.db. O crash reproduzido foi exe+0x4b4e1e9 ao carregar o idioma, antes da injeção da narração.\n\nValidação: build MSVC /W4 /WX; teste de formatação por_br e data/loc/por_br.db, seleção de imagens e limites de buffers. Confirmar também a abertura do jogo com a DLL corrigida.\n',encoding='utf8')
paths=[str((dest/name).relative_to(root)) for name in (*files,'CRASH_FIX.md')]+['tools/narration_studio/pes_extract_library.py']
subprocess.run(['git','add','--',*paths],cwd=root,check=True)
print(json.dumps(dict(staged_files=len(paths),binary_files=0)),flush=True)
