import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.narration_paths import narration_root,profile_directory,profile_directories


class NarrationPathTests(unittest.TestCase):
    def test_runtime_contract_is_one_folder_per_narrator(self):
        with tempfile.TemporaryDirectory() as temporary:
            game=Path(temporary)
            folder=profile_directory(game,'Gustavo Vilani')
            self.assertEqual(folder,narration_root(game)/'Gustavo Vilani')

    def test_catalog_and_workspace_folders_are_not_listed_as_narrators(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=narration_root(temporary)
            (root/'.studio').mkdir(parents=True)
            (root/'Projetos').mkdir()
            profile=root/'Vilani';profile.mkdir()
            (profile/'profile.json').write_text(json.dumps({'name':'Vilani'}),encoding='utf8')
            self.assertEqual(profile_directories(root),[profile])

    def test_profile_name_cannot_escape_narrations(self):
        with tempfile.TemporaryDirectory() as temporary:
            for value in ('..','../outside','A\\B',''):
                with self.subTest(value=value),self.assertRaises(ValueError):
                    profile_directory(temporary,value)


if __name__=='__main__':unittest.main()
