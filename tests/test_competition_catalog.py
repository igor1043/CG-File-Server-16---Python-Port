from pathlib import Path
import tempfile
import unittest
from server16_py.competition_catalog import COMP_OBJ, ICON_MAP, PRESENTATION_ALIASES, nodes, identity_key, icon_mapping, presentation_package
from server16_py.entrance_props_runtime import resolve_asset


class CompetitionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.write(COMP_OBJ, '0,0,FIFA,FIFA,-1\n10,3,C83,TrophyName_Abbr15_83,0\n30,3,C7,TrophyName_Abbr15_7,0\n31,4,S1,FCE_Setup_Stage,30\n')

    def write(self, path, text):
        target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')

    def test_semantic_override_follows_renumbering_and_preserves_custom_art(self):
        self.write(ICON_MAP,'10|117|C7|TrophyName_Abbr15_7\n')
        self.assertEqual(icon_mapping(self.root),{10:83,30:117})

    def test_stale_numeric_row_cannot_override_reused_id(self):
        self.write(ICON_MAP,'10|7\n')
        self.assertEqual(icon_mapping(self.root),{10:83,30:7})

    def test_ambiguous_identity_never_overrides_another_competition(self):
        with (self.root/COMP_OBJ).open('a') as file:file.write('40,3,C7,TrophyName_Abbr15_7,0\n')
        self.write(ICON_MAP,'10|117|C7|TrophyName_Abbr15_7\n')
        self.assertEqual(icon_mapping(self.root),{10:83,30:7,40:7})

    def test_competition_phase_identity_path(self):
        objects=nodes(self.root)
        key=identity_key(objects,30)
        self.assertEqual(identity_key(objects,31),key+'~4:S1:FCE_Setup_Stage')

    def test_changed_compdata_invalidates_cache_and_missing_asset_keeps_fallback(self):
        self.write(ICON_MAP,'10|117|C7|TrophyName_Abbr15_7\n')
        self.assertEqual(icon_mapping(self.root)[30],117)
        self.write(COMP_OBJ,'50,3,C7,TrophyName_Abbr15_7,0\n')
        self.assertEqual(icon_mapping(self.root),{50:117})
        self.write(Path('FSW/settings.ini'),'[movies]\n50=Serie A\n')
        self.assertEqual(resolve_asset(self.root,'50'),(None,'asset_missing'))

    def test_cycles_do_not_produce_identity_keys(self):
        self.write(COMP_OBJ,'1,4,S1,Stage,2\n2,4,S2,Stage,1\n')
        self.assertIsNone(identity_key(nodes(self.root),1))

    def test_presentation_aliases_prefer_new_packages_and_reject_ambiguous_paths(self):
        base=self.root/'MoviesGBD';(base/'Old').mkdir(parents=True)
        self.write(PRESENTATION_ALIASES,'movies|New|Old\n')
        self.assertEqual(presentation_package(self.root,base,'movies','New'),base/'Old')
        (base/'New').mkdir()
        self.assertEqual(presentation_package(self.root,base,'movies','New'),base/'New')
        self.write(PRESENTATION_ALIASES,'movies|Other|Old\nmovies|Other|../New\nmovies|Other|New\n')
        self.assertEqual(presentation_package(self.root,base,'movies','Other'),base/'Other')
