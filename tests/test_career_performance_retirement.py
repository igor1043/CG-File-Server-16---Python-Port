import struct
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.career_read import Database, read
from server16_py.career_save_worker import edit, fifa_crc32
from server16_py.career_service import retirement_age
import test_career_overlay as overlay_fixtures


class Row:
    def __init__(self, **values):
        self.values = values

    def GetIntField(self, field):
        return self.values[field]


def fixture(players, calendar=20261019, budget=100):
    context = {'userid':0, 'club_id':10, 'player_id':None, 'budget':budget}
    pref = Row(transferbudget=budget)
    save = SimpleNamespace(context=lambda:context, one=lambda *args:pref,
        rows=lambda name:players if name=='players' else [Row(currdate=calendar)],
        change=lambda row, field, value:row.values.update({field:value}))
    return save, context


class RetirementRulesTests(unittest.TestCase):
    def test_native_crc_known_vector(self):
        self.assertEqual(fifa_crc32(b'123456789'), 0x0376E6E7)

    def test_removal_keeps_ages_and_untargeted_players(self):
        players = [Row(playerid=1, isretiring=1, birthdate=100), Row(playerid=2, isretiring=0, birthdate=200)]
        save, context = fixture(players, calendar=0)
        self.assertEqual(edit(save, {'action':'remove_retirement','context':context}), context)
        self.assertEqual([r.values for r in players], [dict(playerid=1,isretiring=0,birthdate=100),
                                                     dict(playerid=2,isretiring=0,birthdate=200)])
        self.assertEqual(save.retirement_summary['players_changed'], 1)

    def test_rejuvenation_uses_career_date_preserves_birthday_and_leap_day_rule(self):
        epoch = date(1582,10,14)
        for today, birthday, expected in ((20261019,date(1980,12,24),date(2007,12,24)),
                                          (20261019,date(1980,1,3),date(2008,1,3)),
                                          (20240228,date(1980,2,29),date(2005,2,28))):
            with self.subTest(today=today,birthday=birthday):
                row = Row(isretiring=1,birthdate=(birthday-epoch).days)
                save, context = fixture([row],calendar=today)
                edit(save, {'action':'remove_and_rejuvenate','context':context,'target_age':18})
                self.assertEqual(row.values, dict(isretiring=0,birthdate=(expected-epoch).days))

    def test_rejects_bad_age_context_and_budget_without_changing_records(self):
        row = Row(isretiring=1,birthdate=100)
        for age in (True, 0, 11, 51, '18'):
            save, context = fixture([row])
            with self.assertRaises(ValueError):
                edit(save, {'action':'remove_and_rejuvenate','context':context,'target_age':age})
            self.assertEqual(row.values['isretiring'], 1)
        for amount in (-1, 0, True, 2_000_000_000):
            save, context = fixture([])
            with self.assertRaises(ValueError):edit(save, {'action':'funds','context':context,'amount':amount})
        save, context = fixture([row])
        with self.assertRaises(ValueError):
            edit(save, {'action':'remove_retirement','context':dict(context,club_id=11)})

    def test_configured_retirement_age_and_safe_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);path = root/'ModCarrerMode/config/career_retirement_background.ini'
            path.parent.mkdir(parents=True)
            for content, expected in (('target_age=21',21),('target_age=90',18),('target_age=oops',18)):
                path.write_text(content)
                self.assertEqual(retirement_age(root),expected)


class ReadOnlyDatabaseTests(unittest.TestCase):
    def test_reader_rejects_writes_without_touching_a_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'DATA';path.write_bytes(b'original')
            with self.assertRaises(ValueError):read(temporary, {'op':'prepare','path':str(path)})
            self.assertEqual(path.read_bytes(),b'original')

    def test_integer_range_utf8_and_spare_records(self):
        # One table, two allocated rows, only one live row, string + integer.
        data = bytearray(24+8+4+36+32+16)
        data[:4] = b'DB\0\x08'
        struct.pack_into('<I',data,16,1)
        struct.pack_into('<4sI',data,24,b'TEST',0)
        struct.pack_into('<I',data,40,8)
        struct.pack_into('<HH',data,52,2,1)
        data[60] = 2
        struct.pack_into('<II4sI',data,72,3,0,b'IDDD',8)
        struct.pack_into('<II4sI',data,88,0,8,b'NAME',48)
        data[104] = 11
        data[105:110] = 'São'.encode()+b'\0'
        metadata = {b'TEST':('teams',{b'IDDD':{'name':'teamid','rangelow':'-1'}, b'NAME':{'name':'teamname'}})}
        db = Database(bytes(data),0,len(data),metadata)
        rows = db.tables['teams']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].GetIntField('teamid'),10)
        self.assertEqual(rows[0].GetStringField('teamname'),'São')
        struct.pack_into('<I',data,76,1000)
        with self.assertRaises(ValueError):Database(bytes(data),0,len(data),metadata)


class CareerRetirementFlowTests(unittest.TestCase):
    def test_unknown_fast_layout_falls_back_to_existing_inspector(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector = overlay_fixtures.CareerOverlayTests().make_ready(Path(temporary))
            try:
                request = {'op':'inspect','path':str(Path(temporary)/'DATA')}
                with patch('server16_py.career_service.read_career',side_effect=ValueError('unknown layout')), \
                     patch('server16_py.career_service.run_worker',return_value={'ok':True}) as worker:
                    self.assertEqual(selector.career_service._read(Path(temporary),request),{'ok':True})
                    worker.assert_called_once_with(Path(temporary),request)
            finally:selector.shutdown()

    def test_both_actions_require_review_close_panel_and_persist_request(self):
        for choice, action in ((0,'remove_retirement'),(1,'remove_and_rejuvenate')):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as temporary:
                selector = overlay_fixtures.CareerOverlayTests().make_ready(Path(temporary))
                try:
                    selector.open(career=True);panel = selector.career_panel
                    panel.activate(2);self.assertEqual(panel.page,'retirement')
                    panel.activate(choice)
                    self.assertEqual(panel.page,'confirm');self.assertEqual(panel.focus,1)
                    self.assertIsNone(selector.career_service.pending)
                    panel.activate(0)
                    self.assertIsNone(selector.career_panel)
                    svc = selector.career_service
                    self.assertEqual(svc.pending['action'],action)
                    self.assertEqual(svc.pending['target_age'],18)
                    self.assertEqual(svc.state,'waiting_exit')
                    self.assertTrue((svc.root/'pending.json').is_file())
                finally:selector.shutdown()

    def test_catalog_preloads_on_ram_connection_before_career(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector = overlay_fixtures.CareerOverlayTests().make_ready(Path(temporary))
            try:
                svc = selector.career_service;svc.catalog = None
                svc.live_page = Mock(return_value='game/screens/frontend/MainMenu')
                with patch.object(svc,'load') as loaded:
                    svc.preload();loaded.assert_called_once()
                svc.jobs_runtime.ensure.assert_not_called()
            finally:selector.shutdown()


if __name__ == '__main__':
    unittest.main()
