import json
import os
import sys
import tempfile
import unittest
import wave
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import core
import editor_catalog
import projects
from audio_playback import MciAudio,prepare_preview
from topics import topic


class EditorTests(unittest.TestCase):
    def test_existing_catalog_opens_for_reading_while_another_writer_is_busy(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'catalog.sqlite'
            initializer=core.connect(path);initializer.close()
            writer=core.connect(path);writer.execute('BEGIN IMMEDIATE')
            writer.execute("INSERT INTO sources(key,narrator,path,topic) VALUES ('busy','Voice','voice.wav','Outros comentários')")
            started=time.monotonic()
            try:
                reader=core.connect(path)
                self.assertEqual(reader.execute('SELECT count(*) FROM sources').fetchone()[0],0)
                reader.close()
                self.assertLess(time.monotonic()-started,1)
            finally:writer.rollback();writer.close()

    def fixture(self,root):
        path=Path(root)/'catalog.sqlite'
        db=core.connect(path)
        for i,event in enumerate(('bINTRO_HELLO_SHORT','pPLAYER_NAMES','tLB_FOCUS_TEAM','sINTROSEQ1_STADIUM')):
            db.execute('INSERT INTO clips (key,bank,event,row,wav,status,transcript,topic) VALUES (?,?,?,?,?,?,?,?)',
                       (str(i),'bank',event,i,'original.wav','decoded','original '+str(i),topic(event)))
        db.execute("INSERT INTO sources(key,narrator,path,transcript,topic) VALUES ('source','Custom','custom.mp3','minha apresentação','Abertura e apresentação')")
        db.execute("INSERT INTO mappings VALUES ('Custom','0','source','manual',1)")
        db.commit(); db.close()
        return lambda:core.connect(path)

    def test_paired_page_keeps_unmapped_rows_and_searches_both_transcripts(self):
        with tempfile.TemporaryDirectory() as root,patch.object(editor_catalog,'connect',self.fixture(root)):
            rows,total=editor_catalog.paired_page('Custom',converted={})
            self.assertEqual(total,4)
            self.assertEqual(sum(r['conversion']=='Sem áudio próprio' for r in rows),3)
            rows,total=editor_catalog.paired_page('Custom',query='MINHA APRESENTACAO',converted={})
            self.assertEqual(total,1); self.assertEqual(rows[0]['key'],'0')
            rows,total=editor_catalog.paired_page('Custom',state='Sem áudio próprio',converted={})
            self.assertEqual(total,3); self.assertTrue(all(r['source_key'] is None for r in rows))
            rows,total=editor_catalog.paired_page('Custom',state='Já convertidos',converted={'0':'custom.mp3'})
            self.assertEqual(total,1)
            rows,total=editor_catalog.paired_page('Custom',state='Ainda não convertidos',converted={'0':'custom.mp3'})
            self.assertEqual(total,3)
            rows,total=editor_catalog.paired_page('Custom',state='Com áudio, a converter',converted={})
            self.assertEqual(total,1)
            rows,total=editor_catalog.paired_page('Custom',state='Revisados/aprovados',converted={})
            self.assertEqual(total,0)
            db=core.connect(Path(root)/'catalog.sqlite')
            db.execute("INSERT INTO narration_reviews(profile,clip,reviewed) VALUES ('Custom','0',1)");db.commit();db.close()
            rows,total=editor_catalog.paired_page('Custom',state='Revisados/aprovados',converted={})
            self.assertEqual(total,1);self.assertTrue(rows[0]['reviewed'])
            coverage=editor_catalog.coverage('Custom',{})
            self.assertEqual((coverage['reviewed'],coverage['pending_review']),(1,0))

    def test_column_searches_filter_original_and_custom_text_independently(self):
        with tempfile.TemporaryDirectory() as root,patch.object(editor_catalog,'connect',self.fixture(root)):
            rows,total=editor_catalog.paired_page('Custom',original_query='ORIGINAL 1',converted={})
            self.assertEqual(total,1);self.assertEqual(rows[0]['key'],'1')
            rows,total=editor_catalog.paired_page('Custom',source_query='MINHA APRESENTACAO',converted={})
            self.assertEqual(total,1);self.assertEqual(rows[0]['key'],'0')
            rows,total=editor_catalog.paired_page('Custom',original_query='original 0',source_query='minha apresentação',converted={})
            self.assertEqual(total,1);self.assertEqual(rows[0]['key'],'0')
            rows,total=editor_catalog.paired_page('Custom',original_query='original 1',source_query='minha apresentação',converted={})
            self.assertEqual(total,0)

    def test_conversion_counts_distinguish_missing_and_unconverted(self):
        with tempfile.TemporaryDirectory() as root,patch.object(editor_catalog,'connect',self.fixture(root)):
            counts=editor_catalog.coverage('Custom',{'0':'custom.mp3'})
            self.assertEqual((counts['linked'],counts['converted'],counts['missing'],counts['pending']),(1,1,3,3))
            self.assertEqual(counts['pending_review'],1)
            original=editor_catalog.coverage('Tiago Leifert',{})
            self.assertEqual((original['linked'],original['pending']),(4,0))

    def test_source_usage_counts_include_assignments_outside_the_current_filter(self):
        with tempfile.TemporaryDirectory() as root,patch.object(editor_catalog,'connect',self.fixture(root)):
            db=core.connect(Path(root)/'catalog.sqlite')
            db.execute("INSERT INTO mappings VALUES ('Custom','1','source','manual',1)")
            db.execute("INSERT INTO mappings VALUES ('Other','2','source','manual',1)")
            db.commit();db.close()
            rows,total=editor_catalog.paired_page('Custom',category='Abertura e apresentação',converted={})
            self.assertEqual(total,1)
            self.assertEqual(rows[0]['source_uses'],2)

    def test_edited_source_is_no_longer_counted_as_converted(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); source=root/'voice.wav'; source.write_bytes(b'old')
            build=root/'Custom/build'; build.mkdir(parents=True)
            (build/'profile.npack').write_bytes(b'package')
            (build/'build_report.json').write_text(json.dumps([dict(clip='clip',source=str(source),source_signature=editor_catalog.source_signature(source))]),encoding='utf8')
            with patch.object(editor_catalog,'PROJECTS',root),patch.object(editor_catalog,'GAME',root/'game'):
                self.assertIn('clip',editor_catalog.converted_keys('Custom'))
                source.write_bytes(b'new longer recording')
                self.assertNotIn('clip',editor_catalog.converted_keys('Custom'))

    def test_conversion_report_uses_relocated_catalog_source_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'new library'/'voice.wav';source.parent.mkdir();source.write_bytes(b'converted voice')
            catalog=root/'catalog.sqlite';db=core.connect(catalog)
            db.execute("INSERT INTO sources(key,narrator,path,transcript,topic) VALUES (?,?,?,?,?)",('source','Custom',str(source),'voice','Outros comentários'))
            db.execute("INSERT INTO mappings VALUES ('Custom','clip','source','manual',1)");db.commit();db.close()
            game=root/'game';profile=game/'Narrations'/'Custom';profile.mkdir(parents=True)
            (profile/'profile.npack').write_bytes(b'package')
            signature=editor_catalog.source_signature(source)
            (profile/'build_report.json').write_text(json.dumps([dict(clip='clip',source=r'C:\old\library\voice.wav',source_signature=signature)]),encoding='utf8')
            original_connect=editor_catalog.connect
            with patch.object(editor_catalog,'connect',lambda:original_connect(catalog)),patch.object(editor_catalog,'PROJECTS',root/'projects'),patch.object(editor_catalog,'GAME',game):
                self.assertEqual(editor_catalog.converted_keys('Custom'),{'clip':str(source)})

    def test_install_copies_only_runtime_assets_into_game_narrations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);build=root/'project'/'build';build.mkdir(parents=True)
            for filename in ('profile.npack','profile.json','narrator.txt','portrait.png','project.json','build_report.json'):
                (build/filename).write_text(filename,encoding='utf8')
            (build/'transcriptions').mkdir()
            installed=projects.install_profile(build,'Vilani',root/'game')
            self.assertEqual(installed,root/'game'/'Narrations'/'Vilani')
            self.assertEqual({item.name for item in installed.iterdir()},
                             {'profile.npack','profile.json','narrator.txt','portrait.png'})

    def test_named_competitions_venues_and_club_comments_are_separate(self):
        expected={'pPLAYER_NAMES':'Call names de jogadores','tLB_FOCUS_TEAM':'Nomes de clubes',
                  'tBANTER_TEAM_FOCUS_NON_PICKUP':'Comentários de clubes','cINTROSEQ1_CUP_FINAL':'Campeonatos e competições',
                  'lINTROSEQ1_LEAGUE':'Campeonatos e competições','sINTROSEQ1_STADIUM':'Estádios e cidades'}
        for event,label in expected.items(): self.assertEqual(topic(event),label)

    @unittest.skipUnless(os.name=='nt','WinMM requires Windows')
    def test_native_preview_handles_long_unicode_paths(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'narrações e comentários'/'subpasta de apresentação';directory.mkdir(parents=True)
            path=directory/'bINTRO_SEQ1_WEATHER_STITCH_17_17.wav'
            with wave.open(str(path),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(44100);audio.writeframes(b'\0\0'*44100)
            player=MciAudio()
            try:player.load(path);self.assertEqual(player.length,1000)
            finally:player.close()

    @unittest.skipUnless(os.name=='nt','WinMM requires Windows')
    def test_native_preview_reports_actual_length_and_seek_without_playing(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'silent.wav'
            with wave.open(str(path),'wb') as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(44100); audio.writeframes(b'\0\0'*44100)
            player=MciAudio()
            try:
                player.load(path)
                self.assertEqual(player.length,1000)
                player.seek(375)
                self.assertLessEqual(abs(player.position-375),1)
                self.assertNotEqual(player.mode,'playing')
                self.assertEqual(prepare_preview(path,Path(root)/'cache','unused-ffmpeg'),path)
            finally: player.close()

    def test_seek_retains_paused_state_and_resumes_playing_state(self):
        commands=[]
        def send(command):
            commands.append(command)
            if command.endswith(' mode'): return mode
            if command.endswith(' position'): return '820'
            return ''
        player=MciAudio(send=send); player.opened=True; player.length=1200
        mode='paused'; player.seek(250)
        self.assertFalse(any(c.startswith('play ') for c in commands))
        commands.clear(); mode='playing'; player.seek(400)
        self.assertEqual(commands[-1],f'play {player.alias} from 400')
        commands.clear(); player.seek(10000)
        self.assertIn(f'seek {player.alias} to 1200',commands)
        self.assertFalse(any(c.startswith('play ') for c in commands))


if __name__=='__main__': unittest.main()
