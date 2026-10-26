import configparser
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server16_py.extra_scenes_panel import ExtraScenesSettings, ExtraScenesPanel
import test_match_audio_panel as fixtures
import test_prematch_panel as prematch_fixtures

class ExtraScenesTests(unittest.TestCase):
    def setUp(self):
        # Exercise the retained development UI explicitly, outside public gates.
        for name in ('EXTRA_SCENES_AVAILABLE',):
            gate=patch('server16_py.'+name,True)
            gate.start();self.addCleanup(gate.stop)

    def test_prematch_entry_shares_settings_and_does_not_request_camera(self):
        with tempfile.TemporaryDirectory() as d:
            selector=prematch_fixtures.PrematchTests().selector(Path(d))
            try:
                selector.open(hub=True)
                selector.handle(16,5)
                panel=selector.prematch_panel
                self.assertIsInstance(panel,ExtraScenesPanel)
                self.assertTrue(panel.prematch)
                panel.activate(1)
                self.assertEqual(panel.store.values()['coach_view'],0)
                panel.activate(3)
                self.assertEqual(panel.store.document().getint('scenes','preview_serial'),0)
                selector.handle(7,0)
                self.assertFalse(isinstance(selector.prematch_panel,ExtraScenesPanel))
                rect=next(rect for action,rect,labels in selector.prematch_panel.cards() if action==4)
                selector.handle(8,(((rect[1]+rect[3])//2)<<16)|((rect[0]+rect[2])//2))
                self.assertIsInstance(selector.prematch_panel,ExtraScenesPanel)
                selector.app.lastpagename='game/screens/career/Home'
                before=panel.store.path.read_bytes();selector.prematch_panel.activate(0)
                self.assertFalse(selector.opened)
                self.assertEqual(panel.store.path.read_bytes(),before)
            finally:selector.shutdown()

    def test_save_preserves_advanced_lens_and_unknown_sections(self):
        with tempfile.TemporaryDirectory() as d:
            store=ExtraScenesSettings(d);store.update(enabled=1)
            doc=store.document();doc['coach_full']['distance']='910';doc['custom']={'keep':'yes'};store.save(doc)
            for mode in range(4):store.update(coach_view=mode,mascot_view=3-mode)
            doc=store.document();self.assertEqual(doc['coach_full']['distance'],'910');self.assertEqual(doc['custom']['keep'],'yes')
            self.assertEqual(store.values()['coach_view'],3)
            previous=store.path.read_bytes()
            for value in (True,-1,4,'1'):
                with self.assertRaises(ValueError):store.update(coach_view=value)
            self.assertEqual(store.path.read_bytes(),previous)

    def test_test_frequency_preserves_production_probability(self):
        with tempfile.TemporaryDirectory() as d:
            store=ExtraScenesSettings(d)
            self.assertFalse(store.values()['test_mode'])
            store.update(test_mode=1)
            doc=store.document()
            self.assertEqual(doc.getint('scenes','chance_percent'),40)
            self.assertEqual(doc.getint('scenes','cooldown_seconds'),10)
            self.assertTrue(ExtraScenesSettings(d).values()['test_mode'])
            store.update(test_mode=0)
            self.assertFalse(store.values()['test_mode'])

    def test_preview_persists_monotonic_command_and_target(self):
        with tempfile.TemporaryDirectory() as d:
            store=ExtraScenesSettings(d);store.preview(1)
            self.assertEqual(store.document().getint('scenes','preview_serial'),1)
            store.preview(0);self.assertEqual(store.document().getint('scenes','preview_serial'),2)
            self.assertEqual(store.values()['preview_actor'],0)
            store.update(coach_view=0)
            previous=store.path.read_bytes()
            with self.assertRaises(ValueError):store.preview(0)
            self.assertEqual(store.path.read_bytes(),previous)

    def test_old_runtime_process_cannot_report_ready(self):
        with tempfile.TemporaryDirectory() as d:
            store=ExtraScenesSettings(d);store.status_path.parent.mkdir()
            store.status_path.write_text('[runtime]\npid=10\nready=1\nactive=0\nreason=0\n')
            self.assertIn('Reinicie',store.status(11));self.assertIn('prioridade',store.status(10))
            store.status_path.write_text('[runtime]\nmode=native_cut_producer\npid=10\nready=1\nactive=0\nreason=0\n')
            self.assertIn('cutscenes originais',store.status(10))

    def test_full_sequence_display_preserves_native_selection_weights(self):
        with tempfile.TemporaryDirectory() as d:
            store=ExtraScenesSettings(d)
            self.assertEqual(store.values()['chance_percent'],40)
            self.assertEqual(store.values()['cooldown_seconds'],10)
            doc=store.document();doc['scenes']['coach_weight']='3';doc['scenes']['mascot_weight']='1';doc['scenes']['duration_ms']='12000';store.save(doc)
            self.assertNotIn('duration_ms',store.values()) # Retired cap cannot cut a native reaction in half.
            store.update(coach_view=2)
            self.assertEqual(store.document()['scenes']['coach_weight'],'3')

    def test_overlay_navigation_persistence_and_fixture_guard(self):
        with tempfile.TemporaryDirectory() as d:
            selector=fixtures.MatchAudioTests().make_selector(Path(d))
            try:
                selector.open(audio=True);hub=selector.audio_panel
                index=next(i for i,item in enumerate(hub.items()) if item[0]=='Cenas extras')
                hub.focus=index;hub.handle(6,0)
                panel=hub.child;self.assertIsInstance(panel,ExtraScenesPanel)
                panel.focus=1;panel.handle(3,0);self.assertEqual(panel.store.values()['coach_view'],0)
                panel.handle(2,0);self.assertEqual(panel.store.values()['coach_view'],3)
                panel.focus=3;panel.handle(3,0);self.assertEqual(panel.store.values()['preview_actor'],1)
                panel.handle(6,0);self.assertEqual(panel.store.document().getint('scenes','preview_serial'),1)
                for pad in (False,True):
                    selector.controller_connected=pad;self.assertEqual(panel.render().size,(1200,980))
                old=panel.store.path.read_bytes()
                with patch.object(selector,'match_eligible',return_value=False):panel.activate(0)
                self.assertEqual(panel.store.path.read_bytes(),old)
            finally:selector.shutdown()

if __name__=='__main__':unittest.main()
