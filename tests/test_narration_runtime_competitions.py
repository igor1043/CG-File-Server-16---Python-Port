import time,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from test_narration_runtime import NarrationRuntimeTests

class CompetitionRuntimeTests(unittest.TestCase):
    def make(self):
        runtime=NarrationRuntimeTests().runtime();runtime.game_pid=123
        runtime.app.HID='1';runtime.app.AID='2';runtime.app.TOURNAME='1615';runtime.app.TOURROUNDID='1613';runtime.app._kickoff_generation=4
        runtime.profiles=lambda:[dict(name='Vilani',competitions=['1615']),dict(name='Luiz Roberto',competitions=['1615']),dict(name='Tiago Leifert',competitions=[])]
        runtime.apply=Mock();runtime._seen_context=runtime._context();runtime._context_since=time.monotonic()-1;runtime._previous_auto='Vilani'
        return runtime
    def test_one_choice_per_fixture_and_no_repeat_when_another_is_available(self):
        runtime=self.make();runtime._auto_select(True);runtime.apply.assert_called_once_with('Luiz Roberto',automatic=True)
        runtime._auto_select(True);runtime.apply.assert_called_once()
    def test_manual_choice_is_kept_for_the_current_fixture(self):
        runtime=self.make();runtime._manual_context=runtime._context();runtime._auto_select(True);runtime.apply.assert_not_called()
    def test_never_switches_during_gameplay(self):
        runtime=self.make();runtime._auto_select(False);runtime.apply.assert_not_called()
    def test_saved_narrator_is_restored_instead_of_rerolled_after_restart(self):
        runtime=self.make();runtime.default_narrator='Vilani';runtime._restoring_default=True
        runtime._auto_select(True);runtime.apply.assert_called_once_with('Vilani',automatic=True)

class PreferenceTests(unittest.TestCase):
    def test_successful_preference_roundtrip(self):
        from server16_py.narration_runtime import load_preferences,save_preferences
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'FSW/narration_settings.json'
            save_preferences(path,'Vilani');self.assertEqual(load_preferences(path)['default_narrator'],'Vilani')

if __name__=='__main__':unittest.main()
