import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from server16_py.career_jobs_runtime import CareerJobsRuntime,JobsShared,MAGIC,VERSION


class LiveJobsProtocolTests(unittest.TestCase):
    def make_runtime(self):
        runtime=CareerJobsRuntime(SimpleNamespace(memory=SimpleNamespace(process_id=123),log=Mock()))
        runtime.pid=123;runtime.shared=JobsShared();runtime.shared.load_epoch=5
        runtime.shared.magic=MAGIC;runtime.shared.version=VERSION;runtime.shared.pid=123
        runtime.ready=Mock(return_value=True)
        return runtime

    def test_cpp_layout_and_request_binds_to_current_career_and_load(self):
        self.assertEqual(ctypes.sizeof(JobsShared),208)
        self.assertEqual(JobsShared.registry.offset,48)
        self.assertEqual(JobsShared.clubs.offset,80)
        runtime=self.make_runtime()
        sequence=runtime.request({'club_id':1043,'registry_address':123456,'context_address':9988},130285,350)
        self.assertEqual(sequence,1)
        self.assertEqual((runtime.shared.registry,runtime.shared.context,runtime.shared.request_epoch),(123456,9988,5))
        self.assertIsNone(runtime.poll(sequence,130285,350))
        with self.assertRaisesRegex(ValueError,'aguardando'):runtime.request({'club_id':1043,'registry_address':123456,'context_address':9988},383,7)

    def test_completion_requires_exact_native_ack_and_membership(self):
        runtime=self.make_runtime();s=runtime.shared
        s.sequence=s.completed=4;s.status=1;s.count=2
        s.clubs[0][:]=[383,7];s.clubs[1][:]=[130285,350]
        self.assertIsNone(runtime.poll(3,130285,350))
        self.assertFalse(runtime.poll(4,130285,350)['save_edited'])
        self.assertTrue(runtime.poll(4,130285,350)['proposal_received'])
        self.assertTrue(runtime.poll(4,130285,350)['native_contract_queued'])
        s.reserved=3
        self.assertEqual(runtime.poll(4,130285,350)['valid_for_days'],3)
        with self.assertRaisesRegex(ValueError,'não foi confirmado'):runtime.poll(4,112119,83)
        s.status=-1;s.error=1
        with self.assertRaisesRegex(ValueError,'carreira mudou'):runtime.poll(4,130285,350)

    def test_server_reconnect_reuses_a_ready_native_channel(self):
        runtime=self.make_runtime()
        with patch('server16_py.career_jobs_runtime.threading.Thread') as thread:
            runtime.ensure();thread.assert_not_called()

    def test_native_event_consumed_before_delivery_is_not_a_false_error(self):
        runtime=self.make_runtime();s=runtime.shared
        s.sequence=s.completed=2;s.status=0
        self.assertIsNone(runtime.poll(2,130285,350))
        with self.assertRaisesRegex(ValueError,'aguardando'):
            runtime.request({'club_id':1043,'registry_address':123456,'context_address':9988},383,7)

    def test_obsolete_block_rejection_reports_an_old_module(self):
        runtime=self.make_runtime();s=runtime.shared
        s.sequence=s.completed=2;s.status=-1;s.error=5
        with self.assertRaisesRegex(ValueError,'versão anterior'):
            runtime.poll(2,130285,350)

    def test_disabled_marker_stops_loading_and_reports_unavailable(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            app=SimpleNamespace(memory=SimpleNamespace(process_id=123),exedir=root,log=Mock())
            marker=Path(root)/'ModCarrerMode/config/career_live_jobs.disabled'
            marker.parent.mkdir(parents=True);marker.touch()
            runtime=CareerJobsRuntime(app)
            with patch('server16_py.career_jobs_runtime.threading.Thread') as thread:
                runtime.ensure();thread.assert_not_called()
            self.assertIn('suspensas',runtime.error)

    def test_unready_loaded_module_requires_restart_instead_of_second_injection(self):
        runtime=self.make_runtime();runtime.ready.return_value=False
        with patch('server16_py.career_jobs_runtime._loaded_runtime_paths',return_value=['old.dll']), \
                patch('server16_py.career_jobs_runtime.threading.Thread') as thread, \
                patch('server16_py.career_jobs_runtime.run_owned_reader') as run:
            thread.side_effect=lambda **kwargs:SimpleNamespace(start=kwargs['target'])
            runtime.ensure();run.assert_not_called()
        self.assertIn('Reinicie o FIFA',runtime.error)


if __name__=='__main__':unittest.main()
