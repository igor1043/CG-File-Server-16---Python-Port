import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import core,transcription_worker

class LibraryTests(unittest.TestCase):
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
