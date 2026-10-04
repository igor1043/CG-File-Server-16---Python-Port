from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.audio_profiles import AudioProfileError, AudioProfileRuntime, AudioProfileStore
from server16_py.settings_store import SettingsStore
from server16_py.app import Server16App


class AudioProfileTests(unittest.TestCase):
    def runtime(self, root):
        app=SimpleNamespace(settings=SettingsStore(root/'settings.json'),
            HID='1043',AID='545',_kickoff_generation=1,
            _crowd_master_volume=1.,_goal_master_volume=1.,log=Mock(),chants_runtime=Mock())
        runtime=AudioProfileRuntime(app)
        app.audio_profiles=runtime
        runtime.bind(root/'game')
        return runtime

    def test_creation_preservation_restart_directed_ids_and_other_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=self.runtime(root)
            self.assertEqual(runtime.sync(),(1.,1.))
            path=runtime.path
            original=json.loads(path.read_text())
            original['notes']='keep this'
            original['matches']['7:8']={'chants':.9,'goal_hymns':.8,'name':'another match'}
            path.write_text(json.dumps(original),encoding='utf-8')
            runtime.save_match((.72,.4))
            result=json.loads(path.read_text())
            self.assertEqual(result['notes'],'keep this')
            self.assertEqual(result['matches']['7:8'],original['matches']['7:8'])
            restart=self.runtime(root)
            self.assertEqual(restart.sync(),(.72,.4))
            self.assertEqual(restart.app.settings.crowd_master_volume,1)
            restart.app.HID,restart.app.AID='545','1043'
            self.assertEqual(restart.sync(),(1.,1.))
            restart.app.HID,restart.app.AID='7','8'
            self.assertEqual(restart.sync(),(.9,.8))

    def test_live_context_recovers_profile_and_clear_returns_to_general(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));app=runtime.app
            runtime.save_general((.8,.6));runtime.save_match((.3,.2))
            app._set_display=Mock();app._update_team_logo=Mock();app.tr=lambda key:key
            app.display_value=lambda key:key
            Server16App._clear_live_context(app)
            self.assertEqual((app._crowd_master_volume,app._goal_master_volume),(.8,.6))
            app._read_legacy_team_context=lambda:('1043','545')
            app._read_dashboard_pointer=lambda *args:0
            app.offsets=SimpleNamespace(ORISTADIDBASE=0,S=list(range(6)),ORITOURIDBASE=0,T=list(range(6)))
            app._try_read_context_int=lambda trace,*args:'176' if trace=='S-FIRST' else None
            app._resolve_team_name=lambda team_id:team_id
            app._update_live_match_stats=Mock()
            app._should_auto_apply_runtime=lambda page:False
            Server16App.refresh_live_context(app,'game/screens/playNow/KickOffHub')
            self.assertEqual((app._crowd_master_volume,app._goal_master_volume),(.3,.2))
            app.HID,app.AID='999','545'
            runtime.sync()
            self.assertEqual((app._crowd_master_volume,app._goal_master_volume),(.8,.6))
            runtime.bind(Path(directory)/'other_game')
            self.assertEqual(runtime.sync(),(.8,.6))
            self.assertTrue(runtime.path.is_file())

    def test_legacy_general_volume_adjustment_preserves_match_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));app=runtime.app
            runtime.save_match((.7,.4))
            app._update_crowd_volume_popup=Mock()
            Server16App._set_crowd_master_volume(app,1.5)
            self.assertEqual(app.settings.crowd_master_volume,1.5)
            self.assertEqual((app._crowd_master_volume,app._goal_master_volume),(.7,.4))
            self.assertTrue(app._crowd_master_volume_dirty)
            app.HID='999'
            runtime.sync()
            self.assertEqual((app._crowd_master_volume,app._goal_master_volume),(1.5,1.))

    def test_invalid_json_version_values_and_ids_preserve_existing_file(self):
        cases=[b'{bad',b'{"version":2,"matches":{}}',
            b'{"version":1,"matches":{"1:2":{"chants":NaN,"goal_hymns":1}}}',
            b'{"version":1,"matches":{"1:2":{"chants":true,"goal_hymns":1}}}',
            b'{"version":1,"matches":{"1:2":{"chants":1,"goal_hymns":2}}}',
            b'{"version":1,"matches":{"0:2":{"chants":1,"goal_hymns":1}}}']
        cases.append(json.dumps({'version':1,'matches':{'1:2':{'chants':10**400,'goal_hymns':1}}}).encode())
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));runtime.sync()
            for content in cases:
                with self.subTest(content=content):
                    runtime.path.write_bytes(content)
                    self.assertEqual(runtime.sync(force=True),(1.,1.))
                    with self.assertRaises(AudioProfileError):runtime.save_match((.5,.5))
                    self.assertEqual(runtime.path.read_bytes(),content)
            runtime.app.HID=''
            with self.assertRaises(AudioProfileError):runtime.save_match((.5,.5))

    def test_failed_replace_and_concurrent_edit_do_not_apply_or_destroy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));runtime.save_match((.7,.6))
            previous=runtime.path.read_bytes()
            with patch.object(Path,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):runtime.save_match((.1,.2))
            self.assertEqual(runtime.path.read_bytes(),previous)
            self.assertEqual((runtime.app._crowd_master_volume,runtime.app._goal_master_volume),(.7,.6))
            self.assertEqual(list(runtime.path.parent.glob('.audio_profiles_*.tmp')),[])
            original_stamp=runtime.store._stamp
            calls=0
            def changed_stamp():
                nonlocal calls
                calls+=1
                if calls==2:runtime.path.write_bytes(previous+b'\n')
                return original_stamp()
            with patch.object(runtime.store,'_stamp',side_effect=changed_stamp):
                with self.assertRaisesRegex(AudioProfileError,'mudou'):runtime.save_match((.1,.2))
            self.assertEqual(runtime.path.read_bytes(),previous+b'\n')
            self.assertEqual(list(runtime.path.parent.glob('.audio_profiles_*.tmp')),[])

    def test_manual_edit_is_reloaded_without_changing_global_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));runtime.save_match((.5,.6))
            document=json.loads(runtime.path.read_text())
            document['matches']['1043:545']['chants']=.333
            runtime.path.write_text(json.dumps(document),encoding='utf-8')
            self.assertEqual(runtime.sync(),(.333,.6))
            self.assertEqual(runtime.app.settings.crowd_master_volume,1)
            original=runtime.path.read_bytes()
            runtime.sync(force=True)
            self.assertEqual(runtime.path.read_bytes(),original)

    def test_explicit_general_apply_preserves_file_and_survives_refresh_until_next_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=self.runtime(root);app=runtime.app
            runtime.save_match((.7,.4))
            previous=runtime.path.read_bytes()
            app.chants_runtime.reset_mock()
            self.assertEqual(runtime.apply_general((.8,.6)),(.8,.6))
            self.assertEqual(runtime.path.read_bytes(),previous)
            app.chants_runtime.apply_crowd_master_volume.assert_called_once()
            app.chants_runtime.apply_goal_master_volume.assert_called_once()
            self.assertEqual(runtime.sync(force=True),(.8,.6))
            self.assertEqual(runtime.source,'general')
            self.assertTrue(runtime.has_match_profile)
            self.assertEqual(self.runtime(root).sync(),(.7,.4))
            app._kickoff_generation+=1
            self.assertEqual(runtime.sync(),(.7,.4))
            app.HID='999'
            self.assertEqual(runtime.sync(),(.8,.6))

    def test_specific_apply_supersedes_session_general_and_refreshes_same_live_values(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));app=runtime.app
            runtime.save_match((.7,.4))
            runtime.apply_general((.8,.6))
            self.assertEqual(runtime.apply_match((.2,.3)),(.2,.3))
            self.assertEqual(runtime.source,'match')
            app.chants_runtime.reset_mock()
            self.assertEqual(runtime.apply_match((.2,.3)),(.2,.3))
            app.chants_runtime.apply_crowd_master_volume.assert_called_once()
            app.chants_runtime.apply_goal_master_volume.assert_called_once()
            self.assertEqual(runtime.sync(force=True),(.2,.3))

    def test_failed_apply_keeps_active_values_and_previous_override(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=self.runtime(Path(directory));app=runtime.app
            runtime.save_match((.7,.4));runtime.apply_general((.8,.6))
            previous=dict(app.settings.data)
            app.chants_runtime.reset_mock()
            with patch.object(app.settings,'save',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):runtime.apply_general((.1,.2))
            self.assertEqual(app.settings.data,previous)
            with patch.object(Path,'replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):runtime.apply_match((.1,.2))
            self.assertEqual(runtime.sync(),(.8,.6))
            app.chants_runtime.apply_crowd_master_volume.assert_not_called()
            app.chants_runtime.apply_goal_master_volume.assert_not_called()

    def test_manual_specific_edit_and_installation_change_expire_general_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=self.runtime(root)
            runtime.save_match((.7,.4));runtime.apply_general((.8,.6))
            document=json.loads(runtime.path.read_text())
            document['matches']['1043:545']['chants']=.333
            runtime.path.write_text(json.dumps(document),encoding='utf-8')
            self.assertEqual(runtime.sync(),(.333,.4))
            runtime.apply_general((.8,.6))
            runtime.bind(root/'different_game')
            runtime.save_match((.1,.2))
            self.assertEqual(runtime.sync(),(.1,.2))


if __name__=='__main__':unittest.main()
