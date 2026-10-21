import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from server16_py.frontend_stadium import prepare, assignment_names, transparent_dds, resolve_source, native_fallback


class FrontendStadiumTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name)
        (self.game/'FSW').mkdir()
        (self.game/'StadiumGBD').mkdir()
        (self.game/'FSW/settings.ini').write_text('[stadium]\n130022=ABC,5,46,0\n130023=Missing,ABC,5,46,0\n', encoding='utf8')
        self.pack = self.game/'StadiumGBD/ABC'
        self.pack.mkdir()
        for filename in ('model.rx3','texture_day.rx3','texture_night.rx3'):
            (self.pack/filename).write_bytes(b'RX3l'+bytes(60))

    def test_favorite_and_career_team_ids_use_same_validated_route(self):
        for team, slot in ((130022,176),(130023,261)):
            photo=self.game/f'data/ui/imgAssets/backgroundstadiums/st_{slot}.dds'
            photo.parent.mkdir(parents=True, exist_ok=True)
            photo.write_bytes(b'original photograph')
            result=prepare(self.game,team,slot)
            self.assertEqual(result['name'],'ABC')
            self.assertTrue((self.game/result['model']).is_file())
            self.assertEqual(photo.read_bytes(), b'original photograph')
            route=(self.game/f'data/fifarna/lua/assets/server16_frontend_{slot}.lua').read_text()
            self.assertIn(f'team = {team}',route)
            self.assertEqual((photo.parent/'st_server16_frontend_clear.dds').read_bytes(),transparent_dds())
        self.assertFalse((self.game/'data/sceneassets/stadium/stadium_176.rx3').exists())

    def test_invalid_package_preserves_photo_and_previous_route(self):
        first=prepare(self.game,130022,176)
        route=self.game/'data/fifarna/lua/assets/server16_frontend_176.lua'
        before=route.read_bytes()
        (self.pack/'texture_day.rx3').write_bytes(b'invalid')
        with self.assertRaises(ValueError):prepare(self.game,130022,176)
        self.assertEqual(route.read_bytes(),before)
        self.assertTrue((self.game/first['model']).exists())

    def test_no_assignment_has_no_filesystem_effect(self):
        with self.assertRaises(LookupError):prepare(self.game,999,176)
        self.assertFalse((self.game/'data').exists())

    def test_zip_nested_package_and_day_fallback(self):
        (self.game/'FSW/settings.ini').write_text('[stadium]\n42=Nested,0,0,0\n')
        with zipfile.ZipFile(self.game/'StadiumGBD/Nested.zip','w') as archive:
            for filename in ('model.rx3','texture_day.rx3'):
                archive.writestr('nested/'+filename,b'RX3l'+bytes(60))
        result=prepare(self.game,42,261)
        self.assertEqual(result['day'],result['night'])

    def test_cache_refresh_and_backup_are_stable(self):
        first=prepare(self.game,130022,176)
        again=prepare(self.game,130022,176)
        self.assertFalse(first['cache_hit'])
        self.assertTrue(again['cache_hit'])
        self.assertEqual(first['key'],again['key'])
        (self.pack/'model.rx3').write_bytes(b'RX3l'+bytes(124))
        changed=prepare(self.game,130022,176)
        self.assertNotEqual(first['key'],changed['key'])
        self.assertTrue((self.game/first['model']).exists())

    def test_transparent_image_and_assignment_format(self):
        image=Image.open(io.BytesIO(transparent_dds())).convert('RGBA')
        self.assertEqual(image.getchannel('A').getextrema(),(0,0))
        self.assertEqual(assignment_names('A,B,5,46,0'),['A','B'])
        self.assertEqual(assignment_names('None,5,46,0'),[])
        for value in ('../outside','C:\\outside','a/b'):
            with self.assertRaises(ValueError):resolve_source(self.game/'StadiumGBD',value)

    def test_metadata_and_support_resources_follow_each_team(self):
        (self.pack/'crowd_day.dat').write_bytes(b'crowd placements')
        (self.pack/'1').mkdir();(self.pack/'1/glare1_0.lnx').write_bytes(b'lights')
        with (self.game/'FSW/settings.ini').open('a',encoding='utf8') as f:f.write('[scoreboardstdname]\nABC=Frasqueirão - Natal - RN,1\n')
        result=prepare(self.game,130022,176)
        self.assertEqual(result['display_name'],'Frasqueirão - Natal - RN')
        cache=(self.game/result['model']).parent
        self.assertEqual((cache/'crowd_day.dat').read_bytes(),b'crowd placements')
        self.assertTrue((cache/'1/glare1_0.lnx').exists())
        metadata=(self.game/'ModCarrerMode/runtime/frontend_stadium_route.ini').read_text(encoding='utf16')
        self.assertIn('name=Frasqueirão',metadata)
        self.assertIn('team=130022',metadata)

    def test_manual_background_is_independent_of_match_assignment(self):
        from server16_py.frontend_stadium_selection import save_selection
        original=(self.game/'FSW/settings.ini').read_bytes()
        save_selection(self.game,'ABC',900000)
        result=prepare(self.game,900000,261)
        self.assertEqual(result['name'],'ABC')
        self.assertEqual(result['team'],900000)
        self.assertEqual((self.game/'FSW/settings.ini').read_bytes(),original)
        save_selection(self.game,'auto',900000)
        with self.assertRaises(LookupError):prepare(self.game,900000,261)

    def test_career_entry_ignores_profile_override_and_expires_manual_choice(self):
        from server16_py.frontend_stadium_selection import save_selection,selection
        save_selection(self.game,'ABC',900000)
        with self.assertRaises(LookupError):prepare(self.game,900000,176,career=True,session=77)
        save_selection(self.game,'ABC',900000,career=True,session=77)
        self.assertEqual(prepare(self.game,900000,176,career=True,session=77)['name'],'ABC')
        self.assertEqual(selection(self.game,900000,career=True,session=78),'auto')
        self.assertEqual(selection(self.game,900001,career=True,session=77),'auto')
        with self.assertRaises(LookupError):prepare(self.game,900000,261,career=True,session=78)
        self.assertEqual(selection(self.game,900000),'ABC')

    def test_global_switch_retains_club_choices(self):
        from server16_py.frontend_stadium_selection import enabled,save_enabled,save_selection,selection
        self.assertFalse(enabled(self.game))
        save_selection(self.game,'ABC',900000)
        save_enabled(self.game,False)
        self.assertFalse(enabled(self.game))
        self.assertEqual(selection(self.game,900000),'ABC')
        save_enabled(self.game,True)
        self.assertTrue(enabled(self.game))

    def test_native_and_unassigned_fallback_do_not_hide_unknown_stadium(self):
        folder=self.game/'ModCarrerMode/data/catalogs';folder.mkdir(parents=True)
        (folder/'club_stadium_fallback.tsv').write_text('1|156|60000|Emirates||1|1\n2|175|10000|Custom|Missing pack|1|1\n')
        self.assertEqual(native_fallback(self.game,1,176)['mode'],2)
        self.assertEqual(native_fallback(self.game,2,176)['mode'],0)
        self.assertEqual(native_fallback(self.game,999,176)['mode'],0)

    def test_manual_choice_belongs_to_one_club_and_crowd_route_tracks_model(self):
        from server16_py.frontend_stadium_selection import save_selection
        (self.pack/'crowd_day.dat').write_bytes(b'custom crowd placements')
        (self.pack/'NoSeats.rx3').write_bytes(b'RX3l'+bytes(60))
        save_selection(self.game,'ABC',900000)
        result=prepare(self.game,900000,176)
        self.assertTrue(result['crowd'].endswith('/crowd_day.dat'))
        self.assertTrue(result['chairs'].endswith('/NoSeats.rx3'))
        route=(self.game/'data/fifarna/lua/assets/server16_frontend_176.lua').read_text()
        self.assertIn(result['crowd'],route)
        self.assertIn(result['chairs'],route)
        with self.assertRaises(LookupError):prepare(self.game,900001,261)


class FrontendSelectorTest(unittest.TestCase):
    def test_native_update_preserves_running_image_and_unrelated_mods(self):
        import contextlib,hashlib
        from tools.stage_frontend_native_update import stage
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);game=root/'game'
            old=game/'ModCarrerMode/mods/frontend_stadium/frontend_stadium_native_v6.dll'
            old.parent.mkdir(parents=True);old.write_bytes(b'MZold-loaded-image')
            enabled=game/'ModCarrerMode/mods/enabled.txt'
            enabled.write_text('other_mod.dll\nfrontend_stadium\\frontend_stadium_native_v6.dll\n')
            report=game/'ModCarrerMode/runtime/frontend_stadium_install.json';report.parent.mkdir(parents=True)
            original={'version':6,'files':{str(old.relative_to(game)):hashlib.sha256(old.read_bytes()).hexdigest()}}
            report.write_text(json.dumps(original))
            dll=root/'new.dll';dll.write_bytes(b'MZnew-image')
            with contextlib.redirect_stdout(io.StringIO()):result=stage(game,dll)
            self.assertEqual(old.read_bytes(),b'MZold-loaded-image')
            self.assertIn('other_mod.dll',enabled.read_text())
            self.assertIn('native_v11.dll',enabled.read_text())
            self.assertNotIn('native_v6.dll',enabled.read_text())
            self.assertTrue(result['requires_restart'])
            self.assertEqual(result['version'],11)

    def test_settings_switch_hides_picker_and_handles_controller_and_mouse(self):
        from unittest.mock import patch
        from server16_py.frontend_stadium_selection import enabled
        from test_stadium_selector import StadiumSelectorTests
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);selector=StadiumSelectorTests().make_selector(root)
            selector.app.exedir=root
            try:
                with patch.object(selector,'_preload_catalog'):
                    selector.open(frontend=True)
                    panel=selector.frontend_panel
                    self.assertFalse(enabled(root))
                    self.assertEqual([i for i,r in panel.targets()],[0,2])
                    selector.handle(6,0)
                    self.assertTrue(enabled(root))
                    self.assertEqual([i for i,r in panel.targets()],[0,1,2])
                    # Hit the scaled top of the row: inputs must use the same
                    # 90% coordinates as the published panel texture.
                    selector.handle(8,(95<<16)|450)
                    self.assertFalse(enabled(root))
                    self.assertEqual([i for i,r in panel.targets()],[0,2])
                    with Image.open(selector.shared.image_path) as image:self.assertEqual(image.size,(1080,792))
                    self.assertEqual((selector.shared.width,selector.shared.height),(540,396))
                    selector.handle(7,0)
                    self.assertFalse(selector.opened)
                    selector.open(frontend=True)
                    self.assertFalse(selector.frontend_panel.enabled)
                    selector.handle(6,0)
                    selector.close();selector.open(frontend=True)
                    self.assertTrue(selector.frontend_panel.enabled)
            finally:selector.shutdown()

    def test_hub_background_uses_provider_and_retains_fallback_in_both_modes(self):
        from tools.install_frontend_stadium import patched_hub_background
        for state in ('mainMenuWithStadium','MainMenuHub'):
            source='{"name":"'+state+'","onEnter":[["loadView",["background","BOOTFLOW"]]],"onExit":[]}'
            result=patched_hub_background(source,state)
            self.assertIn('["background", "FIFA", "BOOTFLOW"]',result)
            self.assertEqual(patched_hub_background(result,state),result)
            self.assertIn('"onExit":[]',result)

    def test_background_picker_preserves_match_assignments_and_automatic_mode(self):
        from unittest.mock import patch
        from server16_py.frontend_stadium_selection import selection,save_enabled
        from server16_py.stadium_catalog import StadiumEntry
        from test_stadium_selector import StadiumSelectorTests
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);selector=StadiumSelectorTests().make_selector(root)
            selector.app.exedir=root;selector.app.lastpagename='game/screens/fluxHub/FluxHub'
            state=root/'ModCarrerMode/runtime/frontend_stadium_live.ini';state.parent.mkdir(parents=True)
            state.write_text('[frontend_stadium]\npid=1234\nteam=130022\nphase=3\n',encoding='utf16')
            selector._catalog_cache=[StadiumEntry('BRA - ABC','BRA','Frasqueirão','ABC','130022',root,None)]
            selector._catalog_ready=True
            save_enabled(root,True)
            try:
                with patch.object(selector,'_preload_catalog'),patch.object(selector,'render'):
                    selector.open(frontend=True)
                    self.assertIsNotNone(selector.frontend_panel)
                    selector.frontend_panel.activate(1)
                    self.assertIsNone(selector.frontend_panel)
                    self.assertEqual(selector.results[0].name,'auto')
                    selector.index=1;selector.apply()
                    self.assertEqual(selection(root,130022),'BRA - ABC')
                    selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
                    selector.close();selector.open(frontend=True,frontend_picker=True)
                    self.assertEqual(selector.index,1)
                    selector.index=0;selector.apply()
                    self.assertEqual(selection(root,130022),'auto')
                    selector.close();selector.app.lastpagename='game/screens/playNow/KickOffHub'
                    selector.open()
                    self.assertEqual(len(selector.results),1)
                    self.assertFalse(selector.frontend_mode)
            finally:selector.shutdown()

    def test_back_discards_preview_and_returns_to_settings(self):
        from unittest.mock import patch
        from server16_py.frontend_stadium_selection import selection
        from server16_py.stadium_catalog import StadiumEntry
        from test_stadium_selector import StadiumSelectorTests
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);selector=StadiumSelectorTests().make_selector(root)
            selector.app.exedir=root;selector.app.lastpagename='game/screens/saveload_pc/profile'
            state=root/'ModCarrerMode/runtime/frontend_stadium_live.ini';state.parent.mkdir(parents=True)
            state.write_text('[frontend_stadium]\npid=1234\nteam=130022\nphase=3\n',encoding='utf16')
            selector._catalog_cache=[StadiumEntry('ABC','BRA','Frasqueirão','ABC','130022',root,None)]
            selector._catalog_ready=True
            try:
                with patch.object(selector,'_preload_catalog'),patch.object(selector,'render'):
                    selector.open(frontend=True,frontend_picker=True);selector.index=1;selector.back()
                    self.assertTrue(selector.opened)
                    self.assertIsNotNone(selector.frontend_panel)
                    self.assertEqual(selection(root,130022),'auto')
                    selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
            finally:selector.shutdown()


if __name__ == '__main__':unittest.main()
