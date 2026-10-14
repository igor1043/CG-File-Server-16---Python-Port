import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import core,transcription_worker,pes_extract_library

class LibraryTests(unittest.TestCase):
    def test_publish_copies_recording_when_ntfs_link_limit_is_reached(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);raw=root/'raw';work=root/'repo/tools/narration_studio';work.mkdir(parents=True)
            index=root/'narrações fifa/Custom/indexes/pes_references.json';index.parent.mkdir(parents=True)
            source=root/'recording.flac';source.write_bytes(b'complete recording')
            index.write_text(json.dumps([dict(sha256='token',narrator='Custom',bank='MAIN',id=1,index=2)]),encoding='utf8')
            db=pes_extract_library.open_index(raw)
            db.execute('INSERT INTO assets(sha,path,status,transcript) VALUES (?,?,?,?)',('token',str(source),'decoded','Uma grande defesa.'));db.commit()
            limit=OSError('NTFS link limit');limit.winerror=1142
            with patch.object(pes_extract_library,'WORK',work),patch.object(pes_extract_library.os,'link',side_effect=limit):
                pes_extract_library.publish(raw,db)
            audio=raw/'Custom/original/MAIN/1_2.flac'
            self.assertEqual(audio.read_bytes(),source.read_bytes())
            self.assertEqual(audio.with_suffix('.txt').read_text(encoding='utf8'),'Uma grande defesa.')
            self.assertFalse(audio.with_suffix('.copying').exists())
            self.assertEqual(json.loads((raw/'Custom/index.json').read_text())[0]['audio'],str(audio));db.close()

    def test_attach_folder_reuses_sidecar_transcripts_and_preserves_edited_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);audio=root/'fala.mp3';audio.write_bytes(b'fixture')
            audio.with_suffix('.mp3.txt').write_text('Uma grande defesa.',encoding='utf8')
            catalog=root/'catalog.sqlite';original_connect=core.connect
            with patch.object(core,'connect',lambda:original_connect(catalog)):
                core.import_sources('Custom',root)
                db=original_connect(catalog);row=db.execute('SELECT * FROM sources').fetchone()
                self.assertEqual(row['transcript'],'Uma grande defesa.')
                self.assertEqual(row['topic'],'Defesa e goleiro')
                db.execute('UPDATE sources SET transcript=?',('Edição manual',));db.commit();db.close()
                core.import_sources('Custom',root)
            db=original_connect(catalog)
            self.assertEqual(db.execute('SELECT transcript FROM sources').fetchone()[0],'Edição manual');db.close()

    def test_managed_audio_collection_copies_nested_files_and_transcripts_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'download'/'Villani pack';nested=source/'por_br'/'abertura';nested.mkdir(parents=True)
            audio=nested/'inicio.mp3';audio.write_bytes(b'voice data')
            audio.with_suffix('.mp3.txt').write_text('Começa a partida.',encoding='utf8')
            (nested/'leia-me.md').write_text('not audio',encoding='utf8')
            managed=root/'shared'/'Vilani'
            target,count=core.copy_audio_collection(source,managed)
            self.assertEqual(count,1)
            copied=target/'por_br'/'abertura'/'inicio.mp3'
            self.assertEqual(copied.read_bytes(),audio.read_bytes())
            self.assertEqual(Path(str(copied)+'.txt').read_text(encoding='utf8'),'Começa a partida.')
            repeated,count=core.copy_audio_collection(source,managed)
            self.assertEqual((repeated,count),(target,1))
            self.assertEqual(len(list(managed.iterdir())),1)

    def test_removing_managed_asset_clears_mappings_and_deletes_only_its_sidecars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);managed=root/'assets'/'Custom';managed.mkdir(parents=True)
            audio=managed/'fala.wav';audio.write_bytes(b'audio');audio.with_suffix('.wav.txt').write_text('Transcrição')
            catalog=root/'catalog.sqlite';original_connect=core.connect
            with patch.object(core,'connect',lambda:original_connect(catalog)):
                db=original_connect(catalog)
                db.execute('INSERT INTO sources(key,narrator,path) VALUES (?,?,?)',('asset','Custom',str(audio)))
                db.execute('INSERT INTO mappings VALUES (?,?,?,?,?)',('Custom','clip','asset','manual',1))
                db.commit();db.close()
                result=core.remove_source_asset('Custom','asset',managed)
                self.assertTrue(result['deleted_file']);self.assertFalse(result['delete_error'])
                self.assertEqual(result['profiles'],['Custom'])
                self.assertFalse(audio.exists());self.assertFalse(audio.with_suffix('.wav.txt').exists())
                db=original_connect(catalog)
                self.assertEqual(db.execute('SELECT count(*) FROM sources').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT count(*) FROM mappings').fetchone()[0],0);db.close()

    def test_removing_external_asset_keeps_original_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);audio=root/'originals'/'fala.mp3';audio.parent.mkdir();audio.write_bytes(b'original')
            catalog=root/'catalog.sqlite';original_connect=core.connect
            with patch.object(core,'connect',lambda:original_connect(catalog)):
                db=original_connect(catalog);db.execute('INSERT INTO sources(key,narrator,path) VALUES (?,?,?)',('asset','Custom',str(audio)));db.commit();db.close()
                result=core.remove_source_asset('Custom','asset',root/'managed'/'Custom')
                self.assertFalse(result['deleted_file']);self.assertTrue(audio.exists())

    def test_existing_transcripts_export_beside_audio_without_loading_ai(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);audio=root/'recordings'/'fala.mp3';audio.parent.mkdir();audio.write_bytes(b'unchanged')
            catalog=root/'catalog.sqlite';db=core.connect(catalog)
            db.execute('INSERT INTO sources(key,narrator,path,transcript,topic) VALUES (?,?,?,?,?)',('source','Custom',str(audio),'Uma boa partida.','Outros comentários'));db.commit();db.close()
            project=root/'projects'/'Custom';project.mkdir(parents=True)
            (project/'library_folders.json').write_text(json.dumps([str(audio.parent)]),encoding='utf8')
            with patch.object(transcription_worker,'connect',lambda:core.connect(catalog)),patch.object(transcription_worker,'WORK',root),patch.object(transcription_worker,'PROJECTS',root/'projects'),patch.object(transcription_worker,'export_text'),patch.object(transcription_worker,'whisper_model') as model:
                transcription_worker.transcribe_library('Custom');model.assert_not_called()
            self.assertEqual(audio.read_bytes(),b'unchanged')
            self.assertEqual(audio.with_suffix('.mp3.txt').read_text(encoding='utf8'),'Uma boa partida.')
            self.assertEqual(json.loads((audio.parent/'transcriptions.json').read_text(encoding='utf8'))[0]['audio'],str(audio))
            progress=json.loads((root/'library_progress_Custom.json').read_text())
            self.assertEqual((progress['state'],progress['done'],progress['total']),('complete',1,1))

    def test_nested_audio_import_and_ai_transcription_cover_all_subfolders(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'Vilani';first=root/'por_br_FULL'/'match_01';second=root/'por_br_DEMO'/'special'/'match_02'
            first.mkdir(parents=True);second.mkdir(parents=True)
            audios=[first/'abertura.wav',first/'ataque.mp3',second/'ronaldinho.flac']
            for audio in audios:audio.write_bytes(b'test audio')
            audios[0].with_suffix('.wav.txt').write_text('Boa noite, começa a partida.',encoding='utf8')
            (second/'not-audio.txt').write_text('ignorar',encoding='utf8')
            (root/'subpasta-com-extensao.mp3').mkdir()
            catalog=Path(temporary)/'catalog.sqlite';project=Path(temporary)/'projects'/'Custom';project.mkdir(parents=True)
            (project/'library_folders.json').write_text(json.dumps([str(root)]),encoding='utf8')
            original_connect=core.connect
            with patch.object(core,'connect',lambda:original_connect(catalog)):
                found=core.import_sources('Custom',root)
            self.assertEqual(found,3)

            class StubModel:
                def transcribe(self,path,**kwargs):
                    segment=SimpleNamespace(text=' Fala reconhecida em '+Path(path).stem+'.',no_speech_prob=.1,avg_logprob=-.2)
                    return iter([segment]),None

            with patch.object(transcription_worker,'connect',lambda:core.connect(catalog)),\
                 patch.object(transcription_worker,'WORK',Path(temporary)),\
                 patch.object(transcription_worker,'PROJECTS',Path(temporary)/'projects'),\
                 patch.object(transcription_worker,'export_text'),\
                 patch.object(transcription_worker,'whisper_model',return_value=StubModel()) as model:
                transcription_worker.transcribe_library('Custom')
                model.assert_called_once_with('small')

            for audio in audios:
                sidecar=audio.with_suffix(audio.suffix+'.txt')
                self.assertTrue(sidecar.is_file(),str(sidecar))
                self.assertTrue(sidecar.read_text(encoding='utf8').strip())
            self.assertEqual(audios[0].with_suffix('.wav.txt').read_text(encoding='utf8'),'Boa noite, começa a partida.')
            manifest=json.loads((root/'transcriptions.json').read_text(encoding='utf8'))
            self.assertEqual(len(manifest),3)
            self.assertEqual({Path(item['audio']).resolve() for item in manifest},{audio.resolve() for audio in audios})
            progress=json.loads((Path(temporary)/'library_progress_Custom.json').read_text())
            self.assertEqual((progress['state'],progress['done'],progress['total']),('complete',3,3))

if __name__=='__main__':unittest.main()
