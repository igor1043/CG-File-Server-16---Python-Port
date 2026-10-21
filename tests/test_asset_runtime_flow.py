from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py import app as app_module
from server16_py import asset_runtime, file_tools
from server16_py.app import Server16App
from server16_py.asset_runtime import AssetRuntime
from server16_py.stadium_runtime import StadiumRuntime


class AssetRuntimeFlowTests(unittest.TestCase):
    """Exercise actual copies in an isolated FIFA tree, never an installed game."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.assignments = {}
        self.modules = {"Movies", "ScoreBoard"}
        self.app = SimpleNamespace(
            exedir=self.root, Movies=self.root / "Movies",
            ScoreBoard=self.root / "ScoreBoard", TVLogo=self.root / "TVLogo",
            Movdata=self.root / "data/movies/bootflowoutro.vp8",
            MOVBUMP=self.root / "data/ui/TV/bumper.big",
            Scoredata=self.root / "data/ui", TVdata=self.root / "data/ui/game/overlays",
            TOURROUNDID="round", TOURNAME="tour", HID="1043", derby="1043x567",
            stadmovie=False, curstad="Maracana", log=Mock(), _set_display=Mock(),
            module_enabled=lambda name: name in self.modules,
            display_value=lambda key, **kwargs: key,
            _show_asset_loading=Mock(), _update_asset_loading=Mock(), _hide_asset_loading=Mock(),
            settings_ini=SimpleNamespace(
                key_exists=lambda key, section: (section, key) in self.assignments,
                read=lambda key, section: self.assignments.get((section, key), ""),
            ),
        )
        self.runtime = AssetRuntime(self.app)
        self.runtime.update_audio_overview = Mock()

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def movie_package(self, name):
        self.put(f"Movies/{name}/bootflowoutro.vp8", f"video-{name}".encode())
        self.put(f"Movies/{name}/bumper.big", f"bumper-{name}".encode())

    def test_movie_assignment_priority_and_original_copy_order(self):
        priorities = [("movies", "round"), ("movies", "tour"),
                      ("DerbyMatch", "1043x567"), ("TeamMovies", "1043"), ("movies", "0")]
        for index, key in enumerate(priorities):
            name = f"package-{index}" + "-" * index
            self.assignments[key] = name
            self.movie_package(name)
        original_copy = file_tools.copy_if_exists
        for index, key in enumerate(priorities):
            with self.subTest(priority=key):
                copies = []
                def traced_copy(source, destination):
                    copies.append((Path(source).relative_to(self.root).as_posix(), destination))
                    original_copy(source, destination)
                with patch.object(asset_runtime, "copy_if_exists", side_effect=traced_copy):
                    self.runtime.apply_movie_runtime()
                name = f"package-{index}" + "-" * index
                self.assertEqual(copies, [(f"Movies/{name}/bootflowoutro.vp8", self.app.Movdata),
                                          (f"Movies/{name}/bumper.big", self.app.MOVBUMP)])
                self.assertEqual(self.app.Movdata.read_bytes(), f"video-{name}".encode())
                self.assertEqual(self.app.MOVBUMP.read_bytes(), f"bumper-{name}".encode())
                del self.assignments[key]

    def test_new_official_movie_name_uses_existing_package_without_editing_settings(self):
        self.assignments[("movies", "tour")] = "AUST - Isuzu UTE A-League"
        self.movie_package("Isuzu UTE A-League")
        self.put("ModCarrerMode/data/catalogs/presentation_package_aliases.tsv",
                 b"movies|AUST - Isuzu UTE A-League|Isuzu UTE A-League\n")
        before = dict(self.assignments)
        self.runtime.apply_movie_runtime()
        self.assertEqual(self.app.Movdata.read_bytes(), b"video-Isuzu UTE A-League")
        self.assertEqual(self.assignments, before)

    def test_new_scoreboard_name_resolves_existing_assets_after_native_baseline(self):
        self.assignments[("Scoreboard", "tour")] = "New official name"
        self.put("FSW/ScoreBoard/game/native.big", b"native")
        self.put("ScoreBoard/Old package/game/native.big", b"mapped scoreboard")
        self.put("ModCarrerMode/data/catalogs/presentation_package_aliases.tsv",
                 b"scoreboard|New official name|Old package\n")
        self.app.tvlogoscoreboardtype = "default"
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual((self.app.Scoredata / "game/native.big").read_bytes(), b"mapped scoreboard")

    def test_scoreboard_priority_copies_baseline_before_assigned_files(self):
        priorities = [("Scoreboard", "round"), ("Scoreboard", "tour"),
                      ("HomeTeamScoreBoard", "1043"), ("Scoreboard", "0")]
        self.put("FSW/ScoreBoard/native.big", b"native")
        for index, key in enumerate(priorities):
            name = f"score-{index}"
            self.assignments[key] = name
            self.put(f"ScoreBoard/{name}/game/score.big", f"scoreboard-{index}".encode() + b"!" * index)
        original_copy = file_tools.copy
        for index, key in enumerate(priorities):
            with self.subTest(priority=key):
                copies = []
                def traced_copy(source, destination, **kwargs):
                    copies.append((Path(source).relative_to(self.root).as_posix(), destination))
                    original_copy(source, destination, **kwargs)
                with patch.object(asset_runtime, "copy", side_effect=traced_copy):
                    self.runtime.apply_scoreboard_runtime()
                self.assertEqual(copies, [("FSW/ScoreBoard", self.app.Scoredata / "game"),
                                         (f"ScoreBoard/score-{index}", self.app.Scoredata)])
                self.assertEqual((self.app.Scoredata / "game/native.big").read_bytes(), b"native")
                self.assertEqual((self.app.Scoredata / "game/score.big").read_bytes(),
                                 f"scoreboard-{index}".encode() + b"!" * index)
                del self.assignments[key]

    def test_tvlogo_specific_scoreboard_variant_still_wins(self):
        self.modules.add("TvLogo")
        self.assignments[("TVLogo", "round")] = "channel"
        self.assignments[("Scoreboard", "round")] = "score"
        self.put("TVLogo/channel/sports_9105.big", b"tv logo")
        self.put("ScoreBoard/score/game/score.big", b"root scoreboard")
        self.put("ScoreBoard/score/sports/game/score.big", b"channel-specific scoreboard")
        self.runtime.apply_scoreboard_runtime()
        self.assertEqual(self.app.tvlogoscoreboardtype, "sports")
        self.assertEqual((self.app.Scoredata / "game/score.big").read_bytes(), b"channel-specific scoreboard")

    def test_broken_notifications_do_not_interrupt_asset_copies(self):
        for method in (self.app._show_asset_loading, self.app._update_asset_loading, self.app._hide_asset_loading):
            method.side_effect = RuntimeError("renderer unavailable")
        self.assignments[("movies", "0")] = "intro"
        self.assignments[("Scoreboard", "0")] = "score"
        self.movie_package("intro")
        self.put("FSW/ScoreBoard/native.big", b"native")
        self.put("ScoreBoard/score/game/score.big", b"score")
        self.runtime.apply_scoreboard_runtime()
        self.runtime.apply_movie_runtime()
        self.assertEqual(self.app.Movdata.read_bytes(), b"video-intro")
        self.assertEqual(self.app.MOVBUMP.read_bytes(), b"bumper-intro")
        self.assertEqual((self.app.Scoredata / "game/score.big").read_bytes(), b"score")
        self.assertTrue(self.app.log.called)

    def test_partial_movie_package_keeps_original_copy_if_exists_behavior(self):
        self.assignments[("movies", "0")] = "video-only"
        self.put("Movies/video-only/bootflowoutro.vp8", b"custom video")
        self.put("data/ui/TV/bumper.big", b"previous bumper")
        self.runtime.apply_movie_runtime()
        self.assertEqual(self.app.Movdata.read_bytes(), b"custom video")
        self.assertEqual(self.app.MOVBUMP.read_bytes(), b"previous bumper")

    def test_stadium_movie_is_not_replaced_when_no_movie_assignment_exists(self):
        self.app.stadmovie = True
        self.put("data/movies/bootflowoutro.vp8", b"stadium video")
        self.put("FSW/Nav/bootflowoutro.vp8", b"default video")
        self.runtime.apply_movie_runtime()
        self.assertEqual(self.app.Movdata.read_bytes(), b"stadium video")

    def test_missing_movie_folder_uses_original_native_fallback(self):
        self.assignments[("movies", "0")] = "missing"
        self.put("FSW/Nav/bootflowoutro.vp8", b"default video")
        self.put("FSW/Nav/bumper.big", b"default bumper")
        self.runtime.apply_movie_runtime()
        self.assertEqual(self.app.Movdata.read_bytes(), b"default video")
        self.assertEqual(self.app.MOVBUMP.read_bytes(), b"default bumper")

    def test_cleanup_preserves_enabled_navigation_video_and_bumper(self):
        active = {"data/ui/nav/pausemenuflow.nav": b"OUTRO enabled",
                  "data/movies/bootflowoutro.vp8": b"selected video",
                  "data/ui/TV/bumper.big": b"selected bumper"}
        for path, contents in active.items():
            self.put(path, contents)
        self.put("FSW/Nav/pausemenuflow.nav_Original", b"OUTRO disabled")
        self.put("FSW/Nav/bootflowoutro.vp8", b"native video")
        self.put("FSW/Nav/bumper.big", b"native bumper")
        self.put("FSW/ScoreBoard/native.big", b"native scoreboard")
        self.put("data/ui/game/native.big", b"modified scoreboard")
        self.assertGreaterEqual(file_tools.restore_native_assets(self.app), 1)
        for path, contents in active.items():
            self.assertEqual((self.root / path).read_bytes(), contents)
        self.assertEqual((self.root / "data/ui/game/native.big").read_bytes(), b"native scoreboard")

    def test_launch_does_not_stage_or_require_intro_files(self):
        self.app.fifaEXE = str(self.root / "fifa16.exe")
        self.app._is_target_process_running = Mock(return_value=False)
        self.app.competition_icons = Mock()
        with patch.object(app_module.subprocess, "Popen") as launch, \
             patch.object(app_module, "copy_if_exists", side_effect=AssertionError("launch must not copy assets")):
            Server16App.launch_fifa(self.app)
        launch.assert_called_once_with([self.app.fifaEXE], cwd=str(self.root.resolve()), shell=False)
        self.app.competition_icons.prepare.assert_called_once_with(self.root, force=True)

    def test_bootstrap_preserves_original_movies_enabled_and_disabled_branches(self):
        self.app.fifaEXE = str(self.root / "fifa16.exe")
        for name, relative in (("Psource", "FSW/Police"), ("Pdest", "data/sceneassets/slc"),
                               ("Nsource", "FSW/Nets"), ("Ndest", "data/sceneassets/goalnet"),
                               ("PitchMowsource", "FSW/PitchMowPattern"), ("PitchMowdest", "data/sceneassets/pitch")):
            setattr(self.app, name, self.root / relative)
        self.app._update_audio_overview = Mock()
        self.put("FSW/Nav/pausemenuflow.nav_new", b"OUTRO enabled")
        self.put("FSW/Nav/pausemenuflow.nav_Original", b"OUTRO disabled")
        self.put("FSW/Nav/bootflowoutro.vp8", b"bootstrap movie")
        self.put("FSW/Nav/Fbootflowoutro.vp8", b"disabled branch movie")
        self.put("FSW/Nav/bumper.big", b"bootstrap bumper")
        self.assignments[("movies", "0")] = "custom"
        self.movie_package("custom")
        with patch.object(app_module, "checkver", return_value="test"):
            Server16App.apply_bootstrap_files(self.app)
            self.assertEqual((self.root / "data/ui/nav/pausemenuflow.nav").read_bytes(), b"OUTRO enabled")
            self.assertEqual(self.app.Movdata.read_bytes(), b"bootstrap movie")
            self.assertEqual(self.app.MOVBUMP.read_bytes(), b"bootstrap bumper")
            self.modules.remove("Movies")
            Server16App.apply_bootstrap_files(self.app)
        self.assertEqual((self.root / "data/ui/nav/pausemenuflow.nav").read_bytes(), b"OUTRO disabled")
        self.assertEqual(self.app.Movdata.read_bytes(), b"disabled branch movie")

    def test_valid_stadium_completion_does_not_reapply_movie(self):
        self.app._kickoff_generation = 1
        self.app.AID = "567"
        self.app.memory = Mock()
        self.app.memory.is_open.return_value = True
        self.app.memory.get_int.return_value = 176
        self.app.offsets = SimpleNamespace(ORISTADIDBASE=1, S=[0, 1, 2, 3, 4, 5],
                                          STDNAMEOFFSET176=[1], STDNAMEOFFSET261=[2], STDNAMEBASE=2)
        self.app.CCount = 0
        for name in ("_set_progress", "_set_process_status", "_update_audio_overview",
                     "_hide_stadium_loading_modal", "apply_movie_runtime"):
            setattr(self.app, name, Mock())
        self.app.success = "green"
        self.app._stadium_task_signature = (1, "request")
        runtime = StadiumRuntime(self.app)
        runtime.play_stadium_loaded_sound = Mock()
        runtime.finish_stadium_apply(dict(context=(1, "1043", "567"), injid="176", stadium_type="first",
                                         stad_name="Maracana", stadmovie=True, section_name="stadium", section_id="1043"))
        self.app.apply_movie_runtime.assert_not_called()
        self.assertTrue(self.app.stadmovie)
        self.assertEqual(self.app.curstad, "Maracana")
        self.assertFalse(self.app._stadium_task_running)
        self.app.memory.write_int.assert_called_once_with(1, [0, 1, 2, 4, 5], "176")


if __name__ == "__main__":
    unittest.main()
