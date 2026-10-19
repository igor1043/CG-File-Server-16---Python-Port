"""Compare optimized save preparation with previously native-verified output."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server16_py.career_service import run_worker
from server16_py.career_save_worker import fingerprint


def main():
    root=ROOT/'artifacts/career_sticky_progress';gold=ROOT/'artifacts/career_performance_retirement'
    request=json.loads((root/'request.json').read_text())
    original=Path(request['path']).read_bytes()
    report={'checks':[],'passed':False}
    def save():
        (root/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    # Capture old-worker timing and bytes for a real arbitrary-budget request.
    backup=Path((root/'backup.txt').read_text())
    old_request=dict(request,game='U:/fifa 16',dll=str(ROOT/'bin/FifaLibrary16.dll'),
                     action='funds',amount=12_345_678,output=str(root/'funds_before_DATA'))
    old_json=root/'old_worker_request.json';old_json.write_text(json.dumps(old_request))
    start=time.perf_counter()
    old=subprocess.run([str(ROOT/'bin/python32/python.exe'),str(backup/'career_save_worker.py'),str(old_json)],
                       capture_output=True,text=True,encoding='utf8',env=dict(os.environ,PYTHONNOUSERSITE='1'),
                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True,timeout=90)
    assert json.loads(old.stdout)['ok']
    report['funds_before_seconds']=time.perf_counter()-start
    for action,amount in (('funds',10_000_000),('funds',100_000_000),('funds',12_345_678),
                          ('remove_retirement',None),('remove_and_rejuvenate',None)):
        output=root/(action+('_'+str(amount) if amount else '')+'_DATA')
        command=dict(request,action=action,output=str(output))
        if amount:command['amount']=amount
        start=time.perf_counter();result=run_worker(Path('U:/fifa 16'),command);elapsed=time.perf_counter()-start
        expected=gold/('funds_'+str(amount) if amount else action)/'prepared_DATA'
        assert output.read_bytes()==expected.read_bytes(),(action,amount,'changed output')
        if amount==12_345_678:
            assert output.read_bytes()==(root/'funds_before_DATA').read_bytes()
            report['funds_after_seconds']=elapsed
        report['checks'].append({'name':action,'amount':amount,'seconds':elapsed,
                                  'native_bytes_equal':True,'full_worker_verification':True})
        save();print(action,amount,round(elapsed,3),'exact bytes verified',flush=True)
    assert Path(request['path']).read_bytes()==original
    before=json.loads((root/'baseline.json').read_text());after=json.loads((root/'optimized.json').read_text())
    report.update(passed=True,snapshot_unchanged=True,
        worker_sha256=fingerprint((ROOT/'server16_py/career_save_worker.py').read_bytes()),
        reader_sha256=fingerprint((ROOT/'server16_py/career_read.py').read_bytes()),
        retirement_before_seconds=before['seconds'],retirement_after_seconds=after['seconds'],
        original_save_passed_to_editor=False)
    save();print('ALL CHECKS PASSED',flush=True)


if __name__=='__main__':main()
