"""Run the source Server against the installed game's existing settings.

Used to verify a Python-only overlay fix without restarting FIFA or adding a
second native hook. Close an existing Server before starting this launcher.
"""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--game-root',required=True)
    args=parser.parse_args()
    game=Path(args.game_root).resolve()
    if not (game/'fifa16.exe').is_file():
        raise SystemExit('FIFA 16 installation not found.')
    from server16_py.app import Server16App,main
    Server16App._resolve_base_dir=lambda self:game
    Server16App._resolve_resource_dir=lambda self:ROOT
    main()
