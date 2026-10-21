import configparser
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("panorama_installer", ROOT / "tools/install_panorama_drone.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
DEFAULTS = (ROOT / "native_mods/panorama_drone/panorama_drone.ini").read_text(encoding="utf-8")


class PanoramaInstallTests(unittest.TestCase):
    def test_legacy_defaults_and_new_shots_preserve_user_choices(self):
        old = "; preserve comment\n[panorama_drone]\nduration_seconds=32\nheight_limit_cm=3200\n[shots]\nlow_pitch_flight=0\n[stadium_12345678]\nheight_limit_cm=2500\n"
        text = installer.upgrade_config(old, DEFAULTS)
        cfg = configparser.ConfigParser()
        cfg.read_string(text)
        self.assertEqual(cfg.getint("panorama_drone", "duration_seconds"), 52)
        self.assertEqual(cfg.getint("panorama_drone", "height_limit_cm"), 11000)
        self.assertEqual(cfg.getint("shots", "low_pitch_flight"), 0)
        self.assertEqual(cfg.getint("stadium_12345678", "height_limit_cm"), 2500)
        self.assertEqual(len(cfg["shots"]), 39)
        self.assertEqual(cfg.getint("panorama_drone", "scene_pack_revision"), 6)
        self.assertTrue(text.startswith("; preserve comment"))
        self.assertEqual(installer.upgrade_config(text, DEFAULTS), text)

    def test_custom_values_and_case_insensitive_windows_sections(self):
        old = "[PANORAMA_DRONE]\nDURATION_SECONDS=70\nHEIGHT_LIMIT_CM=4200\n[SHOTS]\nexterior_corner_arrival=0\n"
        text = installer.upgrade_config(old, DEFAULTS)
        cfg = configparser.ConfigParser()
        cfg.read_string(text)
        self.assertEqual(cfg.getint("PANORAMA_DRONE", "duration_seconds"), 70)
        self.assertEqual(cfg.getint("PANORAMA_DRONE", "height_limit_cm"), 4200)
        self.assertEqual(cfg.getint("SHOTS", "exterior_corner_arrival"), 0)
        self.assertEqual(len(cfg["SHOTS"]), 39)

    def test_install_keeps_other_mods_and_enables_only_one_panorama_version(self):
        with tempfile.TemporaryDirectory(prefix="panorama_install_") as temp:
            root = Path(temp)
            build = root / "build"
            build.mkdir()
            (build / "panorama_drone_v5.dll").write_bytes(b"installer-fixture")
            game = root / "game"
            enabled = game / "ModCarrerMode/mods/enabled.txt"
            enabled.parent.mkdir(parents=True)
            enabled.write_text("other_mod.dll\npanorama_drone/panorama_drone_v1.dll\npanorama_drone\\panorama_drone_v2.dll\n", encoding="utf-8")
            result = installer.install(build, [game])
            self.assertEqual(enabled.read_text(encoding="utf-8").splitlines(), ["other_mod.dll", r"panorama_drone\panorama_drone_v5.dll"])
            backup = Path(result["destinations"][0]["backup"])
            self.assertIn("panorama_drone_v2.dll", (backup / "ModCarrerMode/mods/enabled.txt").read_text(encoding="utf-8"))
            self.assertEqual(installer.install(build, [game])["destinations"][0]["changed"], [])

    def test_v3_keeps_timing_profiles_and_disabled_views_while_adding_v4(self):
        old='[panorama_drone]\nscene_pack_revision=3\nduration_seconds=73\nheight_limit_cm=3000\n[shots]\ngoal_approach=0\n[stadium_ABCDEF12]\nroute_scale_percent=70\n'
        text=installer.upgrade_config(old,DEFAULTS)
        cfg=configparser.ConfigParser();cfg.read_string(text)
        self.assertEqual(cfg.getint('panorama_drone','scene_pack_revision'),6)
        self.assertEqual(cfg.getint('panorama_drone','duration_seconds'),73)
        self.assertEqual(cfg.getint('panorama_drone','height_limit_cm'),3000)
        self.assertEqual(cfg.getint('shots','goal_approach'),0)
        self.assertEqual(cfg.getint('shots','centre_circle_inner_orbit'),1)
        self.assertEqual(cfg.getint('shots','goal_low_crane'),1)
        self.assertEqual(cfg.getint('stadium_ABCDEF12','route_scale_percent'),70)
        self.assertEqual(installer.upgrade_config(text,DEFAULTS),text)

    def test_v4_adds_exterior_orbit_without_resetting_existing_cameras(self):
        old='[panorama_drone]\nscene_pack_revision=4\nduration_seconds=80\n[shots]\ncentre_circle_full_turn=0\n'
        text=installer.upgrade_config(old,DEFAULTS)
        cfg=configparser.ConfigParser();cfg.read_string(text)
        self.assertEqual(cfg.getint('panorama_drone','scene_pack_revision'),6)
        self.assertEqual(cfg.getint('panorama_drone','duration_seconds'),80)
        self.assertEqual(cfg.getint('shots','centre_circle_full_turn'),0)
        self.assertEqual(cfg.getint('shots','stadium_exterior_orbit'),1)
        cfg['shots']['stadium_exterior_orbit']='0'
        import io
        saved=io.StringIO();cfg.write(saved)
        updated=configparser.ConfigParser();updated.read_string(installer.upgrade_config(saved.getvalue(),DEFAULTS))
        self.assertEqual(updated.getint('shots','stadium_exterior_orbit'),0)

    def test_v5_adds_both_new_views_and_keeps_saved_timings_and_disabled_orbit(self):
        old='; user profile\n[panorama_drone]\nscene_pack_revision=5\nduration_seconds=62\ntransition_seconds=4\n[shots]\nstadium_exterior_orbit=0\n[stadium_12345678]\nheight_limit_cm=5200\n'
        text=installer.upgrade_config(old,DEFAULTS)
        cfg=configparser.ConfigParser();cfg.read_string(text)
        self.assertEqual(cfg.getint('panorama_drone','scene_pack_revision'),6)
        self.assertEqual(cfg.getint('panorama_drone','duration_seconds'),62)
        self.assertEqual(cfg.getint('panorama_drone','transition_seconds'),4)
        self.assertEqual(cfg.getint('shots','stadium_exterior_orbit'),0)
        self.assertEqual(cfg.getint('shots','stadium_horizontal_profile_orbit'),1)
        self.assertEqual(cfg.getint('shots','halfway_line_full_traverse'),1)
        self.assertEqual(cfg.getint('stadium_12345678','height_limit_cm'),5200)
        self.assertEqual(installer.upgrade_config(text,DEFAULTS),text)


if __name__ == "__main__":
    unittest.main()
