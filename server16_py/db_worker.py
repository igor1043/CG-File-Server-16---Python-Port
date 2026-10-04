"""32-bit worker for reading FIFA 16's database through FifaLibrary16.dll."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _prefer_bundled_site_packages() -> None:
    bundled = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
    if not bundled.is_dir():
        return
    user_site = ""
    try:
        import site
        user_site = str(Path(site.getusersitepackages()).resolve()).casefold()
    except Exception:
        pass
    filtered = []
    for entry in sys.path:
        try:
            resolved = str(Path(entry).resolve()).casefold()
        except Exception:
            resolved = str(entry).casefold()
        if user_site and resolved == user_site:
            continue
        if resolved != str(bundled.resolve()).casefold():
            filtered.append(entry)
    sys.path[:] = [str(bundled), *filtered]


def _pick_field(available: list, candidates: list) -> str | None:
    lower_map = {field.lower(): field for field in available}
    for candidate in candidates:
        if candidate in lower_map:
            return lower_map[candidate]
    return None


def _load_table(db, table_name: str, id_candidates: list[str], name_candidates: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    table = db.GetTable(table_name)
    if table is None:
        return result
    descriptor = table.TableDescriptor
    fields = [descriptor.FieldDescriptors[i].FieldName for i in range(descriptor.NFields)]
    id_field = _pick_field(fields, id_candidates)
    name_field = _pick_field(fields, name_candidates)
    if not id_field or not name_field:
        return result
    for index in range(table.NValidRecords):
        record = table.Records[index]
        name = record.GetStringField(name_field)
        if name:
            result[str(record.GetIntField(id_field))] = name
    return result


def main() -> None:
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: db_worker.py <dll_path> <db_path> <xml_path>"}))
        raise SystemExit(1)

    dll_path = Path(sys.argv[1])
    db_path = Path(sys.argv[2])
    xml_path = Path(sys.argv[3])
    for path, label in ((dll_path, "DLL"), (db_path, "db"), (xml_path, "xml")):
        if not path.exists():
            print(json.dumps({"error": f"{label} not found: {path}"}))
            raise SystemExit(1)

    dll_dir = str(dll_path.parent)
    _prefer_bundled_site_packages()
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")

    try:
        clr = __import__("clr")
        try:
            clr.AddReference(str(dll_path))
        except Exception:
            System = __import__("System")
            System.Reflection.Assembly.LoadFrom(str(dll_path))
            clr.AddReference("FifaLibrary16")
        from FifaLibrary import DbFile  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"error": f"Failed to load FifaLibrary16.dll: {exc}"}))
        raise SystemExit(1)

    try:
        db = DbFile(str(db_path), str(xml_path))
        if not db.Load():
            print(json.dumps({"error": "DbFile.Load() returned False"}))
            raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"error": f"DbFile error: {exc}"}))
        raise SystemExit(1)

    try:
        teams = _load_table(db, "teams", ["teamid", "id"], ["teamname", "name"])
    except Exception as exc:
        print(json.dumps({"error": f"Error reading teams: {exc}"}))
        raise SystemExit(1)
    try:
        stadiums = _load_table(db, "stadiums", ["stadiumid", "id"], ["stadiumname", "name"])
    except Exception:
        stadiums = {}
    try:
        leagues = _load_table(db, "leagues", ["leagueid", "id"], ["leaguename", "name"])
    except Exception:
        leagues = {}

    team_league: dict[str, str] = {}
    try:
        table = db.GetTable("leagueteamlinks")
        if table is not None:
            descriptor = table.TableDescriptor
            fields = [descriptor.FieldDescriptors[i].FieldName for i in range(descriptor.NFields)]
            team_field = _pick_field(fields, ["teamid"])
            league_field = _pick_field(fields, ["leagueid"])
            if team_field and league_field:
                for index in range(table.NValidRecords):
                    record = table.Records[index]
                    team_league[str(record.GetIntField(team_field))] = str(record.GetIntField(league_field))
    except Exception:
        pass

    print(json.dumps({"teams": teams, "stadiums": stadiums, "leagues": leagues, "team_league": team_league}))


if __name__ == "__main__":
    main()
