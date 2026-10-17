import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from server16_py.competition_icons import (
    COMP_OBJ, FIELDS, ICON_MAP, ICONS, CompetitionIconImporter, CompetitionIconService,
    convert, identities, resolve,
)


class CompetitionIconsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = Path(self.temp.name)
        for path, text in ((COMP_OBJ, '1738,3,C999,TrophyName_Abbr15_9,0\n1741,3,C83,Other,0\n'),
                           (ICON_MAP, '# official\n1738|7|C999|TrophyName_Abbr15_9\n'),
                           (Path('FSW/settings.ini'), '[movies]\n1738=BRA - Brasileirão Série A\n1741=BRA - Serie B\n')):
            target = self.game / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        self.folder = self.game / ICONS
        self.folder.mkdir(parents=True)
        self.index = self.folder / 'index.tsv'
        self.index.write_text('\t'.join(FIELDS) + '\n7\tc7.dds\told\told\t1,1,47,47\t0\n'
                              '1738\tc1738.dds\talias\told\t1,1,47,47\t0\n', encoding='utf-8')
        self.messages = []
        self.importer = CompetitionIconImporter(self.game, self.messages.append)

    def image(self, name='1738.png', color=(22, 66, 220, 180)):
        path = self.folder / name
        Image.new('RGBA', (300, 150), color).save(path)
        return path

    def rows(self):
        return {int(row['visual_id']): row for row in csv.DictReader(io.StringIO(self.index.read_text()), delimiter='\t')}

    def test_identity_precedence_and_safe_name_matching(self):
        mapping, labels, aliases = identities(self.game)
        self.assertEqual(mapping, {1738: 7, 1741: 83})
        for name in ('1738', '1738 - qualquer nome', 'BRA - Brasileirao Serie A', 'c7'):
            self.assertEqual(resolve(name, mapping, aliases), 7)
        for name in ('7', '../1738', 'Brasileirao', '99999'):
            with self.assertRaises(ValueError):
                resolve(name, mapping, aliases)

    def test_conversion_index_backups_original_and_idempotence(self):
        source = self.image()
        original = source.read_bytes()
        self.assertEqual(self.importer.sync(force=True), 1)
        target = self.folder / 'c7.dds'
        raw = target.read_bytes()
        self.assertEqual((len(raw), raw[84:88]), (16512, b'DXT5'))
        image = Image.open(target).convert('RGBA')
        self.assertEqual(image.size, (128, 128))
        bounds = image.getchannel('A').getbbox()
        self.assertLessEqual(bounds[2], 48)
        self.assertLessEqual(bounds[3], 48)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(self.rows()[7]['host_available'], '1')
        self.assertEqual(self.rows()[1738]['host_available'], '0')
        self.assertFalse((self.folder / 'c1738.dds').exists())
        backups = list((self.game / 'runtime/backups/career_competition_icons').iterdir())
        self.assertEqual(len(backups), 1)
        manifest = json.loads((backups[0] / 'manifest.json').read_text())
        self.assertIsNone(manifest['files'][(ICONS / 'c7.dds').as_posix()])
        self.assertEqual(self.importer.sync(force=True), 0)
        self.assertEqual(target.read_bytes(), raw)
        # A removed output or an accidentally disabled entry is repaired automatically.
        target.unlink()
        self.assertEqual(self.importer.sync(force=True), 1)

    def test_unknown_corrupt_transparent_and_duplicate_never_change_index(self):
        before = self.index.read_bytes()
        self.image('Brasileirao.png')
        self.image('1738.png')
        self.image('c7.png')
        self.assertEqual(self.importer.sync(force=True), 0)
        self.assertEqual(self.index.read_bytes(), before)
        (self.folder / 'c7.png').unlink()
        (self.folder / '1738.png').write_bytes(b'partial image copy')
        self.assertEqual(self.importer.sync(force=True), 0)
        self.image('1738.png', (0, 0, 0, 0))
        self.assertEqual(self.importer.sync(force=True), 0)
        self.assertEqual(self.index.read_bytes(), before)

    def test_stable_copy_observation_and_no_legacy_reprocessing(self):
        self.image()
        (self.folder / 'c1738.dds').write_bytes(b'legacy blocked asset')
        self.assertEqual(self.importer.sync(), 0)
        self.assertEqual(self.importer.sync(), 1)
        self.assertEqual((self.folder / 'c1738.dds').read_bytes(), b'legacy blocked asset')
        self.assertEqual(self.rows()[1738]['host_available'], '0')

    def test_ambiguous_name_and_shared_visual_duplicates_are_rejected(self):
        with (self.game / ICON_MAP).open('a') as file:
            file.write('2000|83|C700|Custom\n')
        with (self.game / COMP_OBJ).open('a') as file:
            file.write('2000,3,C700,Custom,0\n')
        with (self.game / 'FSW/settings.ini').open('a', encoding='utf-8') as file:
            file.write('2000=BRA - Brasileirão Série A\n')
        mapping, _, aliases = identities(self.game)
        with self.assertRaises(ValueError):
            resolve('BRA - Brasileirao Serie A', mapping, aliases)
        self.image('1741.png')
        self.image('2000.png')
        self.assertEqual(self.importer.sync(force=True), 0)

    def test_changed_art_updates_and_backs_up_previous_dds(self):
        self.image()
        self.importer.sync(force=True)
        old = (self.folder / 'c7.dds').read_bytes()
        self.image(color=(255, 20, 20, 255))
        self.assertEqual(self.importer.sync(force=True), 1)
        self.assertNotEqual((self.folder / 'c7.dds').read_bytes(), old)
        backups = sorted((self.game / 'runtime/backups/career_competition_icons').iterdir())
        self.assertEqual((backups[-1] / ICONS / 'c7.dds').read_bytes(), old)

    def test_no_writes_while_game_running_and_worker_can_prepare_before_launch(self):
        self.image()
        service = CompetitionIconService(self.messages.append)
        service.poll(self.game, game_running=True)
        self.assertIsNone(service.worker)
        self.assertFalse((self.folder / 'c7.dds').exists())
        self.assertEqual(service.prepare(self.game, force=True), 1)

    def test_new_competition_uses_compdata_without_manual_map_or_index(self):
        with (self.game / COMP_OBJ).open('a') as file:
            file.write('2026,3,C91,TrophyName_Abbr15_92,0\n')
        self.index.unlink()
        self.image('2026.png')
        self.assertEqual(self.importer.sync(force=True), 1)
        self.assertTrue((self.folder / 'c92.dds').is_file())
        self.assertEqual(self.rows()[92]['host_available'], '1')

    def test_bad_index_is_preserved(self):
        self.index.write_bytes(b'broken\tindex\n')
        self.image()
        self.assertEqual(self.importer.sync(force=True), 0)
        self.assertEqual(self.index.read_bytes(), b'broken\tindex\n')
        self.assertFalse((self.folder / 'c7.dds').exists())

    def test_deleted_index_recovers_canonical_ids_and_keeps_old_alias_blocked(self):
        data, _ = convert(self.image().read_bytes())
        (self.folder / '1738.png').unlink()
        for visual in (7, 1738):
            (self.folder / f'c{visual}.dds').write_bytes(data)
        self.index.unlink()
        self.assertEqual(self.importer.sync(force=True), 0)
        self.assertEqual(self.rows()[7]['host_available'], '1')
        self.assertEqual(self.rows()[1738]['host_available'], '0')
        self.assertEqual((self.folder / 'c1738.dds').read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
