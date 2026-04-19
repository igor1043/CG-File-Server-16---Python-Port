from __future__ import annotations

import json
from pathlib import Path


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {"FIFAEXE": "default", "CAMERAPACKAGE": ""}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.save()
            return
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {"FIFAEXE": "default", "CAMERAPACKAGE": ""}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def fifa_exe(self) -> str:
        return self.data.get("FIFAEXE", "default")

    @fifa_exe.setter
    def fifa_exe(self, value: str) -> None:
        self.data["FIFAEXE"] = value
        self.save()

    @property
    def camera_package(self) -> str:
        return self.data.get("CAMERAPACKAGE", "")

    @camera_package.setter
    def camera_package(self, value: str) -> None:
        self.data["CAMERAPACKAGE"] = value
        self.save()
