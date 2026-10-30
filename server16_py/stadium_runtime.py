from __future__ import annotations

import random
import shutil
import unicodedata
import tempfile
import threading
import traceback
import winsound
from pathlib import Path
from typing import TYPE_CHECKING

from .file_tools import (
    copy,
    copy_glares,
    copy_if_exists,
    copy_or_clear,
    extra_setup,
    ensure_server16_stadium_access,
    restore_stadium_inj_files,
    set_inj_id,
    stadium_injection_paths,
    is_archive,
    extract_archive,
)
from .dialogs import StadiumChoiceDialog
from .match_string_patcher import patch_match_string
from .stadium_catalog import prematch_page
from .stadium_transaction import StadiumAssetTransaction
from .stadium_match_assets import stage_match_assets

if TYPE_CHECKING:
    from .app import Server16App


class StadiumCopyCancelled(RuntimeError):pass

class StadiumRuntime:
    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self.pending_selection = None
        self._copy_lock = threading.Lock()
        self._applied_slot = None
        self._previous_manual_override = None
        self._replacement=None
        self._cancel_copy=threading.Event()

    def _context(self) -> tuple:
        app = self.app
        return (app._kickoff_generation, app.HID, app.AID)

    def keep_manual_selection_on_setup_return(self, previous_page: str) -> bool:
        app = self.app
        manual = getattr(app, '_manual_stadium_override', None)
        applied = getattr(app, '_last_stadium_applied_signature', None)
        automatic = bool(applied and applied[0] == app._kickoff_generation and
                         len(applied) > 4 and applied[4] == app.HID and app.curstad)
        pending = bool(self.pending_selection and self.pending_selection[0] == self._context())
        # The stadium preview returns to the same setup for automatic choices,
        # too. Starting a new generation here re-copies and switches slots while
        # FIFA is already loading the selected stadium's textures.
        return bool(((manual and manual[0][:3] == self._context()) or automatic or pending) and
                    not getattr(app, '_stadium_fixture_entered', False) and
                    (prematch_page(previous_page) or 'stadiumpan' in (previous_page or '').lower()))

    def _active_injection_slot(self) -> str | None:
        app = self.app
        try:
            if app.memory.is_open():
                stadium_type = getattr(app, 'Stadiumtype', 'first')
                value = str(app.memory.get_int(app.offsets.ORISTADIDBASE,
                    self.stadium_offsets(stadium_type)))
                if value in ('176', '261'):
                    return value
                alternate = 'first' if stadium_type == 'alter' else 'alter'
                value = str(app.memory.get_int(app.offsets.ORISTADIDBASE, self.stadium_offsets(alternate)))
                if value in ('176', '261'):
                    return value
        except Exception:
            pass
        if self._applied_slot in ('176', '261'):
            return self._applied_slot
        value = str(getattr(app, 'STADID', ''))
        return value if value in ('176', '261') else None

    def _next_injection_slot(self) -> tuple[str, str]:
        active = self._active_injection_slot()
        if active:
            slot = '261' if active == '176' else '176'
            return slot, '9' if slot == '261' else '4'
        return set_inj_id(str(self.app.CCount))

    def _validate_copy_context(self, context: tuple | None, section: str, injid: str) -> None:
        if self._cancel_copy.is_set():raise StadiumCopyCancelled('A new stadium was selected')
        if str(injid) not in ('176', '261'):
            raise RuntimeError(f'Unsupported stadium injection ID: {injid}')
        if context is None:  # Isolated copy/benchmark without a live FIFA context.
            return
        app = self.app
        if context != self._context() or not app.memory.is_open() or getattr(app, '_closing', False) or getattr(app, '_match_audio_ended', False):
            raise RuntimeError('The match context changed while preparing stadium assets')
        preview = 'stadiumpan' in (app.lastpagename or '').lower() and not getattr(app, '_stadium_fixture_entered', False)
        if getattr(app, '_stadium_fixture_entered', False) or not (prematch_page(app.lastpagename) or preview):
            raise RuntimeError('The match left the stadium selection screen before application finished')
        if self._active_injection_slot() == str(injid):
            raise RuntimeError('The destination stadium ID became active; previous stadium preserved')

    def cancel_pending_selection(self) -> None:
        """Keep the last working manual choice when the replacement fails."""
        if self.pending_selection and self.app._stadium_task_request_key and self.app._stadium_task_request_key[0] == 'manual':
            self.app._manual_stadium_override = self._previous_manual_override
        self._previous_manual_override = None
        self.pending_selection = None

    @staticmethod
    def _parse_assignment(raw_value: str) -> tuple[list[str], str, str, str]:
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if len(parts) < 4:
            return [], "", "", ""
        police, pitch, net = parts[-3:]
        stadiums = [name for name in parts[:-3] if name and name != "None"]
        return stadiums, police, pitch, net

    @staticmethod
    def _build_task_request_key(section_name: str, section_id: str, raw_value: str) -> tuple[str, str, str]:
        return section_name, section_id, raw_value

    @staticmethod
    def _looks_like_stadium_dir(path: Path) -> bool:
        required_markers = ("model.rx3", "texture_day.rx3", "texture_night.rx3", "crowd_day.dat", "crowd_night.dat")
        return any((path / marker).exists() for marker in required_markers)

    def _find_extracted_stadium_root(self, extracted_root: Path, preferred_name: str) -> Path:
        preferred_path = extracted_root / preferred_name
        if preferred_path.is_dir() and self._looks_like_stadium_dir(preferred_path):
            return preferred_path
        if self._looks_like_stadium_dir(extracted_root):
            return extracted_root
        matches: list[Path] = []
        for candidate in extracted_root.rglob("*"):
            if not candidate.is_dir():
                continue
            if candidate.name.startswith(".") or candidate.name.upper() == "__MACOSX":
                continue
            if candidate.name.casefold() == preferred_name.casefold() and self._looks_like_stadium_dir(candidate):
                return candidate
            if self._looks_like_stadium_dir(candidate):
                matches.append(candidate)
        if not matches:
            raise RuntimeError(f"Could not find a valid stadium folder inside extracted archive {preferred_name}")
        matches.sort(key=lambda path: (len(path.relative_to(extracted_root).parts), str(path).lower()))
        return matches[0]

    def _resolve_stadium_source(self, stadium_name: str) -> tuple[str, Path, str]:
        app = self.app
        normalized_name = (stadium_name or "").strip()
        if not normalized_name or normalized_name == "None":
            raise RuntimeError("No stadium name was provided for runtime loading")
        folder_path = app.targetpath / normalized_name
        if folder_path.is_dir():
            return folder_path.name, folder_path, "folder"
        direct_path = app.targetpath / normalized_name
        if direct_path.is_file() and is_archive(direct_path):
            return direct_path.stem, direct_path, "archive"
        for ext in (".zip", ".rar"):
            archive_path = app.targetpath / f"{normalized_name}{ext}"
            if archive_path.is_file() and is_archive(archive_path):
                return archive_path.stem, archive_path, "archive"

        name_nfc = unicodedata.normalize("NFC", normalized_name)
        name_nfd = unicodedata.normalize("NFD", normalized_name)
        try:
            for item in app.targetpath.iterdir():
                item_nfc = unicodedata.normalize("NFC", item.name)
                stem_nfc = unicodedata.normalize("NFC", item.stem)
                if item.is_dir() and item_nfc in {name_nfc, name_nfd}:
                    return item.name, item, "folder"
                if item.is_file() and item.suffix.lower() in {".zip", ".rar"} and stem_nfc in {name_nfc, name_nfd}:
                    if is_archive(item):
                        return item.stem, item, "archive"
        except Exception:
            pass

        raise RuntimeError(f"Assigned stadium source not found: {folder_path} or matching .zip/.rar archive")

    def apply_stadium_runtime(self) -> None:
        app = self.app
        preview = 'stadiumpan' in (app.lastpagename or '').lower()
        if getattr(app, '_stadium_fixture_entered', False) or not (prematch_page(app.lastpagename) or preview):
            # Never replace models/textures or the stadium ID after loading has
            # begun; those files may already be resident in FIFA's texture cache.
            return
        manual = getattr(app, '_manual_stadium_override', None)
        if manual and manual[0][:3] == self._context():
            # An explicit selection wins for this match; do not replace it on
            # the next context poll with an automatic/random assignment.
            return
        if app._stadium_task_running:
            return
        if app.settings_ini.key_exists(app.TOURROUNDID, "exclude") or app.settings_ini.key_exists(app.TOURNAME, "exclude"):
            app.log(f"Stadium excluded for TOUR={app.TOURNAME} ROUND={app.TOURROUNDID}")
            # Clear stadium from previous match when this tournament/round is excluded
            app.curstad = ""
            app.ScoreboardStadName = ""
            return
        section_id = None
        section_name = None
        if app.settings_ini.key_exists(app.TOURROUNDID, "comp"):
            section_id, section_name = app.TOURROUNDID, "comp"
        elif app.settings_ini.key_exists(app.TOURNAME, "comp"):
            section_id, section_name = app.TOURNAME, "comp"
        elif app.settings_ini.key_exists(app.HID, "stadium"):
            section_id, section_name = app.HID, "stadium"
        if section_id:
            raw_value = app.settings_ini.read(section_id, section_name)
            valid_stadiums, _police, _pitch, _net = self._parse_assignment(raw_value)
            if not valid_stadiums:
                app.log(f"No valid stadiums in assignment [{section_name}] {section_id}: {raw_value}")
                return
            # Filter to stadiums that exist as folder OR as archive
            def _stad_exists(name: str) -> bool:
                # Check direct match
                if (app.targetpath / name).exists():
                    return True
                for ext in (".zip", ".rar"):
                    if (app.targetpath / (name + ext)).exists():
                        return True
                # Check with Unicode normalization (NFC vs NFD mismatch)
                name_nfc = unicodedata.normalize("NFC", name)
                name_nfd = unicodedata.normalize("NFD", name)
                try:
                    for item in app.targetpath.iterdir():
                        item_nfc = unicodedata.normalize("NFC", item.name)
                        if item_nfc == name_nfc or item_nfc == name_nfd:
                            return True
                        stem_nfc = unicodedata.normalize("NFC", item.stem)
                        if stem_nfc == name_nfc or stem_nfc == name_nfd:
                            if item.suffix.lower() in (".zip", ".rar"):
                                return True
                except Exception:
                    pass
                return False
            existing_stadiums = [s for s in valid_stadiums if _stad_exists(s)]
            if existing_stadiums:
                valid_stadiums = existing_stadiums
            # If there are multiple options, exclude the currently loaded stadium
            # so consecutive kickoffs do not repeat the same stadium.
            if len(valid_stadiums) > 1 and app.curstad in valid_stadiums:
                candidates = [s for s in valid_stadiums if s != app.curstad]
            else:
                candidates = valid_stadiums
            task_request_key = self._build_task_request_key(section_name, section_id, raw_value)
            stadium_signature = (app._kickoff_generation, section_name, section_id, raw_value, app.HID, app.TOURNAME, app.TOURROUNDID)
            # Keep the first resolved choice for this assignment/match. Do
            # this BEFORE random.choice, which can otherwise roll a new pack.
            if stadium_signature == app._last_stadium_applied_signature and app.curstad:
                return
            choice_signature = getattr(app, "_stadium_choice_signature", None)
            choice_ready = bool(getattr(app, "_stadium_choice_ready", False))
            if not app.settings.random_stadium_selection and len(candidates) > 1:
                if choice_signature == stadium_signature and choice_ready:
                    desired_stadium = getattr(app, "_stadium_choice_result", None) or random.choice(candidates)
                    app._stadium_choice_ready = False
                elif getattr(app, "_stadium_choice_dialog", None) is not None:
                    try:
                        if app._stadium_choice_dialog.winfo_exists():
                            return
                    except Exception:
                        app._stadium_choice_dialog = None
                    return
                else:
                    self._open_stadium_choice(candidates, stadium_signature)
                    return
            else:
                desired_stadium = random.choice(candidates)
            if stadium_signature == app._last_stadium_applied_signature and app.curstad == desired_stadium:
                app._set_progress(100, f"Stadium already loaded: {desired_stadium}")
                return
            if app._stadium_task_running:
                if task_request_key == app._stadium_task_request_key or stadium_signature == app._stadium_task_signature:
                    app.log(f"Stadium task already running for {desired_stadium}")
                else:
                    app.log(f"Stadium task busy; skipping new request for {desired_stadium}")
                return
            app.injID, app.PoliceNum = self._next_injection_slot()
            app._set_process_status("Loading Stadium", app.gold)
            self.start_stadium_task(
                section_id,
                section_name,
                app.injID,
                stadium_signature,
                task_request_key,
                chosen_stadium=desired_stadium,
            )
            return
        app._last_stadium_applied_signature = None
        app._hide_stadium_loading_modal()
        app._set_progress(25, "Restoring default stadium")
        sceneassets = app.exedir / "data" / "sceneassets"
        ensure_server16_stadium_access(sceneassets, log=app.log)
        copy(app.exedir / "FSW" / "stadium", sceneassets)
        ensure_server16_stadium_access(sceneassets, log=app.log)
        app.curstad = ""
        app.ScoreboardStadName = ""
        app.stadmovie = False
        app._set_display("stadium", "Stadium Module Disable")
        app._update_audio_overview()
        app._set_progress(100, "Default stadium restored")
        app.log("No stadium assignment found; default stadium restored")

    def _open_stadium_choice(self, candidates: list[str], signature: tuple) -> None:
        app = self.app
        app._stadium_choice_signature = signature
        app._stadium_choice_ready = False

        def _resolved(chosen: str | None) -> None:
            app._stadium_choice_dialog = None
            app._stadium_choice_result = chosen if chosen in candidates else random.choice(candidates)
            app._stadium_choice_ready = True
            app.after(0, self.apply_stadium_runtime)

        try:
            dialog = StadiumChoiceDialog(app, candidates, _resolved)
            app._stadium_choice_dialog = dialog
            app.log(f"Waiting for stadium selection before kickoff: {', '.join(candidates)}")
        except Exception as exc:
            app._stadium_choice_dialog = None
            app._stadium_choice_result = random.choice(candidates)
            app._stadium_choice_ready = True
            app.log("Could not open stadium chooser; falling back to random selection", exc)

    def start_stadium_task(
        self,
        section_id: str,
        section_name: str,
        injid: str,
        stadium_signature: tuple,
        task_request_key: tuple[str, str, str],
        chosen_stadium: str | None = None,
        assignment_value: str | None = None,
    ) -> None:
        app = self.app
        app._stadium_task_running = True
        self._cancel_copy.clear()
        app._stadium_task_signature = stadium_signature
        app._stadium_task_request_key = task_request_key
        self.pending_selection = (
            (app._kickoff_generation, app.HID, app.AID),
            chosen_stadium,
        )
        try:
            app._show_stadium_loading_modal(chosen_stadium or section_id, "Preparing stadium assets", progress=4)
        except Exception as exc:
            app.log("Stadium loading notification could not be shown", exc)
        app._set_progress(8, f"Preparing stadium {section_id}")
        try:
            app._update_stadium_loading_modal(10, f"Loading stadium from [{section_name}] {section_id}")
        except Exception as exc:
            app.log("Stadium loading notification update failed", exc)
        # Write the stadium name to memory immediately — before file copying starts —
        # so it is already in place when FIFA renders the match intro screen.
        if chosen_stadium:
            # Resolve the display name from scoreboardstdname ini key
            if app.settings_ini.key_exists(chosen_stadium, "scoreboardstdname"):
                raw_std = app.settings_ini.read(chosen_stadium, "scoreboardstdname")
                display_name = raw_std.split(",")[0].strip()
                std_name = display_name if display_name else chosen_stadium
            else:
                std_name = chosen_stadium
            # Avoid patching fifa_ng_db.db on disk. That change can survive the match
            # lifecycle and leave the game crashing on the next launch.
            # Patch FIFA memory only for the current session.
            patch_match_string(app, std_name)
            # Also pre-write to memory for the scoreboard.
            if app.memory.is_open():
                try:
                    app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, app.offsets.STDNAMEOFFSET176, "_" + std_name)
                    app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, app.offsets.STDNAMEOFFSET261, "_" + std_name)
                    app.log(f"Stadium name pre-written to memory: _{std_name}")
                except Exception as exc:
                    app.log(f"Failed to pre-write stadium name to memory", exc)

        task_context = (app._kickoff_generation, app.HID, app.AID)
        task_stadium_type = app.Stadiumtype
        def worker() -> None:
            try:
                payload = self.run_stadium_copy_job(section_id, section_name, injid, chosen_stadium=chosen_stadium,
                    assignment_value=assignment_value, expected_context=task_context)
                payload['context'] = task_context
                payload['stadium_type'] = task_stadium_type
                app._worker_queue.put(("done", payload))
            except StadiumCopyCancelled:
                app._worker_queue.put(('cancelled',None))
            except Exception as exc:
                app._worker_queue.put(("error", f"Failed to load stadium assets: {exc}\n{traceback.format_exc().strip()}"))

        threading.Thread(target=worker, daemon=True).start()
        app._schedule_worker_poll()

    def apply_manual_stadium(self, name: str, context: tuple) -> None:
        app = self.app
        if context != (app._kickoff_generation,app.HID,app.AID,app.TOURNAME,app.TOURROUNDID):
            raise RuntimeError('The match context has changed')
        if app._stadium_task_running:
            self._resolve_stadium_source(name)
            self._replacement=(name,context);self._cancel_copy.set()
            app._show_stadium_loading_modal(name,'Trocando a seleção; preparando novo estádio…',progress=0)
            return
        self._resolve_stadium_source(name)
        details = ['None', 'None', 'None']
        for key, section in ((app.TOURROUNDID,'comp'), (app.TOURNAME,'comp'), (app.HID,'stadium')):
            value = app.settings_ini.read(key,section)
            _names, police, pitch, net = self._parse_assignment(value)
            if _names:
                details = [police,pitch,net]; break
        raw = ','.join([name]+details)
        self._previous_manual_override = getattr(app, '_manual_stadium_override', None)
        app._manual_stadium_override = (context,name,raw)
        app.injID, app.PoliceNum = self._next_injection_slot()
        signature = (app._kickoff_generation,'manual',app.HID,raw,app.HID,app.TOURNAME,app.TOURROUNDID)
        try:
            self.start_stadium_task(app.HID,'manual',app.injID,signature,('manual',app.HID,raw),name,raw)
        except Exception:
            self.cancel_pending_selection()
            app._stadium_task_running = False
            raise

    def restart_replacement(self):
        replacement=self._replacement;self._replacement=None
        self.cancel_pending_selection();self.app._stadium_task_running=False
        self.app._stadium_task_signature=None;self.app._stadium_task_request_key=None
        self._cancel_copy.clear()
        if replacement:self.apply_manual_stadium(*replacement)

    def run_stadium_copy_job(self, hid: str, section: str, injid: str, chosen_stadium: str | None = None,
            assignment_value: str | None = None, expected_context: tuple | None = None) -> dict:
        temporary_dirs: list[str] = []
        try:
            with self._copy_lock:
                return self._run_stadium_copy_job(hid,section,injid,chosen_stadium,assignment_value,
                    temporary_dirs,expected_context)
        finally:
            for temporary in temporary_dirs:
                shutil.rmtree(temporary,ignore_errors=True)

    def _run_stadium_copy_job(self, hid, section, injid, chosen_stadium, assignment_value, temporary_dirs,
            expected_context=None) -> dict:
        app = self.app
        if assignment_value is None and not app.settings_ini.key_exists(hid, section):
            raise RuntimeError(f"Missing stadium assignment [{section}] {hid}")
        raw_value = assignment_value if assignment_value is not None else app.settings_ini.read(hid, section)
        valid_stadiums, police, pitch, net = self._parse_assignment(raw_value)
        if len(valid_stadiums) == 0 and not all([police, pitch, net]):
            raise RuntimeError(f"Invalid stadium assignment [{section}] {hid}: {raw_value}")
        if not valid_stadiums:
            raise RuntimeError(f"No valid stadium names in assignment [{section}] {hid}")
        # Use the pre-selected stadium if provided (chosen in apply_stadium_runtime),
        # otherwise fall back to random.choice (e.g. when called directly).
        chosen = (chosen_stadium or "").strip()
        if chosen and chosen in valid_stadiums:
            stad_name = chosen
        else:
            stad_name = random.choice(valid_stadiums)
        stad_name, source_path, source_kind = self._resolve_stadium_source(stad_name)
        # Support zip/rar archives: extract to a temp folder and work from there
        _temp_dir = None
        if source_kind == "archive":
            runtime_dir = app.base_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            _temp_dir = tempfile.mkdtemp(prefix="server16_stad_", dir=runtime_dir)
            temporary_dirs.append(_temp_dir)
            try:
                app._worker_queue.put(("progress", 5, f"Extracting {source_path.name}..."))
                def _zip_progress(current, total, filename):
                    pct = 5 + int((current / max(1, total)) * 6)
                    short = filename if len(filename) <= 40 else "..." + filename[-37:]
                    app._worker_queue.put(("progress", pct, f"Extracting {short} ({current}/{total})"))
                backend = extract_archive(source_path, Path(_temp_dir), progress_callback=_zip_progress,
                    fast_publish=True,
                    publication_callback=lambda method, reason: app.log(f'Stadium extraction publication: {method}; {reason}'))
                app.log(f'Stadium archive extractor: {backend}; archive={source_path.name}')
                stad = self._find_extracted_stadium_root(Path(_temp_dir), source_path.stem)
                app.log(f"Archive extracted to: {stad}")
            except Exception:
                # Cleanup temp dir if extraction fails
                import shutil as _shutil2
                _shutil2.rmtree(_temp_dir, ignore_errors=True)
                _temp_dir = None
                raise
        elif source_path.exists():
            stad = source_path
        else:
            raise RuntimeError(f"Assigned stadium folder or archive not found: {source_path}")
        if not (stad / 'model.rx3').is_file() or (stad / 'model.rx3').stat().st_size == 0:
            if _temp_dir:
                shutil.rmtree(_temp_dir, ignore_errors=True)
            raise RuntimeError(f'Stadium package has no model.rx3: {stad_name}')
        for name in ('texture_day.rx3', 'texture_night.rx3'):
            texture = stad / name
            if texture.exists() and (not texture.is_file() or texture.stat().st_size == 0):
                raise RuntimeError(f'Stadium package has an invalid texture: {stad_name}/{name}')
        if not any((stad/name).is_file() for name in ('texture_day.rx3', 'texture_night.rx3')):
            raise RuntimeError(f'Stadium package has no textures: {stad_name}')
        self._validate_copy_context(expected_context, section, injid)
        transaction = StadiumAssetTransaction(app.exedir, app.log)
        try:
            payload = self._prepare_stadium_pack(stad, stad_name, hid, section, injid, police, pitch, net,
                transaction, expected_context)
            if expected_context is None:
                transaction.accept()
            else:
                payload['transaction'] = transaction
            return payload
        except Exception:
            transaction.rollback()
            raise

    def _prepare_stadium_pack(self, stad, stad_name, hid, section, injid, police, pitch, net,
            transaction, expected_context) -> dict:
        app = self.app
        game = transaction.stage
        dest = game / "data" / "sceneassets"
        fsw_stadium = app.exedir / "FSW" / "Stadium"
        # Prepare only the inactive slot in isolation. Restoring the other
        # slot here would replace files FIFA still associates with its model.
        restore_stadium_inj_files(dest, fsw_stadium, str(injid))
        def copy_pack(src, dst):
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Pack timestamps and sizes can match while contents differ.
                # Never use the metadata-only skip optimization for this set.
                shutil.copy2(src, dst)
        # These must be calculated AFTER stad is resolved
        glare1 = stad / "1"
        glare3 = stad / "3"
        no_seats = stad / "NoSeats.rx3"
        day_texture = stad/'texture_day.rx3'
        night_texture = stad/'texture_night.rx3'
        if not day_texture.is_file():
            day_texture = night_texture
        if not night_texture.is_file():
            night_texture = day_texture
        steps: list[tuple[str, callable]] = [
            ("Copying stadium model", lambda: copy_pack(stad / "model.rx3", dest / "stadium" / f"stadium_{injid}.rx3")),
            ("Copying day textures", lambda: copy_pack(day_texture, dest / "stadium" / f"stadium_{injid}_1_textures.rx3")),
            ("Copying night textures", lambda: copy_pack(night_texture, dest / "stadium" / f"stadium_{injid}_3_textures.rx3")),
            ("Copying entrance scene", lambda: copy_or_clear(stad / "EntranceScene" / f"bcstadiumcams_{injid}.dat", game / "data" / "bcdata" / "camera" / f"bcstadiumcams_{injid}.dat")),
            ("Copying crowd day", lambda: copy_pack(stad / "crowd_day.dat", dest / "crowdplacement" / f"crowd_{injid}_1.dat")),
            ("Copying crowd night", lambda: copy_pack(stad / "crowd_night.dat", dest / "crowdplacement" / f"crowd_{injid}_3.dat")),
        ]
        for suffix in range(4):
            steps.extend(
                [
                    (f"Day glare {suffix}", lambda s=suffix: copy_glares(glare1 / f"glare1_{s}.lnx", "1", str(s), injid, game)),
                    (f"Day glare texture {suffix}", lambda s=suffix: copy_pack(glare1 / f"glare1_{s}.rx3", dest / "fx" / f"glares_{injid}_1_{s}.rx3")),
                    (f"Night glare {suffix}", lambda s=suffix: copy_glares(glare3 / f"glare3_{s}.lnx", "3", str(s), injid, game)),
                    (f"Night glare texture {suffix}", lambda s=suffix: copy_pack(glare3 / f"glare3_{s}.rx3", dest / "fx" / f"glares_{injid}_3_{s}.rx3")),
                ]
            )
        steps.extend(
            [
                ("Applying police setup", lambda: extra_setup(app.Psource, game / app.Pdest.relative_to(app.exedir), police, "policeofficer", '9' if str(injid)=='261' else '4')),
                ("Applying net setup", lambda: extra_setup(app.Nsource, game / app.Ndest.relative_to(app.exedir), net, "netcolor", "0", log=app.log)),
                ("Applying pitch setup", lambda: extra_setup(app.PitchMowsource, game / app.PitchMowdest.relative_to(app.exedir), pitch, "pitchmowpattern", "0")),
            ]
        )
        if no_seats.exists():
            steps.append(("Applying crowd chairs", lambda: copy_pack(no_seats, dest / "crowdchair" / f"specificchair_0_{injid}.rx3")))
        total_steps = max(1, len(steps))
        for index, (message, action) in enumerate(steps, start=1):
            self._validate_copy_context(expected_context, section, injid)
            progress = 12 + (index / total_steps) * 72
            app._worker_queue.put(("progress", progress, message))
            action()

        stadmovie = (stad / "StadiumMovie.vp8").exists() and (stad / "StadiumBumper.big").exists()
        if stadmovie:
            copy_pack(stad / "StadiumMovie.vp8", game / app.Movdata.relative_to(app.exedir))
            copy_pack(stad / "StadiumBumper.big", game / app.MOVBUMP.relative_to(app.exedir))
        managed = {Path('data/sceneassets') / rel for rel in stadium_injection_paths(str(injid))}
        managed.add(Path('data/bcdata/camera') / f'bcstadiumcams_{injid}.dat')
        identity, route = stage_match_assets(transaction, str(injid),
            getattr(app, 'HID', hid), getattr(app, 'AID', '0'))
        managed.add(route)
        app._worker_queue.put(('progress', 86, 'Publishing prepared stadium assets'))
        transaction.commit(managed, lambda: self._validate_copy_context(expected_context, section, injid))
        app.log(f'Stadium assets prepared and published as one validated set: {stad_name}; inactive injID={injid}; resources={identity}')
        return {
            "section_id": hid,
            "section_name": section,
            "injid": injid,
            "stad_name": stad_name,
            "stadmovie": stadmovie,
            "stadium_type": app.Stadiumtype,
        }

    def finish_stadium_apply(self, payload: dict) -> None:
        app = self.app
        transaction = payload.get('transaction')
        activated = False
        previous_ids = []
        try:
            if payload.get('context') != (app._kickoff_generation, app.HID, app.AID) or not app.memory.is_open():
                app.log('Discarded stadium completion from an expired match context')
                return
            if transaction is not None:
                self._validate_copy_context(payload['context'], payload['section_name'], payload['injid'])
            offsets = self.stadium_offsets(payload.get("stadium_type", "first"))
            app._set_progress(90, "Writing stadium memory")
            try:
                previous_ids.append((offsets, app.memory.get_int(app.offsets.ORISTADIDBASE, offsets)))
            except Exception:
                pass
            app.memory.write_int(app.offsets.ORISTADIDBASE, offsets, payload["injid"])
            try:
                readback = str(app.memory.get_int(app.offsets.ORISTADIDBASE, offsets))
            except Exception:
                readback = ""
            if readback != str(payload["injid"]):
                fallback_type = "alter" if payload.get("stadium_type", "first") == "first" else "first"
                fallback_offsets = self.stadium_offsets(fallback_type)
                app.log(
                    f"Primary stadium write did not stick for {payload['stad_name']} "
                    f"(expected {payload['injid']}, got {readback or 'unknown'}). Retrying with {fallback_type} chain."
                )
                try:
                    previous_ids.append((fallback_offsets, app.memory.get_int(app.offsets.ORISTADIDBASE, fallback_offsets)))
                except Exception:
                    pass
                app.memory.write_int(app.offsets.ORISTADIDBASE, fallback_offsets, payload["injid"])
                if str(app.memory.get_int(app.offsets.ORISTADIDBASE,fallback_offsets)) != str(payload['injid']):
                    raise RuntimeError('Stadium ID could not be confirmed in FIFA memory')
            activated = True
            self._applied_slot = str(payload['injid'])
            self._previous_manual_override = None
            if transaction is not None:
                transaction.accept()
            stad_name = payload["stad_name"]
            # Extract display name for scoreboardstdname (used in Discord and UI)
            scoreboard_display_name = ""
            if app.settings_ini.key_exists(stad_name, "scoreboardstdname"):
                scoreboard_display_name = app.settings_ini.read(stad_name, "scoreboardstdname").split(",")[0].strip()

            # Write stadium name to memory to both slots for consistency.
            std_offsets_176 = app.offsets.STDNAMEOFFSET176
            std_offsets_261 = app.offsets.STDNAMEOFFSET261
            std_name = "_" + (scoreboard_display_name if scoreboard_display_name else stad_name)
            try:
                app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, std_offsets_176, std_name)
                app.memory.write_string_with_offsets(app.offsets.STDNAMEBASE, std_offsets_261, std_name)
                app.log(f"Stadium name written to memory: {std_name}")
            except Exception as exc:
                app.log(f"Failed to write stadium name to memory", exc)
            # Derive the NEXT slot from the confirmed ID, not a counter that
            # may have been flipped by a retry or a repeated automatic choice.
            app.CCount = '1' if str(payload['injid']) == '176' else '0'
            app.injID = payload["injid"]
            app.StadName = stad_name
            app.curstad = stad_name
            app.ScoreboardStadName = scoreboard_display_name  # Save display name for Discord RPC
            app.stadmovie = bool(payload["stadmovie"])
            app._set_display("stadium", stad_name)
            app._set_display("audio_last_action", f"Stadium {stad_name}")
            app._set_progress(100, f"Stadium applied: {stad_name}")
            app._set_process_status("Stadium Ready", app.success)
            self.play_stadium_loaded_sound()
            app._last_stadium_applied_signature = app._stadium_task_signature
            app._update_audio_overview()
            app.log(f"Applied stadium {stad_name} from [{payload['section_name']}] {payload['section_id']} using injID={payload['injid']}")
        finally:
            try:
                if not activated:
                    self.cancel_pending_selection()
                    for offsets, value in reversed(previous_ids):
                        try:
                            app.memory.write_int(app.offsets.ORISTADIDBASE, offsets, value)
                        except Exception as exc:
                            app.log('Could not restore previous stadium ID after failed activation', exc)
                    if transaction is not None:
                        transaction.rollback()
            finally:
                app._stadium_task_running = False
                self.pending_selection = None
                app._stadium_task_signature = None
                app._stadium_task_request_key = None
                app._hide_stadium_loading_modal(delay_ms=1200)

    def stadium_offsets(self, stadium_type: str) -> list[int]:
        app = self.app
        if stadium_type == "alter":
            return [app.offsets.S[0], app.offsets.S[1], app.offsets.S[3], app.offsets.S[4], app.offsets.S[5]]
        return [app.offsets.S[0], app.offsets.S[1], app.offsets.S[2], app.offsets.S[4], app.offsets.S[5]]

    def play_stadium_loaded_sound(self) -> None:
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            try:
                winsound.Beep(1100, 180)
            except Exception:
                pass
