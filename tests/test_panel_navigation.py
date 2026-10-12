import unittest
from server16_py.panel_navigation import move_focus


class PanelNavigationTests(unittest.TestCase):
    def test_grid_directions_follow_button_positions(self):
        targets=[(0,(0,0,100,100)),(1,(110,0,210,100)),(2,(0,110,100,210)),(3,(110,110,210,210)),(4,(0,220,210,250))]
        self.assertEqual(move_focus(0,5,targets),2)
        self.assertEqual(move_focus(0,3,targets),1)
        self.assertEqual(move_focus(3,4,targets),1)
        self.assertEqual(move_focus(1,3,targets),1)
        self.assertEqual(move_focus(4,4,targets,3),3)
    def test_list_reaches_apply_then_moves_to_back(self):
        targets=[(0,(0,0,210,40)),(1,(0,50,210,90)),(3,(0,100,100,140)),(4,(110,100,210,140))]
        self.assertEqual(move_focus(1,5,targets,4),4)
        self.assertEqual(move_focus(4,2,targets),3)
        self.assertEqual(move_focus(0,4,targets),0)
        self.assertEqual(move_focus(4,9,targets),0)


if __name__=='__main__':unittest.main()
