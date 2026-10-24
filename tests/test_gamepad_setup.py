import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import ImageFont
from server16_py.gamepad_mapping import MappingCapture, mapped_state, STEPS
from server16_py.gamepad_panel import GamepadPanel
from server16_py.settings_store import SettingsStore


def sample(button=False, x=0., trigger=-1.):
    return {'buttons':[button,False], 'axes':[x,0.,0.,0.,trigger,-1.], 'hats':[(0,0)]}


class MappingTests(unittest.TestCase):
    def test_capture_requires_release_between_steps(self):
        c=MappingCapture();c.observe(sample());c.observe(sample())
        self.assertTrue(c.observe(sample(True)));self.assertEqual(c.index,1)
        self.assertFalse(c.observe(sample(True)));self.assertEqual(c.index,1)
        c.observe(sample());self.assertTrue(c.observe(sample(True)));self.assertEqual(c.index,2)

    def test_inverted_axis_trigger_rest_deadzone_and_disconnect(self):
        m={'deadzone':.12,'bindings':{'LX':{'kind':'axis','index':0,'center':0.,'extent':-1.},
            'LT':{'kind':'axis','index':4,'center':-1.,'extent':1.},'A':{'kind':'button','index':0}}}
        idle=mapped_state(sample(x=.04),m);self.assertEqual(idle['left_stick'],(0.,0.));self.assertEqual(idle['left_trigger'],0.)
        active=mapped_state(sample(True,-1.,1.),m);self.assertEqual(active['left_stick'][0],1.)
        self.assertEqual(active['left_trigger'],1.);self.assertTrue(active['buttons']['XUSB_GAMEPAD_A'])
        disconnected=mapped_state({},m);self.assertEqual(disconnected['left_stick'],(0.,0.));self.assertFalse(any(disconnected['buttons'].values()))

    def test_hat_mapping_and_per_device_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            store=SettingsStore(Path(d)/'settings.json')
            mapping={'bindings':{'DPAD_UP':{'kind':'hat','index':0,'component':1,'sign':1}}}
            store.data['gamepad_mappings']={'pad-one':mapping,'pad-two':{'bindings':{}}};store.save()
            reloaded=SettingsStore(store.path)
            state=mapped_state({'hats':[(0,1)]},reloaded.data['gamepad_mappings']['pad-one'])
            self.assertTrue(state['buttons']['XUSB_GAMEPAD_DPAD_UP'])
            self.assertFalse(any(mapped_state({'hats':[(0,1)]},reloaded.data['gamepad_mappings']['pad-two'])['buttons'].values()))


class FakeBridge:
    def __init__(self):
        self.slots=[dict(enabled=False,device_guid='pad-guid',profile='auto',status='disconnected',hide_from_fifa=False) for _ in range(4)]
        self.devices=[SimpleNamespace(name='Controle USB genérico',guid='pad-guid')]
        self.set_mapping=Mock();self.set_slot_config=Mock();self.install_vigembus=Mock()
    def get_slot_snapshot(self,i):return dict(self.slots[i])
    def list_devices(self):return self.devices
    def read_raw_state(self,*args):return sample()
    def dependencies_available(self):return False
    def resolve_profile(self,*args):return 'generic'


class PanelTests(unittest.TestCase):
    def panel(self):
        bridge=FakeBridge();app=SimpleNamespace(gamepad_bridge=bridge,settings=SimpleNamespace(data={}),hidhide=Mock())
        selector=SimpleNamespace(app=app,font=lambda n,b=False:ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf' if b else 'C:/Windows/Fonts/segoeui.ttf',n*2),render=Mock(),close=Mock(),controller_connected=False)
        return GamepadPanel(selector),selector,bridge

    def test_missing_driver_keeps_bridge_disabled_and_preserves_native_input(self):
        p,s,b=self.panel();p.activate(2);b.set_slot_config.assert_not_called()
        self.assertIn('driver',p.message);s.close.assert_not_called()

    def test_mapping_cancel_never_changes_persisted_profile(self):
        p,s,b=self.panel();p.activate(1);p.handle(7,0)
        self.assertEqual(p.page,'capture') # A physical B is being learned.
        p.activate(9);self.assertEqual(p.page,'home');b.set_mapping.assert_not_called()

    def test_keyboard_tabs_and_device_selection_are_independent_of_slot(self):
        p,s,b=self.panel();p.handle(3,0);self.assertEqual(p.slot,1)
        p.activate(0);p.activate(200)
        b.set_slot_config.assert_called_once_with(1,enabled=False,device_guid='pad-guid',profile='auto',hide_from_fifa=False)

    def test_setup_pages_render_without_overlapping_action_rectangles(self):
        p,s,b=self.panel()
        for mode in ('home','devices','capture'):
            p.page=mode;p.devices=b.devices;p.capture=MappingCapture()
            image=p.render();self.assertEqual(image.size,(1800,1300))
            rects=[r for _,r in p.targets()]
            for i,a in enumerate(rects):
                self.assertTrue(0<=a[0]<a[2]<=900 and 0<=a[1]<a[3]<=610)
                for z in rects[i+1:]:self.assertFalse(max(a[0],z[0])<min(a[2],z[2]) and max(a[1],z[1])<min(a[3],z[3]))

if __name__=='__main__':unittest.main()
