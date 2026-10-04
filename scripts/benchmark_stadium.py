"""Read a real stadium, but extract/apply only inside a disposable sandbox.

No FIFA process, memory access or installed game destination is used. Proposed
publication/cache paths exist only in this benchmark, not in the server.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server16_py import file_tools, stadium_runtime
from server16_py.stadium_runtime import StadiumRuntime


def elapsed(action):
    start=time.perf_counter()
    result=action()
    return result, time.perf_counter()-start


def make_app(sandbox, archive, baseline):
    game=sandbox/'simulated_game'
    return SimpleNamespace(
        exedir=game, base_dir=sandbox, targetpath=archive.parent,
        settings_ini=SimpleNamespace(key_exists=lambda *a:True, read=lambda *a:archive.stem+',None,None,None'),
        Psource=baseline/'Police', Nsource=baseline/'Nets', PitchMowsource=baseline/'PitchMowPattern',
        Pdest=game/'data/sceneassets/slc', Ndest=game/'data/sceneassets/goalnet',
        PitchMowdest=game/'data/sceneassets/pitch', PoliceNum='4', Stadiumtype='first',
        Movdata=game/'data/movies/bootflowoutro.vp8', MOVBUMP=game/'data/ui/TV/bumper.big',
        _worker_queue=queue.Queue(), log=lambda *a:None,
    )


def prepare_native_baseline(app, source):
    # Copy only the native slot files used by the worker, not the full game.
    for slot in ('176','261'):
        for relative, template in file_tools._STADIUM_INJECTION_FILES:
            path=source/'Stadium'/relative/template.format(id=slot)
            if path.is_file():
                dest=app.exedir/'FSW/Stadium'/relative/path.name
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,dest)
        for day in ('1','3'):
            for index in range(4):
                for ext in ('rx3','lnx'):
                    path=source/'Stadium/fx'/f'glares_{slot}_{day}_{index}.{ext}'
                    if path.is_file():
                        dest=app.exedir/'FSW/Stadium/fx'/path.name
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(path,dest)


def fingerprint(directory):
    result={}
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            digest=hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
            result[path.relative_to(directory).as_posix()]=digest.hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--scratch-parent',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    archive=args.archive.resolve(strict=True)
    baseline=args.baseline.resolve(strict=True)
    scratch_parent=args.scratch_parent.resolve(strict=True)
    if args.repeats<1 or args.repeats>5:parser.error('repeats must be 1..5')
    if shutil.disk_usage(scratch_parent).free<4*1024**3:parser.error('At least 4 GiB free required')
    if file_tools._rarmod is None:parser.error('rarfile is required to verify CRC/size in this benchmark')
    with file_tools._rarmod.RarFile(archive) as rar:
        members=rar.infolist()
    backends=file_tools._rar_extractors()
    metadata=dict(archive=str(archive),compressed_bytes=archive.stat().st_size,
                  extracted_bytes=sum(m.file_size for m in members if not m.isdir()),
                  files=sum(not m.isdir() for m in members),platform=platform.platform(),
                  python=sys.version,scratch_volume=str(scratch_parent),backends=backends,
                  cache_note='OS cache is uncontrolled; later runs may benefit from it. No disk cache purge.',
                  cleanup_note='Worker temporary cleanup is disabled for byte comparison; sandbox cleanup happens outside timings. No FIFA memory writes or in-game asset contention.',
                  baseline_note='Native slot baseline read from FSW; all destinations are temporary.')
    rows=[]
    with tempfile.TemporaryDirectory(prefix='cgfs16_benchmark_',dir=scratch_parent) as temporary:
        sandbox=Path(temporary).resolve()
        assert sandbox.parent==scratch_parent and sandbox.name.startswith('cgfs16_benchmark_')
        print('ISOLATED SANDBOX:',sandbox,flush=True)
        cached=None; expected=None
        for strategy,backend in [('current',backends[0]),('rename_prototype',backends[0])]+[
                ('backend_comparison',backend) for backend in backends[1:]]:
            for trial in range(args.repeats if strategy!='backend_comparison' else 1):
                run=sandbox/f'{strategy}_{trial}'
                run.mkdir()
                app=make_app(run,archive,baseline)
                prepare_native_baseline(app,baseline)
                timings=dict(extractor_seconds=0.0,validation_seconds=0.0,publication_seconds=0.0)
                extract_actual=file_tools.extract_archive
                run_actual=file_tools.subprocess.run
                check_actual=file_tools._check_rar_output
                copy_actual=file_tools.shutil.copy2
                extracted=None
                def timed_run(*a,**kw):
                    result,seconds=elapsed(lambda:run_actual(*a,**kw))
                    timings['extractor_seconds']+=seconds
                    return result
                def timed_check(*a,**kw):
                    result,seconds=elapsed(lambda:check_actual(*a,**kw))
                    timings['validation_seconds']+=seconds
                    return result
                def timed_copy(src,dst,*a,**kw):
                    result,seconds=elapsed(lambda:copy_actual(src,dst,*a,**kw))
                    # Publication alone: copy from the private rar_stage_* directory.
                    if any(part.startswith('rar_stage_') for part in Path(src).parts):
                        timings['publication_seconds']+=seconds
                    return result
                def extract(source,destination,progress_callback=None,**options):
                    nonlocal extracted
                    extracted=Path(destination)
                    if strategy!='rename_prototype':
                        options['fast_publish']=False  # Historical baseline remains the old copy path.
                        result,seconds=elapsed(lambda:extract_actual(source,destination,progress_callback,**options))
                    else:
                        def prototype():
                            stage=run/'validated_stage';stage.mkdir()
                            executable=backend[1]
                            command=[executable,'x','-idq','-o+','-p-','--',str(source),str(stage)+os.sep]
                            completed=timed_run(command,capture_output=True,text=True,errors='replace',
                                                timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                            if completed.returncode:raise RuntimeError(completed.stderr or completed.stdout)
                            timed_check(stage,members)
                            if not any(p.is_file() for p in stage.rglob('*')):raise RuntimeError('Empty extraction')
                            for p in stage.rglob('*'):
                                if p.is_symlink():raise RuntimeError('Link rejected')
                            def publish():
                                # Both paths are new siblings on the same volume, no merge/overwrite.
                                Path(destination).rmdir()
                                stage.replace(destination)
                            _,timings['publication_seconds']=elapsed(publish)
                            return backend[0]+' + validated rename prototype'
                        result,seconds=elapsed(prototype)
                    timings['extraction_total_seconds']=seconds
                    # Keep one checked tree for the repeated-load/cache and ZIP experiments.
                    return result
                print(f'START {strategy} / {backend[0]} / trial {trial+1}',flush=True)
                try:
                    # Prevent the existing worker cleanup only for retaining its isolated extracted tree.
                    with patch.object(file_tools,'_rar_extractors',return_value=[backend]), \
                         patch.object(file_tools.subprocess,'run',side_effect=timed_run), \
                         patch.object(file_tools,'_check_rar_output',side_effect=timed_check), \
                         patch.object(file_tools.shutil,'copy2',side_effect=timed_copy), \
                         patch.object(stadium_runtime,'extract_archive',side_effect=extract), \
                         patch.object(stadium_runtime.shutil,'rmtree'):
                        payload,total=elapsed(lambda:StadiumRuntime(app).run_stadium_copy_job('1043','stadium','176',archive.stem))
                    actual=fingerprint(app.exedir/'data')
                    if expected is None:expected=actual
                    assert actual==expected,'Applied bytes differ from baseline'
                    timings['worker_total_seconds']=total
                    timings['application_seconds']=total-timings['extraction_total_seconds']
                    row=dict(strategy=strategy,backend=backend[0],trial=trial+1,status='ok',**timings)
                    if cached is None:
                        cached=sandbox/'checked_cache'
                        extracted.replace(cached)
                    print(json.dumps(row),flush=True)
                    rows.append(row)
                except Exception as exc:
                    row=dict(strategy=strategy,backend=backend[0],trial=trial+1,status='failed',error=str(exc))
                    print(json.dumps(row),flush=True);rows.append(row)
                # Only delete a known per-run child of this unique sandbox.
                assert run.resolve().parent==sandbox
                shutil.rmtree(run)
        if cached is not None:
            for trial in range(args.repeats):
                run=sandbox/f'cache_{trial}';run.mkdir()
                app=make_app(run,archive,baseline);prepare_native_baseline(app,baseline)
                app.targetpath=cached
                print(f'START cache_hit / trial {trial+1}',flush=True)
                payload,seconds=elapsed(lambda:StadiumRuntime(app).run_stadium_copy_job('1043','stadium','176',archive.stem))
                assert fingerprint(app.exedir/'data')==expected
                row=dict(strategy='cache_hit_prototype',trial=trial+1,status='ok',worker_total_seconds=seconds)
                print(json.dumps(row),flush=True);rows.append(row)
                assert run.resolve().parent==sandbox
                shutil.rmtree(run)
            for compression,label in ((zipfile.ZIP_STORED,'zip_stored'),(zipfile.ZIP_DEFLATED,'zip_deflate_level1')):
                packed=sandbox/(label+'.zip')
                def create_zip():
                    with zipfile.ZipFile(packed,'w',compression=compression,compresslevel=1 if compression==zipfile.ZIP_DEFLATED else None) as z:
                        for path in sorted(cached.rglob('*')):
                            if path.is_file():z.write(path,path.relative_to(cached).as_posix())
                print('START ZIP creation / '+label,flush=True)
                _,create_seconds=elapsed(create_zip)
                output=sandbox/label
                _,extract_seconds=elapsed(lambda:file_tools.extract_archive(packed,output))
                assert fingerprint(output)==fingerprint(cached)
                row=dict(strategy=label,status='ok',create_seconds=create_seconds,extraction_total_seconds=extract_seconds,compressed_bytes=packed.stat().st_size)
                print(json.dumps(row),flush=True);rows.append(row)
                assert output.resolve().parent==sandbox
                shutil.rmtree(output);packed.unlink()
    report=dict(metadata=metadata,runs=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print('REPORT:',args.output.resolve(),flush=True)


if __name__=='__main__':main()
