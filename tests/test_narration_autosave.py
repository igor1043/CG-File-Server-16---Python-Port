import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import atomic_io,core,editor_edits,projects,profiles

class AutomaticEditingTests(unittest.TestCase):
    def test_progress_write_retries_reader_lock_without_corrupting_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'progress.json';target.write_text('{"done": 0}')
            replace=Path.replace;attempts=[]
            def locked(path,destination):
                attempts.append(path)
                if len(attempts)<3:raise PermissionError('Reader is holding the file')
                return replace(path,destination)
            with patch.object(Path,'replace',locked),patch.object(atomic_io.time,'sleep'):
                atomic_io.write_json(target,dict(done=1))
            self.assertEqual(json.loads(target.read_text()),dict(done=1))
            self.assertEqual(len(list(Path(temporary).glob('*.tmp'))),0)

    def test_progress_lock_does_not_interrupt_transcription(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'progress.json';target.write_text('{"done": 0}')
            with patch.object(Path,'replace',side_effect=PermissionError('Busy')),patch.object(atomic_io.time,'sleep'):
                self.assertFalse(atomic_io.write_json(target,dict(done=1),best_effort=True))
            self.assertEqual(json.loads(target.read_text()),dict(done=0))

    def test_manual_style_survives_transcript_edit_and_topic_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);audio=root/'voice.wav';audio.write_bytes(b'complete voice')
            db=core.connect(root/'catalog.sqlite')
            db.execute('INSERT INTO sources(key,narrator,path,event,topic) VALUES (?,?,?,?,?)',('asset','Custom',str(audio),'GOAL','Gols'))
            editor_edits.update_style(db,'asset','Apresentação genérica')
            editor_edits.update_transcript(db,'sources','asset','Que golaço!');db.commit()
            from topics import update_topics
            update_topics(db)
            row=db.execute('SELECT topic,topic_manual,transcript FROM sources').fetchone();db.close()
            self.assertEqual(tuple(row),('Apresentação genérica',1,'Que golaço!'))
            self.assertEqual(Path(str(audio)+'.txt').read_text(encoding='utf8'),'Que golaço!')

    def test_staging_complete_audio_into_game_keeps_asset_identity_on_reimport(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);original=root/'originals'/'voice.mp3';original.parent.mkdir();original.write_bytes(b'full recording')
            original_connect=core.connect;catalog=root/'catalog.sqlite'
            with patch.object(core,'connect',lambda:original_connect(catalog)):
                core.import_sources('Custom',original)
                db=original_connect(catalog);key=db.execute('SELECT key FROM sources').fetchone()[0];db.close()
                target=core.stage_source_asset('Custom',key,root/'game'/'Narrations'/'Custom'/'Studio'/'assets')
                core.import_sources('Custom',original)
                db=original_connect(catalog);self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],1);db.close()
            self.assertEqual(target.read_bytes(),original.read_bytes());self.assertTrue(original.exists())

    def fixture(self,root):
        catalog=root/'catalog.sqlite';db=core.connect(catalog)
        db.execute("INSERT INTO banks(key,name,active) VALUES ('bank','demo',1)")
        for key,offset in (('changed',32),('alias',32),('unchanged',64)):
            db.execute('INSERT INTO clips(key,bank,offset,wav,event,row,topic) VALUES (?,?,?,?,?,?,?)',(key,'bank',offset,f'{offset:08x}.wav','INTRO',0,'Abertura e apresentação'))
        audio=root/'voice.wav';audio.write_bytes(b'complete source')
        db.execute('INSERT INTO sources(key,narrator,path,transcript,topic) VALUES (?,?,?,?,?)',('source','Custom',str(audio),'Olá a todos','Abertura e apresentação'))
        db.commit();db.close()
        game=root/'game';dest=game/'Narrations'/'Custom';dest.mkdir(parents=True)
        old=b'\x48\0\0\x08old!\x45\0\0\x04';bank='audiodata/speechdata/por_br/demo.sbs'
        data,_=profiles.package_bytes({bank:{32:old,64:old}});(dest/'profile.npack').write_bytes(data)
        return catalog,game,dest,old,bank

    def test_assigned_audio_is_installed_automatically_preserving_other_game_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog,game,dest,old,bank=self.fixture(root)
            original_connect=core.connect;new=b'\x48\0\0\x08new!\x45\0\0\x04'
            with patch.object(core,'connect',lambda:original_connect(catalog)),patch.object(projects,'connect',lambda:original_connect(catalog)),patch.object(profiles,'connect',lambda:original_connect(catalog)),patch.object(projects,'GAME',game),patch.object(projects,'PROJECTS',root/'projects'),patch.object(profiles,'encoded',return_value=new):
                projects.assign_audio('Custom','changed','source')
            slots={offset:data for _,offset,data in projects.unpack(dest/'profile.npack')}
            self.assertEqual(slots,{32:new,64:old})
            db=original_connect(catalog);row=db.execute('SELECT path FROM sources WHERE key=?',('source',)).fetchone();db.close()
            self.assertTrue(Path(row['path']).is_relative_to(dest/'Studio'/'assets'))
            self.assertTrue((dest/'Studio'/'project.json').exists())

    def test_encoding_failure_keeps_installed_package_and_restores_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog,game,dest,old,bank=self.fixture(root);before=(dest/'profile.npack').read_bytes()
            original_connect=core.connect
            with patch.object(core,'connect',lambda:original_connect(catalog)),patch.object(projects,'connect',lambda:original_connect(catalog)),patch.object(profiles,'connect',lambda:original_connect(catalog)),patch.object(projects,'GAME',game),patch.object(projects,'PROJECTS',root/'projects'),patch.object(profiles,'encoded',side_effect=ValueError('Bad recording')):
                with self.assertRaises(ValueError):projects.assign_audio('Custom','changed','source')
            self.assertEqual((dest/'profile.npack').read_bytes(),before)
            db=original_connect(catalog);self.assertEqual(db.execute('SELECT count(*) FROM mappings').fetchone()[0],0);db.close()

    def test_restoring_original_removes_only_the_changed_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog,game,dest,old,bank=self.fixture(root);original_connect=core.connect
            with patch.object(projects,'connect',lambda:original_connect(catalog)),patch.object(projects,'GAME',game),patch.object(projects,'PROJECTS',root/'projects'):
                projects.apply_changes('Custom',['changed'])
            self.assertEqual({offset:data for _,offset,data in projects.unpack(dest/'profile.npack')},{64:old})

    def test_custom_style_and_unused_asset_are_restored_from_editable_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog,game,dest,old,bank=self.fixture(root);original_connect=core.connect
            db=original_connect(catalog);db.execute("UPDATE sources SET topic='Estilo personalizado',topic_manual=1 WHERE key='source'");db.commit();db.close()
            with patch.object(projects,'connect',lambda:original_connect(catalog)),patch.object(projects,'GAME',game),patch.object(projects,'PROJECTS',root/'projects'):
                saved=projects.save('Custom')
                db=original_connect(catalog);db.execute('DELETE FROM sources');db.commit();db.close()
                projects.open_project(saved)
            db=original_connect(catalog);row=db.execute('SELECT topic,topic_manual FROM sources WHERE key=?',('source',)).fetchone();db.close()
            self.assertEqual(tuple(row),('Estilo personalizado',1))

if __name__=='__main__':unittest.main()
