"""One path contract shared by the game server and Narration Studio.

The FIFA-facing layout intentionally stays simple:
    <game root>/Narrations/<narrator>/profile.npack

Editable projects, the source-audio library, and the original-game catalogue
live beside the game instead of inside its runtime narration directory.
"""
from __future__ import annotations

from pathlib import Path


def narration_root(game_root: str | Path) -> Path:
    return Path(game_root).expanduser().resolve() / "Narrations"


def profile_directory(game_root: str | Path, name: str) -> Path:
    """Return a narrator's install directory, rejecting path traversal."""
    name = str(name).strip()
    if (
        not name
        or name in {".", ".."}
        or name.endswith((".", " "))
        or any(char in name for char in '\\/:*?"<>|')
    ):
        raise ValueError("Nome de narrador inválido.")
    return narration_root(game_root) / name


def profile_directories(root: str | Path) -> list[Path]:
    """List only installable narrator folders; ignore workspace/cache files."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(
        (
            child
            for child in root.iterdir()
            if child.is_dir() and (child / "profile.json").is_file()
        ),
        key=lambda child: child.name.casefold(),
    )
