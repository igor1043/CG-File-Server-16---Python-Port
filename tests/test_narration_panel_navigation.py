import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from server16_py.narration_panel import NarrationPanel

class NarrationNavigationTests(unittest.TestCase):
    def panel(self):
        panel=NarrationPanel.__new__(NarrationPanel)
        panel.options=[{'name':str(i)} for i in range(12)]
        panel.index=panel.offset=panel.focus=0
        panel.waiting=False;panel.message=''
        panel.runtime=SimpleNamespace(apply=Mock(),pending=None,error='')
        panel.selector=SimpleNamespace(context=(1,),_context=lambda:(1,),render=Mock(),show_menu=Mock(),close=Mock())
        return panel
    def test_row_applies_and_ack_returns_to_menu(self):
        p=self.panel();p.offset=3;p.activate(1)
        p.runtime.apply.assert_called_once_with('4')
        self.assertTrue(p.waiting)
        p.tick();p.selector.show_menu.assert_called_once();p.selector.close.assert_not_called()
    def test_pending_cannot_send_second_request(self):
        p=self.panel();p.activate(1);p.activate(2)
        p.runtime.apply.assert_called_once_with('1')
    def test_scroll_reaches_last_narrator(self):
        p=self.panel()
        for _ in range(9):p.handle(14,0)
        self.assertEqual(p.offset,9)
        p.activate(2);p.runtime.apply.assert_called_once_with('11')
    def test_failed_ack_keeps_error_visible(self):
        p=self.panel();p.waiting=True;p.runtime.error='Erro';p.tick()
        p.selector.show_menu.assert_not_called();self.assertEqual(p.message,'Erro')
