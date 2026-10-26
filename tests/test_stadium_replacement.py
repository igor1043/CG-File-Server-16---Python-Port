"""Isolated game tree: repeated swaps, inactive slot and recovery semantics."""
import os
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.app import Server16App
from server16_py.offsets import Offsets
from server16_py.stadium_runtime import StadiumRuntime
from server16_py.stadium_transaction import StadiumAssetTransaction
from server16_py.stadium_match_assets import clear_match_routes


class StadiumReplacementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game, self.packages = self.root/'game', self.root/'packages'
        self.assignments = {('stadium','1'): 'A,B,C,None,None,None'}
        self.current_id = 192
        self.app = SimpleNamespace(
            base_dir=self.root, exedir=self.game, targetpath=self.packages,
            HID='1', AID='2', TOURNAME='10', TOURROUNDID='20',
            _kickoff_generation=1, _stadium_task_running=False,
            _stadium_task_request_key=None, _stadium_task_signature=None,
            _last_stadium_applied_signature=None, _last_runtime_signature=('1','2','10','20'),
            _manual_stadium_override=None, _stadium_fixture_entered=False,
            CCount='0', curstad='', injID='176', PoliceNum='4', Stadiumtype='alter',
            settings=SimpleNamespace(random_stadium_selection=True),
            settings_ini=SimpleNamespace(
                key_exists=lambda key, section: (section,key) in self.assignments,
                read=lambda key, section: self.assignments.get((section,key), '')),
            offsets=Offsets(), memory=Mock(), _worker_queue=queue.Queue(),
            lastpagename='game/screens/playNow/KickOffHub', log=Mock(),
            Psource=self.game/'FSW/Police', Nsource=self.game/'FSW/Nets',
            PitchMowsource=self.game/'FSW/PitchMowPattern',
            Pdest=self.game/'data/sceneassets/slc', Ndest=self.game/'data/sceneassets/goalnet',
            PitchMowdest=self.game/'data/sceneassets/pitch',
            Movdata=self.game/'data/movies/bootflowoutro.vp8', MOVBUMP=self.game/'data/ui/TV/bumper.big',
            gold='gold', success='green', _set_progress=Mock(), _set_process_status=Mock(),
            _set_display=Mock(), _update_audio_overview=Mock(), _hide_stadium_loading_modal=Mock(),
            _show_stadium_loading_modal=Mock(), _update_stadium_loading_modal=Mock(),
            _schedule_worker_poll=Mock())
        self.app.memory.is_open.return_value = True
        self.app.memory.get_int.side_effect = lambda *args: self.current_id
        self.app.memory.write_int.side_effect = lambda base, offsets, value: setattr(self, 'current_id', int(value))
        self.runtime = StadiumRuntime(self.app)
        self.app.stadium_runtime = self.runtime
        self.runtime.play_stadium_loaded_sound = Mock()
        for slot in ('176','261'):
            for suffix, contents in (('', b'native model'), ('_1_textures', b'native day'), ('_3_textures', b'native night')):
                self.put(self.game/f'FSW/Stadium/stadium/stadium_{slot}{suffix}.rx3', contents)
                self.put(self.game/f'data/sceneassets/stadium/stadium_{slot}{suffix}.rx3', contents)
        for name in ('A','B','C'):
            self.put(self.packages/name/'model.rx3', (name+' model').encode())
            self.put(self.packages/name/'texture_day.rx3', (name+' day').encode())
            self.put(self.packages/name/'texture_night.rx3', (name+' night').encode())

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def files(self):
        return {path.relative_to(self.game): path.read_bytes() for path in (self.game/'data').rglob('*') if path.is_file()}

    def context(self):
        a=self.app
        return (a._kickoff_generation, a.HID, a.AID, a.TOURNAME, a.TOURROUNDID)

    def apply_synchronously(self, name, section='manual'):
        slot, _ = self.runtime._next_injection_slot()
        if section == 'manual':
            self.runtime._previous_manual_override = self.app._manual_stadium_override
            self.app._manual_stadium_override = (self.context(), name, f'{name},None,None,None')
        self.app._stadium_task_running = True
        self.app._stadium_task_signature = (name,slot)
        self.app._stadium_task_request_key = (section,'1',f'{name},None,None,None')
        self.runtime.pending_selection = (self.context()[:3],name)
        payload = self.runtime.run_stadium_copy_job('1', section, slot, name,
            f'{name},None,None,None', expected_context=self.context()[:3])
        payload['context'] = self.context()[:3]
        self.runtime.finish_stadium_apply(payload)
        return slot

    def assert_pack(self, slot, name):
        folder=self.game/'data/sceneassets/stadium'
        self.assertEqual((folder/f'stadium_{slot}.rx3').read_bytes(), (name+' model').encode())
        self.assertEqual((folder/f'stadium_{slot}_1_textures.rx3').read_bytes(), (name+' day').encode())
        self.assertEqual((folder/f'stadium_{slot}_3_textures.rx3').read_bytes(), (name+' night').encode())

    def test_three_replacements_use_inactive_slot_and_never_reset_active_assets(self):
        self.assertEqual(self.apply_synchronously('A', 'stadium'), '176')
        active = {p:b for p,b in self.files().items() if '176' in p.name}
        self.assertEqual(self.apply_synchronously('B'), '261')
        for rel, data in active.items(): self.assertEqual((self.game/rel).read_bytes(), data)
        active = {p:b for p,b in self.files().items() if '261' in p.name}
        self.assertEqual(self.apply_synchronously('C'), '176')
        for rel, data in active.items(): self.assertEqual((self.game/rel).read_bytes(), data)
        self.assert_pack('176','C')
        self.assert_pack('261','B')
        self.assertEqual(self.current_id, 176)
        self.assertEqual(list((self.game/'runtime').iterdir()), [])

    def test_same_stadium_reapplication_also_switches_slots_despite_counter(self):
        self.apply_synchronously('A', 'stadium')
        self.app.CCount = '0'  # stale counter must not replace active 176.
        self.assertEqual(self.apply_synchronously('A'), '261')
        self.assertEqual(self.app.CCount, '0')

    def test_identical_size_and_timestamp_cannot_skip_different_texture_bytes(self):
        native = self.game/'FSW/Stadium/stadium/stadium_176_1_textures.rx3'
        pack = self.packages/'A/texture_day.rx3'
        pack.write_bytes(b'X'*native.stat().st_size)
        stat=native.stat()
        os.utime(pack, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.apply_synchronously('A', 'stadium')
        self.assertEqual((self.game/'data/sceneassets/stadium/stadium_176_1_textures.rx3').read_bytes(),pack.read_bytes())

    def test_copy_failure_before_publication_keeps_whole_previous_stadium(self):
        self.apply_synchronously('A', 'stadium')
        before=self.files()
        original=__import__('shutil').copy2
        def fail(src,dst,*args,**kwargs):
            if Path(src)==self.packages/'B/texture_night.rx3': raise PermissionError('simulated locked texture')
            return original(src,dst,*args,**kwargs)
        with patch('server16_py.stadium_runtime.shutil.copy2', side_effect=fail):
            with self.assertRaises(PermissionError):
                self.runtime.run_stadium_copy_job('1','manual','261','B','B,None,None,None',self.context()[:3])
        self.assertEqual(self.files(),before)
        self.assertEqual(self.current_id,176)

    def test_partial_publication_rolls_back_all_files_and_selected_id(self):
        self.apply_synchronously('A', 'stadium')
        before=self.files()
        original=os.replace
        def fail(src,dst):
            if 'prepared' in Path(src).parts and Path(dst).name=='stadium_261_3_textures.rx3':
                raise PermissionError('simulated publish failure')
            return original(src,dst)
        with patch('server16_py.stadium_transaction.os.replace', side_effect=fail):
            with self.assertRaises(PermissionError):
                self.runtime.run_stadium_copy_job('1','manual','261','B','B,None,None,None',self.context()[:3])
        self.assertEqual(self.files(),before)
        self.assertEqual(self.current_id,176)
        self.assertEqual(list((self.game/'runtime').iterdir()), [])

    def test_expired_context_after_publication_restores_files_without_memory_write(self):
        self.apply_synchronously('A', 'stadium')
        before=self.files()
        payload=self.runtime.run_stadium_copy_job('1','manual','261','B','B,None,None,None',self.context()[:3])
        payload['context']=self.context()[:3]
        self.app._kickoff_generation += 1
        self.app.memory.write_int.reset_mock()
        self.runtime.finish_stadium_apply(payload)
        self.app.memory.write_int.assert_not_called()
        self.assertEqual(self.files(),before)
        self.assertEqual(self.current_id,176)

    def test_confirmation_failure_restores_assets_and_previous_manual_selection(self):
        self.apply_synchronously('A', 'stadium')
        self.apply_synchronously('B')
        old_choice=self.app._manual_stadium_override
        before=self.files()
        slot='176'
        payload=self.runtime.run_stadium_copy_job('1','manual',slot,'C','C,None,None,None',self.context()[:3])
        payload['context']=self.context()[:3]
        self.runtime._previous_manual_override=old_choice
        self.app._manual_stadium_override=(self.context(),'C','C,None,None,None')
        self.runtime.pending_selection=(self.context()[:3],'C')
        self.app._stadium_task_request_key=('manual','1','C,None,None,None')
        self.app.memory.write_int.side_effect=lambda *args: None  # FIFA refuses writes.
        with self.assertRaisesRegex(RuntimeError,'could not be confirmed'):
            self.runtime.finish_stadium_apply(payload)
        self.assertEqual(self.files(),before)
        self.assertEqual(self.current_id,261)
        self.assertEqual(self.app._manual_stadium_override,old_choice)
        self.assertFalse(self.app._stadium_task_running)

    def test_automatic_assignment_is_not_randomized_again_for_same_match(self):
        signature=(1,'stadium','1',self.assignments[('stadium','1')],'1','10','20')
        self.app._last_stadium_applied_signature=signature
        self.app.curstad='A'
        with patch('server16_py.stadium_runtime.random.choice', side_effect=AssertionError('unwanted re-roll')), \
             patch.object(self.runtime,'start_stadium_task') as start:
            self.runtime.apply_stadium_runtime()
        start.assert_not_called()

    def test_manual_wins_late_round_updates_but_next_fixture_uses_automatic(self):
        self.app._manual_stadium_override=(self.context(),'C','C,None,None,None')
        self.app.TOURROUNDID='21'
        with patch.object(self.runtime,'start_stadium_task') as start:
            self.runtime.apply_stadium_runtime()
            start.assert_not_called()
            self.app._kickoff_generation += 1
            self.runtime.apply_stadium_runtime()
            start.assert_called_once()
            self.assertNotEqual(start.call_args.args[1],'manual')

    def test_setup_return_preserves_manual_but_return_after_play_starts_new_fixture(self):
        a=self.app
        a._manual_stadium_override=(self.context(),'C','C,None,None,None')
        a.lastpagename='game/screens/misc/StadiumPan'
        a.matchstarted=False
        a._is_post_match_page=Server16App._is_post_match_page
        a._native_assets_restored_for_match=False
        a._clear_live_context=Mock()
        a._reset_team_entrance=Mock()
        a._reset_chants_state=Mock()
        a._schedule_kickoff_retry=Mock()
        Server16App._handle_page_transition(a,'game/screens/playNow/KickOffHub')
        self.assertEqual(a._kickoff_generation,1)
        self.assertEqual(a._manual_stadium_override[1],'C')
        a._clear_live_context.assert_not_called()
        a._stadium_fixture_entered=True  # Previous match was actually entered.
        a.lastpagename='game/screens/misc/StadiumPan'
        Server16App._handle_page_transition(a,'game/screens/playNow/KickOffHub')
        self.assertEqual(a._kickoff_generation,2)
        self.assertIsNone(a._manual_stadium_override)
        a._clear_live_context.assert_called_once()

    def test_context_change_during_preparation_never_publishes_new_model(self):
        before=self.files()
        original=__import__('shutil').copy2
        def change_context(src,dst,*args,**kwargs):
            result=original(src,dst,*args,**kwargs)
            if Path(src)==self.packages/'A/model.rx3': self.app._kickoff_generation += 1
            return result
        with patch('server16_py.stadium_runtime.shutil.copy2', side_effect=change_context):
            with self.assertRaisesRegex(RuntimeError,'context changed'):
                self.runtime.run_stadium_copy_job('1','manual','176','A','A,None,None,None',self.context()[:3])
        self.assertEqual(self.files(),before)

    def test_automatic_preview_return_preserves_generation_and_assets(self):
        a=self.app
        a._last_stadium_applied_signature=(1,'stadium','1',self.assignments[('stadium','1')],'1','10','20')
        a.curstad='A'
        a.lastpagename='game/screens/misc/StadiumPan'
        a.matchstarted=False
        a._is_post_match_page=Server16App._is_post_match_page
        a._native_assets_restored_for_match=False
        a._clear_live_context=Mock()
        Server16App._handle_page_transition(a,'game/screens/playNow/KickOffHub')
        self.assertEqual(a._kickoff_generation,1)
        a._clear_live_context.assert_not_called()
        with patch.object(self.runtime,'start_stadium_task') as start:
            self.runtime.apply_stadium_runtime()
            start.assert_not_called()

    def test_automatic_late_apply_never_copies_or_writes_stadium_id(self):
        self.app.lastpagename='game/screens/TV/bumper'
        self.app._stadium_fixture_entered=True
        before=self.files()
        with patch.object(self.runtime,'start_stadium_task') as start:
            self.runtime.apply_stadium_runtime()
            start.assert_not_called()
        with self.assertRaisesRegex(RuntimeError,'selection screen'):
            self.runtime.run_stadium_copy_job('1','stadium','176','A','A,None,None,None',self.context()[:3])
        self.app.memory.write_int.assert_not_called()
        self.assertEqual(self.files(),before)

    def test_loading_begins_after_copy_rolls_back_without_id_switch(self):
        before=self.files()
        payload=self.runtime.run_stadium_copy_job('1','stadium','176','A','A,None,None,None',self.context()[:3])
        payload['context']=self.context()[:3]
        self.app._stadium_fixture_entered=True
        self.app.lastpagename='game/screens/TV/bumper'
        with self.assertRaisesRegex(RuntimeError,'selection screen'):
            self.runtime.finish_stadium_apply(payload)
        self.app.memory.write_int.assert_not_called()
        self.assertEqual(self.files(),before)

    def test_zero_size_texture_is_rejected_before_any_game_file_change(self):
        before=self.files()
        (self.packages/'A/texture_day.rx3').write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError,'invalid texture'):
            self.runtime.run_stadium_copy_job('1','manual','176','A','A,None,None,None',self.context()[:3])
        self.assertEqual(self.files(),before)

    def test_model_without_textures_cannot_use_unrelated_native_backup(self):
        before=self.files()
        for name in ('texture_day.rx3','texture_night.rx3'):
            (self.packages/'A'/name).unlink()
        with self.assertRaisesRegex(RuntimeError,'no textures'):
            self.apply_synchronously('A')
        self.assertEqual(self.files(),before)
        self.app.memory.write_int.assert_not_called()

    def test_single_texture_is_used_for_both_lighting_conditions(self):
        (self.packages/'A/texture_night.rx3').unlink()
        slot=self.apply_synchronously('A')
        self.assertEqual((self.game/f'data/sceneassets/stadium/stadium_{slot}_3_textures.rx3').read_bytes(),b'A day')

    def test_native_lua_repeated_matches_use_same_model_texture_identity(self):
        from lupa import LuaRuntime
        lua=LuaRuntime(unpack_returned_tuples=True)
        def load_script(path):
            lua.execute((self.game/path).read_text(encoding='ascii'))
            return 1
        lua.globals().load_script=load_script
        lua.execute('gSportsRNA = {LoadScriptAsync = function(self,path) return load_script(path) end, LoadScriptAsyncComplete=function() end}; db={stadium={}}')
        helper=Path(__file__).resolve().parents[1]/'native_mods/frontend_stadium/frontend_stadium.lua'
        lua.execute(helper.read_text(encoding='utf8'))
        observed=[]
        for name in ('A','B','C','A'):
            slot=self.apply_synchronously(name)
            lua.execute(f'db.stadium[1]={{stadiumID={slot},homeKitTeamID=1,awayKitTeamID=2,lightType=1}}; Server16FrontendUpdate(1)')
            model=lua.globals().Server16FrontendModel(1).rstrip(';')
            day=lua.globals().Server16FrontendTexture(1).rstrip(';')
            lua.execute('db.stadium[1].lightType=3')
            night=lua.globals().Server16FrontendTexture(1).rstrip(';')
            self.assertEqual((self.game/model).read_bytes(),(name+' model').encode())
            self.assertEqual((self.game/day).read_bytes(),(name+' day').encode())
            self.assertEqual((self.game/night).read_bytes(),(name+' night').encode())
            self.assertEqual(Path(model).parent,Path(day).parent)
            self.assertEqual(Path(day).parent,Path(night).parent)
            observed.append((model,day,night))
        self.assertEqual(observed[0],observed[3])
        self.assertNotEqual(observed[0],observed[2])
        # Old cached files are immutable even when the injection slot is reused.
        for name,paths in zip(('A','B','C'),observed):
            self.assertEqual((self.game/paths[0]).read_bytes(),(name+' model').encode())
        # A different fixture must not inherit an old route, even on the same ID.
        lua.execute('db.stadium[1].awayKitTeamID=3; Server16FrontendUpdate(1)')
        self.assertEqual(lua.globals().Server16FrontendModel(1),'')
        self.assertEqual(lua.globals().Server16FrontendTexture(1),'')
        clear_match_routes(self.game)
        lua.execute('db.stadium[1].awayKitTeamID=2; Server16FrontendUpdate(1)')
        self.assertEqual(lua.globals().Server16FrontendModel(1),'')
        self.assertEqual(lua.globals().Server16FrontendTexture(1),'')

    def test_failed_route_load_does_not_reuse_previous_lua_table(self):
        from lupa import LuaRuntime
        self.apply_synchronously('A')
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('gSportsRNA={LoadScriptAsync=function() error("missing") end}; db={stadium={[1]={stadiumID=176,homeKitTeamID=1,awayKitTeamID=2}}}')
        lua.execute((Path(__file__).resolve().parents[1]/'native_mods/frontend_stadium/frontend_stadium.lua').read_text(encoding='utf8'))
        lua.execute('Server16MatchRoutes[176]={home=1,away=2,model="old",day="old",night="old"}; Server16FrontendUpdate(1)')
        self.assertEqual(lua.globals().Server16FrontendModel(1),'')

    def test_frontend_route_and_match_route_remain_separate(self):
        from lupa import LuaRuntime
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('gSportsRNA={LoadScriptAsync=function() return 1 end, LoadScriptAsyncComplete=function() end}; db={stadium={[0]={stadiumID=176,lightType=1},[1]={stadiumID=261,lightType=3,homeKitTeamID=1,awayKitTeamID=2}}}')
        lua.execute((Path(__file__).resolve().parents[1]/'native_mods/frontend_stadium/frontend_stadium.lua').read_text(encoding='utf8'))
        lua.execute('Server16FrontendRoutes[176]={team=4,model="menu",day="menu day",night="menu night"}; Server16FrontendUpdate(0)')
        self.assertEqual(lua.globals().Server16FrontendModel(0),'menu;')
        self.assertEqual(lua.globals().Server16FrontendTexture(0),'menu day;')
        lua.execute('Server16FrontendRoutes[261]=Server16FrontendRoutes[176]; Server16FrontendUpdate(1)')
        self.assertEqual(lua.globals().Server16FrontendModel(1),'')

    def test_recovery_backup_is_kept_if_windows_refuses_rollback(self):
        tx=StadiumAssetTransaction(self.game,self.app.log)
        rel=Path('data/sceneassets/stadium/stadium_261.rx3')
        old=(self.game/rel).read_bytes()
        self.put(tx.stage/rel,b'new')
        tx.commit({rel},lambda:None)
        with patch('server16_py.stadium_transaction.os.replace', side_effect=PermissionError('locked')):
            with self.assertRaisesRegex(RuntimeError,'backups retained'):
                tx.rollback()
        self.assertEqual((tx.backup/rel).read_bytes(),old)
        tx.rollback()  # Lock released, recovery still works.
        self.assertEqual((self.game/rel).read_bytes(),old)

    def test_partial_rollback_can_retry_without_deleting_already_restored_files(self):
        tx=StadiumAssetTransaction(self.game,self.app.log)
        paths={Path('data/sceneassets/stadium')/name for name in
            ('stadium_261.rx3','stadium_261_1_textures.rx3','stadium_261_3_textures.rx3')}
        before={rel:(self.game/rel).read_bytes() for rel in paths}
        for rel in paths: self.put(tx.stage/rel,b'new')
        tx.commit(paths,lambda:None)
        original=os.replace
        def fail_one(src,dst):
            if 'previous' in Path(src).parts and Path(src).name=='stadium_261_1_textures.rx3':
                raise PermissionError('one texture locked')
            return original(src,dst)
        with patch('server16_py.stadium_transaction.os.replace',side_effect=fail_one):
            with self.assertRaisesRegex(RuntimeError,'backups retained'): tx.rollback()
        self.assertEqual(len(tx.changes),1)
        tx.rollback()
        for rel,data in before.items(): self.assertEqual((self.game/rel).read_bytes(),data)
