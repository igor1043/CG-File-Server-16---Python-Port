from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import sync_tree

if TYPE_CHECKING:
    from .app import Server16App


@dataclass(frozen=True)
class CameraPreset:
    name: str
    path: Path
    data_dir: Path
    example_paths: tuple[Path, ...]
    instructions_text: str


class CameraRuntime:
    PACKAGE_NAME = "Anth's FIFA 16 AIO Camera Mod Package"

    def __init__(self, app: "Server16App") -> None:
        self.app = app

    def package_dir(self) -> Path | None:
        configured = Path(self.app.settings.camera_package).expanduser() if self.app.settings.camera_package else None
        if configured and configured.exists() and configured.is_dir() and configured.name == self.PACKAGE_NAME:
            return configured
        return None

    def is_valid_package_dir(self, directory: str | Path) -> bool:
        path = Path(directory)
        return path.exists() and path.is_dir() and path.name == self.PACKAGE_NAME and (path / "Instructions.txt").exists()

    def discover_presets(self) -> list[CameraPreset]:
        package_dir = self.package_dir()
        if package_dir is None or not package_dir.exists():
            return []
        general_instructions = self._read_text(package_dir / "Instructions.txt")
        presets: list[CameraPreset] = []
        for item in sorted(package_dir.iterdir(), key=lambda path: path.name.lower()):
            if not item.is_dir():
                continue
            data_dir = item / "data"
            if not data_dir.exists():
                continue
            examples = tuple(sorted(item.glob("*.png"), key=lambda path: path.name.lower()))
            specific_instructions = self._read_text(item / "Instructions.txt")
            instructions = self._merge_instructions(specific_instructions, general_instructions)
            presets.append(
                CameraPreset(
                    name=item.name,
                    path=item,
                    data_dir=data_dir,
                    example_paths=examples,
                    instructions_text=instructions,
                )
            )
        return presets

    def apply_preset(self, preset: CameraPreset) -> dict[str, object]:
        app = self.app
        copied_files = 0
        touched_targets: list[str] = []
        for source_path, target_path in self._iter_sync_units(preset.data_dir, app.exedir / "data"):
            copied_files += sync_tree(source_path, target_path)
            touched_targets.append(str(target_path))
        regenerator_result = self.run_regenerator()
        return {
            "preset_name": preset.name,
            "copied_files": copied_files,
            "targets": touched_targets,
            "regenerator": regenerator_result,
        }

    def run_regenerator(self) -> dict[str, object]:
        app = self.app
        candidates = [
            app.exedir / "REGENERATOR.exe",
            Path(r"U:\games\fifa 16\REGENERATOR.exe"),
        ]
        regenerator = next((candidate for candidate in candidates if candidate.exists()), None)
        if regenerator is None:
            return {"launched": False, "message": "REGENERATOR.exe not found / nao encontrado."}
        try:
            subprocess.Popen([str(regenerator)], cwd=str(regenerator.parent), shell=False)
            return {"launched": True, "path": str(regenerator)}
        except Exception as exc:
            return {"launched": False, "message": f"Failed to launch REGENERATOR.exe / Falha ao iniciar o REGENERATOR.exe: {exc}"}

    def _iter_sync_units(self, source_root: Path, target_root: Path):
        if source_root.is_file():
            yield source_root, target_root
            return
        entries = sorted(source_root.iterdir(), key=lambda path: path.name.lower())
        has_files = any(entry.is_file() for entry in entries)
        if has_files:
            yield source_root, target_root
            return
        for entry in entries:
            yield from self._iter_sync_units(entry, target_root / entry.name)

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    @staticmethod
    def _merge_instructions(specific: str, general: str) -> str:
        parts = [part for part in (specific, general) if part]
        if not parts:
            return "No instructions available for this camera.\nSem instrucoes disponiveis para esta camera."
        if specific and general:
            return f"{specific}\n\nGeneral notes / Notas gerais:\n{general}"
        return parts[0]
