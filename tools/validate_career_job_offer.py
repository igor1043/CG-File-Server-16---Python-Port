"""Validate the native proposal pipeline on an isolated copy of a real career.

Never publishes to the input save, attaches to FIFA or displays feedback.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.career_service import run_worker,publish_save
from server16_py.career_save_worker import blocks,fingerprint,read_job_offer,job_offer_offset


def main(args):
    source=Path(args.save).resolve();game=Path(args.game).resolve()
    original=source.read_bytes();output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    slot=output/'test_slot';slot.mkdir();path=slot/'DATA';path.write_bytes(original)
    shutil.copy2(source.with_name('INDEX'),slot/'INDEX')
    index=(slot/'INDEX').read_bytes()
    info=run_worker(game,{'op':'inspect','path':str(path)})
    assert info['context']['player_id'] is None
    common={'op':'prepare','path':str(path),'context':info['context'],'fingerprint':fingerprint(original)}
    prepared=output/'proposal_DATA'
    result=run_worker(game,dict(common,action='job_offer',team_id=args.team,
        league_id=args.league,output=str(prepared)))
    payload=prepared.read_bytes();offset=job_offer_offset(payload)
    assert result['context']==info['context']
    assert result['job_offer']['team_id']==args.team and result['job_offer']['dispatch_pending']
    assert original[160:offset+6]==payload[160:offset+6] and original[offset+50:]==payload[offset+50:]
    for start,size in blocks(original):assert original[start:start+size]==payload[start:start+size]
    backup=Path(publish_save(path,fingerprint(original),payload,output/'backups'))
    reread=run_worker(game,{'op':'inspect','path':str(path)})
    assert reread['context']==info['context'] and reread['job_offer']==result['job_offer']
    assert (backup/'DATA').read_bytes()==original and (slot/'INDEX').read_bytes()==index
    funds=output/'funds_DATA'
    funded=run_worker(game,dict(common,action='funds',amount=1000000,output=str(funds),path=str(source)))
    assert funded['context']['budget']==info['context']['budget']+1000000
    assert read_job_offer(funds.read_bytes())==read_job_offer(original)
    # Existing native applications/offers must never be silently replaced.
    blocked=False
    try:
        run_worker(game,dict(common,action='job_offer',team_id=args.team,
            league_id=args.league,fingerprint=fingerprint(payload),output=str(output/'rejected_DATA')))
    except RuntimeError as exc:
        blocked='andamento' in str(exc)
    assert blocked and not (output/'rejected_DATA').exists()
    assert source.read_bytes()==original
    report={'original_unchanged':True,'source_sha256':fingerprint(original),
        'context_preserved':reread['context'],'native_offer':reread['job_offer'],
        'all_three_databases_identical':True,'index_identical':True,'exact_backup':True,
        'existing_offer_protected':True,'funds_regression':True,
        'changed_bytes':sum(a!=b for a,b in zip(original,payload)),
        'game_attached':False,'ram_written':False,'native_ui_acceptance_observed':False}
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(report,indent=2,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--save',required=True)
    parser.add_argument('--game',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--team',type=int,required=True);parser.add_argument('--league',type=int,required=True)
    main(parser.parse_args())
