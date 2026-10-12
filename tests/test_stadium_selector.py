from __future__ import annotations

import ctypes
import os
import random
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from server16_py.stadium_catalog import COUNTRY_FLAGS, StadiumEntry, build_catalog, filter_catalog, prematch_page
from server16_py.stadium_selector import SelectorShared, StadiumSelector
from server16_py.stadium_runtime import StadiumRuntime
from server16_py.chants_runtime import ChantsRuntime


class StadiumSelectorTests(unittest.TestCase):
    def test_shared_protocol_and_pages(self):
        self.assertEqual(ctypes.sizeof(SelectorShared),1576)
        for name in ('game/screens/playNow/KickOffHub','kit_select'):
            self.assertTrue(prematch_page(name))
        for name in ('game/screens/playNow/SideSelect','game/screens/TV/bumper','game/screens/career/Home','InGame',''):
            self.assertFalse(prematch_page(name))

    def test_catalog_ownership_country_search_and_no_dds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            folder=root/'BRA - Maracanã - Flamengo'; folder.mkdir()
            (folder/'model.rx3').touch()
            (root/(folder.name+'.zip')).touch()
            (root/'ESP - Bernabeu - Real Madrid.rar').touch()
            previews=root/'render'/'thumbnail'/'stadium'; previews.mkdir(parents=True)
            preview=previews/(folder.name+'.JPG'); Image.new('RGB',(4,4)).save(preview)
            (previews/'ESP - Bernabeu - Real Madrid.dds').touch()
            settings=SimpleNamespace(items=lambda section:[('1043',folder.name+',None,None,None')])
            entries=build_catalog(root,settings,{'1043':'Flamengo','10':'Real Madrid'})
            self.assertEqual(len(entries),2)
            brazil=filter_catalog(entries,'maracna','BRA')
            self.assertEqual(len(brazil),1)
            self.assertEqual(brazil[0].team_id,'1043')
            self.assertEqual(brazil[0].preview,preview)
            self.assertIsNone(filter_catalog(entries,'Espanha')[0].preview)
            self.assertEqual(filter_catalog(entries,'sem-correspondencia'),[])

    def test_shared_stadium_does_not_invent_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'BRA - Municipal.zip').touch()
            ini=SimpleNamespace(items=lambda section:[('1','BRA - Municipal,None,None,None'),('2','BRA - Municipal,None,None,None')])
            entries=build_catalog(root,ini,{'1':'Clube A','2':'Clube B'})
            self.assertEqual(entries[0].team_id,'')

    def test_stadium_card_has_counter_but_no_pagination_dots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'BRA - A.zip').touch(); (root/'ESP - B.zip').touch()
            selector=self.make_selector(root)
            try:
                self.open_ready(selector)
                self.assertEqual(selector.position_label(),'1 de 2')
                with Image.open(selector.shared.image_path) as card:
                    for x in range(283,318):
                        for y in range(443,452):
                            self.assertEqual(card.getpixel((x*2,y*2))[:3],(255,255,255))
                selector.change(1,2)
                self.assertEqual(selector.position_label(),'2 de 2')
            finally: selector.shutdown()

    def make_selector(self,root):
        app=SimpleNamespace(base_dir=root,targetpath=root,settings_ini=None,team_db=SimpleNamespace(team_cache={}),
            _kickoff_generation=1,HID='1',AID='2',TOURNAME='',TOURROUNDID='',
            lastpagename='game/screens/playNow/KickOffHub',_stadium_task_running=False,
            memory=SimpleNamespace(is_open=lambda:True),module_enabled=lambda name:True,
            _overlay_visible=False,_crowd_volume_visible=False,_resolve_fifa_pid=lambda:1234,
            _ensure_d3d_overlay_injected=Mock(return_value=True),
            log=Mock(),_resolve_team_logo_path=lambda tid:None,stadium_runtime=SimpleNamespace(apply_manual_stadium=Mock()))
        with patch('server16_py.stadium_selector.SELECTOR_MAPPING_NAME',f'Local\\CGFS16_Selector_test_{os.getpid()}'), \
                patch('server16_py.crowd_control.MAPPING_NAME',f'Local\\CGFS16_Crowd_test_{os.getpid()}'):
            return StadiumSelector(app)

    def open_ready(self,selector):
        selector.open()
        selector._catalog_thread.join(timeout=5)
        self.assertFalse(selector._catalog_thread.is_alive())
        selector._drain_catalog()
        self.assertFalse(selector.loading)

    def test_reopen_starts_at_applied_stadium_and_clears_old_filters(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),None),
                StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None),
                StadiumEntry('BRA - Maracanã','BRA','Maracanã','','',Path('unused'),None)]
            try:
                selector._catalog_cache=entries; selector._catalog_ready=True
                selector.app.curstad='bra - Maracana.RAR'
                with patch.object(selector,'_preload_catalog'), patch.object(selector,'render'):
                    selector.country='ESP'; selector.query=selector.draft='B'
                    selector.open()
                    self.assertEqual(selector.results[selector.index],entries[2])
                    self.assertEqual((selector.query,selector.draft,selector.country),('','',''))
                    self.assertEqual(selector.position_label(),'3 de 3')
                    selector.change(-1,2); selector.close(); selector.open()
                    self.assertEqual(selector.results[selector.index],entries[2])
                    selector.close(); selector.app.curstad='ESP - B'; selector.open()
                    self.assertEqual(selector.results[selector.index],entries[1])
                    selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
            finally: selector.shutdown()

    def test_open_prefers_pending_current_match_and_ignores_expired_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),None),
                StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None)]
            try:
                selector._catalog_cache=entries; selector._catalog_ready=True
                selector.app.curstad=entries[0].name
                selector.app._stadium_task_running=True
                selector.app.stadium_runtime.pending_selection=(selector._context()[:3],entries[1].name)
                with patch.object(selector,'_preload_catalog'), patch.object(selector,'render'):
                    selector.open()
                    self.assertEqual(selector.results[selector.index],entries[1])
                    selector.close()
                    selector.app.stadium_runtime.pending_selection=((0,'1','2'),entries[1].name)
                    selector.app._manual_stadium_override=((0,'1','2','',''),entries[1].name,'unused')
                    selector.open()
                    self.assertEqual(selector.results[selector.index],entries[0])
                    selector.close(); selector.app.curstad='Stadium removed from catalog'; selector.open()
                    self.assertEqual(selector.position_label(),'1 de 2')
            finally: selector.shutdown()

    def test_initial_selection_waits_for_background_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),None),
                StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None)]
            try:
                selector.app.curstad=entries[1].name
                selector._catalog_pending_key='loading'
                with patch.object(selector,'_preload_catalog'), patch.object(selector,'render'):
                    selector.open()
                    self.assertTrue(selector.loading)
                    self.assertEqual(selector.results,[])
                    selector._catalog_results.put((selector._catalog_generation,'loaded',entries,None))
                    selector._drain_catalog()
                    self.assertFalse(selector.loading)
                    self.assertEqual(selector.results[selector.index],entries[1])
            finally: selector.shutdown()

    def test_catalog_refresh_preserves_user_navigation_when_order_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),None),
                StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None),
                StadiumEntry('BRA - C','BRA','C','','',Path('unused'),None)]
            try:
                selector._catalog_cache=entries; selector._catalog_ready=True
                selector._catalog_pending_key='refreshing'
                selector.app.curstad=entries[2].name
                with patch.object(selector,'_preload_catalog'), patch.object(selector,'render'):
                    selector.open(); selector.change(-1,2)
                    self.assertEqual(selector.results[selector.index],entries[1])
                    reordered=[entries[2],entries[0],entries[1]]
                    selector._catalog_results.put((selector._catalog_generation,'loaded',reordered,None))
                    selector._drain_catalog()
                    self.assertEqual(selector.results[selector.index],entries[1])
                    self.assertEqual(selector.position_label(),'3 de 3')
            finally: selector.shutdown()

    def test_injection_failure_retries_and_success_is_not_reinjected(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                inject=selector.app._ensure_d3d_overlay_injected
                inject.side_effect=[False,True]
                with patch('server16_py.stadium_selector.time.monotonic',return_value=100):
                    selector.tick(); selector.tick()
                self.assertEqual(inject.call_count,1)
                self.assertEqual(selector._attempted_pid,0)
                with patch('server16_py.stadium_selector.time.monotonic',return_value=106):
                    selector.tick(); selector.tick()
                self.assertEqual(inject.call_count,2)
                self.assertEqual(selector._attempted_pid,1234)
            finally: selector.shutdown()

    def test_slow_catalog_keeps_heartbeat_and_cancel_discards_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            started=threading.Event(); release=threading.Event()
            def slow_catalog(*args):
                started.set(); release.wait(timeout=5); return []
            try:
                selector._attempted_pid=1234
                with patch('server16_py.stadium_selector.build_catalog',side_effect=slow_catalog):
                    selector.open()
                    self.assertTrue(started.wait(timeout=2))
                    selector.shared.heartbeat=0
                    selector.tick()
                    self.assertTrue(selector.opened and selector.loading)
                    self.assertNotEqual(selector.shared.heartbeat,0)
                    selector.close(); release.set(); selector._catalog_thread.join(timeout=5)
                    selector._drain_catalog()
                self.assertFalse(selector.opened)
                self.assertEqual(selector.entries,[])
                self.assertEqual(selector.shared.visible,0)
            finally:
                release.set(); selector.shutdown()

    def test_cancel_start_keyboard_and_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'BRA - Maracana - Flamengo.zip').touch()
            selector=self.make_selector(root)
            try:
                self.open_ready(selector); selector.handle(11,0)
                self.assertFalse(selector.opened)
                selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
                self.open_ready(selector); selector.handle(9,0)
                self.assertTrue(selector.keyboard)
                for key in 'MARACNA': selector.handle(10,ord(key))
                selector.key('Buscar'); self.assertEqual(len(selector.results),1)
                with Image.open(selector.cache/f'card_{selector.serial%2}.png') as card:
                    self.assertEqual(card.size,(StadiumSelector.WIDTH*2,StadiumSelector.HEIGHT*2))
                selector.apply()
                selector.app.stadium_runtime.apply_manual_stadium.assert_called_once()
                self.assertFalse(selector.opened)  # Hand off to the runtime loading notice.
                self.assertEqual(selector.shared.visible,0)
            finally: selector.shutdown()

    def test_display_name_removes_only_an_identified_club_suffix(self):
        entry=StadiumEntry('BRA - Maracanã - Flamengo','BRA','Maracanã - Flamengo','Flamengo','1043',Path('unused'),None)
        self.assertEqual(StadiumSelector.stadium_title(entry),'Maracanã')
        ambiguous=StadiumEntry('BRA - Municipal - Norte','BRA','Municipal - Norte','','',Path('unused'),None)
        self.assertEqual(StadiumSelector.stadium_title(ambiguous),'Municipal - Norte')

    def test_light_card_mouse_buttons_keyboard_layout_and_gamepad_focus(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'BRA - Maracana.zip').touch()
            selector=self.make_selector(root)
            try:
                self.open_ready(selector)
                with Image.open(selector.shared.image_path) as card:
                    self.assertEqual(card.getpixel((600,20))[:3],(255,255,255))
                    self.assertEqual(card.getpixel((660,980))[:3],(9,104,248))
                actions={action:rect for rect,action in selector.targets}
                self.assertLess(actions['cancel'][0],actions['apply'][0])
                self.assertGreater(actions['next'][0],actions['prev'][0])
                selector.focus=3; selector.handle(2,0); self.assertEqual(selector.focus,4)
                selector.handle(3,0); self.assertEqual(selector.focus,3)
                selector.handle(9,0)
                keys=[(rect,action) for rect,action in selector.targets if action.startswith('key:')]
                self.assertEqual(len(keys),len(selector.KEYS))
                for rect,action in keys:
                    self.assertTrue(0<=rect[0]<rect[2]<selector.KEYBOARD_WIDTH,action)
                    self.assertTrue(0<=rect[1]<rect[3]<selector.KEYBOARD_HEIGHT,action)
                for i,(a,_) in enumerate(keys):
                    for b,_ in keys[i+1:]:
                        self.assertFalse(a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1])
                selector.key_index=35; selector.handle(5,0); self.assertEqual(selector.KEYS[selector.key_index],'Buscar')
                selector.handle(4,0); self.assertTrue(24<=selector.key_index<=35)
                selector.handle(7,0)
                cancel=next(rect for rect,action in selector.targets if action=='cancel')
                x=(cancel[0]+cancel[2])//2; y=(cancel[1]+cancel[3])//2
                selector.handle(8,(y<<16)|x)
                self.assertFalse(selector.opened)
                selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
            finally: selector.shutdown()

    def test_position_counter_tracks_filters_and_flags_are_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            try:
                selector.entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),None),
                    StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None)]
                selector.opened=True; selector.index=1; selector.refresh()
                self.assertEqual(selector.position_label(),'2 de 2')
                selector.action('country:BRA')
                self.assertEqual(selector.position_label(),'1 de 1')
                self.assertEqual(len(selector.entries),2)
                self.assertEqual(COUNTRY_FLAGS['BRA'],'br')
                self.assertIsNotNone(selector.flag('BRA'))
                self.assertIsNone(selector.flag('UNKNOWN'))
                selector.query='zzzz'; selector.refresh()
                self.assertEqual(selector.position_label(),'0 de 0')
            finally: selector.shutdown()

    def test_strong_focus_and_mouse_hover_never_apply_or_change_stadium(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'BRA - A.zip').touch(); (root/'ESP - B.zip').touch()
            selector=self.make_selector(root)
            try:
                self.open_ready(selector)
                with Image.open(selector.shared.image_path) as card:
                    # Eight physical pixels of dark blue, plus a white separator.
                    for x in (19,20,21,22): self.assertEqual(card.getpixel((x*2,246*2))[:3],(0,82,204))
                    self.assertEqual(card.getpixel((23*2,246*2))[:3],(255,255,255))
                index=selector.index
                selector.handle(15,(505<<16)|440)
                self.assertEqual(selector.focus,3)
                self.assertEqual(selector.index,index)
                self.assertTrue(selector.opened)
                with Image.open(selector.shared.image_path) as card:
                    self.assertEqual(card.getpixel((330*2,490*2))[:3],(18,61,134))
                    self.assertEqual(card.getpixel((305*2,505*2))[:3],(0,82,204))
                serial=selector.serial
                selector.handle(15,(505<<16)|441)
                self.assertEqual(selector.serial,serial) # No redraw while hovering the same target.
                selector.handle(15,(505<<16)|140)
                self.assertEqual(selector.focus,4)
                selector.handle(15,(246<<16)|300)
                self.assertEqual(selector.focus,2)
                selector.handle(14,0)
                self.assertEqual(selector.focus,1)
                selector.handle(9,0)
                draft=selector.draft
                selector.handle(15,((selector.HEIGHT+70)<<16)|140)
                self.assertEqual(selector.key_index,1)
                self.assertEqual(selector.draft,draft)
                selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
            finally: selector.shutdown()

    def test_slow_photo_load_never_blocks_navigation_or_publishes_stale_photo(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_selector(Path(temporary))
            started=threading.Event(); release=threading.Event()
            def load(path):
                started.set(); release.wait(timeout=5)
                return Image.new('RGB',(552,232),'red')
            try:
                selector.entries=[StadiumEntry('BRA - A','BRA','A','','',Path('unused'),Path('first.jpg')),
                    StadiumEntry('ESP - B','ESP','B','','',Path('unused'),None)]
                selector.opened=True
                with patch.object(selector,'_load_preview',side_effect=load):
                    selector.refresh()
                    self.assertTrue(started.wait(timeout=2))
                    self.assertTrue(selector._preview_loading)
                    selector.change(1,2)
                    self.assertEqual(selector.position_label(),'2 de 2')
                    release.set()
                    generation,path,preview,error=selector._image_results.get(timeout=5)
                    selector._image_results.put((generation,path,preview,error))
                    selector._drain_images()
                    self.assertIsNone(selector._preview_image)
                    self.assertFalse(selector._preview_loading)
            finally:
                release.set(); selector.shutdown()

    def test_loaded_jpeg_publishes_a_fade_and_reuses_the_cached_photo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); photo=root/'photo.jpg'
            Image.new('RGB',(800,400),'green').save(photo)
            selector=self.make_selector(root)
            try:
                entry=StadiumEntry('BRA - A','BRA','A','','',root,photo)
                selector.entries=[entry]; selector.opened=True; selector.refresh()
                result=selector._image_results.get(timeout=5)
                selector._image_results.put(result); selector._drain_images()
                self.assertFalse(selector._preview_loading)
                self.assertEqual(selector._preview_image.size,(1104,464))
                self.assertIn('card_slide_',selector.shared.image_path)
                selector._request_preview(None)
                with patch.object(selector,'_load_preview',side_effect=AssertionError('cache miss')):
                    selector.refresh()
                self.assertFalse(selector._preview_loading)
                self.assertIn('card_slide_',selector.shared.image_path)
            finally: selector.shutdown()

    def test_obsolete_context_and_failed_apply_stay_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'BRA - Maracana.zip').touch()
            selector=self.make_selector(root)
            try:
                self.open_ready(selector); selector.app.HID='3'; selector.apply()
                selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
                selector.app.HID='1'
                selector.app.stadium_runtime.apply_manual_stadium.side_effect=RuntimeError('missing model')
                selector.apply(); self.assertFalse(selector.applying)
                self.assertTrue(selector.opened)
            finally: selector.shutdown()

    def test_invalid_package_never_modifies_assets_and_manual_context_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'broken').mkdir()
            app=SimpleNamespace(targetpath=root,exedir=root/'game',base_dir=root,settings_ini=None,
                _kickoff_generation=2,HID='1',AID='2',TOURNAME='',TOURROUNDID='',_stadium_task_running=False)
            runtime=StadiumRuntime(app)
            with patch('server16_py.stadium_runtime.restore_stadium_inj_files') as restore:
                with self.assertRaisesRegex(RuntimeError,'no model'):
                    runtime.run_stadium_copy_job('1','manual','176','broken','broken,None,None,None')
                restore.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'context'):
                runtime.apply_manual_stadium('broken',(1,'1','2','',''))

    def test_expired_completion_never_writes_memory(self):
        app=SimpleNamespace(_kickoff_generation=2,HID='1',AID='2',memory=Mock(),log=Mock(),
            _stadium_task_running=True,_hide_stadium_loading_modal=Mock())
        StadiumRuntime(app).finish_stadium_apply({'context':(1,'1','2')})
        app.memory.write_int.assert_not_called()
        self.assertFalse(app._stadium_task_running)


class CrowdAudioSafetyTests(unittest.TestCase):
    def make_runtime(self,root=None):
        app=SimpleNamespace(exedir=root,log=Mock(),_chants_rng=random.Random(1),_crowd_master_volume=0.5,
            _chants_volume_is_crowd=True,_chants_base_volume=0.2,_chants_player=Mock(),_set_display_async=Mock())
        return ChantsRuntime(app)

    def test_id3_versions_invalid_headers_and_safe_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runtime=self.make_runtime(root)
            clean=b'\xff\xfb'+b'\0'*100
            tagged=b'ID3\x03\x00\x00\x00\x00\x00\x04'+b'tags'+clean
            self.assertIsNone(runtime._strip_leading_id3v2(b'ID3\x03\0\0\x80\0\0\0'+clean))
            self.assertIsNone(runtime._strip_leading_id3v2(b'ID3\x09\0\0\0\0\0\0'+clean))
            path=root/'chant.mp3'; path.write_bytes(tagged)
            self.assertEqual(runtime.fix_chants_audio_files([path])['fixed'],1)
            self.assertEqual(path.read_bytes(),clean)
            self.assertEqual((root/'chant.original.mp3').read_bytes(),tagged)
            self.assertEqual(runtime._pick_random_track(root),path)
            self.assertEqual(runtime.fix_chants_audio_files([path])['already_clean'],1)

    def test_master_applies_only_to_crowd_and_survives_fades(self):
        runtime=self.make_runtime(); app=runtime.app
        runtime.apply_crowd_master_volume()
        app._chants_player.set_volume.assert_called_with(0.1)
        app._crowd_master_volume=0
        with patch('server16_py.chants_runtime.time.sleep'):
            runtime.fade_player(app._chants_player,0,0.2,100)
        app._chants_player.set_volume.assert_called_with(0)
        app._chants_player.reset_mock(); app._chants_volume_is_crowd=False
        runtime.apply_crowd_master_volume(); app._chants_player.set_volume.assert_not_called()
        self.assertEqual(runtime._safe_float('nan',0.05),0.05)
        self.assertEqual(runtime._safe_float('inf',0.05),0.05)


if __name__=='__main__':
    unittest.main()
