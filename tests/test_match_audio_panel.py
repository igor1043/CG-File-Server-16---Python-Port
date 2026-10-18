import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from PIL import Image
import test_stadium_selector as fixtures
from server16_py.match_audio_panel import percentage, MatchAudioPanel
from server16_py.settings_store import SettingsStore
from server16_py.audio_profiles import AudioProfileRuntime


class MatchAudioTests(unittest.TestCase):
    def make_selector(self, root):
        selector = fixtures.StadiumSelectorTests().make_selector(root)
        app = selector.app
        app.lastpagename = ''
        app._is_game_running_with = Mock(return_value=True)
        app.settings = SettingsStore(root/'settings.json')
        app.exedir = root/'game'
        app._crowd_master_volume = app._goal_master_volume = 1.0
        app.chants_runtime = Mock()
        return selector

    def open_audio(self, selector):
        # Exercise the audio editor independently of the new category menu.
        selector.open(audio=True)
        selector.audio_panel = MatchAudioPanel(selector)
        selector.render()

    def test_defaults_bounds_and_invalid_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = SettingsStore(Path(temporary)/'settings.json')
            self.assertEqual(settings.goal_master_volume, 1)
            for value, expected in ((-1,0), (2,1), ('invalid',1), (float('nan'),1), (float('inf'),1)):
                settings.data['GOAL_MASTER_VOLUME'] = value
                self.assertEqual(settings.goal_master_volume, expected)
            self.assertEqual(percentage('invalid'),100)
            self.assertEqual(percentage(float('nan')),100)

    def test_match_signal_is_not_chants_dependent_and_blocks_menus(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector = self.make_selector(Path(temporary))
            try:
                selector.app.module_enabled = lambda name: False
                self.assertTrue(selector.match_eligible())
                selector.app.lastpagename = 'game/screens/flux/FluxHub'
                selector.app._is_game_running_with.return_value = False
                self.assertTrue(selector.match_eligible())
                selector.app.lastpagename = ''  # Transient blank while FIFA is paused.
                self.assertTrue(selector.match_eligible())
                selector.app._match_audio_ended = True
                self.assertFalse(selector.match_eligible())
                selector.app._match_audio_ended = False
                selector.app.lastpagename = 'game/screens/career/Home'
                self.assertFalse(selector.match_eligible())
                selector.app._is_game_running_with.return_value = True
                for page in ('game/screens/playNow/KickOffHub', 'training/SkillGame', 'game/screens/playNow/SideSelect'):
                    selector.app.lastpagename = page
                    self.assertFalse(selector.match_eligible())
            finally:
                selector.shutdown()

    def test_keyboard_shortcut_routes_to_music_submenu_and_cancel_never_saves(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector = self.make_selector(Path(temporary))
            try:
                selector._attempted_pid = 1234
                selector.shared.ready = 7
                selector.shared.events[0].kind = 1
                selector.shared.write_index = 1
                selector.tick()
                self.assertEqual(selector.shared.enabled, 2)
                self.assertTrue(selector.audio_panel)
                with Image.open(selector.shared.image_path) as image:
                    self.assertEqual(image.size, (selector.audio_panel.WIDTH*2,selector.audio_panel.HEIGHT*2))
                    self.assertEqual(image.getpixel((600,20))[:3], (255,255,255))
                selector.handle(6,0)  # Open Music from the in-match category menu.
                original = selector.app.settings.path.read_bytes()
                selector.handle(2,0)
                self.assertEqual(selector.audio_panel.child.values, [95,100])
                self.assertEqual(selector.app._crowd_master_volume, 1)
                selector.handle(11,0)
                self.assertFalse(selector.opened)
                self.assertEqual(selector.app.settings.path.read_bytes(), original)
                selector.app.chants_runtime.apply_crowd_master_volume.assert_not_called()
            finally:
                selector.shutdown()

    def test_sliders_keyboard_mouse_drag_apply_and_persistence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selector = self.make_selector(root)
            try:
                self.open_audio(selector)
                selector.handle(8, (143<<16)|300)
                self.assertEqual(selector.audio_panel.values[0],50)
                selector.handle(5,0)
                selector.handle(2,0)
                self.assertEqual(selector.audio_panel.values[1],95)
                selector.handle(12,(248<<16)|40)
                self.assertEqual(selector.audio_panel.values[1],0)
                selector.handle(12,(389<<16)|300)
                self.assertTrue(selector.opened) # Dragging never clicks Apply.
                selector.handle(8,(389<<16)|300)
                self.assertFalse(selector.opened)
                self.assertEqual(selector.app._crowd_master_volume,.5)
                self.assertEqual(selector.app._goal_master_volume,0)
                self.assertEqual(SettingsStore(root/'settings.json').goal_master_volume,0)
                selector.app.chants_runtime.apply_crowd_master_volume.assert_called_once()
                selector.app.chants_runtime.apply_goal_master_volume.assert_called_once()
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[50,0])
            finally:
                selector.shutdown()

    def test_failed_save_and_expired_context_do_not_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector = self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                selector.audio_panel.values = [0,0]
                previous = dict(selector.app.settings.data)
                with patch.object(selector.app.settings,'save',side_effect=OSError('disk full')):
                    selector.audio_panel.apply()
                self.assertEqual(selector.app.settings.data,previous)
                self.assertEqual(selector.app._crowd_master_volume,1)
                self.assertTrue(selector.opened)
                selector.app.HID = '3'
                selector.audio_panel.apply()
                self.assertFalse(selector.opened)
                selector.app.chants_runtime.apply_goal_master_volume.assert_not_called()
            finally:
                selector.shutdown()

    def test_goal_master_scales_only_goal_player_and_survives_fade(self):
        runtime = fixtures.CrowdAudioSafetyTests().make_runtime()
        app = runtime.app
        app._goal_audio_player = app._chants_player
        app._goal_base_volume = .2
        app._goal_master_volume = .5
        app._chants_volume_is_crowd = False
        runtime.apply_goal_master_volume()
        app._chants_player.set_volume.assert_called_with(.1)
        app._goal_master_volume = 0
        with patch('server16_py.chants_runtime.time.sleep'):
            runtime.fade_player(app._chants_player,0,.2,100)
        app._chants_player.set_volume.assert_called_with(0)
        app._chants_player = Mock()
        runtime.apply_goal_master_volume()
        app._chants_player.set_volume.assert_not_called()

    def test_goal_track_uses_base_multiplier_and_cleans_up(self):
        runtime = fixtures.CrowdAudioSafetyTests().make_runtime()
        app = runtime.app
        app._goal_master_volume = .5
        app._chants_resume_after = 0
        app._chants_stop = Mock()
        app._chants_stop.is_set.return_value = False
        app.module_enabled = lambda name: True
        player = Mock()
        player.length_ms.return_value = 1000
        player.mode.return_value = 'stopped'
        with patch('server16_py.chants_runtime.MciAudioPlayer',return_value=player), patch('server16_py.chants_runtime.time.sleep'):
            self.assertTrue(runtime._play_goal_track(Path('anthem.mp3'),.2,'goal','goal','test','test',goal_song=True))
        self.assertTrue(any(call.args == (.1,) for call in player.set_volume.call_args_list))
        self.assertIsNone(app._goal_audio_player)
        self.assertIsNone(app._chants_player)

    def test_muted_fade_can_unmute_without_restoring_stale_volume(self):
        runtime = fixtures.CrowdAudioSafetyTests().make_runtime()
        app=runtime.app
        app._goal_audio_player=app._chants_player
        app._goal_base_volume=.2
        app._goal_master_volume=0
        app._chants_volume_is_crowd=False
        def change_volume(*args):
            app._goal_master_volume=.5
        with patch('server16_py.chants_runtime.time.sleep',side_effect=change_volume):
            runtime.fade_player(app._chants_player,0,0,100,follow_master=True)
        app._chants_player.set_volume.assert_called_with(.1)
        with patch('server16_py.chants_runtime.time.sleep'):
            runtime.fade_player(app._chants_player,.1,0,100)
        app._chants_player.set_volume.assert_called_with(0)

    def test_equal_button_sizes_and_slider_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                panel=selector.audio_panel
                self.assertEqual(panel.CANCEL[2]-panel.CANCEL[0],panel.GENERAL[2]-panel.GENERAL[0])
                self.assertEqual(panel.GENERAL[2]-panel.GENERAL[0],panel.MATCH[2]-panel.MATCH[0])
                for _ in range(25): selector.handle(2,0)
                self.assertEqual(panel.values[0],0)
                for _ in range(25): selector.handle(3,0)
                self.assertEqual(panel.values[0],100)
                selector.close(); selector.open()
                buttons={action:rect for rect,action in selector.targets}
                self.assertEqual(buttons['cancel'][2]-buttons['cancel'][0],buttons['apply'][2]-buttons['apply'][0])
            finally:
                selector.shutdown()

    def test_hover_has_visible_focus_without_adjusting_or_saving_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                values=list(selector.audio_panel.values)
                selector.handle(15,(389<<16)|440)
                self.assertEqual(selector.audio_panel.focus,4)
                with Image.open(selector.shared.image_path) as card:
                    self.assertEqual(card.getpixel((430*2,375*2))[:3],(18,61,134))
                    self.assertEqual(card.getpixel((401*2,385*2))[:3],(0,82,204))
                serial=selector.serial
                selector.handle(15,(389<<16)|441)
                self.assertEqual(selector.serial,serial)
                selector.handle(15,(248<<16)|80)
                self.assertEqual(selector.audio_panel.focus,1)
                self.assertEqual(selector.audio_panel.values,values)
                self.assertTrue(selector.opened)
                selector.app.chants_runtime.apply_crowd_master_volume.assert_not_called()
                selector.app.chants_runtime.apply_goal_master_volume.assert_not_called()
            finally: selector.shutdown()

    def test_general_apply_is_immediate_but_next_fixture_recovers_specific_priority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            selector=self.make_selector(root)
            try:
                self.open_audio(selector)
                selector.audio_panel.values=[65,40]
                selector.audio_panel.focus=4
                selector.handle(6,0)
                self.assertFalse(selector.opened)
                self.assertEqual(selector.app.settings.crowd_master_volume,1)
                self.assertEqual(selector.app.settings.goal_master_volume,1)
                self.assertEqual(selector.app._crowd_master_volume,.65)
                selector.app.audio_profiles=AudioProfileRuntime(selector.app)
                selector.app.audio_profiles.bind(selector.app.exedir)
                selector.app._crowd_master_volume=selector.app._goal_master_volume=1
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[65,40])
                selector.audio_panel.values=[80,50]
                selector.audio_panel.apply('general')
                self.assertFalse(selector.opened)
                self.assertEqual(selector.app._crowd_master_volume,.8)
                self.assertEqual(selector.app._goal_master_volume,.5)
                self.assertEqual(selector.app.settings.crowd_master_volume,.8)
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[80,50])
                self.assertEqual(selector.audio_panel.runtime.source,'general')
                self.assertTrue(selector.audio_panel.runtime.has_match_profile)
                selector.handle(7,0)
                self.assertFalse(selector.opened)
                selector.app.AID='999'
                selector.app._kickoff_generation+=1
                selector.app.audio_profiles.sync()
                self.assertEqual(selector.app._crowd_master_volume,.8)
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[80,50])
                self.assertFalse(selector.audio_panel.runtime.has_match_profile)
                selector.close();selector.app.AID='2';self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[65,40])
            finally:selector.shutdown()

    def test_apply_labels_fit_equal_buttons(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                panel=selector.audio_panel
                self.assertEqual([label for _,_,label in panel.buttons()],
                ['Cancelar','Aplicar geral','Aplicar específico'])
                from server16_py.overlay_canvas import OverlayDraw
                draw=OverlayDraw(panel.render())
                for _,rect,label in panel.buttons():
                    self.assertLessEqual(draw.textlength(label,font=selector.font(14)),rect[2]-rect[0]-16)
            finally:selector.shutdown()

    def test_modal_apply_updates_real_crowd_level_and_never_unpauses_audio(self):
        from server16_py.chants_runtime import ChantsRuntime
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                app=selector.app
                app._set_display_async=Mock()
                app.chants_runtime=ChantsRuntime(app)
                app._chants_player=SimpleNamespace(volume=.2)
                player=app._chants_player
                player.set_volume=lambda volume:setattr(player,'volume',volume)
                app._chants_base_volume=.2
                app._chants_volume_is_crowd=True
                app._chants_paused=False
                self.open_audio(selector)
                selector.audio_panel.runtime.save_match((.65,.4))
                selector.audio_panel.values=[0,25]
                selector.audio_panel.apply('general')
                self.assertEqual(player.volume,0)
                self.assertEqual(app.audio_profiles.sync(),(0,.25))
                self.open_audio(selector)
                selector.audio_panel.values=[50,30]
                selector.audio_panel.apply('match')
                self.assertEqual(player.volume,.1)
                # Apply restores the correct live level even if values didn't change.
                player.volume=0
                self.open_audio(selector)
                selector.audio_panel.apply('match')
                self.assertEqual(player.volume,.1)
                app._chants_paused=True
                self.open_audio(selector)
                selector.audio_panel.values=[80,75]
                selector.audio_panel.apply('general')
                self.assertEqual(player.volume,0)
                self.assertAlmostEqual(app._chants_target_volume,.16)
                app._chants_paused=False
                app.chants_runtime.apply_crowd_master_volume()
                self.assertAlmostEqual(player.volume,.16)
            finally:selector.shutdown()

    def test_legacy_amplification_and_untouched_precision_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                selector.app.settings.data.update(CROWD_MASTER_VOLUME=1.737,GOAL_MASTER_VOLUME=.427)
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[174,43])
                self.assertEqual(selector.audio_panel.maximums,[200,100])
                selector.audio_panel.apply('match')
                self.assertEqual(selector.app._crowd_master_volume,1.737)
                self.assertEqual(selector.app._goal_master_volume,.427)
                self.open_audio(selector)
                self.assertEqual(selector.audio_panel.values,[174,43])
            finally:selector.shutdown()

    def test_corrupt_file_cancel_or_changed_installation_cannot_save_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);selector=self.make_selector(root)
            try:
                self.open_audio(selector)
                path=selector.app.audio_profiles.path
                original=path.read_bytes()
                selector.handle(2,0);selector.handle(7,0)
                self.assertEqual(path.read_bytes(),original)
                path.write_bytes(b'broken json')
                self.open_audio(selector)
                selector.audio_panel.values=[10,20]
                selector.audio_panel.apply('match')
                self.assertTrue(selector.opened)
                self.assertEqual(path.read_bytes(),b'broken json')
                self.assertEqual(selector.app._crowd_master_volume,1)
                selector.app.audio_profiles.bind(root/'different_game')
                selector.audio_panel.apply('match')
                self.assertFalse(selector.opened)
                self.assertFalse((root/'different_game/FSW/audio_profiles.json').exists())
            finally:selector.shutdown()

    def test_external_profile_removal_while_focused_keeps_navigation_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                selector.audio_panel.apply('match')
                self.open_audio(selector)
                selector.audio_panel.focus=4
                selector.app.audio_profiles.save_match()
                selector.handle(5,0)
                self.assertEqual(selector.audio_panel.focus,0)
                selector.handle(7,0)
                self.assertFalse(selector.opened)
            finally:selector.shutdown()

    def test_preloaded_catalog_reopen_and_busy_stadium_browsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'BRA - A.zip').touch()
            (root/'ESP - B.zip').touch()
            selector=fixtures.StadiumSelectorTests().make_selector(root)
            try:
                selector._attempted_pid=1234
                selector.tick()
                selector._catalog_thread.join(timeout=5)
                selector._drain_catalog()
                self.assertFalse(selector.opened)
                with patch('server16_py.stadium_selector.build_catalog',side_effect=AssertionError('cache miss')):
                    selector.open()
                    self.assertFalse(selector.loading)
                    selector.close(); selector.open()
                selector.app._stadium_task_running=True
                selector.tick()
                self.assertEqual(selector.shared.enabled,1)
                selector.handle(3,0)
                self.assertEqual(selector.index,1)
                selector.apply()
                selector.app.stadium_runtime.apply_manual_stadium.assert_called_once_with('ESP - B',selector.context)
                selector.handle(7,0)
                self.assertFalse(selector.opened)
            finally:
                selector.shutdown()

    def test_render_keeps_previous_revision_until_file_is_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                self.open_audio(selector)
                revision=selector.shared.render_ready
                save=Image.Image.save
                def check_save(image,*args,**kwargs):
                    self.assertEqual(selector.shared.render_ready,revision)
                    self.assertEqual(selector.shared.visible,1)
                    return save(image,*args,**kwargs)
                with patch.object(Image.Image,'save',check_save):
                    selector.handle(2,0)
                self.assertGreater(selector.shared.render_ready,revision)
            finally:
                selector.shutdown()


if __name__=='__main__':
    unittest.main()
