import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from server16_py.app import Server16App


class LoadingNoticeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(
            show_stadium_loading_var=Mock(get=Mock(return_value=True)),
            _stadium_loading_hwnd=123, user32=Mock(),
            stadium_loading_modal=Mock(), stadium_loading_bar=Mock(),
            _stadium_loading_hide_job=None, _d3d_overlay_hide_job=None,
            _d3d_overlay_shown_at=0, _stadium_loading_visible=True,
            _stadium_loading_restore_fullscreen=False,
            _asset_loading_started_at={}, _asset_loading_hide_jobs={},
            _asset_loading_fallback=set(), _stadium_task_running=False,
            _ensure_d3d_overlay_injected=Mock(return_value=True),
            _d3d_injector=Mock(), _cancel_stadium_loading_hide=Mock(),
            _try_d3d_overlay_show=Mock(return_value=True),
            _do_hide_d3d_overlay=Mock(), after=Mock(), after_cancel=Mock(), log=Mock(),
        )
        self.app._withdraw_stadium_loading_fallback = lambda: Server16App._withdraw_stadium_loading_fallback(self.app)

    def test_first_movie_notification_waits_without_stadium_popup(self):
        self.app._ensure_d3d_overlay_injected.return_value=False
        Server16App._show_asset_loading(self.app, 'movie', 'Vídeo pré-jogo', 'Caze TV', 'Vinheta', 100)
        self.app.stadium_loading_modal.deiconify.assert_not_called()
        self.app.stadium_loading_modal.withdraw.assert_called_once()
        self.app._d3d_injector.show_asset.assert_not_called()
        # The following fixture uses its own native movie card, not the stadium window.
        self.app._ensure_d3d_overlay_injected.return_value=True
        Server16App._show_asset_loading(self.app, 'movie', 'Vídeo pré-jogo', 'Outro canal', 'Vinheta', 100)
        self.app._d3d_injector.show_asset.assert_called_once_with('movie', 'Outro canal', 'Vinheta', 100, image_path='')
        self.app.stadium_loading_modal.deiconify.assert_not_called()

    def test_hide_after_native_injection_also_closes_old_window(self):
        self.app._d3d_injector.is_injected.return_value=True
        Server16App._hide_stadium_loading_modal(self.app)
        self.app.stadium_loading_modal.withdraw.assert_called_once()
        self.app._do_hide_d3d_overlay.assert_called_once()

    def test_stadium_renderer_unavailable_does_not_open_window(self):
        self.app._try_d3d_overlay_show.return_value=False
        Server16App._show_stadium_loading_modal(self.app, 'Maracana', progress=5)
        self.app.stadium_loading_modal.withdraw.assert_called_once()
        self.app.stadium_loading_modal.deiconify.assert_not_called()

    def test_stadium_native_show_withdraws_legacy_window(self):
        Server16App._show_stadium_loading_modal(self.app, 'Maracana', progress=5)
        self.app._try_d3d_overlay_show.assert_called_once()
        self.app.stadium_loading_modal.withdraw.assert_called_once()


if __name__ == '__main__':
    unittest.main()
