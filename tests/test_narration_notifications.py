import ctypes,unittest
from types import SimpleNamespace
from server16_py.d3d_injector import D3DOverlayInjector,_OverlayShared
from server16_py.stadium_runtime import StadiumRuntime,StadiumCopyCancelled
from unittest.mock import Mock,patch

class NotificationTests(unittest.TestCase):
    def test_narrator_updates_and_hiding_do_not_touch_stadium_or_movie(self):
        inj=D3DOverlayInjector.__new__(D3DOverlayInjector);inj._ready=True;inj._shared=_OverlayShared()
        inj._shared.visible=1;inj._shared.progress_x100=4500;inj._shared.stadium_name='Estádio';inj._shared.movie_visible=1
        inj.show_asset('narration','Vilani','Carregando',5,image_path='portrait.png')
        self.assertEqual(inj._shared.narration_image_path,'portrait.png')
        inj.update_asset('narration',100,'Aplicada');inj.hide_asset('narration')
        self.assertEqual(inj._shared.stadium_name,'Estádio');self.assertEqual(inj._shared.progress_x100,4500)
        self.assertEqual(inj._shared.visible,1);self.assertEqual(inj._shared.movie_visible,1)
        inj.show_asset('narration','Novo narrador')
        self.assertEqual(inj._shared.narration_image_path,'')
    def test_changing_stadium_cancels_staging_then_restarts_new_selection(self):
        app=SimpleNamespace(_kickoff_generation=1,HID='1',AID='2',TOURNAME='',TOURROUNDID='',_stadium_task_running=True,_show_stadium_loading_modal=Mock(),_stadium_task_request_key=None)
        runtime=StadiumRuntime(app);context=(1,'1','2','','')
        with patch.object(runtime,'_resolve_stadium_source'):
            runtime.apply_manual_stadium('Novo',context)
        self.assertEqual(runtime._replacement,('Novo',context))
        with self.assertRaises(StadiumCopyCancelled):runtime._validate_copy_context(context[:3],'manual','176')
        with patch.object(runtime,'apply_manual_stadium') as restart:runtime.restart_replacement();restart.assert_called_once_with('Novo',context)
        self.assertFalse(runtime._cancel_copy.is_set())

if __name__=='__main__':unittest.main()
