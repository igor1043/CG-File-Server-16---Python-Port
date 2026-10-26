from __future__ import annotations

import ctypes
import json
import os
import queue
import random
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import webbrowser
from datetime import datetime
from time import perf_counter
from pathlib import Path
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk

import psutil
from PIL import Image, ImageTk

from . import __version__ as APP_VERSION
import server16_py as features
from .asset_runtime import AssetRuntime
from .audio_profiles import AudioProfileRuntime
from .db_patcher import restore_stadium_names
from .match_string_patcher import patch_match_string
from .assignment_runtime import AssignmentRuntime
from .camera_runtime import CameraPreset, CameraRuntime
from .cloth_motion_switch import ClothMotionSwitch
from .competition_icons import CompetitionIconService
from .shutdown import cleanup_step, bounded_cleanup, finish_frozen_process, close_owned_readers
from .chants_runtime import ChantsRuntime, MciAudioPlayer
from .entrance_runtime import TeamEntranceRuntime
from .entrance_props_runtime import EntrancePropsRuntime
from .discord_rpc_runtime import DiscordRPCRuntime, StadiumPreviewUploader
from .fifa_db import FifaDatabase
from .gamepad_runtime import (
    XINPUT_GAMEPAD_BACK,
    XINPUT_GAMEPAD_DPAD_LEFT,
    XINPUT_GAMEPAD_DPAD_RIGHT,
    XINPUT_GAMEPAD_START,
    XInputGamepadReader,
)
from .file_tools import (
    checkdirs,
    checkver,
    clear_generated_cache,
    copy,
    copy_if_exists,
    extra_setup,
    resolve_stadium_preview_path,
    restore_native_assets,
)
from .dialogs import FifaLocationWarningDialog, ImgbbApiKeyDialog
from .ini_file import SessionIniFile, module_setting_enabled, ensure_audio_module_defaults
from .memory_access import Memory, MemoryAccessError
from .match_state import outside_match_page, pause_page, post_match_page
from .localization import LANGUAGE_LABELS, LocalizationManager, SUPPORTED_LANGUAGES
from .offsets import Offsets
from .settings_editor import SettingsAreaEditor, asset_specs, audio_specs, stadium_specs
from .settings_store import SettingsStore
from .stadium_runtime import StadiumRuntime
from .stadium_selector import StadiumSelector
from .first_person_runtime import first_person_runtime
from .startup_diagnostics import StartupDiagnostics
from .update_checker import GithubReleaseChecker, UpdateCheckResult
try:
    from .d3d_injector import D3DOverlayInjector as _D3DOverlayInjector
except Exception:
    _D3DOverlayInjector = None  # type: ignore[assignment,misc]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
VK_MENU = 0x12
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


class Server16App(tk.Tk):
    UPDATE_REPO_OWNER = "igor1043"
    UPDATE_REPO_NAME = "CG-File-Server-16---Python-Port"

    def __init__(self, splash=None) -> None:
        if splash is not None:
            splash.close()
            splash = None
        super().__init__()
        self._ui_thread = threading.get_ident()
        self._ui_events = queue.Queue()
        self._ui_event_job = None
        self._log_lock = threading.Lock()
        self._stadium_selector = None
        self._manual_stadium_override = None
        self._stadium_fixture_entered = False
        self._launch_splash = splash
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.withdraw()
        self.base_dir = self._resolve_base_dir()
        self.resource_dir = self._resolve_resource_dir()
        self.icon_path = self._resolve_icon_path()
        self._window_icon_image = None
        self.log_path = self.base_dir / "runtime" / "server16.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(self.base_dir / "runtime" / "settings.json")
        self.show_stadium_loading_var = tk.BooleanVar(value=self.settings.show_stadium_loading_notification)
        self.keep_open_var = tk.BooleanVar(value=self.settings.keep_open_on_game_close)
        self.random_stadium_selection_var = tk.BooleanVar(value=self.settings.random_stadium_selection)
        self.localization = LocalizationManager(self.resource_dir / "server16_py" / "locales", self.settings.language)
        if self._launch_splash is not None:
            self._launch_splash.set_message(self.tr("splash.starting"))
        self.log_backup_path = self.log_path.with_suffix(".previous.log")
        self._prepare_runtime_log()
        self.offsets = Offsets.load()
        self.memory = Memory()
        self.pagechange = False
        self.skillgamechange = False
        self.bumperpagechange = False
        self.matchstarted = False
        self._match_audio_ended = False
        self._native_assets_restored_for_match = False
        self.lastpagename = ""
        self.curstad = ""
        self.StadName = ""
        self.ScoreboardStadName = ""  # Display name from scoreboardstdname setting
        self.stadmovie = False
        self.CCount = "0"
        self.injID = "176"
        self.PoliceNum = "4"
        self.HID = ""
        self.AID = ""
        self.STADID = ""
        self.TOURNAME = ""
        self.TOURROUNDID = ""
        self.derby = ""
        self.tvlogoscoreboardtype = "default"
        self._last_runtime_signature = None
        self._last_context_error = None
        self._closing = False
        self._poll_job = None
        self._stats_job = None
        self._kickoff_retry_job = None
        self._overlay_job = None
        self._kickoff_retry_remaining = 0
        self._attached_once = False
        self._logs_visible = False
        self._kickoff_generation = 0
        self._overlay_enabled = False
        self._overlay_visible = False
        self._overlay_space_down = False
        self._overlay_toggle_ready_at = 0.0
        self._overlay_hwnd = 0
        self._fifa_hwnd = 0
        self._crowd_volume_window = None
        self._crowd_volume_canvas = None
        self._crowd_volume_value_label = None
        self._crowd_volume_hwnd = 0
        self._crowd_volume_visible = False
        self._crowd_volume_hide_at = 0.0
        self._crowd_volume_gamepad = XInputGamepadReader()
        self._crowd_volume_previous_buttons = 0
        self._crowd_volume_combo_latched = False
        self._crowd_volume_start_pressed_at = 0.0
        self._crowd_volume_back_pressed_at = 0.0
        self._crowd_volume_last_direction = 0
        self._crowd_volume_next_adjust_at = 0.0
        self._crowd_master_volume = self.settings.crowd_master_volume
        self._goal_master_volume = self.settings.goal_master_volume
        self._goal_audio_player = None
        self._goal_base_volume = 0.0
        self._crowd_master_volume_dirty = False
        self.audio_profiles = AudioProfileRuntime(self)
        self._restore_fullscreen_on_hide = False
        self._launcher_mode = True
        self._worker_queue: queue.Queue[tuple] = queue.Queue()
        self._worker_poll_job = None
        self._stadium_task_running = False
        self._asset_loading_started_at: dict[str, float] = {}
        self._asset_loading_hide_jobs: dict[str, str] = {}
        self._asset_loading_fallback: set[str] = set()
        self._stadium_task_signature = None
        self._stadium_task_request_key = None
        self._last_stadium_applied_signature = None
        self._stadium_choice_dialog = None
        self._stadium_choice_signature = None
        self._stadium_choice_result = None
        self._stadium_choice_ready = False
        self.labels = {}
        self.stat_title_labels = {}
        self.info_labels = {}
        self.module_vars = {}
        self.module_checks = {}
        self.module_states = {}
        self.log_widget = None
        self.logs_frame = None
        self.check_update_button = None
        self.check_update_badge = None
        self._update_available = False
        self.clean_cache_button = None
        self.imgbb_key_button = None
        self.locate_fifa_button = None
        self.launch_fifa_button = None
        self.assign_scoreboard_button = None
        self.assign_movie_button = None
        self.exclude_competition_button = None
        self.start_overlay_button = None
        self.log_status_label = None
        self.log_follow_button = None
        self.language_label = None
        self.language_combo = None
        self.language_var = tk.StringVar(value=self.settings.language)
        self._log_autofollow = True
        self.ui_root = None
        self.tabview = None
        self.dashboard_tab = None
        self.logs_tab = None
        self.audio_tab = None
        self.camera_tab = None
        self.banner_title_label = None
        self.help_label = None
        self.page_banner = None
        self.progress_bar = None
        self.progress_text_label = None
        self.progress_value = None
        self.stadium_loading_modal = None
        self.stadium_loading_title = None
        self.stadium_loading_name = None
        self.stadium_loading_detail = None
        self.stadium_loading_value = None
        self.stadium_loading_bar = None
        self._stadium_loading_hwnd = 0
        self._stadium_loading_visible = False
        self._stadium_loading_restore_fullscreen = False
        self._d3d_injector = None  # D3DOverlayInjector, created lazily
        self._d3d_overlay_shown_at = 0.0   # monotonic time when overlay was shown
        self._d3d_overlay_hide_job = None  # pending after() job for deferred hide
        self._stadium_loading_hide_job = None
        self.status_pill = None
        self.dashboard_canvas = None
        self.dashboard_scrollbar = None
        self.dashboard_content = None
        self.dashboard_window_id = None
        self._audio_details: dict[str, str] = {}
        self._team_logo_labels: dict[str, tk.Label] = {}
        self._team_logo_images: dict[str, ImageTk.PhotoImage | None] = {}
        self._stadium_preview_label = None
        self._stadium_preview_image: ImageTk.PhotoImage | None = None
        self.stadium_loading_preview = None
        self._stadium_loading_image: ImageTk.PhotoImage | None = None
        self._settings_editors: dict[str, SettingsAreaEditor] = {}
        self._camera_presets: list[CameraPreset] = []
        self._camera_presets_by_name: dict[str, CameraPreset] = {}
        self._camera_preview_cache: dict[tuple[str, str], Image.Image] = {}
        self._camera_preview_render_cache: dict[tuple[str, str, int, int], ImageTk.PhotoImage] = {}
        self._camera_selected_name: str | None = None
        self._camera_preview_source_key: tuple[str, str] | None = None
        self._camera_preview_canvas_window = None
        self.camera_listbox = None
        self.camera_name_label = None
        self.camera_preview_canvas = None
        self.camera_preview_frame = None
        self.camera_preview_image_label = None
        self.camera_preview_status = None
        self.camera_package_label = None
        self.camera_select_button = None
        self.camera_example_var = tk.StringVar(value="")
        self.camera_example_combo = None
        self.camera_instruction_text = None
        self.camera_apply_button = None
        self.camera_library_card = None
        self.camera_preview_card = None
        self.logs_group = None
        self.app_version = APP_VERSION
        self._update_check_in_progress = False
        self._update_checker = GithubReleaseChecker(self.UPDATE_REPO_OWNER, self.UPDATE_REPO_NAME)
        self.chants_thread_started = False
        self._chants_stop = threading.Event()
        self._chants_reset_requested = False
        self._chants_game_active = False
        self._chants_oneshot_stop = None
        self._chants_last_track = None
        self._chants_last_goal_time = 0.0
        self._chants_player: MciAudioPlayer | None = None
        self._chants_base_volume = 0.0
        self._chants_volume_is_crowd = False
        self._chant_track_index = 0
        self._chants_paused = False
        self._chants_target_volume = 0.0
        self._entrance_active = False
        self._entrance_armed = False
        self._entrance_pre_match_guard = False
        self._entrance_pre_match_guard_set_at = 0.0
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot: tuple[int, int] | None = None
        self._chants_resume_after = 0.0
        self._chants_rng = random.Random()
        self._last_live_score = (0, 0)
        self._last_live_update = ""
        self.assets_runtime = AssetRuntime(self)
        self.stadium_runtime = StadiumRuntime(self)
        self.chants_runtime = ChantsRuntime(self)
        self.gamepad_bridge = None
        self.entrance_runtime = TeamEntranceRuntime(self)
        self.entrance_props_runtime = EntrancePropsRuntime(self)
        self.assignment_runtime = AssignmentRuntime(self)
        self.camera_runtime = CameraRuntime(self)
        # Initialize DiscordRPC (loads from settings.json)
        discord_rpc_config = self.settings.data.get("discord_rpc", {})
        client_id = discord_rpc_config.get("client_id", "1495719449700077630")
        self.discord_rpc = DiscordRPCRuntime(client_id, logger=None)
        self._discord_rpc_enabled = discord_rpc_config.get("enabled", False)
        self._discord_rpc_last_presence = None
        # Stadium preview uploader for Discord Rich Presence
        _preview_provider = (discord_rpc_config.get("stadium_preview_provider", "discord_webhook") or "discord_webhook").strip().lower()
        _webhook_url = discord_rpc_config.get("stadium_preview_webhook", "")
        _imgur_client_id = (discord_rpc_config.get("stadium_preview_imgur_client_id", "") or "").strip()
        _imgbb_api_key = (discord_rpc_config.get("stadium_preview_imgbb_api_key", "") or "").strip()
        _uploader_enabled = (
            bool(_webhook_url)
            or (_preview_provider == "imgur" and bool(_imgur_client_id))
            or (_preview_provider == "imgbb" and bool(_imgbb_api_key))
        )
        self._stadium_preview_uploader: StadiumPreviewUploader | None = (
            StadiumPreviewUploader(
                _webhook_url,
                provider=_preview_provider,
                imgur_client_id=_imgur_client_id,
                imgbb_api_key=_imgbb_api_key,
            )
            if _uploader_enabled
            else None
        )
        if self._stadium_preview_uploader is not None:
            self._stadium_preview_uploader.add_upload_callback(self._on_stadium_preview_uploaded)
        if self._discord_rpc_enabled:
            self.discord_rpc.connect()
        # Initialize team database (will be loaded when FIFA EXE is selected)
        self.team_db: FifaDatabase | None = None
        self._team_db_load_token = 0
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.GetAsyncKeyState.argtypes = [wintypes.INT]
        self.user32.GetAsyncKeyState.restype = wintypes.SHORT
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        self.user32.SetWindowLongW.restype = ctypes.c_long
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_ulong]
        self.user32.keybd_event.restype = None
        self.user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self._apply_window_icon(self)
        self._configure_theme()
        self._build_ui()
        self._install_exception_hook()
        self._build_stadium_loading_modal()
        self._build_crowd_volume_window()
        self._ui_event_job = self.after(50,self._drain_ui_events)
        try:
            self._stadium_selector = StadiumSelector(self)
        except Exception as exc:
            self.log('Stadium selector initialization failed',exc)
        try:
            # Restore the saved camera without requiring the overlay to open.
            first_person_runtime(self)
        except Exception as exc:
            self.log('First-person initialization failed',exc)
        self.setuppaths()
        self.competition_icons = CompetitionIconService(self.log)
        if not self._check_fifa_location():
            return
        if self.fifaEXE != "default":
            self._check_fifa_settings()
        self.refresh_camera_catalog()
        self.refresh_modules()
        self.log("Bootstrap file writes are deferred until an explicit runtime action")
        self.log("Application started")
        self._startup_diagnostics = None
        try:
            self._startup_diagnostics = StartupDiagnostics(self.base_dir, self.resource_dir, APP_VERSION, self.log)
        except Exception as exc:
            self.log('Startup diagnostics initialization unavailable', exc)
        self._poll_job = self.after(500, self.poll_process)
        self._stats_job = self.after(250, self.stats_loop)
        self._overlay_job = self.after(40, self.overlay_loop)
        self.after(100, self._sync_competition_icons)
        self.after(3000, lambda: self.check_updates(silent=True))
        if self.module_enabled("Chants"):
            self._start_chants_runtime()
        if any(slot.get('enabled') or slot.get('hide_from_fifa') for slot in self.settings.data.get('gamepad_bridge',{}).get('slots',[])):
            from .gamepad_panel import bridge_for
            self.after(800,lambda:bridge_for(self))
        # Log DiscordRPC initialization status
        if self._discord_rpc_enabled:
            self.log("DiscordRPC initialized (enabled in settings)")
        else:
            self.log("DiscordRPC initialized (disabled in settings)")

    def tr(self, key: str, **kwargs) -> str:
        return self.localization.translate(key, **kwargs)

    def display_value(self, key: str, fallback: str | None = None, **kwargs) -> str:
        text = self.tr(f"display.{key}", **kwargs)
        if text == f"display.{key}" and fallback is not None:
            return fallback.format(**kwargs) if kwargs else fallback
        return text

    def progress_text(self, key: str, **kwargs) -> str:
        return self.tr(f"progress.{key}", **kwargs)

    def status_text(self, key: str, **kwargs) -> str:
        return self.tr(f"status.{key}", **kwargs)

    def _language_combo_values(self) -> list[str]:
        return [f"{code.upper()} - {LANGUAGE_LABELS[code]}" for code in SUPPORTED_LANGUAGES]

    def _language_combo_value(self, language: str | None = None) -> str:
        code = (language or self.localization.language).strip().lower()
        return f"{code.upper()} - {LANGUAGE_LABELS.get(code, LANGUAGE_LABELS['en'])}"

    def _selected_language_code(self) -> str:
        raw = (self.language_var.get() or "").split(" - ", 1)[0].strip().lower()
        return raw if raw in SUPPORTED_LANGUAGES else "en"

    def _on_language_selected(self, _event=None) -> None:
        self._set_language(self._selected_language_code())

    def _set_language(self, language: str) -> None:
        normalized = self.localization.set_language(language)
        if self.settings.language != normalized:
            self.settings.language = normalized
        self.language_var.set(self._language_combo_value(normalized))
        self._apply_main_localization()

    def _apply_main_localization(self) -> None:
        window = self._window()
        try:
            window.title(self.tr("app.title"))
        except Exception:
            pass
        if self.start_overlay_button is not None:
            self.start_overlay_button.configure(text=self.tr("button.start_overlay"))
        if self.locate_fifa_button is not None:
            self.locate_fifa_button.configure(text=self.tr("button.locate_fifa_exe"))
        if self.launch_fifa_button is not None:
            self.launch_fifa_button.configure(text=self.tr("button.launch_fifa"))
        if self.assign_scoreboard_button is not None:
            self.assign_scoreboard_button.configure(text=self.tr("button.assign_scoreboard"))
        if self.assign_movie_button is not None:
            self.assign_movie_button.configure(text=self.tr("button.assign_movie"))
        if self.exclude_competition_button is not None:
            self.exclude_competition_button.configure(text=self.tr("button.exclude_competition"))
        if self.check_update_button is not None:
            self.check_update_button.configure(text=self._check_update_button_text())
        if self.clean_cache_button is not None:
            self.clean_cache_button.configure(text=self.tr("button.clean_cache"))
        if self.imgbb_key_button is not None:
            self.imgbb_key_button.configure(text=self.tr("button.imgbb_key"))
        if self.language_label is not None:
            self.language_label.configure(text=self.tr("label.language"))
        if self.language_combo is not None:
            self.language_combo.configure(values=self._language_combo_values())
        if self.banner_title_label is not None:
            self.banner_title_label.configure(text=self.tr("banner.control_room"))
        if self.help_label is not None:
            self.help_label.configure(text=self.tr("help.overlay_toggle"))
        if self.tabview is not None:
            self.tabview.tab(self.dashboard_tab, text=self.tr("tab.dashboard"))
            self.tabview.tab(self.audio_tab, text=self.tr("tab.chants"))
            self.tabview.tab(self.camera_tab, text=self.tr("tab.camera"))
            self.tabview.tab(self.logs_tab, text=self.tr("tab.logs"))
        if self.logs_group is not None:
            self.logs_group.configure(text=self.tr("logs.group"))
        if self.log_follow_button is not None:
            self.log_follow_button.configure(text=self.tr("button.jump_latest"))
        if getattr(self, "keep_open_switch", None) is not None:
            self.keep_open_switch.configure(text=self.tr("toggle.keep_open"))
        if getattr(self, "random_stadium_switch", None) is not None:
            self.random_stadium_switch.configure(text=self.tr("toggle.random_stadium_selection"))
        if getattr(self, "_regen_bh_btn", None) is not None:
            self._regen_bh_btn.configure(text=self.tr("button.regen_bh"))
        self._update_log_follow_ui()
        self._apply_stat_titles()
        self._apply_module_labels()
        self._apply_camera_localization()
        self._refresh_card_titles()

    def _refresh_card_titles(self) -> None:
        if hasattr(self, "_card_title_bindings"):
            for title_label, title_key, subtitle_label, subtitle_key in self._card_title_bindings:
                if title_label.winfo_exists():
                    title_label.configure(text=self.tr(title_key))
                if subtitle_label is not None and subtitle_label.winfo_exists():
                    subtitle_label.configure(text=self.tr(subtitle_key))

    def _apply_stat_titles(self) -> None:
        title_map = {
            "tour": "stat.tournament",
            "round": "stat.round_id",
            "page": "stat.current_page",
            "derby": "stat.derby_key",
            "match_clock_split": "stat.minute_second",
            "game_state": "stat.game_state",
            "goal_active": "stat.goal_status",
            "last_update": "stat.last_update",
            "tvlogo": "stat.tv_logo",
            "scoreboard": "stat.scoreboard",
            "movie": "stat.movie",
            "status": "stat.status",
            "stadium": "stat.current_stadium",
            "stadid": "stat.stadium_id",
            "audio_module": "stat.chants_module",
            "audio_status": "stat.chants_status",
            "audio_current": "stat.current_chant",
            "audio_clubsong": "stat.club_anthem",
            "audio_chants_dir": "stat.chants_folder",
            "audio_last_action": "stat.last_action",
            "audio_crowd_mode": "stat.crowd_mode",
            "audio_crowd_volume": "stat.crowd_volume",
            "audio_source": "stat.crowd_source",
            "audio_next": "stat.next_behavior",
            "home_goals": "stat.home_goals",
            "away_goals": "stat.away_goals",
        }
        for key, label in self.stat_title_labels.items():
            label.configure(text=self.tr(title_map.get(key, key)))

    def _apply_module_labels(self) -> None:
        module_map = {
            "Stadium": "module.stadium",
            "TvLogo": "module.tvlogo",
            "ScoreBoard": "module.scoreboard",
            "Movies": "module.movies",
            "Autorun": "module.autorun",
            "StadiumNet": "module.stadiumnet",
            "Chants": "module.chants",
            "TeamEntrance": "module.team_entrance",
            "DiscordRPC": "module.discord_rpc",
            "ClothPhysics": "module.cloth_physics",
        }
        for name, check in self.module_checks.items():
            check.configure(text=self.tr(module_map.get(name, name)))
        if hasattr(self,"cloth_physics_note"):
            self.cloth_physics_note.configure(text=self.tr("module.cloth_physics_note"))

    def _apply_camera_localization(self) -> None:
        if self.camera_select_button is not None:
            self.camera_select_button.configure(text=self.tr("button.choose_camera_package"))
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(text=self.tr("button.apply_camera"))
        if self.camera_name_label is not None and self._camera_selected_name is None:
            self.camera_name_label.configure(text=self.tr("camera.no_camera_selected"))
        if self.camera_preview_status is not None and not self._camera_preview_source_key:
            self.camera_preview_status.configure(text=self.tr("camera.no_preview"))
        if self.camera_preview_image_label is not None and not getattr(self.camera_preview_image_label, "image", None):
            self.camera_preview_image_label.configure(text=self.tr("placeholder.preview"))
        if hasattr(self, "settings_ini"):
            self.refresh_camera_catalog()

    def _resolve_base_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

    def _resolve_resource_dir(self) -> Path:
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            return Path(bundle_dir)
        return self.base_dir

    def _resolve_icon_path(self) -> Path | None:
        candidates = [
            self.resource_dir / "server16.ico",
            self.base_dir / "server16.ico",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _apply_window_icon(self, window: tk.Misc) -> None:
        if self.icon_path is None:
            return
        icon_value = str(self.icon_path)
        try:
            window.iconbitmap(icon_value)
            window.iconbitmap(default=icon_value)
        except Exception:
            pass
        try:
            image = Image.open(self.icon_path)
            self._window_icon_image = ImageTk.PhotoImage(image)
            window.iconphoto(True, self._window_icon_image)
        except Exception:
            pass

    def _configure_theme(self) -> None:
        self.bg = "#0b1220"
        self.panel = "#111a2b"
        self.panel_alt = "#172338"
        self.card = "#0f1727"
        self.card_soft = "#152033"
        self.fg = "#e6edf3"
        self.muted = "#93a1b2"
        self.accent = "#4cc2ff"
        self.success = "#7ee787"
        self.error = "#ff7b72"
        self.gold = "#f6c177"
        self.configure(bg=self.bg)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=self.bg, foreground=self.fg, fieldbackground=self.panel_alt)
        style.configure("TFrame", background=self.bg)
        style.configure("TLabelframe", background=self.bg, foreground=self.fg, borderwidth=1)
        style.configure("TLabelframe.Label", background=self.bg, foreground=self.accent)
        style.configure("TLabel", background=self.bg, foreground=self.fg)
        style.configure("TButton", background=self.panel_alt, foreground=self.fg, padding=8, borderwidth=0)
        style.map("TButton", background=[("active", "#2b3442")])
        style.configure("TCheckbutton", background=self.bg, foreground=self.fg)
        style.configure(
            "Server16.TEntry",
            fieldbackground=self.panel_alt,
            foreground=self.fg,
            insertcolor=self.fg,
            bordercolor="#2a3c59",
            lightcolor=self.panel_alt,
            darkcolor=self.panel_alt,
            padding=4,
        )
        style.map(
            "Server16.TEntry",
            fieldbackground=[("disabled", self.card_soft), ("readonly", self.card_soft)],
            foreground=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Switch.TCheckbutton",
            background=self.card,
            foreground=self.fg,
            padding=(12, 6),
            indicatoron=False,
            relief="flat",
            borderwidth=1,
            focuscolor=self.card,
        )
        style.map(
            "Switch.TCheckbutton",
            background=[("selected", "#19324d"), ("active", "#223753"), ("!selected", self.card_soft)],
            foreground=[("selected", self.accent), ("!selected", self.fg)],
            bordercolor=[("selected", self.accent), ("!selected", "#2a3c59")],
        )
        style.configure(
            "Server16.TNotebook",
            background=self.bg,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "Server16.TNotebook.Tab",
            background=self.panel,
            foreground=self.muted,
            padding=(16, 8),
            borderwidth=0,
            lightcolor=self.panel,
            darkcolor=self.panel,
        )
        style.map(
            "Server16.TNotebook.Tab",
            background=[("selected", self.card_soft), ("active", self.panel_alt)],
            foreground=[("selected", self.fg), ("active", self.fg)],
        )
        style.configure(
            "Server16.Vertical.TScrollbar",
            background=self.panel_alt,
            troughcolor=self.card_soft,
            bordercolor="#243654",
            arrowcolor=self.fg,
            darkcolor=self.panel_alt,
            lightcolor=self.panel_alt,
            arrowsize=14,
        )
        style.map(
            "Server16.Vertical.TScrollbar",
            background=[("active", "#223753"), ("pressed", "#1b3453")],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Server16.Horizontal.TScrollbar",
            background=self.panel_alt,
            troughcolor=self.card_soft,
            bordercolor="#243654",
            arrowcolor=self.fg,
            darkcolor=self.panel_alt,
            lightcolor=self.panel_alt,
            arrowsize=14,
        )
        style.map(
            "Server16.Horizontal.TScrollbar",
            background=[("active", "#223753"), ("pressed", "#1b3453")],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        style.configure(
            "Server16.TCombobox",
            fieldbackground=self.panel_alt,
            background=self.panel_alt,
            foreground=self.fg,
            arrowcolor=self.fg,
            bordercolor="#2a3c59",
            lightcolor=self.panel_alt,
            darkcolor=self.panel_alt,
            insertcolor=self.fg,
            selectbackground="#1b3453",
            selectforeground=self.fg,
            padding=2,
        )
        style.map(
            "Server16.TCombobox",
            fieldbackground=[("readonly", self.panel_alt), ("disabled", self.card_soft)],
            background=[("readonly", self.panel_alt), ("active", self.panel_alt)],
            foreground=[("readonly", self.fg), ("disabled", self.muted), ("!disabled", self.fg)],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
            selectbackground=[("readonly", "#1b3453")],
            selectforeground=[("readonly", self.fg)],
        )
        style.configure("TCombobox", fieldbackground=self.panel_alt, background=self.panel_alt, foreground=self.fg, arrowcolor=self.fg)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.panel_alt), ("disabled", self.card_soft)],
            foreground=[("readonly", self.fg), ("disabled", self.muted), ("!disabled", self.fg)],
            arrowcolor=[("disabled", self.muted), ("!disabled", self.fg)],
        )
        self.option_add("*TCombobox*Listbox.background", self.panel_alt)
        self.option_add("*TCombobox*Listbox.foreground", self.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", "#1b3453")
        self.option_add("*TCombobox*Listbox.selectForeground", self.fg)
        self.option_add("*TCombobox*Listbox.font", "Consolas 10")
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=self.card_soft, background=self.accent, borderwidth=0, lightcolor=self.accent, darkcolor=self.accent)

    def _install_exception_hook(self) -> None:
        def report(exc_type, exc_value, exc_tb):
            self.log("Unhandled exception", exc_value, exc_info=(exc_type, exc_value, exc_tb))

        self.report_callback_exception = report

    def _build_runtime_log_header(self) -> str:
        mapped_executable = self.settings.fifa_exe or "default"
        settings_path = self.settings.path
        return "\n".join(
            (
                f"Mapped executable: {mapped_executable}",
                f"Settings file: {settings_path}",
            )
        ) + "\n"

    def _prepare_runtime_log(self) -> None:
        header = self._build_runtime_log_header()
        try:
            if self.log_path.exists():
                previous_content = self.log_path.read_text(encoding="utf-8", errors="replace")
                if previous_content and previous_content != header:
                    self.log_backup_path.write_text(previous_content, encoding="utf-8")
            self.log_path.write_text(header, encoding="utf-8")
        except Exception:
            pass

    def log(self, message: str, error: Exception | None = None, exc_info=None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        if error is not None:
            line = f"{line}: {error}"
        if exc_info is not None:
            line = f"{line}\n{''.join(traceback.format_exception(*exc_info)).strip()}"
        elif error is not None:
            line = f"{line}\n{traceback.format_exc().strip()}" if traceback.format_exc().strip() != "NoneType: None" else line
        try:
            with self._log_lock:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception:
            pass
        self._post_ui(self._append_log_line,line)

    def _append_log_line(self,line) -> None:
        if self.log_widget is not None:
            if self._log_widget_is_near_bottom():
                self._log_autofollow = True
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", line + "\n")
            if self._log_autofollow:
                self.log_widget.see("end")
            self.log_widget.configure(state="disabled")
            self._update_log_follow_ui()

    def _post_ui(self,callback,*args) -> None:
        if getattr(self,'_closing',False):
            return
        if threading.get_ident()==self._ui_thread:
            callback(*args)
        else:
            self._ui_events.put((callback,args))

    def _drain_ui_events(self) -> None:
        self._ui_event_job=None
        if self._closing:
            return
        for _ in range(100):
            try:
                callback,args=self._ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception as exc:
                self.log('Queued UI callback failed',exc)
        self._ui_event_job=self.after(50,self._drain_ui_events)

    def _log_widget_is_near_bottom(self) -> bool:
        if self.log_widget is None:
            return True
        _first, last = self.log_widget.yview()
        return last >= 0.995

    def _refresh_log_autofollow_state(self, _event=None) -> None:
        self._log_autofollow = self._log_widget_is_near_bottom()
        self._update_log_follow_ui()

    def _jump_logs_to_latest(self) -> None:
        if self.log_widget is None:
            return
        self._log_autofollow = True
        self.log_widget.see("end")
        self._update_log_follow_ui()

    def _update_log_follow_ui(self) -> None:
        if self.log_status_label is not None:
            if self._log_autofollow:
                self.log_status_label.configure(text=self.tr("logs.following"), fg=self.success)
            else:
                self.log_status_label.configure(text=self.tr("logs.browsing"), fg=self.gold)
        if self.log_follow_button is not None:
            self.log_follow_button.configure(state="disabled" if self._log_autofollow else "normal")

    def _window(self) -> tk.Misc:
        return self.ui_root or self

    def _build_ui(self) -> None:
        root = tk.Toplevel(self)
        root.title(self.tr("app.title"))
        root.geometry("1024x680")
        root.minsize(980, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.configure(bg=self.bg)
        self._apply_window_icon(root)
        self.ui_root = root

        top = tk.Frame(root, bg=self.bg, padx=10, pady=10)
        top.pack(fill="x")
        self.start_overlay_button = ttk.Button(top, text=self.tr("button.start_overlay"), command=self.start_overlay_session)
        self.start_overlay_button.pack(side="left")
        self.locate_fifa_button = ttk.Button(top, text=self.tr("button.locate_fifa_exe"), command=self.select_fifa_exe)
        self.locate_fifa_button.pack(side="left", padx=6)
        self.launch_fifa_button = ttk.Button(top, text=self.tr("button.launch_fifa"), command=self.launch_fifa)
        self.launch_fifa_button.pack(side="left", padx=6)
        self.assign_scoreboard_button = ttk.Button(top, text=self.tr("button.assign_scoreboard"), command=self.assign_scoreboard)
        self.assign_scoreboard_button.pack(side="left", padx=6)
        self.assign_movie_button = ttk.Button(top, text=self.tr("button.assign_movie"), command=self.assign_movie)
        self.assign_movie_button.pack(side="left", padx=6)
        self.exclude_competition_button = ttk.Button(top, text=self.tr("button.exclude_competition"), command=self.exclude_competition)
        self.exclude_competition_button.pack(side="left", padx=6)
        language_host = tk.Frame(top, bg=self.bg)
        language_host.pack(side="right", padx=(10, 6))
        self.language_label = tk.Label(language_host, text=self.tr("label.language"), bg=self.bg, fg=self.muted, font=("Bahnschrift", 9, "bold"))
        self.language_label.pack(side="left", padx=(0, 6))
        self.language_combo = ttk.Combobox(
            language_host,
            state="readonly",
            textvariable=self.language_var,
            values=self._language_combo_values(),
            width=16,
            style="Server16.TCombobox",
        )
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)
        self.language_var.set(self._language_combo_value())
        self.check_update_button = ttk.Button(top, text=self.tr("button.check_update"), command=self.check_updates)
        self.check_update_button.pack(side="right", padx=(0, 6))
        self.check_update_badge = tk.Label(
            top,
            text="NEW",
            bg="#c94f58",
            fg="#ffffff",
            font=("Bahnschrift", 8, "bold"),
            padx=5,
            pady=2,
        )
        self.check_update_badge.pack(side="right", padx=(0, 6))
        self.check_update_badge.pack_forget()

        header = tk.Frame(root, bg=self.bg, padx=10)
        header.pack(fill="x")
        banner = tk.Frame(header, bg=self.panel, bd=0, highlightthickness=1, highlightbackground="#22314b")
        banner.pack(fill="x")
        self.banner_title_label = tk.Label(
            banner,
            text=self.tr("banner.control_room"),
            bg=self.panel,
            fg=self.gold,
            font=("Bahnschrift", 11, "bold"),
            padx=14,
            pady=8,
        )
        self.banner_title_label.pack(side="left")
        self.page_banner = tk.Label(
            banner,
            text="-",
            bg=self.panel,
            fg=self.fg,
            font=("Consolas", 10),
            padx=10,
            pady=8,
        )
        self.page_banner.pack(side="left")
        self.status_pill = tk.Label(
            banner,
            text=self.status_text("waiting_fifa"),
            bg="#1a2740",
            fg=self.accent,
            font=("Bahnschrift", 9, "bold"),
            padx=10,
            pady=5,
        )
        self.status_pill.pack(side="right", padx=10, pady=6)
        help_bar = tk.Frame(header, bg=self.bg)
        help_bar.pack(fill="x", pady=(8, 0))
        self.help_label = tk.Label(
            help_bar,
            text=self.tr("help.overlay_toggle"),
            bg=self.bg,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self.help_label.pack(side="left")

        self.tabview = ttk.Notebook(root, style="Server16.TNotebook")
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_tab = tk.Frame(self.tabview, bg=self.bg)
        self.logs_tab = tk.Frame(self.tabview, bg=self.bg)
        self.audio_tab = tk.Frame(self.tabview, bg=self.bg)
        self.camera_tab = tk.Frame(self.tabview, bg=self.bg)
        self.gamepad_tab = tk.Frame(self.tabview, bg=self.bg)
        self.tabview.add(self.dashboard_tab, text=self.tr("tab.dashboard"))
        self.tabview.add(self.audio_tab, text=self.tr("tab.chants"))
        self.tabview.add(self.camera_tab, text=self.tr("tab.camera"))
        self.tabview.add(self.gamepad_tab, text="Controles")
        self.tabview.add(self.logs_tab, text=self.tr("tab.logs"))
        from .gamepad_panel import build_desktop_tab
        build_desktop_tab(self,self.gamepad_tab)

        dashboard_host = tk.Frame(self.dashboard_tab, bg=self.bg)
        dashboard_host.pack(fill="both", expand=True, padx=10, pady=10)
        self.dashboard_canvas = tk.Canvas(dashboard_host, bg=self.bg, highlightthickness=0, bd=0)
        self.dashboard_scrollbar = ttk.Scrollbar(
            dashboard_host,
            orient="vertical",
            command=self.dashboard_canvas.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.dashboard_canvas.configure(yscrollcommand=self.dashboard_scrollbar.set)
        self.dashboard_scrollbar.pack(side="right", fill="y")
        self.dashboard_canvas.pack(side="left", fill="both", expand=True)
        dashboard = tk.Frame(self.dashboard_canvas, bg=self.bg, padx=10, pady=10)
        self.dashboard_content = dashboard
        self.dashboard_window_id = self.dashboard_canvas.create_window((0, 0), window=dashboard, anchor="nw")
        dashboard.bind("<Configure>", self._on_dashboard_configure)
        self.dashboard_canvas.bind("<Configure>", self._on_dashboard_canvas_configure)
        self.dashboard_canvas.bind_all("<MouseWheel>", self._on_dashboard_mousewheel)
        dashboard.grid_columnconfigure(0, weight=3)
        dashboard.grid_columnconfigure(1, weight=2)
        dashboard.grid_rowconfigure(0, weight=1)

        left = tk.Frame(dashboard, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(0, weight=1)

        self._build_matchup_card(left, 0)
        self._build_match_card(left, 1)
        self._build_assets_card(left, 2)

        right = tk.Frame(dashboard, bg=self.bg)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        self._build_stadium_card(right, 0)
        self._build_modules_card(right, 1)
        self._build_maintenance_card(right, 2)
        self._build_audio_card()
        self._build_camera_tab()
        self._build_logs_card()
        self._apply_main_localization()

    def _build_maintenance_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.maintenance.title", "card.maintenance.subtitle")
        card.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        buttons = tk.Frame(card, bg=self.card)
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        self.clean_cache_button = ttk.Button(
            buttons,
            text=self.tr("button.clean_cache"),
            command=self._clean_generated_cache,
        )
        self.clean_cache_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.imgbb_key_button = ttk.Button(
            buttons,
            text=self.tr("button.imgbb_key"),
            command=self._change_imgbb_api_key,
        )
        self.imgbb_key_button.pack(side="left", fill="x", expand=True)

    def _build_stadium_loading_modal(self) -> None:
        loading_bg,loading_ink,loading_muted,loading_blue='#ffffff','#344651','#8797ab','#0968f8'
        modal = tk.Toplevel(self._window())
        modal.withdraw()
        modal.overrideredirect(True)
        modal.attributes("-topmost", True)
        modal.configure(bg=loading_bg)
        self._apply_window_icon(modal)
        modal_frame = tk.Frame(modal, bg=loading_bg, highlightthickness=1, highlightbackground="#dfe6ef", padx=14, pady=12)
        modal_frame.pack(fill="both", expand=True)
        self.stadium_loading_modal = modal
        self.stadium_loading_title = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.title"),
            bg=loading_bg,
            fg=loading_blue,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        self.stadium_loading_title.pack(fill="x")
        self.stadium_loading_preview = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.preview"),
            bg='#f0f4f8',
            fg=loading_muted,
            font=("Segoe UI", 11, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#dfe6ef",
        )
        self.stadium_loading_preview.pack(fill="x", pady=(8, 8), ipady=24)
        self.stadium_loading_name = tk.Label(
            modal_frame,
            text="-",
            bg=loading_bg,
            fg=loading_ink,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        self.stadium_loading_name.pack(fill="x", pady=(6, 4))
        self.stadium_loading_detail = tk.Label(
            modal_frame,
            text=self.tr("stadium_modal.preparing"),
            bg=loading_bg,
            fg=loading_muted,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
        )
        self.stadium_loading_detail.pack(fill="x", pady=(0, 8))
        self.stadium_loading_value = tk.DoubleVar(value=0)
        ttk.Style(self).configure('StadiumLoading.Horizontal.TProgressbar',background=loading_blue,troughcolor='#edf2f7',bordercolor=loading_bg,lightcolor=loading_blue,darkcolor=loading_blue)
        self.stadium_loading_bar = ttk.Progressbar(
            modal_frame,
            maximum=100,
            variable=self.stadium_loading_value,
            style="StadiumLoading.Horizontal.TProgressbar",
            mode="determinate",
            length=292,
        )
        self.stadium_loading_bar.pack(fill="x", pady=(2, 0))
        modal.geometry("340x274")

    def _withdraw_stadium_loading_fallback(self) -> None:
        # A Tk window shown before injection must never survive the switch to D3D.
        if self._stadium_loading_hwnd:
            try:
                self.user32.ShowWindow(self._stadium_loading_hwnd, SW_HIDE)
            except Exception:
                pass
        if self.stadium_loading_modal is not None:
            self.stadium_loading_bar.stop()
            self.stadium_loading_modal.withdraw()

    def _show_stadium_loading_modal(self, stadium_name: str, detail: str = "Preparing stadium assets", progress: float = 0.0, title: str | None = None, use_d3d: bool = True) -> None:
        self._withdraw_stadium_loading_fallback()
        if not self.show_stadium_loading_var.get():
            return
        self._cancel_stadium_loading_hide()
        if use_d3d and self._try_d3d_overlay_show(stadium_name, detail, progress, narration=title=='Narração aplicada'):
            return
        # Keep the main Server16 status available while the game renderer starts.
        # Only the native overlay may display loading notices over the FIFA window.
        self.log(f"Stadium loading notification awaiting native overlay: {stadium_name}")

    def show_narration_applied(self, name: str) -> None:
        if not features.NARRATION_PICKER_AVAILABLE:return
        self.log(f'Narration applied: {name}; selection modal closed')
        self.show_narration_loading(name,100,'Narração aplicada')
        self._hide_asset_loading('narration',delay_ms=3500)

    def show_narration_loading(self,name: str,progress: float=5,detail: str='Carregando narração…') -> None:
        if not features.NARRATION_PICKER_AVAILABLE:return
        self._ensure_d3d_overlay_injected()
        image_path=''
        try:
            from .narrator_portrait import cached_portrait
            runtime=getattr(self,'_narration_runtime',None)
            profile=next((p for p in runtime.profiles() if p['name']==name),None) if runtime else None
            if profile and profile.get('portrait'):
                image_path=str(cached_portrait(profile['portrait'],name,Path(self.exedir)/'runtime/narration_portraits'))
        except (OSError,ValueError) as exc:self.log('Narrator portrait unavailable: '+str(exc))
        self._show_asset_loading('narration','Narração aplicada' if progress>=100 else 'Carregando narração',name,detail,progress,image_path=image_path)

    def _try_d3d_overlay_show(self, stadium_name: str, detail: str, progress: float, narration: bool = False) -> bool:
        """Inject the D3D overlay DLL and show the notification.

        Returns True if the overlay was shown via D3D injection, False if we
        should fall back to the Tkinter modal.
        """
        if not self._ensure_d3d_overlay_injected():
            return False
        inj = self._d3d_injector
        if inj is None:
            return False
        self._withdraw_stadium_loading_fallback()
        inj.show(('[Narração aplicada] '+stadium_name) if narration else stadium_name, detail or self.tr("stadium_modal.preparing"), progress,
                 image_path=str(self._resolve_stadium_preview_path(stadium_name) or ""))
        self._d3d_overlay_shown_at = time.monotonic()
        self._stadium_loading_visible = True
        self.log(f"Stadium notification via D3D overlay: {stadium_name}")
        return True

    def _ensure_d3d_overlay_injected(self) -> bool:
        """Connect to the overlay plugin loaded by the game-owned mod host."""
        if _D3DOverlayInjector is None:
            self.log("D3D overlay: injector module not available (import failed)")
            return False
        dll_path = self.resource_dir / "bin" / "cgfs16_overlay.dll"
        if not dll_path.exists():
            self.log(f"D3D overlay: DLL not found at {dll_path}")
            return False
        if self._d3d_injector is None:
            try:
                self._d3d_injector = _D3DOverlayInjector(dll_path)
            except Exception as exc:
                self.log(f"D3D overlay injector init failed: {exc}")
                self._d3d_injector = None
                return False
        injector = self._d3d_injector
        if not injector.is_ready():
            self.log(
                "D3D overlay: shared channel or installed plugin build is unavailable"
            )
            return False
        pid = self._resolve_fifa_pid()
        if not pid:
            return False
        if not injector.is_injected(pid):
            if not injector.inject(pid):
                self.log("D3D overlay: native plugin unavailable; restart FIFA after installing the mod")
                return False
            self.log(f"D3D stadium overlay connected to FIFA pid {pid}")
        return True

    def _cancel_stadium_loading_hide(self) -> None:
        if self._stadium_loading_hide_job is not None:
            try:
                self.after_cancel(self._stadium_loading_hide_job)
            except Exception:
                pass
            self._stadium_loading_hide_job = None
        if self._d3d_overlay_hide_job is not None:
            try:
                self.after_cancel(self._d3d_overlay_hide_job)
            except Exception:
                pass
            self._d3d_overlay_hide_job = None

    def _hide_stadium_loading_modal(self, delay_ms: int = 0) -> None:
        if delay_ms > 0:
            self._cancel_stadium_loading_hide()
            self._stadium_loading_hide_job = self.after(delay_ms, self._hide_stadium_loading_modal)
            return
        self._withdraw_stadium_loading_fallback()
        if self._stadium_loading_hide_job is not None:
            try:
                self.after_cancel(self._stadium_loading_hide_job)
            except Exception:
                pass
        self._stadium_loading_hide_job = None
        # ── D3D injection overlay ─────────────────────────────────────────────
        if self._d3d_injector is not None and self._d3d_injector.is_injected():
            # Cancel any previously scheduled deferred hide
            if self._d3d_overlay_hide_job is not None:
                try:
                    self.after_cancel(self._d3d_overlay_hide_job)
                except Exception:
                    pass
                self._d3d_overlay_hide_job = None
            # Enforce minimum visible time (2.5 s) so at least ~150 frames are drawn
            _MIN_VISIBLE_MS = 2500
            elapsed_ms = int((time.monotonic() - self._d3d_overlay_shown_at) * 1000)
            remaining_ms = max(0, _MIN_VISIBLE_MS - elapsed_ms)
            if remaining_ms > 0:
                self._d3d_overlay_hide_job = self.after(
                    remaining_ms, self._do_hide_d3d_overlay
                )
            else:
                self._do_hide_d3d_overlay()
            return
        # ── Tkinter modal fallback ────────────────────────────────────────────
        if self._stadium_loading_hwnd:
            try:
                self.user32.ShowWindow(self._stadium_loading_hwnd, SW_HIDE)
            except Exception:
                pass
        if self.stadium_loading_modal is not None:
            self.stadium_loading_bar.stop()
            self.stadium_loading_modal.withdraw()
        was_visible = self._stadium_loading_visible
        self._stadium_loading_visible = False
        should_restore = self._stadium_loading_restore_fullscreen
        self._stadium_loading_restore_fullscreen = False
        if was_visible and should_restore:
            self.after(140, self._restore_fifa_fullscreen)

    def _do_hide_d3d_overlay(self) -> None:
        self._d3d_overlay_hide_job = None
        if self._d3d_injector is not None:
            self._d3d_injector.hide()
        self._stadium_loading_visible = False
        self.log("Stadium notification hidden via D3D overlay")

    def _update_stadium_loading_modal(self, value: float, detail: str) -> None:
        if not self.show_stadium_loading_var.get():
            return
        # ── D3D injection overlay ─────────────────────────────────────────────
        if self._d3d_injector is not None and self._d3d_injector.is_injected():
            self._d3d_injector.update(value, detail)
            return
        # ── Tkinter modal fallback ────────────────────────────────────────────
        if self.stadium_loading_modal is None:
            return
        if self.stadium_loading_value is not None:
            self.stadium_loading_value.set(max(0, min(100, value)))
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail or self.tr("stadium_modal.preparing"))
        if self.stadium_loading_detail is not None:
            self.stadium_loading_detail.configure(text=detail)
        if self._stadium_loading_visible:
            self._position_stadium_loading_modal()
            self.stadium_loading_modal.update_idletasks()

    def _show_asset_loading(self, kind: str, title: str, name: str, detail: str, progress: float, image_path: str = '') -> None:
        if kind == 'narration' and not features.NARRATION_PICKER_AVAILABLE:return
        if kind != 'narration' and not self.show_stadium_loading_var.get():
            return
        previous = self._asset_loading_hide_jobs.pop(kind, None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except Exception:
                pass
        self._asset_loading_started_at[kind] = time.monotonic()
        self._withdraw_stadium_loading_fallback()
        self._asset_loading_fallback.discard(kind)
        if self._ensure_d3d_overlay_injected():
            self._d3d_injector.show_asset(kind, name, detail, progress, image_path=image_path)
        else:
            self.log(f"{kind} loading notification awaiting native overlay: {name}")

    def _update_asset_loading(self, kind: str, progress: float, detail: str) -> None:
        if kind in self._asset_loading_fallback:
            self._update_stadium_loading_modal(progress, detail)
        elif self._d3d_injector is not None and self._d3d_injector.is_injected():
            self._d3d_injector.update_asset(kind, progress, detail)

    def _hide_asset_loading(self, kind: str, delay_ms: int = 0) -> None:
        if kind not in self._asset_loading_started_at and kind not in self._asset_loading_fallback:
            return
        previous = self._asset_loading_hide_jobs.pop(kind, None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except Exception:
                pass
        elapsed_ms = int((time.monotonic() - self._asset_loading_started_at.get(kind, time.monotonic())) * 1000)
        wait_ms = max(delay_ms, 1200 - elapsed_ms)
        if wait_ms > 0:
            self._asset_loading_hide_jobs[kind] = self.after(wait_ms, self._finish_asset_loading, kind)
            return
        self._finish_asset_loading(kind)

    def _finish_asset_loading(self, kind: str) -> None:
        self._asset_loading_hide_jobs.pop(kind, None)
        self._asset_loading_started_at.pop(kind, None)
        if kind=='narration' and getattr(self,'_narration_notice',None) is not None:self._narration_notice.withdraw()
        if kind in self._asset_loading_fallback:
            self._asset_loading_fallback.discard(kind)
            if not self._stadium_task_running and not self._asset_loading_fallback:
                self._hide_stadium_loading_modal()
        elif self._d3d_injector is not None:
            self._d3d_injector.hide_asset(kind)

    def _position_stadium_loading_modal(self) -> None:
        if self.stadium_loading_modal is None:
            return
        # Always position over FIFA window if it exists, regardless of overlay state
        fifa_hwnd = self._find_fifa_window_handle() if not self._fifa_hwnd else self._fifa_hwnd
        if fifa_hwnd:
            rect = RECT()
            if self.user32.GetWindowRect(fifa_hwnd, ctypes.byref(rect)):
                fifa_width = rect.right - rect.left
                fifa_height = rect.bottom - rect.top
                # Center horizontally, position near top of FIFA window
                modal_w, modal_h = min(340,max(1,fifa_width-32)), min(274,max(1,fifa_height-80))
                x = rect.left + (fifa_width - modal_w) // 2
                y = rect.top + 40
                self.stadium_loading_modal.geometry(f"{modal_w}x{modal_h}+{x}+{y}")
                return
        window = self._window()
        window.update_idletasks()
        root_x = window.winfo_rootx()
        root_y = window.winfo_rooty()
        self.stadium_loading_modal.geometry(f"340x274+{root_x + 24}+{root_y + 24}")

    def _card(self, parent: tk.Misc, title_key: str, subtitle_key: str = "") -> tk.Frame:
        card = tk.Frame(parent, bg=self.card, bd=0, highlightthickness=1, highlightbackground="#243654")
        header = tk.Frame(card, bg=self.card)
        header.pack(fill="x", padx=12, pady=(10, 4))
        title_label = tk.Label(header, text=self.tr(title_key), bg=self.card, fg=self.fg, font=("Bahnschrift", 13, "bold"))
        title_label.pack(anchor="w")
        subtitle_label = None
        if subtitle_key:
            subtitle_label = tk.Label(header, text=self.tr(subtitle_key), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
            subtitle_label.pack(anchor="w", pady=(1, 0))
        if not hasattr(self, "_card_title_bindings"):
            self._card_title_bindings = []
        self._card_title_bindings.append((title_label, title_key, subtitle_label, subtitle_key))
        return card

    def _register_info_label(self, key: str, widget: tk.Widget) -> None:
        self.info_labels.setdefault(key, []).append(widget)

    def _set_display(self, key: str, text: str) -> None:
        primary = self.labels.get(key)
        if primary is not None:
            primary.configure(text=text)
        for widget in self.info_labels.get(key, []):
            widget.configure(text=text)
        if key == "stadium":
            self._update_stadium_preview(text)

    def _set_display_async(self, key: str, text: str) -> None:
        self._post_ui(self._set_display,key,text)

    def _on_dashboard_configure(self, _event=None) -> None:
        if self.dashboard_canvas is not None and self.dashboard_content is not None:
            self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))

    def _on_dashboard_canvas_configure(self, event) -> None:
        if self.dashboard_canvas is not None and self.dashboard_window_id is not None:
            self.dashboard_canvas.itemconfigure(self.dashboard_window_id, width=event.width)

    def _on_dashboard_mousewheel(self, event) -> None:
        if self.tabview is None or self.dashboard_canvas is None:
            return
        current = self.tabview.nametowidget(self.tabview.select())
        if current is not self.dashboard_tab:
            return
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = self.nametowidget(widget)
            except Exception:
                widget = None
        if widget is None:
            return
        try:
            if widget.winfo_toplevel() is not self._window():
                return
        except Exception:
            return
        cursor = widget
        belongs_to_dashboard = False
        while cursor is not None:
            if cursor is self.dashboard_canvas or cursor is self.dashboard_content:
                belongs_to_dashboard = True
                break
            try:
                parent_name = cursor.winfo_parent()
            except Exception:
                break
            if not parent_name:
                break
            try:
                cursor = cursor._nametowidget(parent_name)
            except Exception:
                break
        if not belongs_to_dashboard:
            return
        self.dashboard_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_placeholder(self, parent: tk.Misc, width: int, height: int, text: str, bg: str | None = None) -> tk.Canvas:
        bg_color = bg or self.card_soft
        canvas = tk.Canvas(parent, width=width, height=height, bg=bg_color, highlightthickness=0)
        canvas.create_rectangle(8, 8, width - 8, height - 8, outline="#314666", width=2)
        canvas.create_text(width / 2, height / 2, text=text, fill=self.muted, font=("Bahnschrift", 12, "bold"))
        return canvas

    def _resolve_stadium_preview_path(self, stadium_name: str) -> Path | None:
        stadium_name = (stadium_name or "").strip()
        if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
            return None
        candidate_roots: list[Path] = []
        targetpath = getattr(self, "targetpath", None)
        if targetpath is not None:
            candidate_roots.append(Path(targetpath))
        exedir = getattr(self, "exedir", None)
        if exedir is not None:
            candidate_roots.append(Path(exedir) / "StadiumGBD")
        seen: set[Path] = set()
        for root in candidate_roots:
            try:
                root = root.resolve()
            except Exception:
                root = Path(root)
            if root in seen:
                continue
            seen.add(root)
            candidate = resolve_stadium_preview_path(root, stadium_name)
            if candidate is not None:
                return candidate
        return None

    def _load_preview_photo(self, image_path: Path | None, max_size: tuple[int, int]) -> ImageTk.PhotoImage | None:
        if image_path is None or not image_path.exists():
            return None
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(max_size)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _update_stadium_preview(self, stadium_name: str) -> None:
        label = self._stadium_preview_label
        if label is None:
            return
        self._stadium_preview_image = None
        image_path = self._resolve_stadium_preview_path(stadium_name)
        photo = self._load_preview_photo(image_path, (340, 190))
        if photo is None:
            self._stadium_preview_last_value = stadium_name
            label.configure(image="", text=self.tr("placeholder.stadium_preview"), compound="center")
            return
        self._stadium_preview_image = photo
        label.configure(image=photo, text="", compound="center")

    def _update_stadium_loading_preview(self, stadium_name: str) -> None:
        label = self.stadium_loading_preview
        if label is None:
            return
        self._stadium_loading_image = None
        image_path = self._resolve_stadium_preview_path(stadium_name)
        # Reserve room for title/details/progress at the current Windows DPI.
        # Placeholder padding is not part of an actual image's height.
        label.pack_configure(ipady=0)
        self.stadium_loading_modal.update_idletasks()
        window_height = self.stadium_loading_modal.winfo_height()
        window_height = window_height if window_height > 1 else 274
        reserved = label.master.winfo_reqheight() - label.winfo_reqheight()
        preview_height = min(138, max(32, window_height - reserved - 6))
        photo = self._load_preview_photo(image_path, (300, preview_height))
        if photo is None:
            label.pack_configure(ipady=24)
            label.configure(image="", text="STADIUM\nPREVIEW", compound="center")
            return
        self._stadium_loading_image = photo
        # The image already supplies its height; extra placeholder padding would
        # push the progress bar below the fallback window.
        label.pack_configure(ipady=0)
        label.configure(image=photo, text="", compound="center")

    def prepare_floating_window(self) -> tk.Misc:
        window = self._window()
        if self._overlay_visible:
            self._hide_overlay()
        try:
            window.overrideredirect(False)
        except Exception:
            pass
        try:
            window.attributes("-topmost", False)
        except Exception:
            pass
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except Exception:
            pass
        self._launcher_mode = True
        return window

    def configure_secondary_window(self, window: tk.Toplevel) -> None:
        self._apply_window_icon(window)
        try:
            window.overrideredirect(False)
        except Exception:
            pass
        try:
            window.attributes("-topmost", False)
        except Exception:
            pass
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except Exception:
            pass

    def _build_logo_placeholder_image(self, width: int = 116, height: int = 72) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (width, height), self.card_soft)
        return ImageTk.PhotoImage(image)

    def _resolve_team_logo_path(self, team_id: str) -> Path | None:
        team_id = (team_id or "").strip()
        if not team_id or team_id == "-":
            return None
        crest_dir = self.exedir / "data" / "ui" / "imgAssets" / "crest50x50" / "light"
        candidates = [
            crest_dir / f"l{team_id}.dds",
            crest_dir / f"L{team_id}.dds",
            crest_dir / f"l{int(team_id)}.dds" if team_id.isdigit() else None,
        ]
        for candidate in candidates:
            if candidate is not None and candidate.exists():
                return candidate
        return None

    def _update_team_logo(self, prefix: str, team_id: str) -> None:
        label = self._team_logo_labels.get(prefix)
        if label is None:
            return
        image_ref: ImageTk.PhotoImage | None = None
        logo_path = self._resolve_team_logo_path(team_id)
        if logo_path is not None:
            try:
                image = Image.open(logo_path).convert("RGBA")
                image.thumbnail((116, 72))
                image_ref = ImageTk.PhotoImage(image)
            except Exception as exc:
                self.log(f"Failed to load team crest {logo_path}", exc, exc_info=sys.exc_info())
        if image_ref is None:
            image_ref = self._build_logo_placeholder_image()
            label.configure(text=self.tr("placeholder.logo"), compound="center")
        else:
            label.configure(text="", compound="center")
        label.configure(image=image_ref)
        self._team_logo_images[prefix] = image_ref

    def _build_matchup_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.matchup.title", "card.matchup.subtitle")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=230)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=2)

        self._build_team_panel(body, 0, self.tr("team.a"), "home")
        center = tk.Frame(body, bg=self.card)
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        tk.Label(center, text=self.tr("match.score"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        score_label = tk.Label(center, text="0 x 0", bg=self.card, fg=self.gold, font=("Bahnschrift", 28, "bold"))
        score_label.pack()
        tk.Label(center, text=self.tr("match.time"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9)).pack(pady=(18, 2))
        timer_label = tk.Label(center, text="00:00", bg=self.card, fg=self.accent, font=("Consolas", 18, "bold"))
        timer_label.pack()
        self._register_info_label("score", score_label)
        self._register_info_label("timer", timer_label)
        self._build_team_panel(body, 2, self.tr("team.b"), "away")

    def _build_team_panel(self, parent: tk.Misc, column: int, title: str, prefix: str) -> None:
        panel = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        panel.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))
        logo = tk.Label(
            panel,
            width=116,
            height=72,
            bg=self.card_soft,
            fg=self.muted,
            text=self.tr("placeholder.logo"),
            font=("Bahnschrift", 12, "bold"),
            compound="center",
        )
        logo.pack(padx=10, pady=(12, 8))
        self._team_logo_labels[prefix] = logo
        self._update_team_logo(prefix, "")
        strips = tk.Frame(panel, bg=self.card_soft)
        strips.pack(padx=10, pady=(0, 8))
        for _ in range(8):
            tk.Frame(strips, bg="#243654", width=7, height=7).pack(side="left", padx=2)
        name_key = f"{prefix}_name"
        id_key = "hid" if prefix == "home" else "aid"
        tk.Label(panel, text=self.tr("team.name"), bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10)
        name_label = tk.Label(panel, text=title, bg=self.card_soft, fg=self.fg, font=("Bahnschrift", 14, "bold"))
        name_label.pack(anchor="w", padx=10)
        tk.Label(panel, text=self.tr("team.id"), bg=self.card_soft, fg=self.muted, font=("Bahnschrift", 9)).pack(anchor="w", padx=10, pady=(8, 0))
        id_label = tk.Label(panel, text="-", bg=self.card_soft, fg=self.accent, font=("Consolas", 14, "bold"))
        id_label.pack(anchor="w", padx=10, pady=(0, 10))
        self._register_info_label(name_key, name_label)
        self._register_info_label(id_key, id_label)
        self._set_display(name_key, title)

    def _build_match_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.match.title", "card.match.subtitle")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.configure(height=178)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.tournament", "tour", "-")
        self._build_stat(body, 0, 1, "stat.round_id", "round", "-")
        self._build_stat(body, 1, 0, "stat.current_page", "page", "-")
        self._build_stat(body, 1, 1, "stat.derby_key", "derby", "-")
        self._build_stat(body, 2, 0, "stat.minute_second", "match_clock_split", "00 / 00")
        self._build_stat(body, 2, 1, "stat.game_state", "game_state", self.display_value("idle"))
        self._build_stat(body, 3, 0, "stat.goal_status", "goal_active", self.display_value("no"))
        self._build_stat(body, 3, 1, "stat.last_update", "last_update", "-")

    def _build_assets_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.assets.title", "card.assets.subtitle")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=164)
        card.grid_propagate(False)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.tv_logo", "tvlogo", "default")
        self._build_stat(body, 0, 1, "stat.scoreboard", "scoreboard", "default")
        self._build_stat(body, 1, 0, "stat.movie", "movie", "default")
        self._build_stat(body, 1, 1, "stat.status", "status", self.display_value("idle"))
        ttk.Button(card, text=self.tr("button.edit_asset_settings"), command=self.open_assets_settings_editor).pack(fill="x", padx=12, pady=(0, 12))

    def _build_stadium_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.stadium.title", "card.stadium.subtitle")
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        card.configure(height=358)
        card.grid_propagate(False)
        preview = tk.Label(
            card,
            text=self.tr("placeholder.stadium_preview"),
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 12, "bold"),
            justify="center",
            anchor="center",
            highlightthickness=1,
            highlightbackground="#243654",
        )
        preview.pack(fill="x", padx=12, pady=(6, 10), ipady=40)
        self._stadium_preview_label = preview
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="x", padx=12, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        self._build_stat(body, 0, 0, "stat.current_stadium", "stadium", "-", value_wraplength=300, block_height=64)
        self._build_stat(body, 1, 0, "stat.stadium_id", "stadid", "-")
        ttk.Button(card, text=self.tr("button.assign_stadium"), command=self.assign_stadium).pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(card, text=self.tr("button.edit_stadium_settings"), command=self.open_stadium_settings_editor).pack(fill="x", padx=12, pady=(0, 10))
        self.progress_text_label = tk.Label(card, text=self.display_value("idle"), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        self.progress_text_label.pack(anchor="w", padx=12, pady=(0, 4))
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(card, maximum=100, variable=self.progress_value, style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 12))
        self._set_progress(0, self.display_value("idle"))
        self._update_stadium_preview(self.labels["stadium"].cget("text"))

    def _build_modules_card(self, parent: tk.Misc, row: int) -> None:
        card = self._card(parent, "card.modules.title", "card.modules.subtitle")
        card.grid(row=row, column=0, sticky="ew")
        card.configure(height=384)
        card.grid_propagate(False)
        modules = tk.Frame(card, bg=self.card)
        modules.pack(fill="x", padx=12, pady=(6, 12))
        module_names = [
            "Stadium",
            "TvLogo",
            "ScoreBoard",
            "Movies",
            "Autorun",
            "StadiumNet",
            "Chants",
            "StadiumName",
            "AwayChants",
            "AwayClubSong",
            "TeamEntrance",
            "DiscordRPC",
            "ClothPhysics",
        ]
        for idx, name in enumerate(module_names):
            initial = self._discord_rpc_enabled if name == "DiscordRPC" else False
            var = tk.BooleanVar(value=initial)
            self.module_vars[name] = var
            check = ttk.Checkbutton(
                modules,
                style="Switch.TCheckbutton",
                text=name,
                variable=var,
                command=lambda n=name, v=var: self._on_module_toggle(n, v),
            )
            check.grid(row=idx // 2, column=idx % 2, padx=6, pady=4, sticky="w")
            self.module_checks[name] = check

        self.cloth_physics_note=tk.Label(modules,text=self.tr("module.cloth_physics_note"),bg=self.card,fg=self.muted,font=("Segoe UI",8))
        self.cloth_physics_note.grid(
            row=7,column=0,columnspan=2,padx=6,pady=(0,4),sticky="w")

        notification_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text="Show loading notification",
            variable=self.show_stadium_loading_var,
            command=self._toggle_stadium_loading_visibility,
        )
        notification_switch.pack(anchor="w", padx=12, pady=(0, 10))
        self.keep_open_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text=self.tr("toggle.keep_open"),
            variable=self.keep_open_var,
            command=self._toggle_keep_open,
        )
        self.keep_open_switch.pack(anchor="w", padx=12, pady=(0, 10))
        self.random_stadium_switch = ttk.Checkbutton(
            card,
            style="Switch.TCheckbutton",
            text=self.tr("toggle.random_stadium_selection"),
            variable=self.random_stadium_selection_var,
            command=self._toggle_random_stadium_selection,
        )
        self.random_stadium_switch.pack(anchor="w", padx=12, pady=(0, 10))
        self._regen_bh_btn = ttk.Button(
            card,
            text=self.tr("button.regen_bh"),
            command=self._run_regen_bh,
        )
        self._regen_bh_btn.pack(fill="x", padx=12, pady=(0, 10))

    def _toggle_discord_rpc(self) -> None:
        """Toggle DiscordRPC on/off and save to settings."""
        new_state = self.module_vars["DiscordRPC"].get()
        
        # Update internal state first
        self._discord_rpc_enabled = new_state
        
        # Update settings.json
        discord_config = self.settings.data.get("discord_rpc", {})
        discord_config["enabled"] = new_state
        self.settings.data["discord_rpc"] = discord_config
        self.settings.save()
        self.module_states["DiscordRPC"] = new_state
        self.settings_ini.write("DiscordRPC", "1" if new_state else "0", "Modules")
        self.settings_ini.save()
        
        # Connect or disconnect based on new state
        try:
            if new_state:
                # Enable DiscordRPC
                success = self.discord_rpc.connect()
                if success:
                    self.log("DiscordRPC enabled and connected")
                else:
                    self.log("DiscordRPC enabled but failed to connect (Discord may not be running)")
            else:
                # Disable DiscordRPC - disconnect and clear presence
                self.discord_rpc.disconnect()
                self.log("DiscordRPC disabled and presence cleared")
        except Exception as exc:
            self.log("Error toggling DiscordRPC", exc, exc_info=sys.exc_info())
            # Revert checkbox if there was an error
            self._discord_rpc_enabled = not new_state
            self.module_states["DiscordRPC"] = not new_state
            self.module_vars["DiscordRPC"].set(not new_state)
            discord_config["enabled"] = not new_state
            self.settings.data["discord_rpc"] = discord_config
            self.settings.save()
            self.settings_ini.write("DiscordRPC", "1" if not new_state else "0", "Modules")
            self.settings_ini.save()

    def _toggle_stadium_loading_visibility(self) -> None:
        self.settings.show_stadium_loading_notification = self.show_stadium_loading_var.get()
        self.settings.save()
        if self.show_stadium_loading_var.get():
            return
        self._hide_stadium_loading_modal()

    def _toggle_keep_open(self) -> None:
        self.settings.keep_open_on_game_close = self.keep_open_var.get()
        self.settings.save()

    def _toggle_random_stadium_selection(self) -> None:
        self.settings.random_stadium_selection = self.random_stadium_selection_var.get()
        self.settings.save()

    def _refresh_bh_button_state(self) -> None:
        button = getattr(self, "_regen_bh_btn", None)
        if button is None:
            return
        fifa_exe = getattr(self, "fifaEXE", "default")
        ready = (
            not getattr(self, "_bh_regen_running", False)
            and fifa_exe != "default"
            and Path(fifa_exe).is_file()
            and not self._is_target_process_running()
        )
        button.configure(state="normal" if ready else "disabled")

    def _run_bh_regen_blocking(self) -> tuple[int, int] | None:
        dll_candidates = (
            self.resource_dir / "bin" / "FifaLibrary16.dll",
            self.base_dir / "bin" / "FifaLibrary16.dll",
        )
        dll_path = next((path for path in dll_candidates if path.is_file()), None)
        worker_candidates = (
            self.resource_dir / "server16_py" / "bh_worker.py",
            self.base_dir / "server16_py" / "bh_worker.py",
            Path(__file__).resolve().parent / "bh_worker.py",
        )
        worker_path = next((path for path in worker_candidates if path.is_file()), None)
        python32_candidates = (
            self.resource_dir / "bin" / "python32" / "python.exe",
            self.base_dir / "bin" / "python32" / "python.exe",
        )
        python32 = next((path for path in python32_candidates if path.is_file()), None)
        if dll_path is None or worker_path is None or python32 is None:
            self.log("Regenerate BH unavailable: bundled bridge files are missing")
            return None

        self.log(f"Regenerating BH for {self.exedir}")
        self._post_ui(self._set_progress, 0, "Regenerating BH...")
        worker_env = dict(os.environ)
        worker_env["PYTHONNOUSERSITE"] = "1"
        process = subprocess.Popen(
            [str(python32), str(worker_path), str(dll_path), str(self.exedir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=worker_env,
        )
        ok = failed = 0
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    self.log(f"[BH worker] {line}")
                    continue
                event_type = event.get("t")
                if event_type == "progress":
                    total = max(1, int(event.get("total", 1)))
                    current = int(event.get("i", 0))
                    value = current / total * 100
                    status = "ok" if event.get("ok") else f"failed: {event.get('error', '')}"
                    self.log(f"BH {event.get('file', '?')} -> {status}")
                    self._post_ui(self._set_progress,value,f"Regenerating BH ({current}/{total})")
                elif event_type == "done":
                    ok = int(event.get("ok", 0))
                    failed = int(event.get("failed", 0))
                    self.log(f"BH regeneration complete: {ok} ok, {failed} failed")
                elif event_type == "error":
                    self.log(f"BH regeneration failed: {event.get('msg', 'unknown error')}")
        process.wait()
        return ok, failed

    def _run_regen_bh(self) -> None:
        if getattr(self, "_bh_regen_running", False):
            return
        if getattr(self, "fifaEXE", "default") == "default" or not Path(self.fifaEXE).is_file():
            self.log("Regenerate BH skipped: FIFA 16 EXE is not linked")
            return
        if self._is_target_process_running():
            self.log("Regenerate BH skipped while FIFA 16 is running")
            return
        self._bh_regen_running = True
        self._refresh_bh_button_state()

        def finish() -> None:
            self._bh_regen_running = False
            self._set_progress(0, self.display_value("idle"))
            self._refresh_bh_button_state()

        def work() -> None:
            try:
                self._run_bh_regen_blocking()
            except Exception as exc:
                self.log(f"BH regeneration failed: {exc}")
            finally:
                self._post_ui(finish)

        threading.Thread(target=work, name="bh-regenerator", daemon=True).start()

    def _build_audio_card(self) -> None:
        card = self._card(self.audio_tab, "card.chants.title", "card.chants.subtitle")
        card.pack(fill="both", expand=True, padx=10, pady=10)
        body = tk.Frame(card, bg=self.card)
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_stat(body, 0, 0, "stat.chants_module", "audio_module", self.display_value("disabled"))
        self._build_stat(body, 0, 1, "stat.chants_status", "audio_status", self.display_value("idle"))
        self._build_stat(body, 1, 0, "stat.current_chant", "audio_current", "-")
        self._build_stat(body, 1, 1, "stat.club_anthem", "audio_clubsong", "-")
        self._build_stat(body, 2, 0, "stat.chants_folder", "audio_chants_dir", "-")
        self._build_stat(body, 2, 1, "stat.last_action", "audio_last_action", "-")
        self._build_stat(body, 3, 0, "stat.crowd_mode", "audio_crowd_mode", self.display_value("idle"))
        self._build_stat(body, 3, 1, "stat.crowd_volume", "audio_crowd_volume", "-")
        self._build_stat(body, 4, 0, "stat.crowd_source", "audio_source", "-")
        self._build_stat(body, 4, 1, "stat.next_behavior", "audio_next", "-")
        self._build_stat(body, 5, 0, "stat.home_goals", "home_goals", "0")
        self._build_stat(body, 5, 1, "stat.away_goals", "away_goals", "0")
        button_row = tk.Frame(card, bg=self.card)
        button_row.pack(fill="x", padx=12, pady=(0, 12))
        self._chants_fix_button = ttk.Button(
            button_row,
            text=self.tr("button.fix_chants_audio"),
            command=self._run_fix_chants_audio,
        )
        self._chants_fix_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._chants_settings_button = ttk.Button(
            button_row,
            text=self.tr("button.edit_chants_settings"),
            command=self.open_audio_settings_editor,
        )
        self._chants_settings_button.pack(side="left", fill="x", expand=True)

    def _set_chants_fix_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for name in ("_chants_fix_button", "_chants_settings_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)

    def _run_fix_chants_audio(self) -> None:
        self._set_chants_fix_buttons_enabled(False)

        def scan() -> None:
            try:
                paths = self.chants_runtime.scan_chants_audio_files()
            except Exception as exc:
                self.log(f"Scan chants audio failed: {exc}")
                paths = None
            self._post_ui(after_scan,paths)

        def after_scan(paths: list[Path] | None) -> None:
            self._set_chants_fix_buttons_enabled(True)
            if paths is None:
                messagebox.showerror(self.tr("message.chants"), self.tr("message.chants_fix_error"))
            elif not paths:
                messagebox.showinfo(self.tr("message.chants"), self.tr("message.chants_fix_none"))
            else:
                self._open_chants_fix_dialog(paths)

        threading.Thread(target=scan, daemon=True).start()

    def _open_chants_fix_dialog(self, paths: list[Path]) -> None:
        root_dir = self.exedir / "FSW" / "Chants"
        win = tk.Toplevel(self._window())
        win.title(self.tr("dialog.chants_fix.title"))
        win.configure(bg=self.card)
        win.geometry("560x460")
        win.transient(self._window())
        win.grab_set()
        tk.Label(
            win,
            text=self.tr("dialog.chants_fix.hint", count=len(paths)),
            bg=self.card,
            fg=self.muted,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", padx=12, pady=(12, 6))
        keep_backup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            win,
            text=self.tr("dialog.chants_fix.keep_backup"),
            variable=keep_backup_var,
        ).pack(anchor="w", padx=12, pady=(0, 6))
        listbox = tk.Listbox(
            win,
            selectmode="extended",
            exportselection=False,
            bg=self.panel_alt,
            fg=self.fg,
            selectbackground="#1b3453",
            selectforeground=self.fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        listbox.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        for path in paths:
            try:
                label = str(path.relative_to(root_dir))
            except ValueError:
                label = str(path)
            listbox.insert("end", label)
        listbox.selection_set(0, "end")

        button_row = tk.Frame(win, bg=self.card)
        button_row.pack(fill="x", padx=12, pady=(0, 12))

        def select_all() -> None:
            listbox.selection_set(0, "end")

        def do_fix() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            selected_paths = [paths[index] for index in selection]
            win.destroy()
            self._run_fix_chants_audio_confirmed(selected_paths, keep_backup_var.get())

        ttk.Button(button_row, text=self.tr("dialog.chants_fix.select_all"), command=select_all).pack(side="left")
        ttk.Button(button_row, text=self.tr("button.fix_chants_audio"), command=do_fix).pack(side="right")

    def _run_fix_chants_audio_confirmed(self, paths: list[Path], keep_backup: bool) -> None:
        self._set_chants_fix_buttons_enabled(False)

        def work() -> None:
            try:
                counts = self.chants_runtime.fix_chants_audio_files(paths, keep_backup=keep_backup)
            except Exception as exc:
                self.log(f"Fix chants audio failed: {exc}")
                counts = None
            self._post_ui(done,counts)

        def done(counts: dict[str, int] | None) -> None:
            self._set_chants_fix_buttons_enabled(True)
            if counts is None:
                messagebox.showerror(self.tr("message.chants"), self.tr("message.chants_fix_error"))
                return
            messagebox.showinfo(
                self.tr("message.chants"),
                self.tr(
                    "message.chants_fix_result",
                    fixed=counts["fixed"],
                    clean=counts["already_clean"],
                    errors=counts["errors"],
                ),
            )

        threading.Thread(target=work, daemon=True).start()

    def _build_camera_tab(self) -> None:
        card_host = tk.Frame(self.camera_tab, bg=self.bg)
        card_host.pack(fill="both", expand=True, padx=10, pady=10)
        card_host.grid_columnconfigure(0, weight=2)
        card_host.grid_columnconfigure(1, weight=3)
        card_host.grid_rowconfigure(0, weight=1)

        library_card = self._card(card_host, "card.camera_library.title", "card.camera_library.subtitle")
        self.camera_library_card = library_card
        library_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        library_body = tk.Frame(library_card, bg=self.card)
        library_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.camera_select_button = ttk.Button(
            library_body,
            text=self.tr("button.choose_camera_package"),
            command=self.select_camera_package,
        )
        self.camera_select_button.pack(fill="x", pady=(0, 8))
        self.camera_package_label = tk.Label(
            library_body,
            text=self.tr("camera.no_package_selected"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
            justify="left",
        )
        self.camera_package_label.pack(fill="x", pady=(0, 8))
        list_frame = tk.Frame(library_body, bg=self.card)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", style="Server16.Vertical.TScrollbar")
        self.camera_listbox = tk.Listbox(
            list_frame,
            bg=self.panel_alt,
            fg=self.fg,
            selectbackground="#1b3453",
            selectforeground=self.fg,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Bahnschrift", 11),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self.camera_listbox.yview)
        self.camera_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.camera_listbox.bind("<<ListboxSelect>>", self._on_camera_select)

        detail_card = self._card(card_host, "card.camera_preview.title", "card.camera_preview.subtitle")
        self.camera_preview_card = detail_card
        detail_card.grid(row=0, column=1, sticky="nsew")
        detail_body = tk.Frame(detail_card, bg=self.card)
        detail_body.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        detail_body.grid_columnconfigure(0, weight=1)
        detail_body.grid_rowconfigure(1, weight=1)
        self.camera_name_label = tk.Label(
            detail_body,
            text=self.tr("camera.no_camera_selected"),
            bg=self.card,
            fg=self.gold,
            font=("Bahnschrift", 14, "bold"),
            anchor="w",
        )
        self.camera_name_label.grid(row=0, column=0, sticky="ew")
        preview_shell = tk.Frame(detail_body, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        preview_shell.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        preview_shell.grid_columnconfigure(0, weight=1)
        preview_shell.grid_rowconfigure(0, weight=1)
        self.camera_preview_canvas = tk.Canvas(
            preview_shell,
            bg=self.card_soft,
            highlightthickness=0,
            bd=0,
        )
        self.camera_preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.camera_preview_frame = tk.Frame(self.camera_preview_canvas, bg=self.card_soft)
        self._camera_preview_canvas_window = self.camera_preview_canvas.create_window((0, 0), window=self.camera_preview_frame, anchor="nw")
        self.camera_preview_canvas.bind("<Configure>", self._on_camera_preview_canvas_configure)
        self.camera_preview_image_label = tk.Label(
            self.camera_preview_frame,
            text=self.tr("placeholder.preview"),
            bg=self.card_soft,
            fg=self.muted,
            font=("Bahnschrift", 12, "bold"),
            bd=0,
            relief="flat",
            compound="center",
            anchor="center",
            justify="center",
            padx=12,
            pady=12,
        )
        self.camera_preview_image_label.pack(anchor="nw")
        self.camera_preview_status = tk.Label(
            detail_body,
            text=self.tr("camera.no_preview"),
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 9),
            anchor="w",
        )
        self.camera_preview_status.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.camera_example_combo = ttk.Combobox(detail_body, state="readonly", textvariable=self.camera_example_var)
        self.camera_example_combo.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.camera_example_combo.bind("<<ComboboxSelected>>", self._on_camera_example_change)
        instruction_host = tk.Frame(detail_body, bg=self.panel)
        instruction_host.grid(row=4, column=0, sticky="nsew")
        self.camera_instruction_text = tk.Text(
            instruction_host,
            height=5,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            wrap="word",
        )
        camera_instruction_scrollbar = ttk.Scrollbar(
            instruction_host,
            orient="vertical",
            command=self.camera_instruction_text.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.camera_instruction_text.configure(yscrollcommand=camera_instruction_scrollbar.set)
        self.camera_instruction_text.pack(side="left", fill="both", expand=True)
        camera_instruction_scrollbar.pack(side="right", fill="y")
        self.camera_instruction_text.configure(state="disabled")
        self.camera_apply_button = ttk.Button(detail_body, text=self.tr("button.apply_camera"), command=self.apply_selected_camera)
        self.camera_apply_button.grid(row=5, column=0, sticky="ew", pady=(12, 0))

    def _build_logs_card(self) -> None:
        logs = ttk.LabelFrame(self.logs_tab, text=self.tr("logs.group"), padding=10)
        self.logs_frame = logs
        self.logs_group = logs
        logs.pack(fill="both", expand=True, padx=10, pady=10)
        header = tk.Frame(logs, bg=self.bg)
        header.pack(fill="x", pady=(0, 8))
        self.log_status_label = tk.Label(
            header,
            text=self.tr("logs.following"),
            bg=self.bg,
            fg=self.success,
            font=("Bahnschrift", 9, "bold"),
            anchor="w",
        )
        self.log_status_label.pack(side="left")
        self.log_follow_button = ttk.Button(header, text=self.tr("button.jump_latest"), command=self._jump_logs_to_latest)
        self.log_follow_button.pack(side="right")
        logs_body = tk.Frame(logs, bg=self.panel)
        logs_body.pack(fill="both", expand=True)
        self.log_widget = tk.Text(
            logs_body,
            height=18,
            bg=self.panel,
            fg=self.fg,
            insertbackground=self.fg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            wrap="word",
        )
        log_scrollbar = ttk.Scrollbar(
            logs_body,
            orient="vertical",
            command=self.log_widget.yview,
            style="Server16.Vertical.TScrollbar",
        )
        self.log_widget.configure(yscrollcommand=log_scrollbar.set)
        self.log_widget.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")
        self.log_widget.configure(state="disabled")
        self.log_widget.bind("<ButtonRelease-1>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<ButtonRelease-4>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<ButtonRelease-5>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<MouseWheel>", self._refresh_log_autofollow_state)
        self.log_widget.bind("<KeyRelease>", self._refresh_log_autofollow_state)
        self._update_log_follow_ui()

    def refresh_camera_catalog(self) -> None:
        self._camera_presets = self.camera_runtime.discover_presets()
        self._camera_presets_by_name = {preset.name: preset for preset in self._camera_presets}
        if self.camera_package_label is not None:
            package_dir = self.camera_runtime.package_dir()
            if package_dir is not None and package_dir.exists():
                self.camera_package_label.configure(
                    text=self.tr("camera.cameras_found", count=len(self._camera_presets), path=package_dir),
                    fg=self.muted,
                )
            else:
                self.camera_package_label.configure(
                    text=self.tr("camera.invalid_package_label"),
                    fg=self.error,
                )
        if self.camera_listbox is None:
            return
        self.camera_listbox.delete(0, "end")
        for preset in self._camera_presets:
            self.camera_listbox.insert("end", preset.name)
        if not self._camera_presets:
            self._display_camera_details(None)
            return
        selected_name = self._camera_selected_name if self._camera_selected_name in self._camera_presets_by_name else self._camera_presets[0].name
        index = next((idx for idx, preset in enumerate(self._camera_presets) if preset.name == selected_name), 0)
        self.camera_listbox.selection_clear(0, "end")
        self.camera_listbox.selection_set(index)
        self.camera_listbox.activate(index)
        self.camera_listbox.see(index)
        self._display_camera_details(self._camera_presets[index])

    def _on_camera_select(self, _event=None) -> None:
        if self.camera_listbox is None:
            return
        selection = self.camera_listbox.curselection()
        if not selection:
            return
        name = self.camera_listbox.get(selection[0])
        self._display_camera_details(self._camera_presets_by_name.get(name))

    def _on_camera_example_change(self, _event=None) -> None:
        preset = self._camera_presets_by_name.get(self._camera_selected_name or "")
        if preset is None:
            return
        self._show_camera_example(preset, self.camera_example_var.get())

    def _display_camera_details(self, preset: CameraPreset | None) -> None:
        self._camera_selected_name = preset.name if preset is not None else None
        if self.camera_name_label is not None:
            self.camera_name_label.configure(text=preset.name if preset is not None else self.tr("camera.no_camera_selected"))
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(state="normal" if preset is not None else "disabled")
        if self.camera_instruction_text is not None:
            self.camera_instruction_text.configure(state="normal")
            self.camera_instruction_text.delete("1.0", "end")
            self.camera_instruction_text.insert("1.0", preset.instructions_text if preset is not None else self.tr("camera.instructions_missing"))
            self.camera_instruction_text.configure(state="disabled")
        if self.camera_example_combo is not None:
            values = [path.name for path in preset.example_paths] if preset is not None else []
            self.camera_example_combo.configure(values=values)
            if values:
                self.camera_example_var.set(values[0])
                self._show_camera_example(preset, values[0])
            else:
                self.camera_example_var.set("")
                self._clear_camera_preview(self.tr("camera.no_preview"))

    def _show_camera_example(self, preset: CameraPreset, image_name: str) -> None:
        target = next((path for path in preset.example_paths if path.name == image_name), None)
        if target is None:
            self._clear_camera_preview(self.tr("camera.no_preview"))
            return
        cache_key = (preset.name, target.name)
        image_obj = self._camera_preview_cache.get(cache_key)
        if image_obj is None:
            try:
                image_obj = Image.open(target).convert("RGBA")
                self._camera_preview_cache[cache_key] = image_obj
            except Exception as exc:
                self.log(f"Failed to load camera preview {target}", exc, exc_info=sys.exc_info())
                self._clear_camera_preview(self.tr("camera.failed_open_preview", name=target.name))
                return
        self._camera_preview_source_key = cache_key
        self._render_camera_preview()
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=self.tr("camera.preview_prefix", name=target.name))

    def _clear_camera_preview(self, text: str) -> None:
        self._camera_preview_source_key = None
        if self.camera_preview_image_label is not None:
            self.camera_preview_image_label.configure(image="", text=self.tr("placeholder.preview"))
            self.camera_preview_image_label.image = None
        if self.camera_preview_status is not None:
            self.camera_preview_status.configure(text=text)

    def _on_camera_preview_canvas_configure(self, _event=None) -> None:
        self._render_camera_preview()

    def _render_camera_preview(self) -> None:
        if self._camera_preview_source_key is None or self.camera_preview_canvas is None or self.camera_preview_image_label is None:
            return
        image_obj = self._camera_preview_cache.get(self._camera_preview_source_key)
        if image_obj is None:
            return
        canvas_width = max(1, self.camera_preview_canvas.winfo_width())
        canvas_height = max(1, self.camera_preview_canvas.winfo_height())
        if canvas_width <= 1 or canvas_height <= 1:
            return
        max_width = max(240, canvas_width - 24)
        max_height = max(180, canvas_height - 24)
        src_width, src_height = image_obj.size
        scale = min(max_width / max(1, src_width), max_height / max(1, src_height), 1.0)
        render_width = max(1, int(src_width * scale))
        render_height = max(1, int(src_height * scale))
        render_key = (*self._camera_preview_source_key, render_width, render_height)
        image_ref = self._camera_preview_render_cache.get(render_key)
        if image_ref is None:
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
            resized = image_obj.resize((render_width, render_height), resampling)
            image_ref = ImageTk.PhotoImage(resized)
            self._camera_preview_render_cache[render_key] = image_ref
        self.camera_preview_image_label.configure(image=image_ref, text="")
        self.camera_preview_image_label.image = image_ref
        self.camera_preview_image_label.update_idletasks()

    def select_camera_package(self) -> None:
        selected = filedialog.askdirectory(title=self.tr("message.camera.select_package_dialog"))
        if not selected:
            return
        if not self.camera_runtime.is_valid_package_dir(selected):
            messagebox.showwarning(
                self.tr("message.camera_package"),
                self.tr("message.camera.invalid_package"),
            )
            return
        self.settings.camera_package = selected
        self._camera_preview_cache.clear()
        self.refresh_camera_catalog()
        self.log(f"Camera package selected: {selected}")

    def apply_selected_camera(self) -> None:
        preset = self._camera_presets_by_name.get(self._camera_selected_name or "")
        if preset is None:
            messagebox.showwarning(self.tr("message.camera"), self.tr("message.camera.select_before_apply"))
            return
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.camera"), self.tr("message.warning.select_fifa_first"))
            return
        if self.camera_apply_button is not None:
            self.camera_apply_button.configure(state="disabled")
        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            result = self.camera_runtime.apply_preset(preset)
            regen = result["regenerator"]
            copied_files = result["copied_files"]
            if isinstance(regen, dict) and regen.get("launched"):
                regen_message = self.tr("message.camera.regen_started", path=regen["path"])
            else:
                regen_message = self.tr("message.camera.regen_failed")
            self.log(f"Camera applied: {preset.name} ({copied_files} files updated)")
            self.log(regen_message)
            if self.camera_preview_status is not None:
                self.camera_preview_status.configure(text=self.tr("camera.applied_prefix", name=preset.name))
            messagebox.showinfo(
                self.tr("message.camera.applied_title"),
                self.tr("message.camera.apply_success", name=preset.name, count=copied_files, regen=regen_message),
            )
        except Exception as exc:
            self.log(f"Failed to apply camera {preset.name}", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.camera"), self.tr("message.camera.apply_failed", error=exc))
        finally:
            window.configure(cursor="")
            if self.camera_apply_button is not None:
                self.camera_apply_button.configure(state="normal" if preset is not None else "disabled")

    def _build_stat(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        title: str,
        key: str,
        default: str,
        value_wraplength: int | None = None,
        block_height: int = 44,
    ) -> None:
        block = tk.Frame(parent, bg=self.card)
        block.grid(row=row, column=column, sticky="ew", padx=(0, 10), pady=4)
        block.configure(width=190, height=block_height)
        block.grid_propagate(False)
        title_label = tk.Label(block, text=self.tr(title), bg=self.card, fg=self.muted, font=("Bahnschrift", 9))
        title_label.pack(anchor="w")
        label = tk.Label(
            block,
            text=default,
            bg=self.card,
            fg=self.fg,
            font=("Consolas", 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=value_wraplength,
        )
        label.pack(anchor="w", pady=(2, 0))
        self.stat_title_labels[key] = title_label
        self.labels[key] = label

    def _check_update_button_text(self) -> str:
        key = "button.checking_update" if self._update_check_in_progress else "button.check_update"
        return self.tr(key)

    def _set_update_badge_visible(self, visible: bool) -> None:
        self._update_available = visible
        if self.check_update_badge is None:
            return
        if visible:
            self.check_update_badge.pack(side="right", padx=(0, 6))
        else:
            self.check_update_badge.pack_forget()

    def check_updates(self, *, silent: bool = False) -> None:
        if self._update_check_in_progress:
            return
        self._update_check_in_progress = True
        if not silent and self.check_update_button is not None:
            self.check_update_button.configure(state="disabled", text=self._check_update_button_text())
        self.log("Checking for updates on GitHub releases" + (" (background)" if silent else ""))
        threading.Thread(target=self._run_check_updates_worker, args=(silent,), daemon=True).start()

    def _run_check_updates_worker(self, silent: bool = False) -> None:
        result = self._update_checker.check_latest_release(self.app_version)
        self._post_ui(self._handle_check_updates_result,result,silent)

    def _handle_check_updates_result(self, result: UpdateCheckResult, silent: bool = False) -> None:
        self._update_check_in_progress = False
        if self.check_update_button is not None:
            self.check_update_button.configure(state="normal", text=self._check_update_button_text())

        if not result.ok:
            self.log(f"Update check failed: {result.error}")
            if not silent:
                messagebox.showerror(
                    self.tr("message.update_check_title"),
                    self.tr("message.update_check_error", error=result.error),
                )
            return

        self._set_update_badge_visible(result.update_available)
        if result.update_available:
            self.log(f"Update available: v{result.latest_version} (current v{result.current_version})")
            if silent:
                return
            should_open = messagebox.askyesno(
                self.tr("message.update_check_title"),
                self.tr(
                    "message.update_available",
                    latest=result.latest_version,
                    current=result.current_version,
                ),
            )
            if should_open:
                url = result.release_url or (
                    f"https://github.com/{self.UPDATE_REPO_OWNER}/{self.UPDATE_REPO_NAME}/releases/latest"
                )
                webbrowser.open(url)
            return

        self.log(f"No updates found. Current version is v{result.current_version}")
        if not silent:
            messagebox.showinfo(
                self.tr("message.update_check_title"),
                self.tr("message.update_none", current=result.current_version),
            )

    def _set_progress(self, value: float, text: str) -> None:
        if self.progress_value is not None:
            self.progress_value.set(max(0, min(100, value)))
        if self.progress_text_label is not None:
            self.progress_text_label.configure(text=text)
        self._set_display("status", text)
        if self._stadium_task_running:
            try:
                self._update_stadium_loading_modal(value, text)
            except Exception as exc:
                self.log("Stadium loading notification update failed", exc)
        self.update_idletasks()

    def _set_process_status(self, text: str, color: str | None = None) -> None:
        if self.status_pill is not None:
            self.status_pill.configure(text=text, fg=color or self.accent)

    def _sync_page_banner(self, page_name: str) -> None:
        self._set_display("page", page_name or "-")
        if self.page_banner is not None:
            self.page_banner.configure(text=page_name or "-")

    def _should_auto_apply_runtime(self, page_name: str) -> bool:
        return page_name == "game/screens/playNow/KickOffHub"

    def _schedule_worker_poll(self) -> None:
        if self._closing or self._worker_poll_job is not None:
            return
        self._worker_poll_job = self.after(50, self._poll_worker_queue)

    def _poll_worker_queue(self) -> None:
        self._worker_poll_job = None
        while not self._worker_queue.empty():
            event = self._worker_queue.get()
            kind = event[0]
            if kind == "progress":
                if self.stadium_runtime._replacement is not None:continue
                _, value, text = event
                self._set_progress(value, text)
            elif kind == "done":
                _, payload = event
                if self.stadium_runtime._replacement is not None:
                    self.stadium_runtime.restart_replacement();continue
                try:
                    self._finish_stadium_apply(payload)
                except Exception as exc:
                    self.stadium_runtime.cancel_pending_selection()
                    self._set_progress(100, f'Failed to apply stadium: {exc}')
                    self._set_process_status(self.status_text('stadium_error'), self.error)
                    self.log('Failed to finish stadium application', exc, exc_info=sys.exc_info())
            elif kind == 'cancelled':
                self.stadium_runtime.restart_replacement()
            elif kind == "error":
                if self.stadium_runtime._replacement is not None:
                    self.stadium_runtime.restart_replacement();continue
                _, message = event
                self.stadium_runtime.cancel_pending_selection()
                short_message = str(message).splitlines()[0] if message else self.status_text("stadium_error")
                self._set_progress(100, short_message)
                self._stadium_task_running = False
                self._stadium_task_signature = None
                self._stadium_task_request_key = None
                self._set_process_status(self.status_text("stadium_error"), self.error)
                self._hide_stadium_loading_modal(delay_ms=5000)
                self.log(message)
        if self._stadium_task_running or not self._worker_queue.empty():
            self._schedule_worker_poll()

    def setuppaths(self, load_team_database: bool = True) -> None:
        detected = self._auto_detect_fifa_exe()
        self.fifaEXE = str(detected) if detected is not None else "default"
        if self.settings.fifa_exe != self.fifaEXE:
            self.settings.fifa_exe = self.fifaEXE
        self.MP = Path(self.fifaEXE).stem if self.fifaEXE != "default" else ""
        self.exedir = Path(self.fifaEXE).parent if self.fifaEXE != "default" else self.base_dir
        self.TVLogo = self.exedir / "TVLogoGBD"
        self.TVdata = self.exedir / "data" / "ui" / "game" / "overlays"
        self.Scoredata = self.exedir / "data" / "ui"
        self.MOVBUMP = self.exedir / "data" / "ui" / "TV" / "bumper.big"
        self.ScoreBoard = self.exedir / "ScoreBoardGBD"
        self.Movies = self.exedir / "MoviesGBD"
        self.Movdata = self.exedir / "data" / "movies" / "bootflowoutro.vp8"
        self.targetpath = self.exedir / "StadiumGBD"
        self.Psource = self._first_existing(self.exedir / "FSW" / "Police", self.exedir / "FSW" / "Images" / "Police")
        self.Nsource = self._first_existing(self.exedir / "FSW" / "Nets", self.exedir / "FSW" / "Images" / "Nets")
        self.PitchMowsource = self._first_existing(self.exedir / "FSW" / "PitchMowPattern", self.exedir / "FSW" / "Images" / "PitchMowPattern")
        self.Pdest = self.exedir / "data" / "sceneassets" / "slc"
        self.Ndest = self.exedir / "data" / "sceneassets" / "goalnet"
        self.PitchMowdest = self.exedir / "data" / "sceneassets" / "pitch"
        self.settings_ini = SessionIniFile(self.exedir / "FSW" / "settings.ini")
        self.audio_profiles.bind(self.exedir if self.fifaEXE != 'default' else None)
        self.audio_profiles.sync(force=True)
        self._load_module_states()
        self._refresh_bh_button_state()
        self._update_audio_overview()
        if load_team_database:
            self._load_team_database()

    def _first_existing(self, *paths: Path) -> Path:
        for path in paths:
            if path.exists():
                return path
        return paths[0]

    def _load_module_states(self) -> None:
        module_names = ["Stadium", "TvLogo", "ScoreBoard", "Movies", "Autorun", "StadiumNet", "Chants", "StadiumName", "AwayChants", "AwayClubSong", "TeamEntrance"]
        ensure_audio_module_defaults(self.settings_ini)
        self.module_states = {name: module_setting_enabled(self.settings_ini, name) for name in module_names}
        previous_rpc_state = self._discord_rpc_enabled
        discord_ini_value = self.settings_ini.read("DiscordRPC", "Modules")
        if discord_ini_value in {"0", "1"}:
            self._discord_rpc_enabled = discord_ini_value == "1"
        else:
            # Never fabricate an incomplete game configuration from a Discord default.
            if self.settings_ini.path.is_file():
                self.settings_ini.write("DiscordRPC", "1" if self._discord_rpc_enabled else "0", "Modules")
                self.settings_ini.save()
        self.module_states["DiscordRPC"] = self._discord_rpc_enabled
        self.module_states["ClothPhysics"] = ClothMotionSwitch(self.exedir).enabled()
        loaded = ", ".join(
            f"{name}={'1' if enabled else '0'}"
            for name, enabled in self.module_states.items()
        )
        self.log(f"Modules loaded from {self.exedir / 'FSW' / 'settings.ini'}: {loaded}")

        if self._discord_rpc_enabled:
            if not self.discord_rpc.is_connected():
                self.discord_rpc.connect()
        elif previous_rpc_state or self.discord_rpc.is_connected():
            self.discord_rpc.disconnect()

        discord_var = self.module_vars.get("DiscordRPC")
        if discord_var is not None:
            discord_var.set(self._discord_rpc_enabled)

    def module_enabled(self, name: str) -> bool:
        if name == "ClothPhysics":
            return ClothMotionSwitch(self.exedir).enabled()
        if name == "DiscordRPC":
            return self._discord_rpc_enabled
        if not hasattr(self, "settings_ini") or self.settings_ini is None:
            return self.module_states.get(name, False)
        enabled = module_setting_enabled(self.settings_ini, name)
        self.module_states[name] = enabled
        return enabled

    def _open_settings_editor(self, editor_key: str, title: str, specs, initial_section: str | None = None) -> None:
        self.prepare_floating_window()
        existing = self._settings_editors.get(editor_key)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            existing._refresh_active_frame()
            return
        editor = SettingsAreaEditor(self, self.tr(title), specs, initial_section=initial_section)
        self._settings_editors[editor_key] = editor
        editor.bind("<Destroy>", lambda _event, key=editor_key: self._settings_editors.pop(key, None))

    def open_stadium_settings_editor(self) -> None:
        self._open_settings_editor("stadium", "dialog.editor.section.stadium_settings", stadium_specs())

    def open_assets_settings_editor(self) -> None:
        self._open_settings_editor("assets", "dialog.editor.section.asset_settings", asset_specs())

    def open_audio_settings_editor(self) -> None:
        self._open_settings_editor("audio", "dialog.editor.section.chants_settings", audio_specs())

    def get_imgbb_api_key(self) -> str:
        discord_config = self.settings.data.get("discord_rpc", {})
        return (discord_config.get("stadium_preview_imgbb_api_key", "") or "").strip()

    def set_imgbb_api_key(self, key: str) -> None:
        discord_config = dict(self.settings.data.get("discord_rpc", {}))
        discord_config["stadium_preview_imgbb_api_key"] = (key or "").strip()
        self.settings.data["discord_rpc"] = discord_config
        self.settings.save()

    def _rebuild_stadium_preview_uploader(self) -> None:
        discord_config = self.settings.data.get("discord_rpc", {})
        provider = (discord_config.get("stadium_preview_provider", "discord_webhook") or "discord_webhook").strip().lower()
        webhook_url = discord_config.get("stadium_preview_webhook", "")
        imgur_client_id = (discord_config.get("stadium_preview_imgur_client_id", "") or "").strip()
        imgbb_api_key = self.get_imgbb_api_key()
        enabled = (
            bool(webhook_url)
            or (provider == "imgur" and bool(imgur_client_id))
            or (provider == "imgbb" and bool(imgbb_api_key))
        )
        if not enabled:
            self._stadium_preview_uploader = None
            return
        uploader = StadiumPreviewUploader(
            webhook_url,
            provider=provider,
            imgur_client_id=imgur_client_id,
            imgbb_api_key=imgbb_api_key,
        )
        uploader.add_upload_callback(self._on_stadium_preview_uploaded)
        self._stadium_preview_uploader = uploader

    def _change_imgbb_api_key(self) -> None:
        dialog = ImgbbApiKeyDialog(self, self.get_imgbb_api_key())
        self.wait_window(dialog)
        new_key = dialog.result
        if new_key is None:
            return
        self.set_imgbb_api_key(new_key)
        self._rebuild_stadium_preview_uploader()
        self._discord_rpc_last_presence = None
        self.log("ImgBB API key updated")
        messagebox.showinfo(self.tr("dialog.imgbb_key.title"), self.tr("message.imgbb_key_saved"))

    def _clean_generated_cache(self) -> None:
        if not messagebox.askyesno(
            self.tr("message.clean_cache_title"),
            self.tr("message.clean_cache_confirm"),
        ):
            return
        try:
            bytes_freed, folders_removed = clear_generated_cache(self.base_dir)
        except Exception as exc:
            self.log("Error clearing generated cache", exc, exc_info=sys.exc_info())
            messagebox.showerror(
                self.tr("message.clean_cache_title"),
                self.tr("message.clean_cache_error", error=exc),
            )
            return
        if folders_removed == 0:
            self.log("Clean cache: nothing to clean")
            messagebox.showinfo(self.tr("message.clean_cache_title"), self.tr("message.clean_cache_empty"))
            return
        size_mb = bytes_freed / (1024 * 1024)
        size_text = f"{size_mb:.1f} MB" if size_mb >= 0.1 else f"{bytes_freed} B"
        self.log(f"Clean cache: removed {folders_removed} folder(s), freed {size_text}")
        messagebox.showinfo(
            self.tr("message.clean_cache_title"),
            self.tr("message.clean_cache_done", size=size_text, count=folders_removed),
        )

    def _check_fifa_location(self) -> bool:
        if self.fifaEXE == "default":
            return True
        try:
            fifa_dir = self.exedir.resolve()
            app_dir = self.base_dir.resolve()
        except Exception:
            return True
        if fifa_dir == app_dir:
            return True
        self.log(
            "CGFS16 is not in the same folder as the linked FIFA 16 executable "
            f"(app: {app_dir}, FIFA: {fifa_dir}) -- Launch FIFA and file operations may not work correctly"
        )
        self._dismiss_launch_splash()
        dialog = FifaLocationWarningDialog(self, fifa_dir, app_dir)
        self.wait_window(dialog)
        if dialog.result:
            self.log("User chose to continue despite the FIFA location mismatch (unstable mode)")
            return True
        self.log("Closing application: user chose to close after the FIFA location mismatch warning")
        self.on_close()
        return False

    def select_fifa_exe(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("Executable", "*.exe")], title=self.tr("filedialog.select_fifa_exe"))
        if not filename:
            return
        window = self._window()
        window.configure(cursor="watch")
        window.update_idletasks()
        try:
            self._set_process_status(self.status_text("loading_fifa_data"), self.accent)
            self._set_progress(8, self.progress_text("saving_executable"))
            self.settings.fifa_exe = filename
            self._set_progress(24, self.progress_text("configuring_paths"))
            self.setuppaths(load_team_database=False)
            if not self._check_fifa_location():
                return
            self._load_team_database(lambda value, text: self._set_progress(value, text))
            self._set_progress(82, self.progress_text("applying_bootstrap"))
            self.apply_bootstrap_files()
            self._set_progress(94, self.progress_text("refreshing_modules"))
            self.refresh_modules()
            self._set_progress(100, self.progress_text("fifa_data_ready"))
            self._set_process_status(self.status_text("fifa_ready"), self.success)
            self.log(f"Selected FIFA executable: {filename}")
        except Exception as exc:
            self._set_process_status(self.status_text("fifa_load_error"), self.error)
            self.log("Failed while loading FIFA data after selecting executable", exc, exc_info=sys.exc_info())
            messagebox.showerror(self.tr("message.fifa16"), self.tr("message.error.load_fifa_data"))
        finally:
            try:
                window.configure(cursor="")
                window.update_idletasks()
            except Exception:
                pass

    def _auto_detect_fifa_exe(self) -> Path | None:
        for name in ("fifa16.exe", "FIFA16.exe", "FIFA 16.exe", "fifa 16.exe"):
            candidate = self.base_dir / name
            if candidate.is_file():
                return candidate
        if self.settings.fifa_exe and self.settings.fifa_exe != "default":
            candidate = Path(self.settings.fifa_exe)
            if candidate.is_file():
                return candidate
        return None

    def _check_fifa_settings(self) -> bool:
        path = self.exedir / "FSW" / "settings.ini"
        if path.is_file():
            return True
        self.log(f"FIFA configuration not found: {path}")
        self._dismiss_launch_splash()
        messagebox.showwarning(
            self.tr("message.fifa16"),
            self.tr("message.warning.missing_fifa_settings", path=str(path)),
        )
        return False

    def _load_team_database(self, progress_callback=None) -> None:
        """Load FIFA team database for the selected installation"""
        if not self.fifaEXE or self.fifaEXE == "default":
            self._team_db_load_token += 1
            self.team_db = None
            self.discord_rpc.set_team_name_resolver(None)
            if progress_callback is not None:
                progress_callback(0, "Team database idle")
            else:
                self._set_progress(0, "Team database idle")
            return

        def _report_progress(value: float, text: str) -> None:
            if progress_callback is not None:
                progress_callback(value, text)
            else:
                self._set_progress(value, text)

        self._team_db_load_token += 1
        load_token = self._team_db_load_token
        fifa_root = Path(self.fifaEXE).parent
        self.team_db = None
        self.discord_rpc.set_team_name_resolver(None)
        self._set_process_status("Loading Team DB", self.gold)
        _report_progress(10, self.progress_text("connecting_database"))

        def _apply_success(db: FifaDatabase, team_count: int) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = db
            self.discord_rpc.set_team_name_resolver(self.team_db.get_team_name)
            if self.HID and self.AID:
                self.entrance_props_runtime.prepare_match()
            self.log(f" Team database loaded for {fifa_root.name} ({team_count} teams)")
            _report_progress(100, f"{self.progress_text('database_ready')} ({team_count} teams)")
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _apply_failure(reason: str) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = None
            self.log(f"️  Could not connect to team database: {reason}")
            _report_progress(0, self.progress_text("database_unavailable"))
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _apply_error(message: str) -> None:
            if load_token != self._team_db_load_token or self._closing:
                return
            self.team_db = None
            self.log(f"❌ Error loading team database: {message}")
            _report_progress(0, self.progress_text("database_failed"))
            if not self.memory.is_open():
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)

        def _worker() -> None:
            try:
                db = FifaDatabase(fifa_root)
                self._post_ui(_report_progress,40,self.progress_text("connecting_database"))
                if not db.connect():
                    reason = db.last_error or "unknown reason"
                    self._post_ui(_apply_failure,reason)
                    return
                self._post_ui(_report_progress,80,self.progress_text("loading_teams"))
                team_count = db.load_all_teams()
                self._post_ui(_apply_success,db,team_count)
            except Exception as exc:
                self._post_ui(_apply_error,str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _resolve_team_name(self, team_id: str) -> str | None:
        """Resolve a team id to its display name using the loaded team database."""
        if not team_id or team_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_team_name(team_id)
        except Exception:
            return None

    def _resolve_stadium_name(self, stadium_id: str) -> str | None:
        """Resolve a stadium id to its display name using the loaded database."""
        if not stadium_id or stadium_id in {"-", "0"} or self.team_db is None:
            return None
        try:
            return self.team_db.get_stadium_name(stadium_id)
        except Exception:
            return None

    def _has_active_custom_stadium_assignment(self) -> bool:
        """Return True when current context resolves to a custom stadium assignment in settings.ini."""
        manual = getattr(self,'_manual_stadium_override',None)
        if manual and manual[0] == (self._kickoff_generation,self.HID,self.AID,self.TOURNAME,self.TOURROUNDID):
            return True
        if not hasattr(self, "settings_ini") or self.settings_ini is None:
            return False
        try:
            if self.TOURROUNDID and self.settings_ini.key_exists(self.TOURROUNDID, "comp"):
                return True
            if self.TOURNAME and self.settings_ini.key_exists(self.TOURNAME, "comp"):
                return True
            if self.HID and self.settings_ini.key_exists(self.HID, "stadium"):
                return True
        except Exception:
            return False
        return False

    def _is_target_process_running(self) -> bool:
        if not self.MP:
            return False
        try:
            return any(Path((p.info.get("name") or "")).stem.lower() == self.MP.lower() for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    def start_overlay_session(self) -> None:
        fifa_path = self._auto_detect_fifa_exe()
        if fifa_path is None:
            messagebox.showwarning(
                self.tr("message.fifa16"),
                self.tr("message.warning.find_fifa_same_folder"),
            )
            self.select_fifa_exe()
            fifa_path = self._auto_detect_fifa_exe()
            if fifa_path is None:
                return
        self.settings.fifa_exe = str(fifa_path)
        self.setuppaths()
        if not self._check_fifa_settings():
            return
        self.apply_bootstrap_files()
        self.refresh_modules()
        self._overlay_enabled = True
        self._launcher_mode = False
        self._set_process_status(self.status_text("overlay_armed"), self.accent)
        self.log(f"Overlay session armed for FIFA executable: {fifa_path}")
        if not self._is_target_process_running():
            self.launch_fifa()
        self._hide_overlay()

    def launch_fifa(self) -> None:
        if self.fifaEXE == "default":
            messagebox.showwarning(self.tr("message.fifa16"), self.tr("message.warning.select_fifa_first"))
            return
        if self._is_target_process_running():
            self.log(f"FIFA process already running: {self.fifaEXE}")
            return
        try:
            from .loose_ui import activate
            self.log('Career/panorama loose UI activation', activate(self.exedir))
        except Exception as exc:
            self.log('Career/panorama UI activation unavailable', exc)
            messagebox.showerror(self.tr('message.fifa16'), str(exc))
            return
        self.competition_icons.prepare(self.exedir, force=True)
        diagnostics = getattr(self, '_startup_diagnostics', None)
        if diagnostics:
            diagnostics.prepare_launch(self.fifaEXE)
        subprocess.Popen([self.fifaEXE], cwd=str(Path(self.fifaEXE).resolve().parent), shell=False)
        self.log(f"Launched FIFA executable: {self.fifaEXE}")

    def _sync_competition_icons(self) -> None:
        if self._closing:
            return
        try:
            if self.fifaEXE != 'default':
                self.competition_icons.poll(self.exedir, self._is_target_process_running())
        except Exception as exc:
            self.log('Ícones da carreira: não foi possível verificar a instalação', exc)
        self.after(3000, self._sync_competition_icons)

    def overlay_loop(self) -> None:
        self._overlay_job = None
        if self._closing:
            return
        try:
            if self._stadium_selector is not None:
                self._stadium_selector.tick()
                if self._stadium_selector.opened:
                    self._overlay_job=self.after(40,self.overlay_loop)
                    return
            self._sync_overlay_hotkey()
            self._sync_crowd_volume_controller()
            if self._overlay_visible:
                self._position_overlay()
        except Exception as exc:
            self.log("Overlay loop error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._overlay_job = self.after(40, self.overlay_loop)

    def _sync_overlay_hotkey(self) -> None:
        if not self._overlay_enabled:
            return
        now = perf_counter()
        foreground = int(self.user32.GetForegroundWindow() or 0)
        self._fifa_hwnd = self._find_fifa_window_handle()
        key_down = bool(self.user32.GetAsyncKeyState(0x20) & 0x8000)
        if self._overlay_visible:
            can_toggle = bool(self._fifa_hwnd or self._overlay_hwnd)
        else:
            can_toggle = foreground in {self._fifa_hwnd, self._overlay_hwnd} and foreground != 0
        if key_down and not self._overlay_space_down and can_toggle and now >= self._overlay_toggle_ready_at:
            if self._overlay_visible:
                self._hide_overlay()
            else:
                self._show_overlay()
            self._overlay_toggle_ready_at = now + 0.22
        self._overlay_space_down = key_down
        if self._overlay_visible and not self._fifa_hwnd:
            self._hide_overlay()

    def _build_crowd_volume_window(self) -> None:
        """Create the non-activating floating crowd-volume control."""
        window = tk.Toplevel(self._window())
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=self.card)
        window.protocol("WM_DELETE_WINDOW", self._hide_crowd_volume_popup)

        frame = tk.Frame(window, bg=self.card, highlightthickness=1, highlightbackground=self.gold)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(
            frame,
            text="VOLUME DA TORCIDA",
            bg=self.card,
            fg=self.gold,
            font=("Bahnschrift", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(10, 0))
        self._crowd_volume_value_label = tk.Label(
            frame,
            text="100%",
            bg=self.card,
            fg=self.fg,
            font=("Bahnschrift", 14, "bold"),
        )
        self._crowd_volume_value_label.pack(anchor="e", padx=14, pady=(0, 2))
        self._crowd_volume_canvas = tk.Canvas(
            frame,
            width=330,
            height=24,
            bg=self.panel,
            highlightthickness=0,
        )
        self._crowd_volume_canvas.pack(fill="x", padx=14, pady=(0, 2))
        tk.Label(
            frame,
            text="Select + Start  •  D-pad / analógico esquerdo para ajustar",
            bg=self.card,
            fg=self.muted,
            font=("Bahnschrift", 8),
        ).pack(anchor="w", padx=14, pady=(0, 10))
        self._update_crowd_volume_popup()
        self._crowd_volume_window = window

    def _update_crowd_volume_popup(self) -> None:
        value = self.settings.crowd_master_volume
        percent = round(value * 100)
        if self._crowd_volume_value_label is not None:
            self._crowd_volume_value_label.configure(text=f"{percent}%")
        canvas = self._crowd_volume_canvas
        if canvas is None:
            return
        canvas.delete("all")
        width = max(1, int(canvas.winfo_width() or 330))
        height = max(1, int(canvas.winfo_height() or 24))
        left = 2
        top = 5
        right = width - 2
        bottom = height - 5
        canvas.create_rectangle(left, top, right, bottom, fill="#15243a", outline="#314b6d")
        fill_right = left + int((right - left) * (value / 2.0))
        if fill_right > left:
            canvas.create_rectangle(left, top, fill_right, bottom, fill=self.accent, outline="")
        for mark in range(1, 10):
            x = left + int((right - left) * mark / 10)
            canvas.create_line(x, top + 2, x, bottom - 2, fill="#476080")

    def _position_crowd_volume_window(self) -> None:
        window = self._crowd_volume_window
        if window is None:
            return
        window.update_idletasks()
        width = max(360, int(window.winfo_reqwidth()))
        height = max(108, int(window.winfo_reqheight()))
        rect = RECT()
        if self._fifa_hwnd and self.user32.GetWindowRect(self._fifa_hwnd, ctypes.byref(rect)):
            game_width = max(1, rect.right - rect.left)
            game_height = max(1, rect.bottom - rect.top)
            x = rect.left + max(0, (game_width - width) // 2)
            y = rect.top + max(8, game_height - height - 70)
        else:
            root = self._window()
            x = root.winfo_rootx() + max(0, (root.winfo_width() - width) // 2)
            y = root.winfo_rooty() + max(0, (root.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _show_crowd_volume_popup(self) -> None:
        window = self._crowd_volume_window
        if window is None:
            return
        self._update_crowd_volume_popup()
        self._position_crowd_volume_window()
        window.deiconify()
        window.update_idletasks()
        self._crowd_volume_hwnd = int(window.winfo_id())
        self._apply_noactivate_window_style(self._crowd_volume_hwnd)
        try:
            self.user32.ShowWindow(self._crowd_volume_hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass
        self._crowd_volume_visible = True
        self._crowd_volume_hide_at = perf_counter() + 3.0

    def _hide_crowd_volume_popup(self) -> None:
        if self._crowd_master_volume_dirty:
            try:
                self.settings.save()
            except Exception as exc:
                self.log("Failed to save crowd master volume", exc)
            self._crowd_master_volume_dirty = False
        window = self._crowd_volume_window
        if window is not None:
            try:
                window.withdraw()
            except Exception:
                pass
        self._crowd_volume_visible = False
        self._crowd_volume_hide_at = 0.0

    def _set_crowd_master_volume(self, value: float) -> None:
        value = max(0.0, min(2.0, round(float(value), 2)))
        if abs(value - self.settings.crowd_master_volume) < 0.0001:
            return
        self.settings.data["CROWD_MASTER_VOLUME"] = value
        self._crowd_master_volume_dirty = True
        self.audio_profiles.sync(force=True)
        self._update_crowd_volume_popup()

    def _adjust_crowd_master_volume(self, direction: int) -> None:
        self._set_crowd_master_volume(self.settings.crowd_master_volume + (0.05 * direction))
        self._show_crowd_volume_popup()

    def _sync_crowd_volume_controller(self) -> None:
        """Read Start+Select and adjust only the crowd audio multiplier."""
        selector = self._stadium_selector
        if selector is not None and selector.shared.enabled in (2, 3):
            self._crowd_volume_previous_buttons = 0
            self._crowd_volume_combo_latched = False
            if self._crowd_volume_visible:
                self._hide_crowd_volume_popup()
            return
        if not self._overlay_enabled:
            self._crowd_volume_previous_buttons = 0
            self._crowd_volume_start_pressed_at = 0.0
            self._crowd_volume_back_pressed_at = 0.0
            if self._crowd_volume_visible:
                self._hide_crowd_volume_popup()
            return

        if not self._fifa_hwnd:
            self._crowd_volume_previous_buttons = 0
            self._crowd_volume_combo_latched = False
            if self._crowd_volume_visible:
                self._hide_crowd_volume_popup()
            return

        sample = self._crowd_volume_gamepad.poll()
        now = perf_counter()
        buttons = sample.buttons if sample is not None else 0
        previous = self._crowd_volume_previous_buttons
        start_down = bool(buttons & XINPUT_GAMEPAD_START)
        back_down = bool(buttons & XINPUT_GAMEPAD_BACK)
        start_edge = start_down and not bool(previous & XINPUT_GAMEPAD_START)
        back_edge = back_down and not bool(previous & XINPUT_GAMEPAD_BACK)
        if start_edge:
            self._crowd_volume_start_pressed_at = now
        if back_edge:
            self._crowd_volume_back_pressed_at = now

        combo_edge = (
            (start_down and back_down and not self._crowd_volume_combo_latched)
            or (start_edge and now - self._crowd_volume_back_pressed_at <= 0.35)
            or (back_edge and now - self._crowd_volume_start_pressed_at <= 0.35)
        )
        if combo_edge:
            self._crowd_volume_combo_latched = True
            if self._crowd_volume_visible:
                self._hide_crowd_volume_popup()
            else:
                self._show_crowd_volume_popup()
        if not start_down and not back_down:
            self._crowd_volume_combo_latched = False

        direction = 0
        if buttons & XINPUT_GAMEPAD_DPAD_LEFT:
            direction = -1
        elif buttons & XINPUT_GAMEPAD_DPAD_RIGHT:
            direction = 1
        elif sample is not None and sample.left_x <= -16000:
            direction = -1
        elif sample is not None and sample.left_x >= 16000:
            direction = 1

        if self._crowd_volume_visible and direction:
            if direction != self._crowd_volume_last_direction:
                self._crowd_volume_next_adjust_at = now
            if now >= self._crowd_volume_next_adjust_at:
                self._adjust_crowd_master_volume(direction)
                self._crowd_volume_next_adjust_at = now + 0.12
        else:
            self._crowd_volume_last_direction = 0
        self._crowd_volume_last_direction = direction
        self._crowd_volume_previous_buttons = buttons

        if self._crowd_volume_visible and now >= self._crowd_volume_hide_at:
            self._hide_crowd_volume_popup()

    def _apply_noactivate_window_style(self, hwnd: int) -> None:
        if not hwnd:
            return
        try:
            ex_style = int(self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            ex_style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            self.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            self.user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def _apply_overlay_window_style(self) -> None:
        self._apply_noactivate_window_style(self._overlay_hwnd)

    def _focus_fifa_window(self) -> None:
        if not self._fifa_hwnd:
            return
        try:
            self.user32.ShowWindow(self._fifa_hwnd, SW_RESTORE)
        except Exception:
            pass
        try:
            self.user32.SetForegroundWindow(self._fifa_hwnd)
        except Exception:
            pass

    def _show_overlay(self) -> None:
        if not self._fifa_hwnd:
            return
        window = self._window()
        self._launcher_mode = False
        self._restore_fullscreen_on_hide = self._is_probable_fullscreen_window(self._fifa_hwnd)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.deiconify()
        window.update_idletasks()
        self._overlay_hwnd = window.winfo_id()
        self._apply_overlay_window_style()
        self._position_overlay()
        try:
            self.user32.ShowWindow(self._overlay_hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass
        self.after(10, self._focus_fifa_window)
        self._overlay_visible = True
        self._set_process_status(self.status_text("overlay_visible"), self.success)

    def _hide_overlay(self) -> None:
        window = self._window()
        self._overlay_visible = False
        if self._overlay_hwnd:
            try:
                self.user32.ShowWindow(self._overlay_hwnd, SW_HIDE)
            except Exception:
                pass
        window.withdraw()
        self._set_process_status(self.status_text("overlay_hidden"), self.gold if self._overlay_enabled else self.accent)
        self.after(10, self._focus_fifa_window)
        if self._restore_fullscreen_on_hide:
            self.after(120, self._restore_fifa_fullscreen)

    def _position_overlay(self) -> None:
        if not self._fifa_hwnd:
            return
        window = self._window()
        rect = RECT()
        if not self.user32.GetWindowRect(self._fifa_hwnd, ctypes.byref(rect)):
            return
        game_width = max(1, rect.right - rect.left)
        game_height = max(1, rect.bottom - rect.top)
        overlay_width = min(game_width - 24, max(980, int(game_width * 0.86)))
        overlay_height = min(max(360, int(game_height * 0.58)), game_height - 24)
        x = rect.left + max(0, (game_width - overlay_width) // 2)
        y = rect.top + 8
        window.geometry(f"{overlay_width}x{overlay_height}+{x}+{y}")
        if self._overlay_hwnd:
            try:
                self.user32.SetWindowPos(
                    self._overlay_hwnd,
                    HWND_TOPMOST,
                    x,
                    y,
                    overlay_width,
                    overlay_height,
                    SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
            except Exception:
                pass

    def _is_probable_fullscreen_window(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        rect = RECT()
        if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        screen_width = max(1, int(self.user32.GetSystemMetrics(0)))
        screen_height = max(1, int(self.user32.GetSystemMetrics(1)))
        tolerance = 8
        return abs(width - screen_width) <= tolerance and abs(height - screen_height) <= tolerance

    def _restore_fifa_fullscreen(self) -> None:
        if not self._fifa_hwnd:
            return
        self._focus_fifa_window()
        try:
            self.user32.keybd_event(VK_MENU, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, 0, 0)
            self.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            self.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            self.log("Attempted fullscreen restore with Alt+Enter")
        except Exception as exc:
            self.log("Failed to restore FIFA fullscreen", exc, exc_info=sys.exc_info())
        finally:
            self._restore_fullscreen_on_hide = False
            self.after(180, self._focus_fifa_window)

    def _find_fifa_window_handle(self) -> int:
        pid = self._resolve_fifa_pid()
        if not pid:
            return 0
        matches: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def enum_proc(hwnd, _lparam):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            owner_pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value == pid:
                rect = RECT()
                if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    if rect.right > rect.left and rect.bottom > rect.top:
                        matches.append(int(hwnd))
                        return False
            return True

        self.user32.EnumWindows(enum_proc, 0)
        return matches[0] if matches else 0

    def _resolve_fifa_pid(self) -> int:
        if self.memory.process_id and self.memory.is_open():
            return int(self.memory.process_id)
        if not self.MP:
            return 0
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if Path((proc.info.get("name") or "")).stem.lower() == self.MP.lower():
                    return int(proc.info["pid"])
        except Exception:
            return 0
        return 0

    def apply_bootstrap_files(self) -> None:
        if self.fifaEXE == "default":
            return
        started_at = perf_counter()
        self.version = checkver(self.fifaEXE)
        self.log(f"Applying bootstrap files for version: {self.version}")
        for path in (
            self.Pdest,
            self.Ndest,
            self.PitchMowdest,
            self.TVdata,
            self.Scoredata / "game",
            self.exedir / "data" / "sceneassets" / "stadium",
            self.exedir / "data" / "sceneassets" / "fx",
            self.exedir / "data" / "sceneassets" / "crowdplacement",
            self.exedir / "data" / "sceneassets" / "crowdchair",
            self.exedir / "data" / "bcdata" / "camera",
            self.exedir / "data" / "ui" / "nav",
            self.exedir / "data" / "ui" / "TV",
            self.exedir / "data" / "movies",
        ):
            checkdirs(path)
        extra_setup(self.Psource, self.Pdest, "4", "4", "4")
        extra_setup(self.Psource, self.Pdest, "9", "9", "9")
        extra_setup(self.Nsource, self.Ndest, "0", "netcolor", "0")
        extra_setup(self.PitchMowsource, self.PitchMowdest, "0", "pitchmowpattern", "0")
        copy(self.exedir / "FSW" / "stadium", self.exedir / "data" / "sceneassets")
        copy(self.exedir / "FSW" / "TVLogo", self.TVdata)
        copy(self.exedir / "FSW" / "ScoreBoard", self.Scoredata / "game")
        if self.module_enabled("Movies"):
            copy_if_exists(self.exedir / "FSW" / "Nav" / "pausemenuflow.nav_new", self.exedir / "data" / "ui" / "nav" / "pausemenuflow.nav")
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bootflowoutro.vp8", self.Movdata)
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bumper.big", self.MOVBUMP)
        else:
            copy_if_exists(self.exedir / "FSW" / "Nav" / "pausemenuflow.nav_Original", self.exedir / "data" / "ui" / "nav" / "pausemenuflow.nav")
            copy_if_exists(self.exedir / "FSW" / "Nav" / "Fbootflowoutro.vp8", self.Movdata)
            copy_if_exists(self.exedir / "FSW" / "Nav" / "bumper.big", self.MOVBUMP)
        self._update_audio_overview()
        self.log(f"Bootstrap files ready in {perf_counter() - started_at:.2f}s")

    def refresh_modules(self) -> None:
        self._load_module_states()
        for name, var in self.module_vars.items():
            if name == "DiscordRPC":
                var.set(self._discord_rpc_enabled)
            else:
                var.set(self.module_enabled(name))
        self._update_audio_overview()

    def toggle_module(self, module: str) -> None:
        if module in self.module_vars:
            self.module_vars[module].set(self.module_enabled(module))

    def _on_module_toggle(self, name: str, var: tk.BooleanVar) -> None:
        """Called when user clicks a module toggle. Saves state to settings.ini."""
        enabled = var.get()
        if name == "ClothPhysics":
            switch=ClothMotionSwitch(self.exedir)
            try:
                switch.set_enabled(enabled)
            except (OSError,ValueError) as exc:
                var.set(switch.enabled())
                self.log("Cloth physics pre-launch switch failed",exc)
                messagebox.showerror(self.tr("module.cloth_physics"),str(exc),parent=self)
                return
            self.module_states[name]=enabled
            self.log(f"Cloth physics {'enabled' if enabled else 'disabled'}; live control and next launch updated")
            return
        self.settings_ini.write(name, "1" if enabled else "0", "Modules")
        self.settings_ini.save()
        self.module_states[name] = enabled
        if name == "TeamEntrance" and not enabled:
            self.entrance_runtime.reset()
        self.log(f"Module '{name}' {'enabled' if enabled else 'disabled'} by user")

    def poll_process(self) -> None:
        if self._closing:
            return
        try:
            if not self.offsets.is_configured():
                self._sync_page_banner("Offsets nao configurados na classe Offsets")
                self._set_process_status(self.status_text("offsets_missing"), self.error)
                self.log("Offsets are not configured")
                self._poll_job = self.after(500, self.poll_process)
                return
            running = bool(self.MP) and any(Path((p.info.get("name") or "")).stem.lower() == self.MP.lower() for p in psutil.process_iter(["name"]))
            attached = running and self.memory.attack(self.MP)
            diagnostics = getattr(self, '_startup_diagnostics', None)
            if running and diagnostics and self.memory.process_id:
                diagnostics.attach(self.memory.process_id, self.fifaEXE)
            if attached:
                self._attached_once = True
                self._set_process_status(self.status_text("fifa_attached"), self.success)
                self.update_page_name()
            else:
                self._sync_page_banner("Process not running")
                self._set_process_status(self.status_text("waiting_fifa"), self.accent)
                if self._attached_once:
                    self._match_audio_ended = True
                    self._reset_team_entrance()
                    self._reset_chants_state()
                    if self.settings.keep_open_on_game_close:
                        self.log("Game process ended; keeping server open")
                        self._restore_native_runtime_assets()
                        self.memory.close()
                        self._attached_once = False
                        self._clear_live_context()
                        self._reset_team_entrance()
                        self._reset_chants_state()
                    else:
                        self.log("Game process ended; closing server automatically")
                        self.on_close()
                        return
                self._reset_team_entrance()
                self._reset_chants_state()
        except Exception as exc:
            self._sync_page_banner(f"Polling error: {exc}")
            self._set_process_status(self.status_text("polling_error"), self.error)
            self.log("Polling error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._poll_job = self.after(500, self.poll_process)

    def stats_loop(self) -> None:
        if self._closing:
            return
        try:
            if self.memory.is_open():
                page_name = self.labels["page"].cget("text") if "page" in self.labels else self.lastpagename
                self._update_live_match_stats(page_name)
                # Only refresh context when HID/AID are missing or context was
                # never captured. Once we have both IDs, avoid calling
                # refresh_live_context from the stats loop — it would re-trigger
                # apply_all_runtime and re-roll the random stadium every 250ms.
                missing_ids = not self.HID or not self.AID
                no_signature = self._last_runtime_signature is None
                if (missing_ids or no_signature) and self._page_can_have_match_context(page_name):
                    self.refresh_live_context(page_name)
            # Update DiscordRPC presence
            if self._discord_rpc_enabled:
                self._update_discord_presence()
        except Exception as exc:
            self.log("Stats loop error", exc, exc_info=sys.exc_info())
        if not self._closing:
            self._stats_job = self.after(250, self.stats_loop)

    def update_page_name(self) -> None:
        try:
            page_name = self.memory.get_string(self.offsets.ORIPGBASE, self.offsets.PG1, size=64)
            diagnostics = getattr(self, '_startup_diagnostics', None)
            if diagnostics:
                diagnostics.page_seen(page=page_name)
            pending = getattr(self, '_page_read_pending', 0)
            if pending:
                self.log(f'Page reader ready after {pending} pending reads')
                self._page_read_pending = 0
            self._sync_page_banner(page_name)
            self._handle_page_transition(page_name)
            if self._page_can_have_match_context(page_name):
                self.refresh_live_context(page_name)
        except Exception as exc:
            self._sync_page_banner(f"Offset pending: {exc}")
            self._set_process_status(self.status_text("reading_page"), self.gold)
            diagnostics = getattr(self, '_startup_diagnostics', None)
            if diagnostics:
                diagnostics.page_seen(error=exc)
            self._page_read_pending = getattr(self, '_page_read_pending', 0) + 1
            now = time.monotonic()
            if self._page_read_pending == 1 or now-getattr(self, '_page_read_log_at', 0) >= 10:
                self._page_read_log_at = now
                self.log(f'Page reader pending ({self._page_read_pending} attempts): {exc}')

    def _handle_page_transition(self, page_name: str) -> None:
        if page_name == self.lastpagename:
            return
        previous_page = self.lastpagename
        self.log(f"Page transition: {previous_page or '<startup>'} -> {page_name}")
        self.lastpagename = page_name
        had_match_context = bool(self.HID or self.AID or self._last_runtime_signature is not None or self.matchstarted)
        if outside_match_page(page_name):
            self._match_audio_ended = True
            # Request audio teardown BEFORE potentially slow asset restoration.
            self._reset_chants_state()
            self._reset_team_entrance()
        if self._is_post_match_page(page_name) and not self._native_assets_restored_for_match:
            if had_match_context:
                self._restore_native_runtime_assets()
                self._native_assets_restored_for_match = True
        if page_name == "game/screens/playNow/KickOffHub":
            if (self.stadium_runtime.keep_manual_selection_on_setup_return(previous_page) or
                (getattr(self,'_stadium_selector',None) is not None and
                 self._stadium_selector.keep_crowd_on_setup_return(previous_page))):
                self.pagechange = True
                self.skillgamechange = self.bumperpagechange = False
                self.log('Returned to pre-match setup; keeping stadium for the same fixture')
                return
            self._match_audio_ended = False
            self._stadium_fixture_entered = False
            self._manual_stadium_override = None
            self._kickoff_generation += 1
            self._native_assets_restored_for_match = False
            self._last_stadium_applied_signature = None
            self.pagechange = True
            self.skillgamechange = False
            self.bumperpagechange = False
            self._clear_live_context()
            self._kickoff_retry_remaining = 12
            self._schedule_kickoff_retry()
            # Stop any audio still playing from the previous match
            self._reset_team_entrance()
            self._reset_chants_state()
            return
        if "training/SkillGame" in page_name:
            self.skillgamechange = True
            return
        if not page_name.strip() and not self.matchstarted and not self.skillgamechange and not self._match_audio_ended:
            self._start_chants_runtime()
            # The FIFA "started" flag becomes true during the walkout, before
            # the real kick-off.  Arm the crowd guard only when an entrance
            # worker was actually scheduled; otherwise normal crowd audio
            # must remain available when the feature is disabled or unmapped.
            self._entrance_armed = False
            self._entrance_pre_match_guard = False
            self._entrance_pre_match_guard_set_at = 0.0
            if self.module_enabled("TeamEntrance") and self._start_team_entrance():
                self._entrance_armed = True
                self._entrance_pre_match_guard = True
                self._entrance_pre_match_guard_set_at = time.time()
            return
        if "TV/bumper" in page_name or "skillGames/SkillGa" in page_name:
            if "TV/bumper" in page_name:
                self._match_audio_ended = False
                self._stadium_fixture_entered = True
            if not self.bumperpagechange and not self.skillgamechange:
                self.pagechange = False
                self.bumperpagechange = True
                self.skillgamechange = True
                self.tv_bumper_page()
                # Patch the match string in memory now that the bumper is loading
                # — this is the last moment before FIFA renders the stadium name
                if self.curstad:
                    if self.settings_ini.key_exists(self.curstad, "scoreboardstdname"):
                        raw = self.settings_ini.read(self.curstad, "scoreboardstdname")
                        std_name = raw.split(",")[0].strip() or self.curstad
                    else:
                        std_name = self.curstad
                    patch_match_string(self, std_name)
            return
        self.pagechange = False
        self.bumperpagechange = False
        self.skillgamechange = False

    @staticmethod
    def _is_post_match_page(page_name: str) -> bool:
        return post_match_page(page_name)

    def _clear_live_context(self) -> None:
        if getattr(self, 'entrance_props_runtime', None) is not None:
            self.entrance_props_runtime.clear_context()
        self.HID = ""
        self.AID = ""
        self.audio_profiles.sync()
        self.STADID = ""
        self.TOURNAME = ""
        self.TOURROUNDID = ""
        self.derby = ""
        self.StadName = ""
        self._last_runtime_signature = None
        self._last_live_score = (0, 0)
        self._last_score_snapshot = (0, 0)
        self._last_chants_score_snapshot = None
        self._chants_resume_after = 0.0
        self._chants_last_track = None
        self._chants_last_goal_time = 0.0
        self._last_live_update = ""
        self._set_display("hid", "-")
        self._set_display("aid", "-")
        self._set_display("tour", "-")
        self._set_display("round", "-")
        self._set_display("derby", "-")
        self._set_display("stadid", "-")
        self._set_display("stadium", "-")
        self._set_display("home_name", self.tr("team.a"))
        self._set_display("away_name", self.tr("team.b"))
        self._update_team_logo("home", "")
        self._update_team_logo("away", "")
        self._set_display("score", "0 x 0")
        self._set_display("timer", "00:00")
        self._set_display("home_goals", "0")
        self._set_display("away_goals", "0")
        self._set_display("match_clock_split", "00 / 00")
        self._set_display("game_state", self.display_value("idle"))
        self._set_display("goal_active", self.display_value("no"))
        self._set_display("last_update", "-")

    def _schedule_kickoff_retry(self) -> None:
        if self._closing or self._kickoff_retry_job is not None:
            return
        self._kickoff_retry_job = self.after(250, self._kickoff_retry_tick)

    def _kickoff_retry_tick(self) -> None:
        self._kickoff_retry_job = None
        if self._closing:
            return
        page_name = self.labels["page"].cget("text")
        if page_name != "game/screens/playNow/KickOffHub":
            self._kickoff_retry_remaining = 0
            return
        self.refresh_live_context(page_name)
        if self.HID not in {"", "0"} and self.AID not in {"", "0"}:
            self._kickoff_retry_remaining = 0
            self.log(f"KickOffHub context captured HID={self.HID} AID={self.AID}")
            return
        if self._kickoff_retry_remaining > 0:
            self._kickoff_retry_remaining -= 1
            self._schedule_kickoff_retry()

    def _page_can_have_match_context(self, page_name: str) -> bool:
        if not page_name:
            return False
        candidates = (
            "KickOffHub",
            "playNow",
            "team",
            "squad",
            "stadium",
            "TV/bumper",
        )
        lowered = page_name.lower()
        return any(token.lower() in lowered for token in candidates)

    def _read_legacy_team_context(self) -> tuple[str | None, str | None]:
        if not self.MP:
            return None, None
        legacy_memory = Memory()
        try:
            if not legacy_memory.attack(self.MP) or not legacy_memory.is_open():
                return None, None
            hid = str(legacy_memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:5]))
            aid = str(legacy_memory.get_int(self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]]))
            if hid == "0":
                friendly_hid = str(legacy_memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5]))
                friendly_aid = str(legacy_memory.get_int(self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]]))
                if friendly_hid != "0":
                    hid = friendly_hid
                if friendly_aid != "0":
                    aid = friendly_aid
            return hid, aid
        except Exception as exc:
            self.log("Legacy team context read failed", exc, exc_info=sys.exc_info())
            return None, None
        finally:
            legacy_memory.close()

    def refresh_live_context(self, page_name: str) -> None:
        hid, aid = self._read_legacy_team_context()
        if hid is None:
            hid = self._try_read_context_int("HT-HID", self.offsets.ORIHTIDBASE, self.offsets.HT, page_name)
        if aid is None:
            aid = self._try_read_context_int("HT-AID", self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]], page_name)
        dashboard_hid = self._read_dashboard_pointer("DASHBOARDHOMEIDBASE", "DASHBOARDHOMEID")
        dashboard_aid = self._read_dashboard_pointer("DASHBOARDAWAYIDBASE", "DASHBOARDAWAYID")
        if hid in {"0", None} or aid in {"0", None}:
            friendly_hid = self._try_read_context_int("HT2-HID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5], page_name)
            friendly_aid = self._try_read_context_int("HT2-AID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]], page_name)
            if hid in {"0", None} and friendly_hid not in {None, "0"}:
                hid = friendly_hid
            if aid in {"0", None} and friendly_aid not in {None, "0"}:
                aid = friendly_aid
        if hid in {"0", None} and dashboard_hid not in {None, 0}:
            hid = str(dashboard_hid)
        if aid in {"0", None} and dashboard_aid not in {None, 0}:
            aid = str(dashboard_aid)
        self.Stadiumtype = "first"
        stadid = self._try_read_context_int(
            "S-FIRST",
            self.offsets.ORISTADIDBASE,
            [self.offsets.S[0], self.offsets.S[1], self.offsets.S[2], self.offsets.S[4], self.offsets.S[5]],
            page_name,
        )
        if stadid == "0" or stadid is None:
            alter = self._try_read_context_int(
                "S-ALTER",
                self.offsets.ORISTADIDBASE,
                [self.offsets.S[0], self.offsets.S[1], self.offsets.S[3], self.offsets.S[4], self.offsets.S[5]],
                page_name,
            )
            if alter is not None:
                stadid = alter
                self.Stadiumtype = "alter"
        tour = self._try_read_context_int("T-TOUR", self.offsets.ORITOURIDBASE, self.offsets.T[:5], page_name)
        round_id = self._try_read_context_int("T-ROUND", self.offsets.ORITOURIDBASE, self.offsets.T[:4] + [self.offsets.T[5]], page_name)
        if hid not in {None, "0"}:
            self.HID = hid
        if aid not in {None, "0"}:
            self.AID = aid
        self.audio_profiles.sync()
        if stadid not in {None, "0"}:
            self.STADID = stadid
        if tour not in {None, "0"}:
            self.TOURNAME = tour
        if round_id not in {None, "0"}:
            self.TOURROUNDID = round_id
        if not any(value for value in (self.HID, self.AID, self.STADID, self.TOURNAME, self.TOURROUNDID)):
            return
            return
        self.derby = f"{self.HID}vs{self.AID}"
        self._set_display("hid", self.HID or "-")
        self._set_display("aid", self.AID or "-")
        self._update_team_logo("home", self.HID or "")
        self._update_team_logo("away", self.AID or "")
        self._set_display("tour", self.TOURNAME or "-")
        self._set_display("round", self.TOURROUNDID or "-")
        self._set_display("derby", self.derby or "-")
        self._set_display("stadid", self.STADID or "-")
        home_name = self._resolve_team_name(self.HID or "")
        away_name = self._resolve_team_name(self.AID or "")
        self._set_display("home_name", home_name or (f"{self.tr('team.a')} ({self.HID})" if self.HID else self.tr("team.a")))
        self._set_display("away_name", away_name or (f"{self.tr('team.b')} ({self.AID})" if self.AID else self.tr("team.b")))
        self._update_live_match_stats(page_name)
        # STADID is intentionally excluded from the signature: it reflects the
        # stadium currently loaded in FIFA memory and fluctuates while the game
        # boots, which would otherwise re-trigger apply_all_runtime on every
        # memory read and cause the random stadium to keep re-rolling.
        signature = (self.HID, self.AID, self.TOURNAME, self.TOURROUNDID)
        if signature != self._last_runtime_signature:
            self._last_runtime_signature = signature
            self.log(
                f"Live context updated page={page_name} HID={self.HID or '-'} AID={self.AID or '-'} "
                f"TOUR={self.TOURNAME or '-'} ROUND={self.TOURROUNDID or '-'} STAD={self.STADID or '-'}"
            )
            if self._should_auto_apply_runtime(page_name):
                self.apply_all_runtime()

    def _try_read_context_int(self, trace_name: str, static_ptr: int, offsets: list[int], page_name: str) -> str | None:
        try:
            value = str(self.memory.get_int(static_ptr, offsets))
            self._last_context_error = None
            return value
        except MemoryAccessError as exc:
            message = f"Context not ready for page '{page_name}' [{trace_name}]: {exc}"
            if message != self._last_context_error:
                self._last_context_error = message
                self.log(message)
                self._log_pointer_debug()
            return None
        except Exception as exc:
            self.log(f"Failed to read context {trace_name}", exc, exc_info=sys.exc_info())
            return None

    def _try_read_optional_int(self, static_ptr: int, offsets: list[int]) -> int | None:
        try:
            if not static_ptr or not offsets or not any(offsets):
                return None
            return self.memory.get_int(static_ptr, offsets)
        except Exception:
            return None

    def _read_dashboard_pointer(self, base_attr: str, offsets_attr: str) -> int | None:
        static_ptr = getattr(self.offsets, base_attr, 0)
        offsets = getattr(self.offsets, offsets_attr, [])
        if not static_ptr or not offsets or not any(offsets):
            return None
        return self._try_read_optional_int(static_ptr, offsets)

    def _is_game_running(self) -> bool:
        return self._is_game_running_with(self.memory)

    def _is_game_running_with(self, memory: Memory) -> bool:
        if self._match_audio_ended or outside_match_page(self.lastpagename) or pause_page(self.lastpagename):
            return False
        try:
            started = memory.get_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
            ran_time = memory.get_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            return started == 1 and ran_time >= 1
        except Exception:
            return False

    def _update_live_match_stats(self, page_name: str) -> None:
        score_home = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMEHOMEGOALSCORE)
        score_away = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMEAWAYGOALSCORE)
        raw_time = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
        started = self._try_read_optional_int(self.offsets.GAMESTARTEDBINARYBASE, self.offsets.GAMESTARTEDBINARY)
        if score_home is not None and score_away is not None:
            if (score_home, score_away) != self._last_live_score:
                self._chants_resume_after = max(self._chants_resume_after, time.time() + 6.0)
                self._last_live_score = (score_home, score_away)
        score_home_display = score_home if score_home is not None else 0
        score_away_display = score_away if score_away is not None else 0
        self._set_display("home_goals", str(score_home_display))
        self._set_display("away_goals", str(score_away_display))
        self._set_display("score", f"{score_home_display} x {score_away_display}")
        if raw_time is None:
            minutes = 0
            seconds = 0
        else:
            total_seconds = raw_time // 100 if raw_time > 6000 else raw_time
            minutes, seconds = divmod(max(0, total_seconds), 60)
        self._set_display("timer", f"{max(0, minutes):02d}:{max(0, seconds):02d}")
        self._set_display("match_clock_split", f"{max(0, minutes):02d} / {max(0, seconds):02d}")
        goal_active = time.time() < self._chants_resume_after
        if started == 1 and raw_time and raw_time >= 1:
            game_state = self.display_value("running")
        elif self.matchstarted or self._chants_paused:
            game_state = self.display_value("paused")
        else:
            game_state = self.display_value("idle")
        self._set_display("game_state", game_state)
        self._set_display("goal_active", self.display_value("yes") if goal_active else self.display_value("no"))
        self._last_live_update = datetime.now().strftime("%H:%M:%S")
        self._set_display("last_update", self._last_live_update)
        if "TV/bumper" in page_name:
            self._set_display("audio_last_action", self.display_value("tv_bumper_active"))

    def _on_stadium_preview_uploaded(self, stadium_name: str, url: str) -> None:
        """Called after a stadium preview is uploaded to Discord webhook.
        Forces a DiscordRPC refresh so the new image URL is applied immediately."""
        self.log(f"Discord stadium preview uploaded: {stadium_name} -> {url}")
        self._post_ui(setattr,self,'_discord_rpc_last_presence',None)

    def _update_discord_presence(self) -> None:
        """Update Discord Rich Presence with current match state."""
        # Only update if DiscordRPC is enabled
        if not self._discord_rpc_enabled:
            return
        
        try:
            if not self.discord_rpc.is_connected():
                # Try to reconnect if not connected
                self.discord_rpc.connect()
            
            page_name = self.labels.get("page", tk.Label()).cget("text") if "page" in self.labels else self.lastpagename
            
            # Get current match state
            score_home = self.labels.get("home_goals", tk.Label()).cget("text") if "home_goals" in self.labels else "0"
            score_away = self.labels.get("away_goals", tk.Label()).cget("text") if "away_goals" in self.labels else "0"
            # Read match time directly from memory to avoid stale UI label values.
            match_time = "00:00"
            raw_time = self._try_read_optional_int(self.offsets.GAMESTATSBASE, self.offsets.GAMERANTIME)
            if raw_time is not None:
                total_seconds = raw_time // 100 if raw_time > 6000 else raw_time
                minutes, seconds = divmod(max(0, total_seconds), 60)
                match_time = f"{minutes:02d}:{seconds:02d}"
            elif "timer" in self.labels:
                match_time = self.labels.get("timer", tk.Label()).cget("text")
            game_state = self.labels.get("game_state", tk.Label()).cget("text") if "game_state" in self.labels else "Idle"
            pause_menu_tokens = ("fluxhub", "stadiumpan")
            if any(token in (page_name or "").lower() for token in pause_menu_tokens):
                # These pages are in-match pause hubs, so expose paused explicitly to RPC.
                game_state = "paused"
            custom_stadium_display = ""
            if self._has_active_custom_stadium_assignment():
                custom_stadium_display = (
                    self.ScoreboardStadName
                    or self.curstad
                    or getattr(self, "StadName", "")
                )
            stadium_display = custom_stadium_display or self._resolve_stadium_name(self.STADID) or ""

            # Resolve stadium preview URL via uploader (non-blocking)
            stadium_image_url: str | None = None
            if self._stadium_preview_uploader is not None:
                candidate_names = []
                for name in [self.curstad, custom_stadium_display, stadium_display]:
                    norm = (name or "").strip()
                    if norm and norm not in candidate_names:
                        candidate_names.append(norm)

                resolved_name = ""
                preview_path = None
                for candidate_name in candidate_names:
                    preview_path = self._resolve_stadium_preview_path(candidate_name)
                    if preview_path is not None:
                        resolved_name = candidate_name
                        break

                if preview_path is not None and resolved_name:
                    cached = self._stadium_preview_uploader.get_cached_url(resolved_name)
                    if cached:
                        stadium_image_url = cached
                    else:
                        self._stadium_preview_uploader.get_or_upload(resolved_name, preview_path)
                        # Upload is async; stadium_image_url stays None until callback fires

            discord_rpc_config = self.settings.data.get("discord_rpc", {})
            stadium_preview_mode = discord_rpc_config.get("stadium_preview_mode", "button_fallback")
            stadium_preview_override_url = (discord_rpc_config.get("stadium_preview_override_url", "") or "").strip()
            if stadium_preview_override_url:
                stadium_image_url = stadium_preview_override_url

            # Build presence using helper
            presence = self.discord_rpc.build_match_presence(
                home_team=self.HID or "",
                away_team=self.AID or "",
                home_score=int(score_home) if score_home.isdigit() else 0,
                away_score=int(score_away) if score_away.isdigit() else 0,
                match_time=match_time,
                tournament=self.TOURNAME or "",
                round_name=self.TOURROUNDID or "",
                stadium=stadium_display,
                game_state=game_state,
                stadium_image_url=stadium_image_url,
                external_image_mode=stadium_preview_mode,
            )
            
            # Only update if presence changed (reduce API calls)
            if presence != self._discord_rpc_last_presence:
                sent = self.discord_rpc.update_presence(**presence)
                self._discord_rpc_last_presence = presence
                # Log DiscordRPC updates for debugging
                self.log(f"DiscordRPC updated: {presence.get('state', 'N/A')}")
                self.log(f"DiscordRPC image key: {presence.get('large_image', '')}")
                self.log(f"DiscordRPC external image mode: {stadium_preview_mode}")
                if stadium_preview_override_url:
                    self.log(f"DiscordRPC external image override URL: {stadium_preview_override_url}")
                if sent:
                    self.log("DiscordRPC update_presence result: ok")
                else:
                    self.log("DiscordRPC update_presence result: failed")
        except Exception as exc:
            self.log("Discord RPC update error", exc, exc_info=sys.exc_info())

    def _log_pointer_debug(self) -> None:
        traces = [
            ("HT-HID", self.offsets.ORIHTIDBASE, self.offsets.HT),
            ("HT-AID", self.offsets.ORIHTIDBASE, self.offsets.HT[:4] + [self.offsets.HT[5]]),
            ("HT2-HID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:5]),
            ("HT2-AID", self.offsets.ORIFRIHTIDBASE, self.offsets.HT2[:4] + [self.offsets.HT2[5]]),
            ("S-FIRST", self.offsets.ORISTADIDBASE, [self.offsets.S[0], self.offsets.S[1], self.offsets.S[2], self.offsets.S[4], self.offsets.S[5]]),
            ("S-ALTER", self.offsets.ORISTADIDBASE, [self.offsets.S[0], self.offsets.S[1], self.offsets.S[3], self.offsets.S[4], self.offsets.S[5]]),
            ("T-TOUR", self.offsets.ORITOURIDBASE, self.offsets.T[:5]),
            ("T-ROUND", self.offsets.ORITOURIDBASE, self.offsets.T[:4] + [self.offsets.T[5]]),
        ]
        for name, static_ptr, offsets in traces:
            try:
                chain = self.memory.trace_pointer_chain(static_ptr, offsets)
                self.log(f"Pointer trace {name}\n" + "\n".join(chain))
            except Exception as exc:
                self.log(f"Pointer trace {name} failed", exc, exc_info=sys.exc_info())

    def apply_all_runtime(self) -> None:
        self.log(f"Applying runtime HID={self.HID} AID={self.AID} TOUR={self.TOURNAME} ROUND={self.TOURROUNDID} STAD={self.STADID}")
        self._set_progress(5, "Applying runtime")
        self.entrance_props_runtime.prepare_match()
        if self.module_enabled("Stadium"):
            self.apply_stadium_runtime()
        else:
            self._set_display("stadium", "Stadium Module Disable")
            # Clear stadium from previous match when module is disabled
            self.curstad = ""
            self.ScoreboardStadName = ""
        self.apply_scoreboard_runtime()
        self.apply_movie_runtime()
        if not self._stadium_task_running:
            self._set_progress(100, "Runtime ready")

    def apply_stadium_runtime(self) -> None:
        self.stadium_runtime.apply_stadium_runtime()

    def _start_stadium_task(
        self,
        section_id: str,
        section_name: str,
        injid: str,
        stadium_signature: tuple,
        task_request_key: tuple[str, str, str],
        chosen_stadium: str | None = None,
    ) -> None:
        self.stadium_runtime.start_stadium_task(
            section_id,
            section_name,
            injid,
            stadium_signature,
            task_request_key,
            chosen_stadium=chosen_stadium,
        )

    def _run_stadium_copy_job(
        self,
        hid: str,
        section: str,
        injid: str,
        chosen_stadium: str | None = None,
    ) -> dict:
        return self.stadium_runtime.run_stadium_copy_job(
            hid,
            section,
            injid,
            chosen_stadium=chosen_stadium,
        )

    def _finish_stadium_apply(self, payload: dict) -> None:
        self.stadium_runtime.finish_stadium_apply(payload)

    def _stadium_offsets(self, stadium_type: str) -> list[int]:
        return self.stadium_runtime.stadium_offsets(stadium_type)

    def _play_stadium_loaded_sound(self) -> None:
        self.stadium_runtime.play_stadium_loaded_sound()

    def _update_audio_overview(self) -> None:
        self.assets_runtime.update_audio_overview()

    def apply_scoreboard_runtime(self) -> None:
        self.assets_runtime.apply_scoreboard_runtime()

    def apply_movie_runtime(self) -> None:
        self.assets_runtime.apply_movie_runtime()

    def tv_bumper_page(self) -> None:
        self.assets_runtime.tv_bumper_page()

    def _start_chants_runtime(self) -> None:
        self.chants_runtime.start_chants_runtime()

    def _start_team_entrance(self) -> bool:
        return self.entrance_runtime.start_for_match()

    def _restore_native_runtime_assets(self) -> None:
        try:
            restored = restore_native_assets(self)
            self.log(f"Native runtime assets restored from FSW ({restored} source files processed; not a changed-file count)")
        except Exception as exc:
            self.log("Failed to restore native runtime assets", exc, exc_info=sys.exc_info())

    def _reset_chants_state(self) -> None:
        self.chants_runtime.reset_chants_state()

    def _reset_team_entrance(self) -> None:
        self.entrance_runtime.reset()

    def _fade_player(self, player: MciAudioPlayer, start: float, end: float, duration_ms: int) -> None:
        self.chants_runtime.fade_player(player, start, end, duration_ms)

    def _play_club_song_if_exists(self, team_id: str) -> None:
        # Compatibility wrapper kept for legacy call sites.
        self.chants_runtime._play_club_song(team_id)

    def _chants_runtime_loop(self) -> None:
        self.chants_runtime.chants_runtime_loop()

    def _refresh_context_for_assignment(self) -> None:
        self.assignment_runtime.refresh_context_for_assignment()

    def _default_scope_for_scoreboard(self) -> str:
        return self.assignment_runtime.default_scope_for_scoreboard()

    def _default_scope_for_movie(self) -> str:
        return self.assignment_runtime.default_scope_for_movie()

    def _default_scope_for_stadium(self) -> str:
        return self.assignment_runtime.default_scope_for_stadium()

    def _resolve_assignment_target(self, scope: str, mapping: dict[str, tuple[str, str]]) -> tuple[str, str] | tuple[None, None]:
        return self.assignment_runtime.resolve_assignment_target(scope, mapping)

    def assign_scoreboard(self) -> None:
        self.assignment_runtime.assign_scoreboard()

    def assign_movie(self) -> None:
        self.assignment_runtime.assign_movie()

    def assign_stadium(self) -> None:
        self.assignment_runtime.assign_stadium()

    def exclude_competition(self) -> None:
        self.assignment_runtime.exclude_competition()

    def scoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assignment_runtime.scoreboards(comp, tvlogo, scoreboard)

    def teamscoreboards(self, comp: str, tvlogo: str, scoreboard: str) -> None:
        self.assignment_runtime.teamscoreboards(comp, tvlogo, scoreboard)

    def moviesassign(self, comp: str, movie: str, section: str) -> None:
        self.assignment_runtime.moviesassign(comp, movie, section)

    def assignstadium_value(self, comp: str, value: str, section: str) -> None:
        self.assignment_runtime.assignstadium_value(comp, value, section)

    def assigncompstadium(self, comp: str, value: str, section: str) -> None:
        self.assignment_runtime.assigncompstadium(comp, value, section)

    def _assign_with_delete(self, comp: str, key: str, value: str, default_value: str, success_message: str) -> None:
        self.assignment_runtime.assign_with_delete(comp, key, value, default_value, success_message)

    def _dismiss_launch_splash(self) -> None:
        splash, self._launch_splash = self._launch_splash, None
        if splash is not None:
            try:
                splash.close(wait=False)
            except Exception:
                pass

    def _show_closing_splash(self):
        try:
            from .splash import SplashScreen

        except Exception:
            return None
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                try:
                    child.withdraw()
                except Exception:
                    pass
        try:
            return SplashScreen(self.tr("splash.closing"),master=self)
        except Exception:
            return None

    def on_close(self) -> None:
        if self._closing:
            return
        # Do not interrupt a BIG/BH or stadium write to force the UI closed.
        if (getattr(self, '_stadium_task_running', False) or getattr(self, '_bh_regen_running', False)
                or (getattr(self, 'competition_icons', None) is not None and self.competition_icons.busy)):
            if not getattr(self, '_close_pending', False):
                self._close_pending = True
                self.log("Shutdown: waiting for the current file operation")
                self.after(100, self._retry_close)
            return
        self._closing = True
        def step(label, action):
            return cleanup_step(label, action, self.log)
        step('start log', lambda:self.log("Shutdown: starting cleanup"))
        diagnostics = getattr(self, '_startup_diagnostics', None)
        if diagnostics is not None:
            step('startup diagnostics', diagnostics.close)
        # Cancel all Tk timers, including optional panels, before releasing maps.
        def cancel_jobs():
            for job in self.tk.call('after', 'info'):
                step('cancel timer', lambda job=job:self.after_cancel(job))
        step('timers', cancel_jobs)
        step('startup splash', self._dismiss_launch_splash)
        closing_splash = step('closing splash creation', self._show_closing_splash)
        step('volume popup', self._hide_crowd_volume_popup)
        step('audio stop signal', self._chants_stop.set)
        bridge=getattr(self,'gamepad_bridge',None)
        if bridge is not None:
            step('physical controller visibility',bridge.release_hidhide_cloaks_on_shutdown)
            step('gamepad bridge',bridge.stop)
        step('database reader processes', close_owned_readers)
        selector, self._stadium_selector = self._stadium_selector, None
        if selector is not None:
            step('match panels and shared memory', selector.shutdown)
        def audio_cleanup():
            step('entrance audio', self._reset_team_entrance)
            step('chants audio', self._reset_chants_state)
        bounded_cleanup('audio', audio_cleanup, self.log)
        # Network disconnects must not keep the hidden Tk root alive.
        bounded_cleanup('discord', self.discord_rpc.disconnect, self.log)
        if step('game process state', self._is_target_process_running) is False:
            step('native runtime assets', self._restore_native_runtime_assets)
        step('stadium names', lambda:restore_stadium_names(self))
        if self._d3d_injector is not None:
            step('overlay mapping', self._d3d_injector.destroy)
        step('game process handle', self.memory.close)
        # Frozen builds own the process; after cleanup, do not enter Tcl/CLR
        # destruction/finalization that can leave the hidden process alive.
        if closing_splash is not None and not getattr(sys, 'frozen', False):
            step('closing splash', lambda:closing_splash.close(min_visible=0.7))
        step('quit event loop', self.quit)
        if not getattr(sys, 'frozen', False):
            step('destroy windows', self.destroy)
        self._shutdown_complete = True
        step('completion log', lambda:self.log("Shutdown: cleanup complete"))
        finish_frozen_process()

    def _retry_close(self) -> None:
        self._close_pending = False
        self.on_close()


def main(splash=None) -> None:
    if os.name == "nt":
        try:
            shell32 = ctypes.WinDLL("shell32", use_last_error=True)
            set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
            set_app_id.argtypes = [wintypes.LPCWSTR]
            set_app_id.restype = ctypes.c_long
            set_app_id("Igor1043.CGFS16.Server16Python")
        except Exception:
            pass
    app = Server16App(splash=splash)
    if app._closing:
        if getattr(app, '_shutdown_complete', False):
            finish_frozen_process()
        return
    app.after(150, app._dismiss_launch_splash)
    try:
        app.mainloop()
    finally:
        if not app._closing:
            app.on_close()
        if getattr(app, '_shutdown_complete', False):
            finish_frozen_process()
