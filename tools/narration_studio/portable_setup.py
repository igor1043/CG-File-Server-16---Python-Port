"""First-run game-folder selection for the standalone Windows editor."""
from pathlib import Path
import json, os, sys


def valid_game_root(path):
    """A FIFA folder is accepted only when it contains the actual game EXE."""
    return (Path(path).expanduser() / 'fifa16.exe').is_file()

def configuration_path(app_root=None):
    override=os.environ.get('F16_NARRATION_CONFIG')
    if override:return Path(override).expanduser().resolve()
    if getattr(sys,'frozen',False):
        local=os.environ.get('LOCALAPPDATA') or str(Path.home()/'AppData'/'Local')
        return Path(local)/'FIFA16NarrationStudio'/'studio_config.json'
    return Path(app_root or Path(__file__).resolve().parent)/'studio_config.json'

def ensure_game_config():
    if not getattr(sys,'frozen',False) or '--smoke' in sys.argv or os.environ.get('F16_NARRATION_CONFIG'):
        return
    app_root=Path(sys.executable).resolve().parent
    config_file=configuration_path(app_root)
    template=app_root/'studio_config.json'
    if config_file.exists():config=json.loads(config_file.read_text(encoding='utf8'))
    else:
        config=json.loads(template.read_text(encoding='utf8')) if template.exists() else {}
        config['game']=''
    game=Path(config.get('game','') or app_root)
    if not game.is_absolute(): game=(app_root/game).resolve()
    if valid_game_root(game): return
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root=tk.Tk();root.withdraw()
    try:
        while True:
            messagebox.showinfo(
                'Narration Studio',
                'Na primeira abertura, selecione a pasta raiz do FIFA 16 — a mesma que contém fifa16.exe.\n\n'
                'O programa vai localizar a base original do Tiago Leifert e os perfis em Narrations.',
                parent=root,
            )
            selected=filedialog.askdirectory(title='Selecione a pasta que contém fifa16.exe',parent=root)
            if not selected:
                raise SystemExit('A seleção da pasta do FIFA 16 foi cancelada.')
            if valid_game_root(selected): break
            messagebox.showerror(
                'Pasta inválida',
                'Essa pasta não contém fifa16.exe. Selecione a raiz correta do FIFA 16.',
                parent=root,
            )
        config['game']=str(Path(selected).resolve())
        config_file.parent.mkdir(parents=True,exist_ok=True)
        temporary=config_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
        temporary.replace(config_file)
    finally:
        root.destroy()
