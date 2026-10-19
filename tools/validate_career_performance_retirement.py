"""Compare readers and exercise finances/retirement only on snapshot slots."""
import json
import shutil
import subprocess
import sys
import time
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server16_py.career_service import run_worker, publish_save
from server16_py.career_read import read
from server16_py.career_save_worker import fingerprint, blocks


def main():
    game = Path('U:/fifa 16')
    root = ROOT/'artifacts/career_performance_retirement'
    source = root/'snapshot/DATA'
    original = source.read_bytes()
    baseline = json.loads((root/'baseline.json').read_text(encoding='utf8'))
    report = {'checks': [], 'timing_before': baseline['timing'], 'timing_after': {}}
    retirement_only = '--retirement-only' in sys.argv
    if retirement_only:
        previous = json.loads((root/'validation.json').read_text(encoding='utf8'))
        report['checks'] = [row for row in previous['checks'] if row['name'] == 'funds']
        assert len(report['checks']) == 3
    def check(name, **details):
        report['checks'].append(dict(name=name, **details))
        (root/'validation.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        print(name, details, flush=True)
    for op in ('catalog', 'inspect'):
        started = time.perf_counter()
        quick = read(game, {'op': op, 'path': str(source)})
        report['timing_after'][op] = round(time.perf_counter()-started, 4)
        expected = json.loads((root/(op+'.json')).read_text(encoding='utf8'))
        assert json.loads(json.dumps(quick)) == expected
        check(op+'_exact_match_with_editor')
    audit = run_worker(game, {'op': 'inspect', 'path': str(source), 'retirement_audit': True})
    common = {'op': 'prepare', 'path': str(source), 'context': audit['context'], 'fingerprint': fingerprint(original)}
    for amount in (() if retirement_only else (10_000_000, 100_000_000, 12_345_678)):
        target = root/('funds_'+str(amount))
        target.mkdir(exist_ok=True)
        output = target/'prepared_DATA'
        result = run_worker(game, dict(common, action='funds', amount=amount, output=str(output)))
        assert result['context']['budget'] == audit['context']['budget']+amount
        delta = sum(a != b for a, b in zip(original, output.read_bytes()))
        assert 0 < delta < 100
        # Use actual exclusive-file publication + reread in a COPY of a slot.
        (target/'DATA').write_bytes(original)
        shutil.copy2(source.with_name('INDEX'), target/'INDEX')
        index = (target/'INDEX').read_bytes()
        backup = Path(publish_save(target/'DATA', fingerprint(original), output.read_bytes(), target/'backups'))
        assert (backup/'DATA').read_bytes() == original
        assert (target/'INDEX').read_bytes() == index
        assert read(game, {'op': 'inspect', 'path': str(target/'DATA')})['context'] == result['context']
        check('funds', amount=amount, budget_after=result['context']['budget'], changed_bytes=delta,
              backup_exact=True, index_unchanged=True, published_copy_reopened=True)
    native = Path('U:/mods/FIFA Friends V12/ModCarrerMode/source/career_native/build/tests/build_retirement_engine_test/retirement_engine_test.exe')
    for action in ('remove_retirement', 'remove_and_rejuvenate'):
        target = root/action
        target.mkdir(exist_ok=True)
        output = target/'prepared_DATA'
        result = run_worker(game, dict(common, action=action, target_age=18, output=str(output)))
        after = run_worker(game, {'op': 'inspect', 'path': str(output), 'retirement_audit': True})
        epoch = date(1582, 10, 14)
        stamp = str(audit['date'])
        current = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
        expected = []
        for ident, retiring, birth in audit['players']:
            if retiring == 1 and action == 'remove_and_rejuvenate':
                birthday = epoch+timedelta(days=birth)
                year = current.year-18-((current.month, current.day) < (birthday.month, birthday.day))
                birth = (date(year, birthday.month, min(birthday.day, monthrange(year, birthday.month)[1]))-epoch).days
            expected.append([ident, 0 if retiring == 1 else retiring, birth])
        assert after['players'] == expected
        assert after['context'] == audit['context']
        blocks(output.read_bytes())
        (target/'DATA').write_bytes(original)
        shutil.copy2(source.with_name('INDEX'), target/'INDEX')
        process = subprocess.run([str(native), str(target/'DATA'), action, '18'], capture_output=True,
                                 text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), check=True)
        native_audit = run_worker(game, {'op': 'inspect', 'path': str(target/'DATA'), 'retirement_audit': True})
        assert native_audit['players'] == after['players'], 'Retirement must match existing native card rules.'
        assert output.read_bytes() == (target/'DATA').read_bytes(), 'Retirement bytes must match the native engine.'
        assert read(game, {'op': 'inspect', 'path': str(output)})['context'] == after['context']
        (target/'DATA').write_bytes(original)
        index = (target/'INDEX').read_bytes()
        backup = Path(publish_save(target/'DATA',fingerprint(original),output.read_bytes(),target/'backups'))
        assert (backup/'DATA').read_bytes() == original and (target/'INDEX').read_bytes() == index
        check(action, **result['retirement'], native_card_semantics_equal=True,
              native_bytes_equal=output.read_bytes() == (target/'DATA').read_bytes(),
              full_player_audit=True, publication_copy_verified=True, native_result=process.stdout.strip())
        # Repeating removal on the resulting COPY must be a no-op.
        repeated = run_worker(game, {'op': 'prepare', 'action': action, 'path': str(output),
            'context': after['context'], 'fingerprint': fingerprint(output.read_bytes()),
            'target_age': 18, 'output': str(target/'repeated_DATA')})
        assert repeated['retirement']['players_changed'] == 0
        assert (target/'repeated_DATA').read_bytes() == output.read_bytes()
        check(action+'_idempotent')
    assert source.read_bytes() == original
    # The live source was only read to create the snapshot, never passed to an editor.
    report.update(snapshot_unchanged=True, live_save_passed_to_editor=False, passed=True,
        worker_sha256=fingerprint((ROOT/'server16_py/career_save_worker.py').read_bytes()),
        reader_sha256=fingerprint((ROOT/'server16_py/career_read.py').read_bytes()))
    (root/'validation.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print('ALL CHECKS PASSED', flush=True)


if __name__ == '__main__':
    main()
