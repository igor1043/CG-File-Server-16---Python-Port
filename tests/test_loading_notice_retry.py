import unittest
from types import MethodType
from unittest.mock import patch

from server16_py.app import Server16App
from server16_py.loading_notices import loading_notices
import test_loading_notice_lifecycle as fixtures


class LoadingNoticeRetryTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.LoadingNoticeLifecycleTests();fixture.setUp();self.app=fixture.app
        self.app._kickoff_generation=1;self.app.HID='18';self.app.AID='22'
        for name in ('_hide_asset_loading','_finish_asset_loading','_hide_stadium_loading_modal'):
            setattr(self.app,name,MethodType(getattr(Server16App,name),self.app))
        self.clock=patch('time.monotonic',return_value=100);self.now=self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_each_asset_survives_copy_finished_before_native_connection(self):
        for kind in ('scoreboard','movie','narration'):
            with self.subTest(kind=kind):
                self.app._ensure_d3d_overlay_injected.return_value=False
                Server16App._show_asset_loading(self.app,kind,'Loading',kind,'Copying',4)
                Server16App._update_asset_loading(self.app,kind,100,'Ready')
                self.app._hide_asset_loading(kind,delay_ms=500)
                self.assertIn(kind,loading_notices(self.app).pending)
                self.now.return_value=105
                self.app._ensure_d3d_overlay_injected.return_value=True
                loading_notices(self.app).retry()
                self.app._d3d_injector.show_asset.assert_called_with(kind,kind,'Ready',100,image_path='')
                self.assertEqual(self.app._asset_loading_started_at[kind],105)
                self.assertEqual(self.app.after.call_args.args[:2],(1200,self.app._finish_asset_loading))
                self.assertNotIn(kind,loading_notices(self.app).pending)
                self.app._finish_asset_loading(kind)

    def test_stadium_retries_last_progress_and_keeps_minimum_visible_time(self):
        self.app._try_d3d_overlay_show.return_value=False
        Server16App._show_stadium_loading_modal(self.app,'Arena',progress=4)
        Server16App._update_stadium_loading_modal(self.app,100,'Ready')
        self.app._hide_stadium_loading_modal()
        self.now.return_value=103
        def show(*args,**kwargs):
            self.app._d3d_overlay_shown_at=103
            return True
        self.app._try_d3d_overlay_show.side_effect=show
        loading_notices(self.app).retry()
        self.app._try_d3d_overlay_show.assert_called_with('Arena','Ready',100,narration=False)
        self.assertEqual(self.app.after.call_args.args,(2500,self.app._do_hide_d3d_overlay))

    def test_new_fixture_never_displays_previous_fixture_notice(self):
        self.app._ensure_d3d_overlay_injected.return_value=False
        Server16App._show_asset_loading(self.app,'movie','','Old fixture','',10)
        self.app._kickoff_generation+=1
        self.app._ensure_d3d_overlay_injected.return_value=True
        loading_notices(self.app).retry()
        self.app._d3d_injector.show_asset.assert_not_called()
        self.assertFalse(loading_notices(self.app).pending)

    def test_timeout_and_disabled_setting_cancel_pending_without_popup(self):
        for disabled in (False,True):
            with self.subTest(disabled=disabled):
                self.now.return_value=100
                self.app._ensure_d3d_overlay_injected.return_value=False
                Server16App._show_asset_loading(self.app,'movie','','Old fixture','',10)
                if disabled:self.app.show_stadium_loading_var.get.return_value=False
                else:self.now.return_value=113
                loading_notices(self.app).retry()
                self.assertFalse(loading_notices(self.app).pending)
                self.app._d3d_injector.show_asset.assert_not_called()
                self.app.stadium_loading_modal.deiconify.assert_not_called()


if __name__=='__main__':unittest.main()
