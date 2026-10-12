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

if __name__=='__main__':unittest.main()
