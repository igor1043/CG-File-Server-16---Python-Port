"""Rendered bounds and input regression tests for the Server16 panels."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from server16_py.overlay_canvas import OverlayDraw, fit_text
from server16_py.input_hints import footer_y
from server16_py.career_panel import CareerPanel
from server16_py.frontend_stadium_panel import FrontendStadiumPanel
from server16_py.match_settings_panel import MatchSettingsPanel
from server16_py.smoke_settings_panel import SmokeSettingsPanel
from server16_py.match_audio_panel import MatchAudioPanel
from server16_py.match_hub_panel import MatchHubPanel
from server16_py.extra_scenes_panel import ExtraScenesPanel
from server16_py.narration_panel import NarrationPanel
from server16_py.prematch_panel import PrematchPanel
from server16_py.settings_store import SettingsStore
import test_career_overlay as career_fixtures


def render_text(panel):
    records=[]
    original=OverlayDraw.text
    def capture(draw, xy, value, max_width=None, **kwargs):
        font=kwargs.get('font')
        visible=fit_text(draw,value,font,max_width) if max_width is not None else str(value)
        box=draw.draw.textbbox(tuple(v*2 for v in xy),visible,font=font,anchor=kwargs.get('anchor'))
        records.append((str(value),visible,tuple(v/2 for v in box)))
        return original(draw,xy,value,max_width=max_width,**kwargs)
    with patch.object(OverlayDraw,'text',capture):image=panel.render()
    return image,records


def panel_states(selector):
    """Real renderers, isolated fixture data; never launch or read FIFA."""
    selector.app.settings=SettingsStore(selector.app.base_dir/'settings.json')
    selector.app.chants_runtime=Mock()
    selector.app._crowd_master_volume=selector.app._goal_master_volume=1.
    career=CareerPanel(selector,selector.career_service)
    for page in ('home','clubs','finances','funds','retirement','confirm','status'):
        career.page=page;career.focus=len(career.items())-1
        career.confirmation={'action':'funds','amount':1000,'label':'1.000','return':'funds'}
        career.message='Mensagem de teste: '+('um aviso longo para conferir os limites da tela. '*4)
        yield 'career-'+page,career
    selector.career_service.selected=None
    career.page='home'
    yield 'career-loading',career
    selector.career_service.state='waiting_save'
    yield 'career-save',career
    selector.career_service.state='error'
    yield 'career-error',career
    for career_mode in (False,True):
        selector._frontend_career=career_mode
        for enabled in (False,True):
            panel=FrontendStadiumPanel(selector);panel.enabled=enabled
            panel.message='Escolha salva.'
            yield f'frontend-{career_mode}-{enabled}',panel
    for crowd in (False,True):
        yield f'prematch-{crowd}',PrematchPanel(selector,crowd=crowd)
    settings=MatchSettingsPanel(selector)
    yield 'presentation',settings
    for goal in (False,True):
        smoke=SmokeSettingsPanel(settings);smoke.goal=goal;smoke.focus=28
        yield f'smoke-{goal}',smoke
    for cloth in (False,True):
        audio=MatchAudioPanel(selector,include_cloth=cloth)
        audio.message='Uma mensagem bastante longa '+('W'*160)
        yield f'audio-{cloth}',audio
    hub=MatchHubPanel(selector)
    for page in ('home','graphics','camera'):
        hub.page=page
        yield 'match-'+page,hub
    extra=ExtraScenesPanel(hub,prematch=True)
    yield 'extra-scenes-hidden',extra
    options=[dict(name='W'*80,commentator='W'*100)]
    runtime=SimpleNamespace(current=options[0]['name'],profiles=lambda:options)
    with patch('server16_py.narration_panel.narration_runtime',return_value=runtime):
        yield 'narration-hidden',NarrationPanel(selector)


class OverlayLayoutTests(unittest.TestCase):
    def test_career_information_and_messages_clear_all_buttons_and_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=career_fixtures.CareerOverlayTests().make_ready(Path(tmp))
            try:
                panel=CareerPanel(selector,selector.career_service)
                panel.focus=4
                _,texts=render_text(panel)
                info=next(box for original,_,box in texts if original.startswith('Carreira em execução:'))
                self.assertGreater(info[1],max(r[3] for _,r in panel.targets())+5)
                for page in ('home','clubs','funds','retirement','confirm','status'):
                    panel.page=page;panel.message='Aviso importante: '+('salve sua carreira antes de continuar. '*6)
                    _,texts=render_text(panel)
                    messages=[box for original,_,box in texts if original.startswith(('Aviso importante:','continuar.','carreira antes','de continuar','salve sua'))]
                    self.assertTrue(messages,page)
                    for box in messages:
                        self.assertGreater(box[1],max(r[3] for _,r in panel.targets())+5,page)
                        self.assertLess(box[3],footer_y(panel.HEIGHT)-5,page)
            finally:selector.shutdown()

    def test_all_panels_keep_rendered_text_inside_the_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=career_fixtures.CareerOverlayTests().make_ready(Path(tmp))
            try:
                for controller in (False,True):
                    selector.controller_connected=controller
                    for name,panel in panel_states(selector):
                        with self.subTest(panel=name,controller=controller):
                            image,texts=render_text(panel)
                            width,height=(600,panel._layout_height) if isinstance(panel,FrontendStadiumPanel) else (image.width/2,image.height/2)
                            for original,visible,box in texts:
                                self.assertGreaterEqual(box[0],0,(name,visible))
                                self.assertLessEqual(box[2],width,(name,visible))
                                self.assertGreaterEqual(box[1],0,(name,visible))
                                self.assertLessEqual(box[3],height,(name,visible))
                            if isinstance(panel,SmokeSettingsPanel):
                                self.assertLess(dict(panel.targets())[28][3]+5,footer_y(panel.HEIGHT)-5)
                    # Recreate a complete career after exercising loading/error states.
                    selector.career_service.selected=selector.career_service.saves[0]
                    selector.career_service.state='ready'
            finally:selector.shutdown()

    def test_keyboard_physical_rows_and_mouse_controller_typing_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=career_fixtures.CareerOverlayTests().make_ready(Path(tmp))
            try:
                selector.opened=True;selector.action('search')
                rectangles={selector.KEYS[i]:r for i,r in selector.keyboard_targets()}
                for letters in ('1234567890','QWERTYUIOP','ASDFGHJKL','ZXCVBNM'):
                    self.assertEqual(len({rectangles[k][1] for k in letters}),1)
                    self.assertEqual(sorted(letters,key=lambda k:rectangles[k][0]),list(letters))
                self.assertLess(rectangles['Q'][0],rectangles['A'][0])
                self.assertLess(rectangles['A'][0],rectangles['Z'][0])
                for source,direction,destination in (('Q',5,'A'),('A',4,'Q'),('A',5,'Z'),('F',4,'R'),('F',5,'V'),('9',5,'O')):
                    selector.key_index=selector.KEYS.index(source);selector.handle(direction,0)
                    self.assertEqual(selector.KEYS[selector.key_index],destination)
                selector.draft=''
                for key in 'QAZ9':
                    r=rectangles[key];position=(((r[1]+r[3])//2)<<16)|((r[0]+r[2])//2)
                    selector.handle(15,position)
                    self.assertEqual(selector.KEYS[selector.key_index],key)
                    selector.handle(6,0)
                self.assertEqual(selector.draft,'QAZ9')
                selector.handle(9,0)
                self.assertEqual(selector.draft,'QAZ9')
                r=rectangles['Buscar'];selector.handle(8,(((r[1]+r[3])//2)<<16)|((r[0]+r[2])//2))
                self.assertEqual(selector.query,'QAZ9');self.assertFalse(selector.keyboard)
            finally:selector.shutdown()

    def test_fit_uses_actual_glyph_width_and_handles_tiny_columns(self):
        draw=OverlayDraw(Image.new('RGBA',(400,100)))
        from server16_py.stadium_selector import StadiumSelector
        font=StadiumSelector.font(17)
        for text in ('W'*100,'i'*100,'Anápolis · São Paulo'):
            visible=fit_text(draw,text,font,100)
            self.assertLessEqual(draw.textlength(visible,font=font),100)
        self.assertEqual(fit_text(draw,'Too wide',font,1),'')


if __name__=='__main__':unittest.main()
