"""First-run game-folder selection for the standalone Windows editor."""
from pathlib import Path
import json, os, sys

def ensure_game_config():
    if not getattr(sys,'frozen',False) or '--smoke' in sys.argv or os.environ.get('F16_NARRATION_CONFIG'):
        return
    app_root=Path(sys.executable).resolve().parent
    config_path=app_root/'studio_config.json'
    config=json.loads(config_path.read_text(encoding='utf8')) if config_path.exists() else {}
    game=Path(config.get('game','') or app_root)
    if not game.is_absolute(): game=(config_path.parent/game).resolve()
    if (game/'fifa16.exe').is_file(): return
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root=tk.Tk();root.withdraw()
    messagebox.showinfo('Narration Studio','Selecione a pasta raiz do FIFA 16. O programa salvará esse local na configuração portátil.',parent=root)
    selected=filedialog.askdirectory(title='Selecione a pasta raiz do FIFA 16')
    root.destroy()
    if not selected or not (Path(selected)/'fifa16.exe').is_file():
        raise SystemExit('Selecione uma pasta que contenha fifa16.exe para abrir o editor.')
    config['game']=str(Path(selected).resolve())
    temporary=config_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
    temporary.replace(config_path)
