"""Offline integration checks. Operates on output copies, never live saves.

python tools/validate_career_overlay.py --game "U:/fifa 16" --save <DATA> --output <new-folder>
"""
from __future__ import annotations
import argparse
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def make_player_fixture(args):
    sys.path.insert(0,str(ROOT/'server16_py'))
    from db_worker import _prefer_bundled_site_packages
    _prefer_bundled_site_packages()
    sys.path.insert(0,str(ROOT/'bin'))
    import clr
    clr.AddReference(str(ROOT/'bin/FifaLibrary16.dll'))
    from FifaLibrary import DbFile
    from server16_py.career_save_worker import Save, set_int, blocks
    data=Path(args.save).read_bytes()
    with tempfile.TemporaryDirectory() as temporary:
        save=Save(data,Path(args.game)/'data/db/fifa_ng_db-meta.xml',temporary,DbFile)
        context=save.context()
        links=[r for r in save.rows('teamplayerlinks') if r.GetIntField('teamid')==context['club_id']]
        player=links[0].GetIntField('playerid')
        table=save.table('career_playasplayer')
        if table.NValidRecords or table.NRecords<1:
            raise ValueError('Fixture requires a manager snapshot with a free player-career row.')
        row=table.Records[0]
        set_int(row,'userid',context['userid']);set_int(row,'playerid',player)
        table.NValidRecords=1
        user=save.one('career_users','userid',context['userid'])
        set_int(user,'usertype',0);set_int(user,'playertype',0)
        database=save.databases[save._table_owner['career_playasplayer']]
        path=Path(temporary)/'player.db'
        assert database.SaveDb(str(path))
        verify=DbFile(str(path),str(Path(args.game)/'data/db/fifa_ng_db-meta.xml'))
        assert verify.Load() and verify.ComputeAllCrc()
        offset,size=save.ranges[save._table_owner['career_playasplayer']]
        payload=path.read_bytes()
        assert len(payload)==size
        result=bytearray(data);result[offset:offset+size]=payload
        struct.pack_into('<I',result,132,zlib.crc32(result[160:]))
        blocks(result)
        Path(args.output).write_bytes(result)
        print(json.dumps({'player_id':player}))


def main(args):
    from server16_py.career_service import run_worker, publish_save
    from server16_py.career_save_worker import blocks, fingerprint
    game=Path(args.game).resolve();source=Path(args.save).resolve()
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    before=source.read_bytes()
    inspection=run_worker(game,{'op':'inspect','path':str(source)})
    context=inspection['context']
    report={'source_sha256':fingerprint(before),'original_unchanged':False,'checks':[]}
    assert context['player_id'] is None, 'Use a manager snapshot for all three scenarios.'
    common={'op':'prepare','path':str(source),'context':context,'fingerprint':fingerprint(before)}
    funds=output/'funds_DATA'
    result=run_worker(game,dict(common,action='funds',amount=10_000_000,output=str(funds)))
    assert result['context']['budget']==context['budget']+10_000_000
    changed=sum(a!=b for a,b in zip(before,funds.read_bytes()))
    assert changed<100, 'An integer budget edit must preserve unrelated payload bytes.'
    report['checks'].append({'action':'funds','budget':result['context']['budget'],'changed_bytes':changed})
    catalog=inspection['catalog']
    from server16_py.competition_catalog import nodes
    objects=nodes(game)
    mapping={int(row[1][1:]):ident for ident,row in objects.items() if row[0]==3 and row[1].startswith('C') and row[1][1:].isdigit()}
    target=next((league,team) for league,team in catalog['links']
                if team!=context['club_id'] and league in mapping and 0<mapping[league]<=2000)
    league,team=target
    transfer=output/'manager_DATA'
    result=run_worker(game,dict(common,action='transfer',team_id=team,league_id=league,
                              primarycompobjid=mapping[league],output=str(transfer)))
    assert result['context']['club_id']==team
    report['checks'].append({'action':'manager_transfer','team_id':team,'league_id':league})
    # Build a synthetic player career from a COPY of the manager snapshot.
    player=output/'player_fixture_DATA'
    subprocess.run([str(ROOT/'bin/python32/python.exe'),str(Path(__file__).resolve()),'--make-player',
                    '--game',str(game),'--save',str(source),'--output',str(player)],check=True,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    info=run_worker(game,{'op':'inspect','path':str(player)})
    assert info['context']['player_id'] is not None
    player_output=output/'player_transfer_DATA'
    result=run_worker(game,{'op':'prepare','path':str(player),'context':info['context'],
                          'fingerprint':info['fingerprint'],'action':'transfer','team_id':team,
                          'league_id':league,'primarycompobjid':mapping[league],'output':str(player_output)})
    assert result['context']['club_id']==team and result['context']['player_id']==info['context']['player_id']
    report['checks'].append({'action':'player_transfer','player_id':info['context']['player_id'],'team_id':team})
    # Exercise the real publication and exclusive-lock path in a test slot.
    slot=output/'test_slot';slot.mkdir();(slot/'DATA').write_bytes(before)
    (slot/'INDEX').write_bytes(source.with_name('INDEX').read_bytes())
    index=(slot/'INDEX').read_bytes()
    backup=Path(publish_save(slot/'DATA',fingerprint(before),funds.read_bytes(),output/'backups'))
    assert (backup/'DATA').read_bytes()==before and (slot/'INDEX').read_bytes()==index
    blocks((slot/'DATA').read_bytes())
    report['checks'].append({'action':'publish_copy','index_unchanged':True,'backup_exact':True})
    report['original_unchanged']=source.read_bytes()==before
    assert report['original_unchanged']
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


def validate_real_player(args):
    from server16_py.career_service import run_worker
    from server16_py.career_save_worker import fingerprint
    from server16_py.competition_catalog import nodes
    game=Path(args.game).resolve();source=Path(args.save).resolve()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=False)
    before=source.read_bytes()
    snapshot=output/'source_DATA';snapshot.write_bytes(before)
    info=run_worker(game,{'op':'inspect','path':str(snapshot)})
    assert info['context']['player_id'] is not None, 'This must be a player career.'
    objects=nodes(game)
    mapping={int(row[1][1:]):ident for ident,row in objects.items() if row[0]==3 and row[1].startswith('C') and row[1][1:].isdigit()}
    league,team=next((league,team) for league,team in info['catalog']['links']
                    if team!=info['context']['club_id'] and league in mapping and 0<mapping[league]<=2000)
    result=run_worker(game,{'op':'prepare','path':str(snapshot),'context':info['context'],
                          'fingerprint':info['fingerprint'],'action':'transfer','team_id':team,
                          'league_id':league,'primarycompobjid':mapping[league],
                          'output':str(output/'transferred_DATA')})
    assert result['context']['club_id']==team
    assert result['context']['player_id']==info['context']['player_id']
    assert source.read_bytes()==before
    report={'before':info['context'],'after':result['context'],'original_unchanged':True}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--game',required=True);parser.add_argument('--save',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--make-player',action='store_true')
    parser.add_argument('--player-only',action='store_true')
    args=parser.parse_args()
    if args.make_player:make_player_fixture(args)
    elif args.player_only:validate_real_player(args)
    else:main(args)
