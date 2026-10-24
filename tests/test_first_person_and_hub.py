import ctypes
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from PIL import Image
from server16_py.first_person_runtime import CameraShared, FirstPersonRuntime, load_preferences, save_preferences
from server16_py.match_hub_panel import MatchHubPanel
import test_match_audio_panel as audio_fixtures


class CameraRuntimeTests(unittest.TestCase):
    def test_head_smoothing_persists_all_levels_and_survives_other_edits(self):
        with tempfile.TemporaryDirectory() as d:
            app=SimpleNamespace(base_dir=Path(d),memory=SimpleNamespace(is_open=lambda:False),log=Mock())
            with patch('server16_py.first_person_runtime.MAPPING_NAME',f'Local\\camera_smoothing_test_{os.getpid()}'):
                for profile in range(4):
                    runtime=FirstPersonRuntime(app)
                    try:
                        runtime.configure(head_smoothing=profile,enabled=True,fov=150)
                        runtime.configure(mode=1,distance=2)
                        runtime.configure(mode=0)
                        self.assertEqual((runtime.profile,runtime.shared.profile),(profile,profile))
                    finally:runtime.close()
                    runtime=FirstPersonRuntime(app)
                    try:
                        self.assertEqual((runtime.profile,runtime.shared.profile,runtime.shared.requested,runtime.fov),(profile,profile,1,150))
                    finally:runtime.close()

    def test_preferences_validate_corrupt_and_wrong_types(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'camera.json'
            self.assertEqual(load_preferences(p),(False,85,0))
            for data in ('[]','null','broken','{"enabled":1,"fov":true}', '{"enabled":"true","fov":121}'):
                p.write_text(data)
                self.assertEqual(load_preferences(p),(False,85,0))
            p.write_text('{"profile":0,"framing":0,"fov":90,"look_bias":20}')
            self.assertEqual(load_preferences(p),(False,85,0))
            p.write_text('{"fov":115}')
            self.assertEqual(load_preferences(p),(False,85,0))
            save_preferences(p,True,80,1)
            self.assertEqual(load_preferences(p),(True,80,1))  # New explicit choices survive.
            p.write_text('{"version":3,"mode":true}')
            self.assertEqual(load_preferences(p),(False,85,0))

    def test_command_ack_preferences_and_shutdown(self):
        self.assertEqual(ctypes.sizeof(CameraShared),80)
        with tempfile.TemporaryDirectory() as d:
            app=SimpleNamespace(base_dir=Path(d),memory=SimpleNamespace(is_open=lambda:True),_resolve_fifa_pid=lambda:1234,log=Mock())
            with patch('server16_py.first_person_runtime.MAPPING_NAME',f'Local\\camera_test_{os.getpid()}'):
                runtime=FirstPersonRuntime(app)
            try:
                self.assertEqual(runtime.status(),'Câmera original ativa.')
                runtime.configure(enabled=True,fov=85,mode=1)
                self.assertEqual((runtime.shared.profile,runtime.shared.framing,runtime.shared.look_bias),(0,1,0))
                self.assertEqual((runtime.shared.version,runtime.shared.fov,runtime.shared.mode),(4,85,1))
                runtime.shared.ready=1
                runtime.tick()  # Initial pid must not discard first activation.
                self.assertEqual(runtime.shared.requested,1)
                self.assertIn('Conectando',runtime.status())
                runtime.shared.ack=runtime.shared.command
                runtime.shared.enabled=runtime.shared.valid=1
                self.assertEqual(runtime.status(),'Terceira pessoa ativa.')
                saved=json.loads(runtime.path.read_text())
                self.assertEqual(saved,{'version':4,'enabled':True,'mode':1,'fov_first_person':85,'fov_career':85,'distance':0,'head_smoothing':0})
                command=runtime.shared.command
                for kwargs in ({'fov':121},{'fov':True},{'enabled':1},{'mode':2},{'mode':False},{'distance':3},{'distance':True},{'head_smoothing':4},{'head_smoothing':True}):
                    with self.assertRaises(ValueError):runtime.configure(**kwargs)
                    self.assertEqual(runtime.shared.command,command)
                for mode in (0,1):
                    runtime.configure(mode=mode)
                    self.assertEqual((runtime.shared.mode,runtime.shared.requested),(mode,1))
                    runtime.shared.ack=runtime.shared.command
                runtime.shared.enabled=0  # F10 while the overlay is closed.
                runtime._last_tick=100
                with patch('server16_py.first_person_runtime.time.monotonic',return_value=100):runtime.tick()
                self.assertTrue(runtime.enabled)  # One stale enabled mirror must not erase On.
                with patch('server16_py.first_person_runtime.time.monotonic',return_value=100.3):runtime.tick()
                self.assertEqual(runtime.shared.requested,0)
                self.assertEqual(load_preferences(runtime.path),(False,85,1))
                runtime.shared.error=1
                self.assertIn('Outra câmera',runtime.status())
                runtime.configure(enabled=False)
                self.assertEqual(runtime.shared.requested,0)
                runtime.configure(mode=0)
                self.assertEqual(runtime.shared.requested,0)  # Switching modes never forces On.
            finally:runtime.close()

    def test_saved_activation_restores_without_menu_across_server_and_game_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            app=SimpleNamespace(base_dir=Path(d),memory=SimpleNamespace(is_open=lambda:False),_resolve_fifa_pid=lambda:1234,log=Mock())
            path=Path(d)/'runtime/first_person_camera.json'
            save_preferences(path,True,75,1)
            with patch('server16_py.first_person_runtime.MAPPING_NAME',f'Local\\camera_restart_test_{os.getpid()}'):
                runtime=FirstPersonRuntime(app)
                try:
                    self.assertEqual(runtime.shared.requested,1)
                    self.assertIn('aguardando o FIFA',runtime.status())
                    app.memory.is_open=lambda:True
                    with patch('server16_py.first_person_runtime.threading.Thread') as thread:
                        runtime.tick()
                        thread.return_value.start.assert_called_once()
                    runtime.shared.ready=1
                    runtime.shared.ack=runtime.shared.command
                    runtime.shared.enabled=1
                    runtime.tick()
                    self.assertTrue(runtime.enabled)
                    runtime.shared.enabled=0
                    runtime._last_tick=0  # Native watchdog after a Server stall.
                    runtime.tick()
                    self.assertTrue(runtime.enabled)
                    # Process loss is not the user's off switch.
                    app.memory.is_open=lambda:False
                    runtime.tick()
                    self.assertEqual(runtime.shared.requested,1)
                    self.assertTrue(load_preferences(path)[0])
                    app.memory.is_open=lambda:True
                    app._resolve_fifa_pid=lambda:5678
                    runtime.tick()
                    self.assertEqual((runtime.game_pid,runtime.shared.requested),(5678,1))
                    runtime.shared.ready=1
                    runtime.shared.error=1  # Hook conflict must not change the saved choice.
                    runtime.shared.ack=runtime.shared.command
                    runtime.tick()
                    self.assertTrue(runtime.enabled)
                    runtime.shared.error=3  # Deferred initialization preserves saved On.
                    runtime.tick()
                    self.assertTrue(runtime.enabled)
                    self.assertIn('aguardando inicialização',runtime.status())
                    self.assertTrue(load_preferences(path)[0])
                    runtime.configure(fov=85)
                    self.assertTrue(runtime.enabled)
                finally:runtime.close()
                runtime=FirstPersonRuntime(app)
                try:
                    self.assertEqual((runtime.shared.requested,runtime.fov,runtime.shared.mode),(1,85,1))
                    runtime.configure(enabled=False)
                finally:runtime.close()
                self.assertEqual(load_preferences(path),(False,85,1))

    def test_modes_keep_separate_lenses_and_migrate_the_old_wide_career_lens(self):
        with tempfile.TemporaryDirectory() as d:
            app=SimpleNamespace(base_dir=Path(d),memory=SimpleNamespace(is_open=lambda:False),log=Mock())
            path=Path(d)/'runtime/first_person_camera.json'
            path.parent.mkdir()
            path.write_text('{"version":3,"enabled":true,"fov":120,"mode":1}')
            self.assertEqual(load_preferences(path),(True,85,1))
            with patch('server16_py.first_person_runtime.MAPPING_NAME',f'Local\\camera_lenses_test_{os.getpid()}'):
                runtime=FirstPersonRuntime(app)
                try:
                    runtime.configure(mode=0)
                    self.assertEqual((runtime.fov,runtime.shared.fov),(85,85))
                    runtime.configure(fov=150)
                    self.assertEqual((runtime.fov,runtime.shared.fov),(150,150))
                    with self.assertRaises(ValueError):runtime.configure(fov=151)
                    runtime.configure(mode=1)
                    self.assertEqual((runtime.fov,runtime.shared.fov),(85,85))
                    with self.assertRaises(ValueError):runtime.configure(fov=105)
                    runtime.configure(fov=70)
                    runtime.configure(distance=2)
                    self.assertEqual(runtime.shared.distance,2)
                    runtime.configure(mode=0)
                    self.assertEqual(runtime.fov,150)
                finally:runtime.close()
                runtime=FirstPersonRuntime(app)
                try:
                    self.assertEqual(runtime.fov,150)
                    runtime.configure(mode=1)
                    self.assertEqual(runtime.fov,70)
                    self.assertEqual(runtime.distance,2)
                finally:runtime.close()

    def test_save_failure_keeps_current_camera_choice(self):
        with tempfile.TemporaryDirectory() as d:
            app=SimpleNamespace(base_dir=Path(d),memory=SimpleNamespace(is_open=lambda:False),log=Mock())
            with patch('server16_py.first_person_runtime.MAPPING_NAME',f'Local\\camera_save_test_{os.getpid()}'):
                runtime=FirstPersonRuntime(app)
            try:
                with patch('server16_py.first_person_runtime.save_preferences',side_effect=PermissionError('locked')):
                    with self.assertRaises(PermissionError):runtime.configure(enabled=True,fov=115)
                self.assertEqual((runtime.enabled,runtime.fov,runtime.shared.requested),(False,85,0))
            finally:runtime.close()


class HubTests(unittest.TestCase):
    def test_music_apply_returns_to_categories_and_updates_volume(self):
        with tempfile.TemporaryDirectory() as d:
            selector=audio_fixtures.MatchAudioTests().make_selector(Path(d))
            try:
                selector.open(audio=True)
                hub=selector.audio_panel
                selector.handle(6,0)
                hub.child.values=[65,40]
                selector.handle(18,1)
                self.assertTrue(selector.opened)
                self.assertIsNone(hub.child)
                self.assertEqual(hub.page,'home')
                self.assertEqual(selector.app._crowd_master_volume,.65)
                self.assertEqual(selector.app._goal_master_volume,.4)
            finally:selector.shutdown()

    def test_music_back_and_camera_settings_do_not_leak_to_game(self):
        with tempfile.TemporaryDirectory() as d:
            selector=audio_fixtures.MatchAudioTests().make_selector(Path(d))
            runtime=SimpleNamespace(enabled=False,fov=105,mode=0,distance=0,profile=0,status=lambda:'Câmera original ativa.',configure=Mock())
            try:
                selector.open(audio=True)
                hub=selector.audio_panel
                self.assertIsInstance(hub,MatchHubPanel)
                self.assertEqual([i[0] for i in hub.items()],['Música','Gráficos','Câmera','Controles','Fechar'])
                selector.handle(6,0)
                self.assertFalse(hub.child.include_cloth)
                selector.handle(2,0)
                self.assertEqual(hub.child.values[0],95)
                selector.handle(7,0)
                self.assertEqual(hub.page,'home')
                self.assertTrue(selector.opened)
                self.assertEqual(selector.app._crowd_master_volume,1)
                with patch.object(hub,'camera',return_value=runtime):
                    hub.activate(2)
                    selector.handle(6,0)
                    runtime.configure.assert_called_with(enabled=True)
                    self.assertEqual([i[0] for i in hub.items()],['Câmera do jogador','Modo','Campo de visão','Suavização da cabeça','Voltar'])
                    selector.handle(5,0)
                    selector.handle(6,0)
                    runtime.configure.assert_called_with(mode=1)
                    runtime.mode=1
                    self.assertEqual(hub.items()[3],('Distância','Perto'))
                    hub.focus=3
                    selector.handle(3,0)
                    runtime.configure.assert_called_with(distance=1)
                    hub.focus=1
                    selector.handle(2,0)
                    runtime.configure.assert_called_with(mode=0)
                    runtime.mode=0
                    selector.handle(5,0)
                    selector.handle(2,0)
                    runtime.configure.assert_called_with(fov=100)
                    for pad in (False,True):
                        selector.controller_connected=pad
                        image=hub.render()
                        self.assertEqual(image.size,(1200,980))
                    selector.handle(3,0)
                    runtime.configure.assert_called_with(fov=110)
                    runtime.fov=145
                    selector.handle(3,0)
                    runtime.configure.assert_called_with(fov=150)
                    runtime.fov=150
                    selector.handle(3,0)
                    runtime.configure.assert_called_with(fov=150)
                    runtime.fov=75
                    selector.handle(2,0)
                    runtime.configure.assert_called_with(fov=75)
                    hub.focus=3
                    selector.handle(3,0)
                    runtime.configure.assert_called_with(head_smoothing=1)
                    selector.handle(2,0)
                    runtime.configure.assert_called_with(head_smoothing=3)
                    hub.focus=4
                    selector.handle(6,0)
                self.assertEqual(hub.page,'home')
                selector.handle(7,0)
                self.assertFalse(selector.opened)
            finally:selector.shutdown()

    def test_changed_fixture_cannot_change_camera(self):
        with tempfile.TemporaryDirectory() as d:
            selector=audio_fixtures.MatchAudioTests().make_selector(Path(d))
            try:
                selector.open(audio=True)
                hub=selector.audio_panel
                selector.app._kickoff_generation+=1
                with patch.object(hub,'camera') as camera:
                    hub.page='camera'
                    hub.activate(0)
                    camera.assert_not_called()
                self.assertFalse(selector.opened)
            finally:selector.shutdown()
