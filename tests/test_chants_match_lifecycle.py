"""Deterministic audio/match tests: no installed game, MCI or real inputs."""
import random
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.app import Server16App
from server16_py.audio_profiles import AudioProfileRuntime
from server16_py.chants_runtime import ChantsRuntime
from server16_py.match_audio_panel import MatchAudioPanel
from server16_py.match_state import GoalClockProgress
from server16_py.offsets import Offsets
from server16_py.settings_store import SettingsStore


class Clock:
    def __init__(self):
        self.now = 0.0
        self.tick = lambda: None
        self.player = None
        self.limit = 200

    def sleep(self, seconds):
        self.now += seconds
        if self.player and self.player.state == 'playing':
            self.player.position = min(self.player.duration, self.player.position + seconds)
            if self.player.position >= self.player.duration:
                self.player.state = 'stopped'
        self.tick()
        if self.now > self.limit:
            raise AssertionError('Audio worker did not terminate')


class Player:
    def __init__(self, clock):
        self.clock = clock
        clock.player = self
        self.volume = 0.0
        self.position = 0.0
        self.duration = 120.0
        self.state = 'closed'
        self.levels = []
        self.pauses = []
        self.resumes = []
        self.closed_at = None

    def open(self, path): self.state = 'stopped'
    def length_ms(self): return round(self.duration*1000)
    def position_ms(self): return round(self.position*1000)
    def set_volume(self, level):
        self.volume = level
        self.levels.append(level)
    def play(self): self.state = 'playing'
    def pause(self):
        self.pauses.append((self.clock.now, self.position, self.volume))
        self.state = 'paused'
    def resume(self):
        self.resumes.append((self.clock.now, self.position, self.volume))
        self.state = 'playing'
    def stop(self): self.state = 'stopped'
    def close(self):
        self.state = 'closed'
        self.closed_at = self.clock.now
    def mode(self): return 'stopped' if self.position >= self.duration else self.state
    def is_playing(self): return self.mode() == 'playing'
    def is_paused(self): return self.mode() == 'paused'


class ChantsLifecycleTests(unittest.TestCase):
    def make_runtime(self, root, *, running_clock=False):
        clock = Clock()
        player = Player(clock)
        config = 'team,0.1,0.1,0.1,0.1,0.1,0.2'
        app = SimpleNamespace(
            exedir=root, MP='fake', HID='1', AID='2', lastpagename='',
            offsets=Offsets(), matchstarted=True, _match_audio_ended=False,
            _chants_player=None, _chants_target_volume=0.0, _chants_base_volume=0.0,
            _chants_volume_is_crowd=False, _chants_paused=False, _chants_reset_requested=False,
            _chants_stop=threading.Event(), _chants_resume_after=0.0,
            _chants_rng=random.Random(1), _chants_last_goal_time=0,
            _last_chants_score_snapshot=(0,0), _entrance_active=False,
            _goal_master_volume=0.5, _crowd_master_volume=0.5,
            module_enabled=lambda name: True, log=Mock(), _set_display_async=Mock(),
            settings_ini=SimpleNamespace(key_exists=lambda *args: True, read=lambda *args: config),
        )
        memory = Mock()
        memory.attack.return_value = memory.is_open.return_value = True
        memory.get_int.side_effect = lambda base, offset: (
            1 if offset == app.offsets.GAMESTARTEDBINARY else
            100 + (int(max(0, clock.now - 8)) if running_clock else 0) if offset == app.offsets.GAMERANTIME else 0
        )
        app._is_game_running_with = lambda mem: Server16App._is_game_running_with(app, mem)
        runtime = ChantsRuntime(app)
        return runtime, clock, player, memory

    def simulate(self, runtime, clock, player, memory, run):
        with ExitStack() as stack:
            stack.enter_context(patch('server16_py.chants_runtime.time.sleep', side_effect=clock.sleep))
            stack.enter_context(patch('server16_py.chants_runtime.time.monotonic', side_effect=lambda: clock.now))
            stack.enter_context(patch('server16_py.chants_runtime.time.time', side_effect=lambda: clock.now))
            stack.enter_context(patch('server16_py.chants_runtime.MciAudioPlayer', return_value=player))
            stack.enter_context(patch('server16_py.chants_runtime.Memory', return_value=memory))
            return run()

    def test_both_team_goal_anthems_fade_after_replay_skip_and_release_cooldown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            song = root/'FSW/Chants/team/ClubSong.mp3'
            song.parent.mkdir(parents=True)
            song.touch()
            for team in ('1', '2'):
                with self.subTest(team=team):
                    runtime, clock, player, memory = self.make_runtime(root, running_clock=True)
                    self.assertTrue(self.simulate(runtime, clock, player, memory,
                        lambda: runtime._play_club_song(team, memory)))
                    self.assertGreaterEqual(player.closed_at, 9)
                    self.assertLess(player.closed_at, 13)
                    self.assertLess(player.position, player.duration)
                    self.assertEqual(player.levels[-1], 0)
                    self.assertIn(0.1, player.levels)
                    messages = [call.args[0] for call in runtime.app.log.call_args_list]
                    self.assertTrue(any('kick-off detected' in m for m in messages))
                    self.assertTrue(any(f'Club anthem {team}' == call.args[1]
                        for call in runtime.app._set_display_async.call_args_list if call.args[0]=='audio_source'))
                    self.assertLess(runtime.app._chants_resume_after, clock.now + 2)
                    self.assertIsNone(runtime.app._goal_audio_player)

    def test_long_pause_preserves_song_position_and_resumes_at_current_master(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'))
        def tick():
            runtime.app.lastpagename = 'game/screens/fluxHub/FluxHub' if 2 <= clock.now < 42 else ''
            if 2 <= clock.now < 42:
                runtime.app._goal_master_volume = 0.25
                runtime.apply_goal_master_volume()
        clock.tick = tick
        self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
            Path('ClubSong.mp3'), .2, 'goal', 'goal', 'Away anthem', 'next', chants_memory=memory, goal_song=True))
        self.assertEqual(len(player.pauses), 1)
        self.assertEqual(len(player.resumes), 1)
        self.assertEqual(player.pauses[0][2], 0)
        self.assertEqual(player.pauses[0][1], player.resumes[0][1])
        self.assertGreaterEqual(player.resumes[0][0], 42)
        self.assertGreaterEqual(player.closed_at, 159)
        self.assertLess(player.closed_at, 162)
        self.assertEqual(player.position, player.duration)
        self.assertIn(.05, player.levels)

    def test_repeated_pauses_never_restart_or_truncate_either_team_song(self):
        for team in ('Home', 'Away'):
            with self.subTest(team=team):
                runtime, clock, player, memory = self.make_runtime(Path('.'))
                def tick():
                    runtime.app.lastpagename = 'FluxHub' if any(
                        start<=clock.now<end for start,end in ((2,12),(25,50),(65,75))) else ''
                clock.tick=tick
                self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
                    Path('ClubSong.mp3'),.2,'goal','goal',f'{team} anthem','next',chants_memory=memory,goal_song=True))
                self.assertEqual(len(player.pauses),3)
                self.assertEqual(len(player.resumes),3)
                for paused,resumed in zip(player.pauses,player.resumes):
                    self.assertEqual(paused[1],resumed[1])
                self.assertEqual(player.position,player.duration)
                self.assertGreater(player.closed_at,160)
                self.assertLess(player.closed_at,169)

    def test_pause_longer_than_track_duration_does_not_consume_song_timeout(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'))
        player.duration=12
        clock.limit=240
        clock.tick=lambda: setattr(runtime.app,'lastpagename','FluxHub' if 2<=clock.now<192 else '')
        self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
            Path('ClubSong.mp3'),.2,'goal','goal','anthem','next',chants_memory=memory,goal_song=True))
        self.assertEqual(len(player.resumes),1)
        self.assertEqual(player.pauses[0][1],player.resumes[0][1])
        self.assertEqual(player.position,12)
        self.assertGreaterEqual(player.closed_at,202)
        self.assertLess(player.closed_at,205)

    def test_away_crowd_reaction_still_cuts_on_kickoff(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'), running_clock=True)
        self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
            Path('Support.mp3'),.2,'crowd','reaction','Away crowd','next',chants_memory=memory,crowd_volume=True))
        self.assertLess(player.closed_at,15)
        self.assertLess(player.position,player.duration)
        self.assertTrue(any('kick-off detected' in call.args[0] for call in runtime.app.log.call_args_list))

    def test_inaccurate_or_missing_mp3_duration_does_not_cut_progressing_song(self):
        for reported_duration,actual_duration in ((10000,120),(0,240)):
            with self.subTest(duration=reported_duration):
                runtime, clock, player, memory = self.make_runtime(Path('.'))
                player.duration=actual_duration
                player.length_ms=lambda:reported_duration
                clock.limit=260
                self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
                    Path('ClubSong.mp3'),.2,'goal','goal','anthem','next',chants_memory=memory,goal_song=True))
                self.assertEqual(player.position,actual_duration)
                self.assertGreaterEqual(player.closed_at,actual_duration)
                self.assertFalse(any('safety timeout' in call.args[0] for call in runtime.app.log.call_args_list))

    def test_stalled_decoder_still_expires_without_endless_anthem(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'))
        player.length_ms=lambda:10000
        player.position_ms=lambda:0
        self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
            Path('ClubSong.mp3'),.2,'goal','goal','anthem','next',chants_memory=memory,goal_song=True))
        self.assertLess(player.closed_at,15)
        self.assertTrue(any('safety timeout' in call.args[0] for call in runtime.app.log.call_args_list))

    def test_modal_apply_changes_live_goal_song_now_and_paused_resume_uses_selected_volume(self):
        for scope in ('general','match'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                runtime, clock, player, memory = self.make_runtime(root)
                app=runtime.app
                app.settings=SettingsStore(root/'settings.json')
                app.chants_runtime=runtime
                app.audio_profiles=AudioProfileRuntime(app)
                app.audio_profiles.bind(root)
                app.audio_profiles.save_match((.5,.5))
                previous=app.audio_profiles.path.read_bytes()
                selector=SimpleNamespace(app=app,context=(1,'1','2'),_context=lambda:(1,'1','2'),
                    match_eligible=lambda:True,close=Mock(),render=Mock())
                applied_running=applied_paused=False
                levels=[]
                def tick():
                    nonlocal applied_running,applied_paused
                    app.lastpagename='FluxHub' if 8<=clock.now<18 else ''
                    if clock.now>=4 and not applied_running:
                        panel=MatchAudioPanel(selector);panel.values=[30,25];panel.apply(scope)
                        levels.append(player.volume)
                        applied_running=True
                    if app._chants_paused and not applied_paused:
                        panel=MatchAudioPanel(selector);panel.values=[45,75];panel.apply(scope)
                        levels.append(player.volume)
                        applied_paused=True
                    if applied_paused:
                        app.audio_profiles.sync()
                clock.tick=tick
                self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
                    Path('ClubSong.mp3'),.2,'goal','goal','anthem','next',chants_memory=memory,goal_song=True))
                self.assertEqual(levels,[.05,0])
                self.assertIn(.15, [round(level,2) for level in player.levels])
                self.assertEqual(player.position,player.duration)
                self.assertEqual(selector.close.call_count,2)
                self.assertEqual(app.audio_profiles.sync(),(.45,.75))
                if scope=='general':
                    self.assertEqual(app.audio_profiles.path.read_bytes(),previous)
                    app._kickoff_generation=1
                    self.assertEqual(app.audio_profiles.sync(),(.5,.5))

    def test_post_match_closes_paused_song_without_resume(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'))
        def tick():
            runtime.app.lastpagename = ('MatchDetailsEndGame' if clock.now >= 12 else
                'FluxHub' if clock.now >= 2 else '')
        clock.tick = tick
        self.simulate(runtime, clock, player, memory, lambda: runtime._play_goal_track(
            Path('ClubSong.mp3'), .2, 'goal', 'goal', 'Home anthem', 'next', chants_memory=memory, goal_song=True))
        self.assertEqual(len(player.pauses), 1)
        self.assertEqual(player.resumes, [])
        self.assertLess(player.closed_at, 13)

    def test_crowd_worker_closes_at_end_without_waiting_for_mode_menu(self):
        runtime, clock, player, memory = self.make_runtime(Path('.'))
        app = runtime.app
        player.state = 'playing'
        player.volume = app._chants_target_volume = 0.1
        app._chants_player = player
        app._chants_volume_is_crowd = True
        def tick():
            if clock.now >= .5: app.lastpagename = 'MatchDetailsEndGame'
            if player.closed_at is not None: app._chants_stop.set()
        clock.tick = tick
        self.simulate(runtime, clock, player, memory, runtime.chants_runtime_loop)
        self.assertLess(player.closed_at, 1.5)
        self.assertIsNone(app._chants_player)
        self.assertEqual(player.levels[-1], 0)

    def test_goal_routing_has_no_second_away_reaction_after_clubsong(self):
        for scores, team in (((1,0),'1'), ((0,1),'2')):
            with self.subTest(team=team):
                runtime, clock, player, memory = self.make_runtime(Path('.'))
                app = runtime.app
                app._is_game_running_with = lambda mem: True
                memory.get_int.side_effect = lambda base, offset: scores[0] if offset == app.offsets.GAMEHOMEGOALSCORE else scores[1]
                def song(*args, **kwargs):
                    app._chants_stop.set()
                    return True
                with patch.object(runtime, '_play_club_song', side_effect=song) as play, patch.object(runtime, '_play_away_reaction') as away:
                    self.simulate(runtime, clock, player, memory, runtime.chants_runtime_loop)
                    play.assert_called_once_with(team, chants_memory=memory)
                    away.assert_not_called()

    def test_terminal_page_teardown_precedes_asset_restore_and_survives_blank_page(self):
        order = []
        app = SimpleNamespace(lastpagename='', log=Mock(), HID='1', AID='2', matchstarted=True,
            _match_audio_ended=False, _native_assets_restored_for_match=False,
            _last_runtime_signature=('1','2'), _is_post_match_page=Server16App._is_post_match_page,
            _reset_chants_state=lambda: order.append('chants'),
            _reset_team_entrance=lambda: order.append('entrance'),
            _restore_native_runtime_assets=lambda: order.append('assets'),
            offsets=Offsets(), skillgamechange=False)
        Server16App._handle_page_transition(app, 'game/screens/MatchDetailsEndGame')
        self.assertEqual(order, ['chants','entrance','assets'])
        self.assertTrue(app._match_audio_ended)
        Server16App._handle_page_transition(app, '')
        self.assertFalse(Server16App._is_game_running_with(app, Mock()))

    def test_audio_reset_does_not_hide_asset_restoration_context(self):
        app = SimpleNamespace(lastpagename='', log=Mock(), HID='', AID='', matchstarted=True,
            _match_audio_ended=False, _native_assets_restored_for_match=False,
            _last_runtime_signature=None, _is_post_match_page=Server16App._is_post_match_page,
            _reset_team_entrance=Mock(), _restore_native_runtime_assets=Mock())
        app._reset_chants_state = lambda: setattr(app, 'matchstarted', False)
        Server16App._handle_page_transition(app, 'MatchDetailsEndGame')
        app._restore_native_runtime_assets.assert_called_once()

    def test_clock_backward_jitter_and_single_jump_never_confirm_kickoff(self):
        detector = GoalClockProgress()
        for now, value in ((0,100),(1,104),(2,104),(3,104),(4,100),(5,100),(6,100)):
            self.assertFalse(detector.observe(value, now))
        for now, value in ((7,101),(8,102)):
            self.assertFalse(detector.observe(value, now))
        self.assertTrue(detector.observe(103, 9))

    def test_game_memory_running_flag_cannot_override_pause_or_terminal_page(self):
        runtime, _, _, memory = self.make_runtime(Path('.'))
        self.assertTrue(runtime.app._is_game_running_with(memory))
        for page in ('FluxHub', 'StadiumPan', 'InstantReplay', 'MatchDetailsEndGame', 'training/Hub', 'playNow/SideSelect'):
            with self.subTest(page=page):
                runtime.app.lastpagename = page
                self.assertFalse(runtime.app._is_game_running_with(memory))
