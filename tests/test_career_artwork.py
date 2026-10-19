import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from server16_py.career_artwork import artwork, artwork_path


class CareerArtworkTests(unittest.TestCase):
    def image(self,path,color):
        path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGBA',(32,24),color).save(path,format='PNG')

    def test_country_flag_uses_database_iso_and_installed_nation_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data={'nation_codes':{'191':'br'},'nations':{'191':'Brasil'}}
            self.assertEqual(artwork_path(root,'country',191,data).name,'br.png')
            native=root/'data/ui/imgAssets/flags512x512/f_191.dds';self.image(native,'green')
            self.assertEqual(artwork_path(root,'country',191,data),native)

    def test_league_custom_icon_resolves_competition_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);assets=root/'data/ui/imgAssets'
            self.image(assets/'league/light/l7.dds','blue')
            custom=assets/'careerCompetitionIcons/1761.png';self.image(custom,'red')
            with patch('server16_py.career_artwork.nodes',return_value={1761:(3,'C7','Brazil',0)}):
                self.assertEqual(artwork_path(root,'league',7,{}),custom)
                self.assertEqual(artwork(root,'league',7,{},(144,144)).getpixel((10,10)),(255,0,0,255))

    def test_crest_follows_selected_team_asset_instead_of_previous_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);assets=root/'data/ui/imgAssets/crest/light'
            self.image(assets/'l88.dds','blue');self.image(assets/'l99.dds','red')
            data={'teams':[{'id':1,'asset_id':88},{'id':2,'asset_id':99}]}
            first=artwork(root,'team',1,data,(144,144));second=artwork(root,'team',2,data,(144,144))
            self.assertNotEqual(first.getpixel((10,10)),second.getpixel((10,10)))
            self.assertLessEqual(first.width,144);self.assertLessEqual(first.height,144)

    def test_missing_artwork_is_optional_and_does_not_break_navigation(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(artwork(Path(temporary),'team',10000000,{},(144,144)))


if __name__=='__main__':unittest.main()
