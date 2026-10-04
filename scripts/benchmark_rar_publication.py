"""Compare validated legacy copy and production fast publication, without touching FIFA."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py import file_tools


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def tree_digest(root):
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--scratch-parent',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    archive=args.archive.resolve(strict=True)
    parent=args.scratch_parent.resolve(strict=True)
    if archive.suffix.lower()!='.rar':parser.error('Use the existing RAR; no ZIP conversion is performed')
    if not 1<=args.repeats<=5:parser.error('repeats must be 1..5')
    if file_tools._rarmod is None:parser.error('rarfile required for CRC/size verification')
    backends=file_tools._rar_extractors()
    if not backends:parser.error('No installed RAR extractor found')
    with file_tools._rarmod.RarFile(archive) as source:
        members=source.infolist()
    bytes_unpacked=sum(m.file_size for m in members if not m.isdir())
    if shutil.disk_usage(parent).free<bytes_unpacked*3:parser.error('Insufficient scratch space')
    before=digest(archive)
    rows=[];reference=None
    original_run=file_tools.subprocess.run
    original_check=file_tools._check_rar_output
    original_publish=file_tools._publish_rar_output
    with tempfile.TemporaryDirectory(prefix='cgfs16_rar_compare_',dir=parent) as temporary:
        sandbox=Path(temporary).resolve()
        assert sandbox.parent==parent and sandbox.name.startswith('cgfs16_rar_compare_')
        print('ISOLATED SANDBOX:',sandbox,flush=True)
        schedule=[]
        for trial in range(args.repeats):
            pair=('legacy_copy','fast_publish') if trial%2==0 else ('fast_publish','legacy_copy')
            schedule.extend((method,trial+1) for method in pair)
        schedule.append(('forced_rename_failure',1))
        for strategy,trial in schedule:
            with tempfile.TemporaryDirectory(prefix='run_',dir=sandbox) as trial_directory:
                run=Path(trial_directory).resolve()
                assert run.parent==sandbox and run.name.startswith('run_')
                output=run/'extracted'
                timings=dict(extractor_seconds=0.0,validation_seconds=0.0,publication_seconds=0.0)
                def timed(action,key):
                    start=time.perf_counter()
                    result=action()
                    timings[key]+=time.perf_counter()-start
                    return result
                def subprocess_run(*a,**kw):return timed(lambda:original_run(*a,**kw),'extractor_seconds')
                def check(*a,**kw):return timed(lambda:original_check(*a,**kw),'validation_seconds')
                def publish(*a,**kw):return timed(lambda:original_publish(*a,**kw),'publication_seconds')
                def published(method,reason):timings.update(publication_method=method,publication_reason=reason)
                print(f'START {strategy} / trial {trial}',flush=True)
                start=time.perf_counter()
                with patch.object(file_tools,'_rar_extractors',return_value=[backends[0]]), \
                     patch.object(file_tools.subprocess,'run',side_effect=subprocess_run), \
                     patch.object(file_tools,'_check_rar_output',side_effect=check), \
                     patch.object(file_tools,'_publish_rar_output',side_effect=publish):
                    if strategy=='forced_rename_failure':
                        with patch.object(Path,'rename',side_effect=PermissionError('simulated antivirus lock')):
                            backend=file_tools.extract_archive(archive,output,fast_publish=True,publication_callback=published)
                    else:
                        backend=file_tools.extract_archive(archive,output,fast_publish=strategy=='fast_publish',publication_callback=published)
                total=time.perf_counter()-start
                actual=tree_digest(output)
                if reference is None:reference=actual
                assert actual==reference,'Extracted bytes differ from validated legacy output'
                expected_method='rename' if strategy=='fast_publish' else 'copy'
                assert timings['publication_method']==expected_method,timings
                row=dict(strategy=strategy,trial=trial,backend=backend,total_seconds=total,hashes_match=True,**timings)
                rows.append(row)
                print(json.dumps(row),flush=True)
    assert digest(archive)==before,'Source archive changed during benchmark'
    summary={}
    for method in ('legacy_copy','fast_publish'):
        subset=[r for r in rows if r['strategy']==method]
        summary[method]={key:statistics.median(r[key] for r in subset)
                         for key in ('total_seconds','extractor_seconds','validation_seconds','publication_seconds')}
    old=summary['legacy_copy']['total_seconds'];new=summary['fast_publish']['total_seconds']
    report=dict(metadata=dict(archive=str(archive),archive_sha256=before,source_unchanged=True,
        compressed_bytes=archive.stat().st_size,unpacked_bytes=bytes_unpacked,backend=backends[0],
        platform=platform.platform(),python=sys.version,scratch_volume=str(parent),
        note='Interleaved alternating order, OS cache uncontrolled. Timings exclude output SHA256 and cleanup. Extraction only, no application or memory writes.'),
        runs=rows,medians=summary,median_gain_seconds=old-new,median_gain_percent=(old-new)/old*100)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('REPORT:',args.output.resolve(),flush=True)
    print('MEDIAN GAIN:',report['median_gain_seconds'],'seconds;',report['median_gain_percent'],'%',flush=True)


if __name__=='__main__':main()
