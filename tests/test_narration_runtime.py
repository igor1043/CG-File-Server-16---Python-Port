import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from server16_py.narration_runtime import NarrationRuntime


class NarrationRuntimeTests(unittest.TestCase):
    def runtime(self):
        runtime=NarrationRuntime.__new__(NarrationRuntime)
        runtime.app=SimpleNamespace(base_dir=Path('.'),memory=SimpleNamespace(is_open=lambda:True),_resolve_fifa_pid=lambda:123,log=Mock())
        runtime.shared=SimpleNamespace(heartbeat=0,phase=0,ack=0,command=0,status=0,error=0,ready=1,reads=0,replaced=0)
        runtime.current='Tiago Leifert';runtime.pending=None;runtime.deadline=0;runtime.next_inject=0;runtime.pid=0;runtime.game_pid=0;runtime.error='';runtime._diagnostics=None;runtime._inject_results=queue.Queue();runtime._injecting=False
        return runtime

    @patch('server16_py.narration_runtime.narration_dll_loaded',return_value=True)
    @patch('server16_py.narration_runtime.subprocess.run')
    def test_reopening_server_reuses_existing_game_worker(self,run,loaded):
        runtime=self.runtime();runtime.tick(True)
        runtime._inject_results.put(runtime._inject_results.get(timeout=1))
        runtime.tick(True)
        loaded.assert_called_once_with(123);run.assert_not_called()
        self.assertEqual(runtime.pid,123)
        self.assertEqual(runtime.shared.phase,1)

    @patch('server16_py.narration_runtime.narration_dll_loaded',return_value=True)
    def test_new_game_discards_previous_selection_and_request(self,loaded):
        runtime=self.runtime();runtime.pid=runtime.game_pid=42
        runtime.current='Vilani';runtime.pending='Luiz Roberto'
        runtime.shared.command=7;runtime.shared.ack=6
        runtime.tick(True)
        self.assertEqual(runtime.current,'Tiago Leifert')
        self.assertIsNone(runtime.pending)
        self.assertEqual(runtime.shared.ack,7)

    def test_late_acknowledgment_updates_current_narrator(self):
        runtime=self.runtime();runtime.pid=runtime.game_pid=123
        runtime.app.show_narration_applied=Mock()
        runtime.pending='Vilani';runtime.shared.command=runtime.shared.ack=8
        runtime.shared.status=2
        runtime.tick(True)
        self.assertEqual(runtime.current,'Vilani')
        self.assertIsNone(runtime.pending)
        runtime.app.show_narration_applied.assert_called_once_with('Vilani')

    @patch('server16_py.narration_runtime.narration_dll_loaded')
    @patch('server16_py.narration_runtime.subprocess.run')
    def test_narration_injection_waits_for_loaded_game_page(self,run,loaded):
        runtime=self.runtime();runtime.app.lastpagename=''
        runtime.tick(False)
        loaded.assert_not_called();run.assert_not_called()
        self.assertEqual(runtime.pid,0)


if __name__=='__main__':unittest.main()
