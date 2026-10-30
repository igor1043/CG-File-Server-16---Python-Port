"""Retry short-lived loading notices until FIFA's existing overlay is connected.

Asset copies can complete before the first usable render frame. Keep their last
progress and start the minimum display time only after publishing the notice.
Nothing here loads a DLL, copies game assets or changes narrator selection.
"""
from dataclasses import dataclass
import time


@dataclass
class PendingNotice:
    name: str
    detail: str
    progress: float
    image_path: str
    context: tuple
    expires: float
    hide_delay: int | None = None
    narration: bool = False


class LoadingNotices:
    RETRY_MS = 200
    TIMEOUT = 12.0

    def __init__(self, app):
        self.app = app
        self.pending = {}
        self.job = None

    def context(self):
        app = self.app
        memory = getattr(app, 'memory', None)
        return (getattr(memory, 'process_id', 0),
                getattr(app, '_kickoff_generation', 0),
                getattr(app, 'HID', ''), getattr(app, 'AID', ''))

    def wait(self, kind, name, detail, progress, image_path='', narration=False):
        self.pending[kind] = PendingNotice(name, detail, progress, image_path,
            self.context(), time.monotonic() + self.TIMEOUT, narration=narration)
        self._schedule()

    def cancel(self, kind):
        self.pending.pop(kind, None)
        if not self.pending and self.job is not None:
            self.app.after_cancel(self.job)
            self.job = None

    def update(self, kind, progress, detail):
        notice = self.pending.get(kind)
        if notice is None:
            return False
        notice.progress, notice.detail = progress, detail
        return True

    def defer_hide(self, kind, delay_ms):
        notice = self.pending.get(kind)
        if notice is None:
            return False
        notice.hide_delay = max(0, delay_ms)
        return True

    def _schedule(self):
        if self.pending and self.job is None:
            self.job = self.app.after(self.RETRY_MS, self.retry)

    def retry(self):
        self.job = None
        app = self.app
        context = self.context()
        for kind, notice in list(self.pending.items()):
            if (notice.context != context or time.monotonic() >= notice.expires
                    or not app.show_stadium_loading_var.get()
                    or getattr(app, '_closing', False)):
                self.pending.pop(kind, None)
                if kind != 'stadium':
                    app._asset_loading_started_at.pop(kind, None)
                continue
            if kind == 'stadium':
                shown = app._try_d3d_overlay_show(notice.name, notice.detail,
                    notice.progress, narration=notice.narration)
            else:
                shown = app._ensure_d3d_overlay_injected()
                if shown:
                    app._d3d_injector.show_asset(kind, notice.name, notice.detail,
                        notice.progress, image_path=notice.image_path)
                    app._asset_loading_started_at[kind] = time.monotonic()
            if shown:
                self.pending.pop(kind, None)
                app.log(f'{kind} loading notification delivered: {notice.name}')
                if notice.hide_delay is not None:
                    if kind == 'stadium':
                        app._hide_stadium_loading_modal(delay_ms=notice.hide_delay)
                    else:
                        app._hide_asset_loading(kind, delay_ms=notice.hide_delay)
        self._schedule()


def loading_notices(app):
    controller = getattr(app, '_loading_notices', None)
    if controller is None:
        controller = app._loading_notices = LoadingNotices(app)
    return controller
