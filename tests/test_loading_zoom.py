import tkinter as tk
import unittest

from PIL import Image, ImageTk

from server16_py.app import Server16App


class LoadingZoomTests(unittest.TestCase):
    def test_original_size_fallback_keeps_progress_visible_with_image(self):
        root = tk.Tk()
        root.withdraw()
        try:
            root._window = lambda: root
            root._apply_window_icon = lambda window: None
            root.tr = lambda key: 'Carregando estádio' if key.endswith('title') else 'Preparando'
            Server16App._build_stadium_loading_modal(root)
            root._resolve_stadium_preview_path = lambda name: None
            root._load_preview_photo = lambda path, size: ImageTk.PhotoImage(Image.new('RGB', size), master=root)
            Server16App._update_stadium_loading_preview(root, 'Estádio teste')
            root.stadium_loading_modal.deiconify()
            root.update()
            bar = root.stadium_loading_bar
            frame = bar.master
            self.assertEqual(root.stadium_loading_modal.winfo_width(), 340)
            self.assertEqual(root.stadium_loading_modal.winfo_height(), 274)
            self.assertTrue(bar.winfo_ismapped())
            self.assertGreater(bar.winfo_height(), 0)
            self.assertLessEqual(bar.winfo_y()+bar.winfo_height(), frame.winfo_height())
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
