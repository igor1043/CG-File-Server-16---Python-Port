from __future__ import annotations

import configparser
from pathlib import Path


class IniFile:
    def __init__(self, ini_path: str | Path) -> None:
        self.path = Path(ini_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _load(self) -> configparser.ConfigParser:
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        raw = self.path.read_bytes()
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                parser.read_string(raw.decode(encoding), source=str(self.path))
                return parser
            except UnicodeDecodeError:
                continue
            except configparser.Error:
                continue
        return parser

    @staticmethod
    def _resolve_section_name(parser: configparser.ConfigParser, section: str) -> str | None:
        if parser.has_section(section):
            return section
        section_lower = section.lower()
        for existing in parser.sections():
            if existing.lower() == section_lower:
                return existing
        return None

    def read(self, key: str, section: str) -> str:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section and parser.has_option(resolved_section, key):
            return parser.get(resolved_section, key)
        return ""

    def write(self, key: str, value: str, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if not resolved_section:
            parser.add_section(section)
            resolved_section = section
        parser.set(resolved_section, key, value)
        with self.path.open("w", encoding="cp1252", errors="replace") as handle:
            parser.write(handle)

    def delete_key(self, key: str, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section:
            parser.remove_option(resolved_section, key)
            with self.path.open("w", encoding="cp1252", errors="replace") as handle:
                parser.write(handle)

    def delete_section(self, section: str) -> None:
        parser = self._load()
        resolved_section = self._resolve_section_name(parser, section)
        if resolved_section:
            parser.remove_section(resolved_section)
        with self.path.open("w", encoding="cp1252", errors="replace") as handle:
            parser.write(handle)

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self.read(key, section))


class SessionIniFile:
    def __init__(self, ini_path: str | Path) -> None:
        self.path = Path(ini_path)
        self._sections: dict[str, dict[str, str]] = {}
        self._section_names: dict[str, str] = {}
        self._last_mtime_ns: int | None = None
        self._load()

    def _load(self) -> None:
        self._sections = {}
        self._section_names = {}
        if not self.path.exists():
            self._last_mtime_ns = None
            return
        raw = self.path.read_bytes()
        text = ""
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        current_section: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1].strip()
                section_key = section_name.lower()
                canonical = self._section_names.setdefault(section_key, section_name)
                self._sections.setdefault(canonical, {})
                current_section = canonical
                continue
            if current_section is None or "=" not in line:
                continue
            key, value = line.split("=", 1)
            self._sections[current_section][key.strip()] = value.strip()
        try:
            self._last_mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns = None

    def _reload_if_needed(self, force: bool = False) -> None:
        if force:
            self._load()
            return
        try:
            current_mtime = self.path.stat().st_mtime_ns
        except OSError:
            current_mtime = None
        if current_mtime != self._last_mtime_ns:
            self._load()

    def _resolve_section_name(self, section: str) -> str | None:
        self._reload_if_needed()
        return self._section_names.get(section.lower())

    def read(self, key: str, section: str) -> str:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            return self._sections.get(resolved_section, {}).get(key, "")
        return ""

    def write(self, key: str, value: str, section: str) -> None:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            resolved_section = section
            self._section_names[section.lower()] = section
            self._sections[section] = {}
        self._sections.setdefault(resolved_section, {})[key] = value

    def save(self) -> None:
        lines: list[str] = []
        for section, values in self._sections.items():
            lines.append(f"[{section}]")
            for key, value in values.items():
                lines.append(f"{key}={value}")
            lines.append("")
        payload = "\n".join(lines).rstrip() + ("\n" if lines else "")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(payload, encoding="cp1252", errors="replace")
        try:
            self._last_mtime_ns = self.path.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns = None

    def delete_key(self, key: str, section: str) -> None:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            self._sections.get(resolved_section, {}).pop(key, None)

    def delete_section(self, section: str) -> None:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if resolved_section:
            self._sections.pop(resolved_section, None)
            self._section_names.pop(section.lower(), None)

    def key_exists(self, key: str, section: str) -> bool:
        return bool(self.read(key, section))

    def sections(self) -> list[str]:
        self._reload_if_needed()
        return list(self._sections.keys())

    def items(self, section: str) -> list[tuple[str, str]]:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            return []
        return list(self._sections.get(resolved_section, {}).items())

    def as_dict(self, section: str) -> dict[str, str]:
        self._reload_if_needed()
        resolved_section = self._resolve_section_name(section)
        if not resolved_section:
            return {}
        return dict(self._sections.get(resolved_section, {}))

    def reload(self) -> None:
        self._reload_if_needed(force=True)
