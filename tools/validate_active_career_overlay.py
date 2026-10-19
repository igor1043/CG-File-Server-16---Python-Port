"""Offline automatic-career flow with real x86 DB reads, on owned copies only."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(args):
    from server16_py.career_active_save import read_active_save
    from server16_py.career_save_worker import fingerprint
    from server16_py.career_service import run_worker
    from server16_py.stadium_selector import StadiumSelector
    source=Path(args.save).resolve();game=Path(args.game).resolve()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    original=source.read_bytes()
    path=out/'fixture/FIFA16/abc/DATA';path.parent.mkdir(parents=True)
    path.write_bytes(original);(path.parent/'INDEX').write_bytes(b'offline fixture index')
    runtime=out/'fixture/ModCarrerMode/runtime';runtime.mkdir(parents=True)
    (runtime/'career_save_source.tsv').write_text(
        'schema=3\npid=123\nprocess_created_100ns=999\nsave_type=SaveType_Career\n'
        f'complete_file=1\noperation=read\nsize_bytes={len(original)}\npath={path}\n')
    context=run_worker(game,{'op':'inspect','path':str(path)})['context']
    memory=SimpleNamespace(is_open=lambda:True,process_id=123)
    app=SimpleNamespace(base_dir=out/'server',targetpath=out,exedir=game,settings_ini=None,
        team_db=SimpleNamespace(team_cache={}),_kickoff_generation=1,HID='1',AID='2',
        TOURNAME='',TOURROUNDID='',lastpagename='game/screens/career/Home',_stadium_task_running=False,
        memory=memory,module_enabled=lambda _:True,_overlay_visible=False,_crowd_volume_visible=False,
        _resolve_fifa_pid=lambda:123,_ensure_d3d_overlay_injected=Mock(return_value=True),
        log=lambda *a:None,_resolve_team_logo_path=lambda _:None,
        stadium_runtime=SimpleNamespace(apply_manual_stadium=Mock()))
    with patch('server16_py.stadium_selector.SELECTOR_MAPPING_NAME',f'Local\\CGFS16_OfflineAuto_{os.getpid()}'), \
         patch('server16_py.crowd_control.MAPPING_NAME',f'Local\\CGFS16_OfflineAutoCrowd_{os.getpid()}'):
        selector=StadiumSelector(app)
    try:
        svc=selector.career_service
        svc.feedback=Mock()
        svc.jobs_runtime=Mock()
        svc.jobs_runtime.ready.return_value=False
        svc.active_save=lambda:read_active_save(out/'fixture',memory)
        svc.context_reader.profile=lambda **_: {k:context[k] for k in ('userid','club_id')}
        with patch('server16_py.career_active_save.process_created',return_value=999):
            selector.open(career=True)
            panel=selector.career_panel
            panel.activate(0);assert panel.page=='clubs'
            deadline=time.monotonic()+60
            while not svc.inspection and time.monotonic()<deadline:
                svc.tick();time.sleep(.03)
            assert svc.inspection,svc.message
            assert svc.selected['path']==str(path)
            for page in ('home','clubs','finances','funds'):
                panel.page=page;panel.focus=0
                panel.render().save(out/(page+'.png'))
            panel.page='home';panel.activate(0)
            before=panel.team;panel.activate(2)
            assert panel.page=='clubs' and panel.team!=before
            panel.page='home';panel.activate(1);assert panel.page=='finances'
            panel.activate(0);assert panel.page=='funds'
            panel.amount='1000000';panel.activate(12);assert panel.page=='confirm'
            panel.render().save(out/'confirmation.png')
            panel.activate(0);assert svc.pending and svc.pending['amount']==1000000
            assert svc.pending['path']==str(path)
            svc.cancel()
        assert path.read_bytes()==original and source.read_bytes()==original
        report={'automatic_file_binding':True,'real_db_worker':True,'context':context,
                'stacked_country_league_team_selectors':True,'finances_and_confirmation_open':True,
                'request_binds_active_copy':True,'original_unchanged':True,
                'fixture_unchanged':True,'source_sha256':fingerprint(original),
                'game_attached':False,'ram_written':False}
        (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
        print(json.dumps(report,indent=2,ensure_ascii=False))
    finally:selector.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--game',required=True);parser.add_argument('--save',required=True)
    parser.add_argument('--output',required=True)
    main(parser.parse_args())
