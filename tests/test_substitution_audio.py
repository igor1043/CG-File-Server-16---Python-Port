from dataclasses import replace
from pathlib import Path
import tempfile,unittest
from server16_py.substitution_events import Player,Snapshot,SubstitutionTracker
from server16_py.substitution_audio import AudioSession,Settings,read_settings,save_settings


def match(clock=100,page='',identity=(1,2),incoming=(),away_incoming=(),replay=False,phase=15):
    rows=[]
    for side,club,swaps in ((0,1043,incoming),(1,567,away_incoming)):
        active=set(range(1+side*100,12+side*100));bench=set(range(12+side*100,24+side*100))
        for old,new in swaps:active.discard(old);active.add(new);bench.discard(new);bench.add(old)
        rows.extend(Player(i,club,side,(i%27) if i in active else 28) for i in sorted(active|bench))
    return Snapshot(identity,clock,phase,replay,page,(1043,567),tuple(rows))


class TrackerTest(unittest.TestCase):
 def test_initial_attach_and_tactical_positions_do_not_trigger(self):
  t=SubstitutionTracker();s=match();self.assertEqual([],t.observe(s));changed=replace(s,players=tuple(replace(p,role=27-p.role) if p.role<28 else p for p in s.players))
  for _ in range(4):self.assertEqual([],t.observe(changed))
 def test_substitution_is_one_event_after_stable_samples(self):
  t=SubstitutionTracker();t.observe(match());s=match(incoming=((5,12),));self.assertEqual([],t.observe(s));events=t.observe(s);self.assertEqual(1,len(events));self.assertEqual((1043,(12,),(5,)),(events[0].club,events[0].incoming,events[0].outgoing))
  for _ in range(10):self.assertEqual([],t.observe(s))
 def test_several_players_in_one_change_are_one_event(self):
  t=SubstitutionTracker();t.observe(match());s=match(incoming=((3,12),(4,13),(5,14)));t.observe(s);self.assertEqual((12,13,14),t.observe(s)[0].incoming)
 def test_menu_preparation_and_cancelled_change_never_play(self):
  t=SubstitutionTracker();t.observe(match());pending=match(page='game/screens/career/TeamManagement',incoming=((5,12),))
  for _ in range(4):self.assertEqual([],t.observe(pending))
  for _ in range(4):self.assertEqual([],t.observe(match()))
 def test_replay_and_menu_preserve_committed_baseline(self):
  t=SubstitutionTracker();t.observe(match());s=match(incoming=((5,12),),replay=True)
  for _ in range(5):self.assertEqual([],t.observe(s))
  s=replace(s,replay=False);t.observe(s);self.assertEqual(1,len(t.observe(s)))
 def test_new_match_clock_reset_and_postgame_do_not_replay_old_changes(self):
  t=SubstitutionTracker();t.observe(match());changed=match(incoming=((5,12),));t.observe(changed);t.observe(changed)
  self.assertEqual([],t.observe(match(identity=(7,8),incoming=((5,12),))))
  self.assertEqual([],t.observe(match(clock=0,identity=(7,8))))
  self.assertEqual([],t.observe(match(page='game/screens/postGameFlow/MatchResults')))
 def test_outgoing_and_incoming_can_be_observed_in_separate_samples(self):
  t=SubstitutionTracker();t.observe(match());partial=replace(match(),players=tuple(replace(p,role=29) if p.id==5 and p.side==0 else p for p in match().players))
  t.observe(partial);self.assertEqual([],t.observe(partial));s=match(incoming=((5,12),));t.observe(s);self.assertEqual((12,),t.observe(s)[0].incoming)
 def test_both_teams_are_identified_independently(self):
  t=SubstitutionTracker();t.observe(match());s=match(incoming=((5,12),),away_incoming=((105,112),));t.observe(s);self.assertEqual([1043,567],[e.club for e in t.observe(s)])
 def test_actual_native_substitution_phase_zero_survives_stadium_pan_label(self):
  t=SubstitutionTracker();t.observe(match());s=replace(match(phase=0,page='game/screens/misc/StadiumPan',incoming=((5,12),)),presentation='package_sub_oop')
  self.assertTrue(s.playable);t.observe(s);self.assertEqual((12,),t.observe(s)[0].incoming)
 def test_live_phase_with_stale_stadium_pan_label_can_commit(self):
  t=SubstitutionTracker();t.observe(match());s=match(page='game/screens/misc/StadiumPan',incoming=((5,12),));t.observe(s);self.assertEqual(1,len(t.observe(s)))
 def test_real_team_management_overrides_stale_substitution_graph(self):
  t=SubstitutionTracker();t.observe(match());s=replace(match(phase=0,page='game/screens/teammanagement/TeamManagement',incoming=((5,12),)),presentation='package_sub_oop')
  self.assertFalse(s.playable)
  for _ in range(4):self.assertEqual([],t.observe(s))
 def test_unknown_phase_waits_without_losing_roster_baseline(self):
  t=SubstitutionTracker();t.observe(match());s=match(phase=0,incoming=((5,12),))
  for _ in range(4):self.assertEqual([],t.observe(s))
  s=replace(s,phase=15);t.observe(s);self.assertEqual(1,len(t.observe(s)))
 def test_replayed_substitution_does_not_emit(self):
  t=SubstitutionTracker();t.observe(match());s=replace(match(phase=0,replay=True,incoming=((5,12),)),presentation='package_sub_oop')
  for _ in range(4):self.assertEqual([],t.observe(s))


class PlayerMock:
 def __init__(self):self.calls=[];self.state='stopped'
 def open(self,path):self.calls.append(('open',Path(path).name))
 def set_volume(self,v):self.calls.append(('volume',v))
 def play(self):self.calls.append(('play',));self.state='playing'
 def pause(self):self.calls.append(('pause',));self.state='paused'
 def resume(self):self.calls.append(('resume',));self.state='playing'
 def stop(self):self.calls.append(('stop',));self.state='stopped'
 def close(self):self.calls.append(('close',));self.state='closed'
 def mode(self):return self.state


class AudioTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.game=Path(self.tmp.name);folder=self.game/'FSW/Substitutions';folder.mkdir(parents=True);(folder/'1043.mp3').write_bytes(b'fixture');self.players=[]
  def factory():p=PlayerMock();self.players.append(p);return p
  self.audio=AudioSession(self.game,factory);self.audio.observe(match(),0)
 def tearDown(self):self.audio.close();self.tmp.cleanup()
 def sub(self,at=1,incoming=((5,12),),**kwargs):
  s=match(incoming=incoming,**kwargs);self.audio.observe(s,at);self.audio.observe(s,at+.1);return s
 def test_track_by_club_plays_once_and_further_players_do_not_stack(self):
  s=self.sub();self.assertEqual(1,len(self.players));self.assertIn(('open','1043.mp3'),self.players[0].calls)
  self.sub(2,((5,12),(4,13)));self.assertEqual(1,len(self.players));self.assertEqual(1,self.players[0].calls.count(('play',)))
 def test_missing_opponent_track_does_not_play_the_home_track(self):
  self.sub(away_incoming=((105,112),),incoming=());self.assertEqual([],self.players)
 def test_away_track_is_never_played_even_when_installed(self):
  (self.game/'FSW/Substitutions/567.mp3').write_bytes(b'visitor fixture')
  self.sub(away_incoming=((105,112),),incoming=());self.assertEqual([],self.players)
 def test_flamengo_as_visitor_does_not_use_its_installed_track(self):
  def reversed_teams(s):return replace(s,clubs=(567,1043),players=tuple(replace(p,club=(567,1043)[p.side]) for p in s.players))
  self.audio.reset('fixture');self.audio.observe(reversed_teams(match()),0)
  s=reversed_teams(match(away_incoming=((105,112),)));self.audio.observe(s,1);self.audio.observe(s,1.1)
  self.assertEqual([],self.players)
 def test_pause_preserves_position_and_resume_does_not_restart(self):
  s=self.sub();p=self.players[0];self.audio.observe(replace(s,page='game/screens/pause/Pause'),2);self.audio.observe(s,8)
  self.assertIn(('pause',),p.calls);self.assertIn(('resume',),p.calls);self.assertEqual(1,p.calls.count(('play',)))
 def test_timeout_exit_disabled_and_connection_loss_close_only_own_player(self):
  self.audio.settings=Settings(max_seconds=2);s=self.sub();p=self.players[0];self.audio.observe(s,4);self.assertIn(('close',),p.calls)
  self.audio.observe(None,6);self.assertIsNone(self.audio.identity)
 def test_settings_validate_volume_and_keep_original_config(self):
  p=self.game/'options.ini';p.write_text('[substitution_audio]\nenabled=false\nvolume=.2\n',encoding='utf8');self.assertEqual(Settings(False,.2),read_settings(p));raw=p.read_bytes();p.write_text('[substitution_audio]\nvolume=nan\n',encoding='utf8')
  with self.assertRaises(ValueError):read_settings(p)
 def test_native_substitution_does_not_reset_audio_baseline_or_pause_track(self):
  s=replace(match(phase=0,page='game/screens/misc/StadiumPan',incoming=((5,12),)),presentation='package_sub_oop')
  self.audio.observe(s,1);self.audio.observe(s,1.1);self.assertEqual(1,len(self.players));self.audio.observe(s,2)
  self.assertEqual('playing',self.players[0].state);self.assertNotIn(('pause',),self.players[0].calls)
 def test_transient_phase_preserves_baseline_until_live_resume(self):
  s=match(phase=0,incoming=((5,12),));self.audio.observe(s,1);self.assertEqual([],self.players)
  s=replace(s,phase=15);self.audio.observe(s,2);self.audio.observe(s,2.1);self.assertEqual(1,len(self.players))
 def test_volume_updates_during_playback_without_restarting(self):
  s=self.sub();p=self.players[0];self.audio.settings=Settings(volume=.08);self.audio.observe(s,2)
  self.assertIn(('volume',.08),p.calls);self.assertEqual(1,p.calls.count(('play',)))
  self.audio.observe(s,3);self.assertEqual(1,p.calls.count(('volume',.08)))
 def test_saved_volume_preserves_enabled_and_other_options(self):
  p=self.game/'audio.ini';p.write_text('[substitution_audio]\nenabled=false\nvolume=.35\npoll_ms=150\nmax_seconds=90\n[other]\nkey=value\n')
  self.assertEqual(Settings(False,.12,90,150),save_settings(p,volume=.12));self.assertIn('key = value',p.read_text())
  self.assertTrue(save_settings(p,enabled=True).enabled);self.assertEqual(.12,read_settings(p).volume)
 def test_invalid_volume_or_malformed_config_is_not_overwritten(self):
  p=self.game/'audio.ini';p.write_text('[substitution_audio]\nvolume=.2\n');original=p.read_bytes()
  for volume in (-1,2,float('nan'),True):
   with self.assertRaises(ValueError):save_settings(p,volume=volume)
   self.assertEqual(original,p.read_bytes())
  p.write_text('[substitution_audio]\nvolume=invalid\n');original=p.read_bytes()
  with self.assertRaises(ValueError):save_settings(p,volume=.2)
  self.assertEqual(original,p.read_bytes())

if __name__=='__main__':unittest.main()
