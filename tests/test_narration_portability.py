import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
from portable_setup import configuration_path


def probe():
    studio=Path(__file__).resolve().parents[1]/'tools/narration_studio'
    sys.path.insert(0,str(studio))
    from core import GAME,WORK,PROJECTS,SOURCE_ROOT,relocate_catalog_paths
    config_path=Path(os.environ['F16_NARRATION_CONFIG'])
    expected={key:(config_path.parent/value).resolve() for key,value in {
        'game':'../game','catalog_root':'../catalog','projects':'../projects','source_root':'../sources'
    }.items()}
    assert GAME==expected['game'] and WORK==expected['catalog_root']
    assert PROJECTS==expected['projects'] and SOURCE_ROOT==expected['source_root']
    manifest={'resolved_roots':{'game_root':r'U:\old FIFA','work_root':r'U:\old FIFA\Narrations\.studio','source_root':r'J:\mods\fifa 16'}}
    (WORK/'portable_catalog.json').write_text(json.dumps(manifest),encoding='utf8')
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('CREATE TABLE banks(key TEXT,source TEXT,sbr TEXT,body TEXT); CREATE TABLE clips(key TEXT,wav TEXT); CREATE TABLE sources(key TEXT,path TEXT);')
    db.execute('INSERT INTO banks VALUES(?,?,?,?)',('b',r'U:\old FIFA\data_audio3.big',r'U:\old FIFA\Narrations\.studio\banks\b.sbr',r'U:\old FIFA\data_audio3.big'))
    db.execute('INSERT INTO clips VALUES(?,?)',('c',r'U:\old FIFA\Narrations\.studio\original_wav\x.wav'))
    db.execute('INSERT INTO sources VALUES(?,?)',('s',r'J:\mods\fifa 16\03_Recursos\VILANI\x.wav'))
    relocate_catalog_paths(db)
    bank=db.execute('SELECT source,sbr,body FROM banks').fetchone()
    clip=db.execute('SELECT wav FROM clips').fetchone()
    source=db.execute('SELECT path FROM sources').fetchone()
    assert Path(bank['source'])==expected['game']/'data_audio3.big'
    assert Path(bank['sbr'])==expected['catalog_root']/'banks'/'b.sbr'
    assert Path(clip['wav'])==expected['catalog_root']/'original_wav'/'x.wav'
    assert Path(source['path'])==expected['source_root']/'03_Recursos'/'VILANI'/'x.wav'


class NarrationPortabilityTests(unittest.TestCase):
    def test_frozen_editor_keeps_machine_specific_config_outside_shared_folder(self):
        with tempfile.TemporaryDirectory(prefix='f16_user_config_') as temporary:
            with patch.dict(os.environ,{'LOCALAPPDATA':temporary},clear=False),patch.object(sys,'frozen',True,create=True):
                self.assertEqual(configuration_path(Path(temporary)/'portable'),Path(temporary)/'FIFA16NarrationStudio'/'studio_config.json')
                override=Path(temporary)/'test-config.json'
                with patch.dict(os.environ,{'F16_NARRATION_CONFIG':str(override)},clear=False):
                    self.assertEqual(configuration_path(),override.resolve())

    def test_relative_config_and_moved_catalog_paths(self):
        with tempfile.TemporaryDirectory(prefix='f16_portability_') as temporary:
            root=Path(temporary);app=root/'editor';app.mkdir()
            for name in ('game','catalog','projects','sources'):(root/name).mkdir()
            config=app/'studio_config.json'
            config.write_text(json.dumps({'game':'../game','catalog_root':'../catalog','projects':'../projects','source_root':'../sources'}),encoding='utf8')
            env=dict(os.environ,F16_NARRATION_CONFIG=str(config))
            result=subprocess.run([sys.executable,__file__,'--probe'],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr or result.stdout)


if __name__=='__main__' and '--probe' in sys.argv:
    probe()
elif __name__=='__main__':
    unittest.main()
