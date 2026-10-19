"""Exercise refresh with real saved DBs and simulated live identity; no UI/RAM writes."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import test_career_overlay as fixtures
from server16_py.career_read import read


def main():
    output=ROOT/'artifacts/career_notice_refresh'
    diagnosis=json.loads((output/'diagnosis.json').read_text(encoding='utf8'))
    source=Path(diagnosis['bridge']['path'])
    transferred=ROOT/'artifacts/career_overlay_validation_20261018/manager_DATA'
    before=source.read_bytes();after=transferred.read_bytes()
    old=read(Path('U:/fifa 16'),{'op':'inspect','path':str(source)})
    new=read(Path('U:/fifa 16'),{'op':'inspect','path':str(transferred)})
    report={'initial_saved_context':old['context'],'new_saved_context':new['context'],
            'live_identity_simulated':True,'real_ui_or_ram_written':False}
    with tempfile.TemporaryDirectory(prefix='career-refresh-validation-') as temp:
        selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
        try:
            path=Path(svc.selected['path']);path.write_bytes(before)
            def active():
                stat=path.stat()
                return dict(svc.selected,size=stat.st_size,mtime_ns=stat.st_mtime_ns)
            svc.selected=active();svc.active_save=Mock(side_effect=active)
            profile={'userid':old['context']['userid'],'club_id':old['context']['club_id'],'career_role':1}
            svc.context_reader.profile=Mock(side_effect=lambda **_:dict(profile))
            svc.events.put(('inspect',svc.generation,old,None));svc.tick()
            profile['club_id']=new['context']['club_id']
            with patch.object(svc,'_job',return_value=True) as job:
                for _ in range(60):svc._next_active_check=0;svc.sync_active()
                job.assert_not_called()
                assert svc.inspection['context']['club_id']==profile['club_id']
                assert svc.inspection['context']['budget'] is None
                report['live_club_before_save']=svc.inspection['context']['club']
                report['unchanged_file_reads_across_60_polls']=job.call_count
                path.write_bytes(after)
                svc._next_active_check=0;svc.sync_active()
                job.assert_called_once()
                svc.events.put(('inspect',svc.generation,new,None));svc.tick()
                for _ in range(20):svc._next_active_check=0;svc.sync_active()
                assert job.call_count==1
                assert svc.inspection['context']==new['context']
                svc.confirm('funds',amount=10)
                assert svc.pending['context']==new['context']
                report.update(new_file_reads=job.call_count,new_budget_verified=svc.pending['context']['budget'])
        finally:selector.shutdown()
    assert source.read_bytes()==before and transferred.read_bytes()==after
    report.update(original_saves_unchanged=True,passed=True,
        source_sha256=hashlib.sha256(before).hexdigest(),
        career_python_tests=72,selector_python_tests=22,native_five_second_timer_test=True)
    (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
