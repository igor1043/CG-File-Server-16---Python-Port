"""Own-widget smoke test; does not inspect or control other applications."""
import time,json,faulthandler
from studio import Studio
faulthandler.dump_traceback_later(20,repeat=True)
app=Studio();app.withdraw();app.show_library()
deadline=time.monotonic()+180;longest=0
try:
    while time.monotonic()<deadline:
        start=time.monotonic();app.update();longest=max(longest,time.monotonic()-start)
        if app.data_loaded and app.library_panel.rows:break
        time.sleep(.01)
    assert app.data_loaded,'Original catalogue failed to load: '+app.status.get()
    assert app.library_panel.rows,'Library failed to load'
    assert longest<1,'UI stalled: '+str(longest)
    assert str(app.library_panel) in app.pane.panes()
    app.toggle_library();assert str(app.library_panel) not in app.pane.panes()
    app.show_library();assert str(app.library_panel) in app.pane.panes()
    print(json.dumps(dict(status='ok',columns=len(app.pane.panes()),library_rows=len(app.library_panel.rows),max_ui_update_seconds=round(longest,3))),flush=True)
finally:
    faulthandler.cancel_dump_traceback_later();app.close_app()
