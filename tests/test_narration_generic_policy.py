import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
from generic_policy import blocked_reasons,candidate_allowed,intro_role,reference

class GenericPolicyTests(unittest.TestCase):
    def test_english_goal_proposals_preserve_scene_and_gender(self):
        from topics import topic
        self.assertEqual(topic('',transcript='What a goal!'),'Gols')
        self.assertEqual(topic('',transcript='That was almost a goal.'),'Ataque e chances')
        self.assertTrue(candidate_allowed(dict(event='bGOAL_SCORED_GEN'),dict(event='',transcript='What a goal!')))
        self.assertTrue(candidate_allowed(dict(event='bGOAL_SCORED_GEN'),dict(event='',transcript='Gooooool! Gol!')))
        self.assertEqual(topic('',transcript='Gol! Gol!'),'Gols')
        self.assertFalse(candidate_allowed(dict(event='bGOAL_SCORED_GEN'),dict(event='',transcript='Almost a goal!')))
        self.assertTrue(blocked_reasons(dict(event='',transcript='She scores a great goal.')))
        self.assertTrue(blocked_reasons(dict(event='',transcript='She scored a great goal.')))
        self.assertTrue(blocked_reasons(dict(event='',transcript='Ela pegou a bola e chutou.')))
        self.assertTrue(blocked_reasons(dict(event='',transcript='Ela foi titular na equipe.')))

    def test_generic_scene_proposals_keep_own_goals_and_set_pieces_distinct(self):
        source=dict(event='',transcript='Que belo gol!')
        self.assertFalse(candidate_allowed(dict(event='bOWN_GOAL'),source))
        self.assertFalse(candidate_allowed(dict(event='bOFFSIDE'),dict(event='',transcript='É escanteio.')))
        self.assertTrue(candidate_allowed(dict(event='bOFFSIDE'),dict(event='',transcript='O assistente marcou impedimento.')))
    def test_specific_matchup_is_rejected_even_before_transcription(self):
        self.assertIn('evento específico',blocked_reasons(dict(event='mINTRO_SEQ1_MATCHUP_SPECIFIC',transcript='')))

    def test_team_names_and_tv_banter_are_rejected(self):
        for text in ('Hoje temos Juventus e Torino.','Flamengo e Vasco, cinco a um.','Eu escalaria o Caio no Cartola.','Veja o filme depois do Fantástico.'):
            self.assertTrue(blocked_reasons(dict(event='',transcript=text)),text)

    def test_neutral_club_introduction_and_audience_greeting_are_allowed(self):
        for text in ('Escalação definida, está na tela para você.','Alô Brasil, vamos juntos!','Você ligado na Globo, entra no clima do jogão!','As duas equipes têm qualidade para fazer um bom jogo.'):
            self.assertFalse(blocked_reasons(dict(event='',transcript=text)),text)

    def test_opening_cannot_take_an_in_match_goal_comment(self):
        original=dict(event='bINTROSEQ3_CNOTES_INTRO')
        source=dict(event='',transcript='Primeiro gol foi de bola parada.')
        self.assertFalse(candidate_allowed(original,source))

    def test_miss_is_not_used_for_a_scored_goal(self):
        original=dict(event='bGOAL_SCORED_GEN')
        self.assertFalse(candidate_allowed(original,dict(event='',transcript='Se entra é o chamado golaço!')))
        self.assertTrue(candidate_allowed(original,dict(event='',transcript='Ele precisa de uma bola e ela foi para o fundo da rede.')))

    def test_intro_roles_preserve_raw_names_weather_and_referee(self):
        self.assertEqual(intro_role('tTS_TEAM_INTRO'),'lineup')
        self.assertEqual(intro_role('mINTROSEQ2_MATCHUP'),'expectation')
        self.assertEqual(intro_role('bINTRO_HELLO_SHORT'),'welcome')
        for event in ('tINTRO_CLUB_NAME','bINTROSEQ4_WEATHER_RAIN','rINTROSEQ4_REF'):
            self.assertIsNone(intro_role(event))
        self.assertIn('escalação',reference('tTS_TEAM_INTRO'))

if __name__=='__main__':unittest.main()
