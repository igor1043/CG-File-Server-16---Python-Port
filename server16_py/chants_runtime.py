from __future__ import annotations

import shutil
import math
import tempfile
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .memory_access import Memory
from .match_state import GoalClockProgress, outside_match_page, pause_page
from .rival_chants import RivalChants

if TYPE_CHECKING:
    from .app import Server16App


class MciAudioPlayer:
    _counter = 0
    _lock = threading.RLock()

    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._winmm = ctypes.WinDLL("winmm")
        self._winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p]
        self._winmm.mciSendStringW.restype = ctypes.c_uint
        with self._lock:
            MciAudioPlayer._counter += 1
        self.alias = f"server16_audio_{MciAudioPlayer._counter}"
        self._open = False
        self.volume = 0.0

    def _send(self, command: str) -> str:
        buffer = self._ctypes.create_unicode_buffer(255)
        with self._lock:
            result = self._winmm.mciSendStringW(command, buffer, len(buffer), 0)
        if result != 0:
            raise RuntimeError(f"MCI command failed ({result}): {command}")
        return buffer.value

    def open(self, path: Path) -> None:
        self.close()
        self._send(f'open "{path}" type mpegvideo alias {self.alias}')
        self._open = True

    def play(self) -> None:
        if self._open:
            self._send(f"play {self.alias} from 0")

    def length_ms(self) -> int:
        if not self._open:
            return 0
        try:
            self._send(f"set {self.alias} time format milliseconds")
            raw = self._send(f"status {self.alias} length").strip()
            return max(0, int(raw))
        except Exception:
            return 0

    def position_ms(self) -> int | None:
        if not self._open:
            return None
        try:
            self._send(f"set {self.alias} time format milliseconds")
            return max(0, int(self._send(f"status {self.alias} position").strip()))
        except Exception:
            return None

    def pause(self) -> None:
        if self._open:
            self._send(f"pause {self.alias}")

    def resume(self) -> None:
        if self._open:
            self._send(f"resume {self.alias}")

    def stop(self) -> None:
        if self._open:
            try:
                self._send(f"stop {self.alias}")
            except Exception:
                pass

    def close(self) -> None:
        if self._open:
            try:
                self._send(f"close {self.alias}")
            except Exception:
                pass
            self._open = False

    def set_volume(self, volume: float) -> None:
        if self._open:
            level = max(0, min(1000, int(volume * 1000)))
            self._send(f"setaudio {self.alias} volume to {level}")
            self.volume = level / 1000

    def mode(self) -> str:
        if not self._open:
            return "closed"
        try:
            return self._send(f"status {self.alias} mode").strip().lower()
        except Exception:
            return "closed"

    def is_playing(self) -> bool:
        return self.mode() == "playing"

    def is_paused(self) -> bool:
        return self.mode() == "paused"


class ChantsRuntime:
    MAX_PRE_MATCH_GUARD_SECONDS = 90.0

    def __init__(self, app: "Server16App") -> None:
        self.app = app
        self._special_audio_cooldown_until = 0.0

    @staticmethod
    def _safe_float(raw: str, default: float = 0.05) -> float:
        try:
            value = float(raw)
            return value if math.isfinite(value) else default
        except Exception:
            return default

    @staticmethod
    def _id3v2_tag_total(header: bytes) -> int | None:
        if len(header) < 10 or header[:3] != b"ID3":
            return None
        if header[3] not in (2,3,4) or any(value & 0x80 for value in header[6:10]):
            return None
        flags = header[5]
        size = 0
        for value in header[6:10]:
            size = (size << 7) | (value & 0x7F)
        tag_total = 10 + size + (10 if header[3]==4 and flags & 0x10 else 0)
        return tag_total if tag_total > 0 else None

    def _strip_leading_id3v2(self, data: bytes) -> bytes | None:
        tag_total = self._id3v2_tag_total(data[:10])
        if tag_total is None or tag_total >= len(data):
            return None
        remainder = data[tag_total:]
        if len(remainder) < 2 or remainder[0] != 0xFF or (remainder[1] & 0xE0) != 0xE0:
            return None
        return remainder

    def _needs_fix(self, path: Path) -> bool:
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                tag_total = self._id3v2_tag_total(handle.read(10))
                if tag_total is None or tag_total >= size:
                    return False
                handle.seek(tag_total)
                probe = handle.read(2)
        except Exception:
            return False
        return len(probe) == 2 and probe[0] == 0xFF and (probe[1] & 0xE0) == 0xE0

    def scan_chants_audio_files(self) -> list[Path]:
        root = self.app.exedir / "FSW" / "Chants"
        if not root.exists():
            return []
        return [
            path
            for path in sorted(root.rglob("*.mp3"))
            if not path.name.endswith(".original.mp3") and self._needs_fix(path)
        ]

    def fix_chants_audio_files(self, paths: list[Path] | None = None, keep_backup: bool = True) -> dict[str, int]:
        app = self.app
        if paths is None:
            root = app.exedir / "FSW" / "Chants"
            paths = (
                [p for p in sorted(root.rglob("*.mp3")) if not p.name.endswith(".original.mp3")]
                if root.exists()
                else []
            )
        counts = {"fixed": 0, "already_clean": 0, "errors": 0}
        for path in paths:
            try:
                stripped = self._strip_leading_id3v2(path.read_bytes())
            except Exception as exc:
                app.log(f"Fix chants audio: failed to read {path}", exc, exc_info=sys.exc_info())
                counts["errors"] += 1
                continue
            if stripped is None:
                counts["already_clean"] += 1
                continue
            try:
                if keep_backup:
                    backup = path.with_name(path.stem + ".original" + path.suffix)
                    if not backup.exists():
                        shutil.copy2(path, backup)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent,prefix=path.stem+'.',suffix='.tmp',delete=False) as handle:
                        temporary=Path(handle.name)
                        handle.write(stripped)
                    temporary.replace(path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                counts["fixed"] += 1
                app.log(f"Fix chants audio: stripped ID3v2 tag from {path}")
            except Exception as exc:
                app.log(f"Fix chants audio: failed to rewrite {path}", exc, exc_info=sys.exc_info())
                counts["errors"] += 1
        return counts

    def _parse_chants_config(self, raw: str) -> list[str]:
        return [part.strip() for part in raw.split(",")] if raw else []

    def _pick_random_track(self, folder: Path, last_track: Path | None = None) -> Path | None:
        files = sorted(f for f in folder.glob("*.mp3") if not f.name.casefold().endswith('.original.mp3'))
        if not files:
            return None
        candidates = [f for f in files if f != last_track] if len(files) > 1 else files
        return self.app._chants_rng.choice(candidates)

    def _pick_crowd_track(self, folder, opponent, last_track=None, avoid_normal_repeat=True):
        if folder.name == 'Support':
            if not hasattr(self, '_rivals'):
                self._rivals = RivalChants(self.app)
            track = self._rivals.pick(folder, opponent, last_track)
            if track is not None:
                self.app.log(f'Rival chant selected: opponent={opponent}; file={track.name}')
                return track
        return self._pick_random_track(folder, last_track if avoid_normal_repeat else None)

    def _open_crowd_track(self, player, track, folder):
        try:
            player.open(track)
            player.set_volume(0)
            player.play()
        except Exception as exc:
            if track.parent == folder:
                raise
            self._rivals.reject(track)
            self.app.log(f'Rival chant unavailable; falling back to Support: {track}', exc)
            player.close()
            fallback = self._pick_random_track(folder, getattr(self.app, '_chants_last_track', None))
            if fallback is None:
                raise
            player.open(fallback)
            player.set_volume(0)
            player.play()
            return fallback
        return track

    def _player_state(self) -> str:
        app = self.app
        player = app._chants_player
        if player is None:
            return "idle"
        try:
            mode = player.mode()
        except Exception:
            return "busy"
        if mode in {"closed", "stopped"}:
            return "idle"
        if mode == "paused":
            return "paused"
        return "busy"

    def _special_audio_locked(self) -> bool:
        app = self.app
        if time.time() < self._special_audio_cooldown_until:
            return True
        return self._player_state() in {"busy", "paused"}

    def _mark_special_audio(self, cooldown: float = 0.75) -> None:
        self._special_audio_cooldown_until = time.time() + max(0.0, cooldown)

    def _crowd_volume_multiplier(self) -> float:
        try:
            value = float(getattr(self.app, "_crowd_master_volume", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.0, min(2.0, value))

    def _scale_crowd_volume(self, base_volume: float) -> float:
        return max(0.0, min(1.0, base_volume * self._crowd_volume_multiplier()))

    def apply_crowd_master_volume(self) -> None:
        """Apply the live master multiplier to the current crowd track only."""
        app = self.app
        if not getattr(app, "_chants_volume_is_crowd", False):
            return
        player = getattr(app, "_chants_player", None)
        base_volume = float(getattr(app, "_chants_base_volume", 0.0) or 0.0)
        if player is None or base_volume <= 0.0:
            return
        target = self._scale_crowd_volume(base_volume)
        app._chants_target_volume = target
        app._set_display_async("audio_crowd_volume", f"{target:.2f}")
        try:
            player.set_volume(0 if getattr(app, '_chants_paused', False) or self._match_audio_finished() else target)
        except Exception as exc:
            app.log("Failed to apply live crowd master volume", exc)

    def start_chants_runtime(self) -> None:
        app = self.app
        if app.chants_thread_started or not app.module_enabled("Chants"):
            return
        app.chants_thread_started = True
        app._chants_stop.clear()
        app._chants_thread = threading.Thread(target=self.chants_runtime_loop, daemon=True)
        app._chants_thread.start()
        app.log("Chants monitor started")

    def _scale_goal_volume(self, base_volume: float) -> float:
        master = self._safe_float(getattr(self.app, '_goal_master_volume', 1.0), 1.0)
        return max(0.0, min(1.0, base_volume * max(0.0, min(1.0, master))))

    def apply_goal_master_volume(self) -> None:
        app = self.app
        player = getattr(app, '_goal_audio_player', None)
        if player is None or player is not getattr(app, '_chants_player', None):
            return
        target = self._scale_goal_volume(getattr(app, '_goal_base_volume', 0.0))
        app._chants_target_volume = target
        app._set_display_async('audio_crowd_volume', f'{target:.2f}')
        try:
            player.set_volume(0 if getattr(app, '_chants_paused', False) or self._match_audio_finished() else target)
        except Exception as exc:
            app.log('Failed to apply live goal anthem volume', exc)

    def reset_chants_state(self) -> None:
        app = self.app
        app.matchstarted = False
        app._chants_paused = False
        app._chant_track_index = 0
        app._chants_resume_after = 0.0
        app._chants_reset_requested = True
        # Keep the live level until the audio worker has faded/closed it.
        if app._chants_player is None:
            app._chants_target_volume = 0.0
            app._chants_base_volume = 0.0
            app._chants_volume_is_crowd = False
        app._last_chants_score_snapshot = None
        app._set_display_async("audio_current", "No active track")
        app._set_display_async("audio_crowd_mode", "Idle")
        app._set_display_async("audio_crowd_volume", "-")
        app._set_display_async("audio_source", "-")
        app._set_display_async("audio_next", "Waiting for kickoff")

    def _resolve_pending_entrance_arm(self) -> None:
        app = self.app
        if not getattr(app, "_entrance_armed", False):
            return
        page_name = getattr(app, "lastpagename", "") or ""
        if "TV/bumper" in page_name:
            return
        entrance_runtime = getattr(app, "entrance_runtime", None)
        if entrance_runtime is not None and getattr(entrance_runtime, "_started_match_key", None) is not None:
            app._entrance_armed = True
            return
        app._entrance_armed = False
        page_blocks = getattr(app, "_page_blocks_team_entrance", None)
        if callable(page_blocks) and page_blocks(page_name):
            app.log(f"Team entrance disarmed (match resumed on a menu page): {page_name!r}")
            return
        start_entrance = getattr(app, "_start_team_entrance", None)
        if callable(start_entrance):
            app.log(f"Team entrance armed via match-resumed signal: {page_name!r}")
            start_entrance()

    def fade_player(self, player: MciAudioPlayer, start: float, end: float, duration_ms: int, follow_master: bool = False) -> None:
        actual = getattr(player, 'volume', None)
        if isinstance(actual, (int, float)) and math.isfinite(actual):
            start = actual
        steps = 20
        if duration_ms <= 0:
            player.set_volume(end)
            return
        sleep_time = max(0.01, duration_ms / 1000 / steps)
        for step in range(steps + 1):
            target = end
            if (follow_master or end>start) and player is getattr(self.app,'_chants_player',None) and getattr(self.app,'_chants_volume_is_crowd',False):
                target=self._scale_crowd_volume(self.app._chants_base_volume)
            elif (follow_master or end>start) and player is getattr(self.app, '_goal_audio_player', None):
                target=self._scale_goal_volume(self.app._goal_base_volume)
            volume = start + ((target - start) * step / steps)
            try:
                player.set_volume(volume)
            except Exception:
                break
            time.sleep(sleep_time)

    def _open_player(self, path: Path, volume: float, fade_ms: int = 300) -> MciAudioPlayer:
        """Open and start playing a track, returning the player."""
        player = MciAudioPlayer()
        try:
            player.open(path)
            player.set_volume(0)
            player.play()
            self.fade_player(player, 0, volume, fade_ms)
        except Exception:
            player.close()
            raise
        return player

    def _play_goal_track(
        self,
        track: Path,
        volume: float,
        current: str,
        mode: str,
        source: str,
        next_text: str,
        fade_in_ms: int = 300,
        fade_out_ms: int = 500,
        minimum_hold_seconds: float = 8.0,
        chants_memory: "Memory | None" = None,
        crowd_volume: bool = False,
        goal_song: bool = False,
    ) -> bool:
        app = self.app
        if app._chants_stop.is_set() or getattr(app, '_chants_reset_requested', False) or self._match_audio_finished():
            return False
        base_volume = max(0.0, volume)
        if crowd_volume:
            volume = self._scale_crowd_volume(base_volume)
        elif goal_song:
            volume = self._scale_goal_volume(base_volume)
        player = MciAudioPlayer()
        try:
            app._chants_player = player
            if goal_song:
                app._goal_audio_player = player
                app._goal_base_volume = base_volume
            app._chants_base_volume = base_volume if crowd_volume else 0.0
            app._chants_volume_is_crowd = crowd_volume
            app._chants_target_volume = volume
            app._chants_paused = False
            player.open(track)
            duration_ms = player.length_ms()
            player.set_volume(0)
            player.play()
            self.fade_player(player, 0, volume, fade_in_ms, follow_master=True)
            duration_seconds = duration_ms / 1000 if duration_ms > 0 else 0.0
            hold_seconds = max(minimum_hold_seconds, duration_seconds)
            hold_until = time.time() + hold_seconds
            app._chants_resume_after = max(app._chants_resume_after, hold_until + 1.0)
            app._set_display_async("audio_current", current)
            app._set_display_async("audio_crowd_mode", mode)
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", source)
            app._set_display_async("audio_next", next_text)
            app.log(f"Goal audio started: {track.name} duration={duration_ms}ms hold={hold_seconds:.1f}s")
            hard_seconds = max(hold_seconds + 2.0, duration_seconds + 2.0 if duration_seconds > 0 else 180.0)
            last_safety_position = 0
            player_paused = False
            app._chants_paused = False
            progress = GoalClockProgress(required_hits=2, sample_seconds=.5) if goal_song else GoalClockProgress()
            non_running_reads = resume_reads = 0
            active_seconds = 0.0
            last_tick = time.monotonic()
            while not app._chants_stop.is_set() and not getattr(app, "_chants_reset_requested", False) and app.module_enabled("Chants"):
                if self._match_audio_finished():
                    app.log(f"Goal audio stopped: match ended ({source})")
                    break
                now = time.monotonic()
                if not player_paused:
                    active_seconds += max(0.0, now - last_tick)
                last_tick = now
                mode_state = player.mode()
                if mode_state in {"stopped", "closed"}:
                    break
                if active_seconds >= hard_seconds:
                    position = player.position_ms() if goal_song else None
                    # Some MP3s report an inaccurate duration. Keep a progressing
                    # ClubSong alive, but still release a stalled decoder.
                    if goal_song and position is not None and position > last_safety_position:
                        last_safety_position = position
                        hard_seconds = active_seconds + 30.0
                    else:
                        app.log(f"Goal audio stopped: playback safety timeout ({source})")
                        break
                if chants_memory is not None:
                    is_running = app._is_game_running_with(chants_memory)
                    if not is_running:
                        progress.reset()
                        resume_reads = 0
                        non_running_reads += 1
                        confirmed_pause = pause_page(getattr(app, 'lastpagename', '')) or non_running_reads >= 3
                        if confirmed_pause and not player_paused and player.is_playing():
                            fade_from = app._chants_target_volume if crowd_volume or goal_song else volume
                            app._chants_paused = True
                            self.fade_player(player, fade_from, 0, 400)
                            player.pause()
                            player_paused = True
                            app.log(f"Goal audio paused: {source}")
                            app._set_display_async("audio_crowd_mode", "Paused")
                            app._set_display_async("audio_next", "Resume on return")
                    else:
                        non_running_reads = 0
                        if player_paused and player.is_paused():
                            resume_reads += 1
                            if resume_reads < 3:
                                time.sleep(0.2)
                                continue
                            player.resume()
                            app._chants_paused = False
                            fade_to = app._chants_target_volume if crowd_volume or goal_song else volume
                            self.fade_player(player, 0, fade_to, 300, follow_master=True)
                            player_paused = False
                            last_tick = time.monotonic()
                            app.log(f"Goal audio resumed: {source}")
                            app._set_display_async("audio_crowd_mode", mode)
                            app._set_display_async("audio_next", next_text)
                        # Both the goal anthem and the crowd reaction fade when
                        # live play resumes. Skipping a replay must not leave the
                        # anthem playing over the next attack. A pause still
                        # preserves playback position and never counts as kickoff.
                        if active_seconds >= (1.0 if goal_song else 6.0):
                            try:
                                game_time = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
                            except Exception:
                                game_time = None
                            if progress.observe(game_time, time.monotonic()):
                                app.log(f"Goal audio cut: kick-off detected ({source}) hits={progress.hits}")
                                break
                        else:
                            progress.reset()
                time.sleep(0.2)
            fade_from = app._chants_target_volume if crowd_volume or goal_song else volume
            self.fade_player(player, fade_from, 0, fade_out_ms)
            app.log(f"Goal audio finished: {track.name}")
            return True
        finally:
            try:
                player.close()
            finally:
                if getattr(app, '_goal_audio_player', None) is player:
                    app._goal_audio_player = None
                    app._goal_base_volume = 0.0
                if app._chants_player is player:
                    app._chants_player = None
                    app._chants_target_volume = 0.0
                    app._chants_base_volume = 0.0
                    app._chants_volume_is_crowd = False
                    app._chants_paused = False
                app._chants_resume_after = time.time() + 1.0

    def _match_audio_finished(self) -> bool:
        return bool(getattr(self.app, '_match_audio_ended', False) or
                    outside_match_page(getattr(self.app, 'lastpagename', '')))

    def _pre_match_guard_tick(
        self,
        chants_memory: Memory,
        pre_match_last_time: int | None,
        pre_match_last_real: float | None,
        pre_match_speed_hits: int,
    ) -> tuple[bool, int | None, float | None, int]:
        """Release the pre-match crowd guard only after real kick-off.

        FIFA reports the game as started while the players are still walking
        out.  Sustained match-clock movement is the reliable signal that the
        actual kick-off happened; the time ceiling prevents a broken memory
        read from suppressing crowd audio for the entire match.
        """
        app = self.app
        now = time.time()
        guard_set_at = getattr(app, "_entrance_pre_match_guard_set_at", 0.0) or now
        if not getattr(app, "_entrance_pre_match_guard_set_at", 0.0):
            app._entrance_pre_match_guard_set_at = guard_set_at
        if now - guard_set_at >= self.MAX_PRE_MATCH_GUARD_SECONDS:
            app._entrance_pre_match_guard = False
            app._entrance_pre_match_guard_set_at = 0.0
            app.log(
                "Pre-match Support guard force-released after "
                f"{now - guard_set_at:.1f}s without confirmed kick-off speed"
            )
            return True, pre_match_last_time, pre_match_last_real, pre_match_speed_hits

        try:
            game_time = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMERANTIME)
        except Exception:
            game_time = None

        released = False
        if game_time is not None and pre_match_last_time is not None and pre_match_last_real is not None:
            real_delta = max(0.001, now - pre_match_last_real)
            timer_delta = abs(game_time - pre_match_last_time)
            speed = timer_delta / real_delta
            if timer_delta >= 1 and speed >= 6.0:
                pre_match_speed_hits += 1
            else:
                pre_match_speed_hits = 0
            if pre_match_speed_hits >= 3:
                app._entrance_pre_match_guard = False
                app._entrance_pre_match_guard_set_at = 0.0
                app.log(f"Pre-match Support guard released at clock speed={speed:.1f}")
                released = True
        return released, game_time, now, pre_match_speed_hits

    def chants_runtime_loop(self) -> None:
        app = self.app
        cooldown_until = 0.0
        next_chant_after = 0.0
        non_running_reads = 0
        pre_match_last_time: int | None = None
        pre_match_last_real: float | None = None
        pre_match_speed_hits = 0
        chants_memory = Memory()
        while not app._chants_stop.is_set():
            try:
                # Handle reset request from Tkinter thread safely
                if getattr(app, "_chants_reset_requested", False):
                    app._chants_reset_requested = False
                    if app._chants_player is not None:
                        try:
                            current_vol = app._chants_target_volume if app._chants_target_volume > 0 else 0.05
                            self.fade_player(app._chants_player, current_vol, 0, 400)
                            app._chants_player.stop()
                            app._chants_player.close()
                        except Exception:
                            pass
                        app._chants_player = None
                        app._chants_base_volume = 0.0
                        app._chants_volume_is_crowd = False
                        app._chants_target_volume = 0.0
                        app._chants_paused = False
                    cooldown_until = next_chant_after = 0.0
                    non_running_reads = 0
                    time.sleep(0.1)
                    continue

                if not app.module_enabled("Chants"):
                    self.reset_chants_state()
                    time.sleep(0.5)
                    continue

                if not app.MP or not chants_memory.attack(app.MP) or not chants_memory.is_open():
                    self.reset_chants_state()
                    time.sleep(0.5)
                    continue

                if self._match_audio_finished():
                    if app._chants_player is not None:
                        self.reset_chants_state()
                    time.sleep(0.2)
                    continue

                hid = (app.HID or "").split()[0].strip() if app.HID and app.HID.strip() else ""
                aid = (app.AID or "").split()[0].strip() if app.AID and app.AID.strip() else ""
                home_chants = app.settings_ini.read(hid, "chantsid") if hid and app.settings_ini.key_exists(hid, "chantsid") else ""
                away_chants = app.settings_ini.read(aid, "chantsid") if aid and app.settings_ini.key_exists(aid, "chantsid") else ""

                if not app._is_game_running_with(chants_memory):
                    non_running_reads += 1
                    pre_match_last_time = None
                    pre_match_last_real = None
                    pre_match_speed_hits = 0
                    if non_running_reads >= 3 or pause_page(getattr(app, 'lastpagename', '')):
                        app.matchstarted = False
                        # Only pause if not already paused by a sub-function
                        if app._chants_player is not None and app._chants_player.is_playing() and not app._chants_paused:
                            start_volume = app._chants_target_volume if app._chants_target_volume > 0 else 0.05
                            app._chants_paused = True
                            self.fade_player(app._chants_player, start_volume, 0, 500)
                            app._chants_player.pause()
                            app._chants_paused = True
                            app._set_display_async("audio_crowd_mode", "Paused")
                            app._set_display_async("audio_next", "Resume on return")
                    time.sleep(0.5)
                    continue

                non_running_reads = 0
                was_matchstarted = app.matchstarted
                app.matchstarted = True
                if not was_matchstarted:
                    self._resolve_pending_entrance_arm()

                if getattr(app, "_entrance_pre_match_guard", False):
                    released, pre_match_last_time, pre_match_last_real, pre_match_speed_hits = self._pre_match_guard_tick(
                        chants_memory, pre_match_last_time, pre_match_last_real, pre_match_speed_hits
                    )
                    if released:
                        next_chant_after = time.time() + 1.0
                    if getattr(app, "_entrance_pre_match_guard", False):
                        app._set_display_async("audio_crowd_mode", "Waiting for kick-off")
                        app._set_display_async("audio_next", "Support chants after actual kick-off")
                        time.sleep(0.2)
                        continue

                if getattr(app, "_entrance_active", False):
                    app._set_display_async("audio_crowd_mode", "Waiting for entrance")
                    app._set_display_async("audio_next", "Crowd audio after entrance")
                    time.sleep(0.2)
                    continue

                score_home = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMEHOMEGOALSCORE)
                score_away = chants_memory.get_int(app.offsets.GAMESTATSBASE, app.offsets.GAMEAWAYGOALSCORE)
                if app._last_chants_score_snapshot is None:
                    app._last_chants_score_snapshot = (score_home, score_away)
                previous_home, previous_away = app._last_chants_score_snapshot

                if (score_home, score_away) != (previous_home, previous_away):
                    # Preserve the crowd track position during the goal reaction.
                    if app._chants_player is not None and app._chants_player.is_playing():
                        self.fade_player(app._chants_player, app._chants_target_volume or 0.05, 0, 500)
                        app._chants_player.pause()
                        app._chants_paused = True
                        app.log("Crowd chant paused for goal reaction")
                    scorer = hid if score_home > previous_home else aid if score_away > previous_away else ""
                    app._last_chants_score_snapshot = (score_home, score_away)
                    app._chants_resume_after = time.time() + 6.0
                    app._chants_last_goal_time = time.time()
                    app._set_display_async("audio_crowd_mode", "Goal reaction")
                    app._set_display_async("audio_last_action", f"Goal {score_home} x {score_away}")
                    app._set_display_async("audio_next", "Club song, then crowd")
                    if scorer:
                        time.sleep(2.0)
                        club_song_played = False
                        if scorer == hid or app.module_enabled("AwayClubSong"):
                            club_song_played = self._play_club_song(scorer, chants_memory=chants_memory)
                        # A completed club anthem already supplied the goal reaction.
                        if not club_song_played and scorer == aid and away_chants and app.module_enabled("AwayChants"):
                            self._play_away_reaction(
                                away_chants,
                                score_home,
                                score_away,
                                skip_random=club_song_played,
                                chants_memory=chants_memory,
                            )
                    else:
                        app.log(f"Goal club song skipped: scorer unavailable for score {score_home} x {score_away} (hid={hid or '-'}, aid={aid or '-'})")
                    cooldown_until = max(time.time() + 4.5, app._chants_resume_after)
                    next_chant_after = cooldown_until
                    continue

                app._last_chants_score_snapshot = (score_home, score_away)

                if time.time() < cooldown_until:
                    app._set_display_async("audio_crowd_mode", "Goal reaction cooldown")
                    app._set_display_async("audio_next", "Wait until crowd can restart")
                    time.sleep(0.5)
                    continue

                if app._chants_paused and app._chants_player is not None and app._chants_player.is_paused():
                    app._chants_player.resume()
                    app._chants_paused = False
                    resume_volume = app._chants_target_volume
                    if resume_volume <= 0.0 and self._crowd_volume_multiplier() > 0.0:
                        resume_volume = 0.04
                    self.fade_player(app._chants_player, 0, resume_volume, 300, follow_master=True)
                    app._chants_paused = False
                    app.log("Crowd chant resumed after goal reaction")
                    app._set_display_async("audio_crowd_mode", "Resumed")
                    app._set_display_async("audio_next", "Keep crowd running")

                if not home_chants:
                    app._set_display_async("audio_crowd_mode", "Awaiting home chants")
                    app._set_display_async("audio_next", "Wait for home chants configuration")
                    time.sleep(0.5)
                    continue

                # Clean up stopped player
                if app._chants_player is not None and app._chants_player.mode() == "stopped":
                    try:
                        app._chants_player.close()
                    except Exception:
                        pass
                    app._chants_player = None
                    app._chants_base_volume = 0.0
                    app._chants_volume_is_crowd = False
                    if app._chants_rng.random() < 0.7:
                        next_chant_after = time.time() + app._chants_rng.uniform(1.5, 4.0)
                    else:
                        next_chant_after = time.time()

                if app._chants_player is not None and app._chants_player.is_playing():
                    app._set_display_async("audio_crowd_mode", "Playing")
                    app._set_display_async("audio_next", "Current chant still active")
                    time.sleep(0.5)
                    continue

                if app._chants_player is not None and app._chants_player.is_paused():
                    app._set_display_async("audio_next", "Waiting resume")
                    time.sleep(0.5)
                    continue

                if time.time() < next_chant_after:
                    remaining = max(0.0, next_chant_after - time.time())
                    # Try away chants during home crowd pause
                    _home_parts = self._parse_chants_config(home_chants) if home_chants else []
                    away_prob = self._safe_float(_home_parts[9], 0.35) if len(_home_parts) > 9 else 0.35
                    if (remaining > 0.5
                            and away_chants
                            and app.module_enabled("AwayChants")
                            and app._chants_rng.random() < away_prob):
                        app.log(f"Away chant triggered: remaining={remaining:.1f}s prob={away_prob:.2f}")
                        self._play_away_chant(away_chants, score_home, score_away)
                    else:
                        app._set_display_async("audio_crowd_mode", "Crowd pause")
                        app._set_display_async("audio_next", f"Next chant in {remaining:.1f}s")
                        time.sleep(0.5)
                    continue

                # Parse home chants config
                parts = self._parse_chants_config(home_chants)
                if len(parts) < 6:
                    app._set_display_async("audio_crowd_mode", "Invalid config")
                    app._set_display_async("audio_next", "Fix chantsid config")
                    time.sleep(0.5)
                    continue

                folder = parts[0].replace("/", "\\").strip("\\")
                chants_root = app.exedir / "FSW" / "Chants" / folder
                score_diff = score_home - score_away
                if score_diff >= -2:
                    subdir = "Support"
                    volume_index = 1 if score_diff == 0 else 2 if score_diff > 0 else 3 if score_diff == -1 else 4
                else:
                    subdir = "Complaint"
                    volume_index = 5

                chants_dir = chants_root / subdir
                if not chants_dir.exists():
                    app._set_display_async("audio_next", f"Missing folder {subdir}")
                    time.sleep(0.5)
                    continue

                last_played = getattr(app, "_chants_last_track", None)
                track = self._pick_crowd_track(chants_dir, aid, last_track=last_played)
                if track is None:
                    app._set_display_async("audio_next", f"No tracks in {subdir}")
                    time.sleep(0.5)
                    continue
                app._chants_last_track = track

                volume = self._safe_float(parts[volume_index], 0.05)
                if subdir == "Complaint":
                    volume = max(0.03, volume * (0.75 + (app._chants_rng.random() * 0.25)))

                # Configurable silence
                silence_prob = self._safe_float(parts[7], 0.15) if len(parts) > 7 else 0.15
                silence_max = self._safe_float(parts[8], 8.0) if len(parts) > 8 else 8.0
                silence_min = min(3.0, silence_max)
                if app._chants_rng.random() < silence_prob:
                    silence_duration = app._chants_rng.uniform(silence_min, max(silence_min, silence_max))
                    next_chant_after = time.time() + silence_duration
                    app._set_display_async("audio_crowd_mode", "Crowd silence")
                    app._set_display_async("audio_next", f"Silence for {silence_duration:.1f}s")
                    time.sleep(0.5)
                    continue

                # Crowd fatigue after 20 min without goal
                time_since_goal = time.time() - app._chants_last_goal_time if app._chants_last_goal_time > 0 else 0.0
                if time_since_goal > 1200:
                    fatigue_factor = max(0.70, 1.0 - ((time_since_goal - 1200) / 1200) * 0.30)
                else:
                    fatigue_factor = 1.0
                volume = max(0.02, volume * fatigue_factor)
                base_volume = volume
                volume = self._scale_crowd_volume(base_volume)

                # Play home chant using app._chants_player
                app._chants_base_volume = base_volume
                app._chants_volume_is_crowd = True
                app._chants_target_volume = volume
                app._chants_player = MciAudioPlayer()
                track = self._open_crowd_track(app._chants_player, track, chants_dir)
                app._chants_last_track = track
                self.fade_player(app._chants_player, 0, volume, 300, follow_master=True)
                app._set_display_async("audio_current", track.stem)
                app._set_display_async("audio_last_action", f"Chants {subdir}")
                app._set_display_async("audio_clubsong", hid if hid else "-")
                app._set_display_async("audio_crowd_mode", f"{subdir} ({score_home}-{score_away})")
                app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
                app._set_display_async("audio_source", "Home crowd")
                app._set_display_async("audio_next", "Random crowd loop while match runs")

            except Exception as exc:
                app.log("Chants monitor error", exc, exc_info=sys.exc_info())
            time.sleep(0.5)

        player = app._chants_player
        app._chants_player = None
        if player is not None:
            player.close()
        chants_memory.close()
        app.chants_thread_started = False
        app.log("Chants monitor stopped")

    def _play_club_song(self, team_id: str, chants_memory: "Memory | None" = None) -> bool:
        """Play the goal club song and hold the chants loop until it finishes."""
        app = self.app
        if self._special_audio_locked():
            if app._chants_player is not None:
                try:
                    self.fade_player(app._chants_player, app._chants_target_volume or 0.05, 0, 250)
                    app._chants_player.stop()
                    app._chants_player.close()
                except Exception:
                    pass
                app._chants_player = None
                app._chants_base_volume = 0.0
                app._chants_volume_is_crowd = False
        if not team_id or not app.settings_ini.key_exists(team_id, "chantsid"):
            app.log(f"Goal club song skipped for {team_id or '-'}: chantsid not configured")
            return False
        raw = app.settings_ini.read(team_id, "chantsid")
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 7:
            app.log(f"Goal club song skipped for {team_id}: invalid chantsid config")
            return False
        folder = parts[0].replace("/", "\\").strip("\\")
        club_song = app.exedir / "FSW" / "Chants" / folder / "ClubSong.mp3"
        if not club_song.exists():
            app.log(f"Goal club song skipped for {team_id}: missing {club_song}")
            return False
        volume = self._safe_float(parts[6], 0.08)
        try:
            played = self._play_goal_track(
                club_song,
                volume,
                "ClubSong",
                "Club song",
                f"Club anthem {team_id}",
                "Return to crowd after anthem",
                minimum_hold_seconds=12.0,
                chants_memory=chants_memory,
                goal_song=True,
            )
            app._set_display_async("audio_current", "ClubSong")
            app._set_display_async("audio_clubsong", team_id)
            return played
        except Exception as exc:
            app.log(f"Club song failed for {team_id}", exc, exc_info=sys.exc_info())
            return False

    def _play_away_chant(self, away_chants: str, score_home: int, score_away: int) -> None:
        """Play away chant using app._chants_player and return immediately.
        The main chants loop remains free to handle pause/resume globally.
        """
        app = self.app
        if self._special_audio_locked():
            return
        parts = self._parse_chants_config(away_chants)
        if len(parts) < 6:
            return
        folder = parts[0].replace("/", "\\").strip("\\")
        score_diff = score_away - score_home
        if score_diff >= -2:
            subdir = "Support"
            volume_index = 1 if score_diff == 0 else 2 if score_diff > 0 else 3
        else:
            subdir = "Complaint"
            volume_index = 5
        chants_dir = app.exedir / "FSW" / "Chants" / folder / subdir
        if not chants_dir.exists():
            return
        track = self._pick_crowd_track(chants_dir, getattr(app, 'HID', ''),
                                       getattr(self, '_away_last_track', None), avoid_normal_repeat=False)
        if track is None:
            return
        base_volume = self._safe_float(parts[volume_index], 0.05)
        volume = max(0.02, min(base_volume * 0.45, 0.06))
        base_volume = volume
        volume = self._scale_crowd_volume(base_volume)
        try:
            app._chants_player = MciAudioPlayer()
            app._chants_base_volume = base_volume
            app._chants_volume_is_crowd = True
            app._chants_target_volume = volume
            track = self._open_crowd_track(app._chants_player, track, chants_dir)
            self._away_last_track = track
            self.fade_player(app._chants_player, 0, volume, 300, follow_master=True)
            self._mark_special_audio(1.0)
            app._set_display_async("audio_current", track.stem)
            app._set_display_async("audio_crowd_mode", f"Away crowd ({score_home}-{score_away})")
            app._set_display_async("audio_crowd_volume", f"{volume:.2f}")
            app._set_display_async("audio_source", "Away crowd")
            app._set_display_async("audio_next", "Away chant during home pause")
        except Exception as exc:
            app.log("Away chant failed", exc, exc_info=sys.exc_info())

    def _play_away_reaction(
        self,
        away_chants: str,
        score_home: int,
        score_away: int,
        skip_random: bool = False,
        chants_memory: "Memory | None" = None,
    ) -> bool:
        """Play away reaction after an away goal and hold the chants loop until it finishes."""
        app = self.app
        if self._special_audio_locked():
            return False
        parts = self._parse_chants_config(away_chants)
        if len(parts) < 6 or (not skip_random and app._chants_rng.random() > 0.45):
            return False
        folder = parts[0].replace("/", "\\").strip("\\")
        support_dir = app.exedir / "FSW" / "Chants" / folder / "Support"
        track = self._pick_random_track(support_dir)
        if track is None:
            return False
        base_volume = self._safe_float(parts[2], 0.04)
        volume = max(0.02, min(0.12, base_volume * 0.6))
        app._set_display_async("audio_last_action", f"Away crowd reaction {score_home} x {score_away}")
        try:
            played = self._play_goal_track(
                track,
                volume,
                track.stem,
                "Away reaction",
                "Away crowd",
                "Return to crowd after reaction",
                fade_in_ms=250,
                fade_out_ms=350,
                chants_memory=chants_memory,
                crowd_volume=True,
            )
            return played
        except Exception as exc:
            app.log("Away reaction failed", exc, exc_info=sys.exc_info())
            return False
