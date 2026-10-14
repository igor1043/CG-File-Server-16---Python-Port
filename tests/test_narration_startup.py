import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
from startup_wizard import original_catalog_status


class NarrationStartupTests(unittest.TestCase):
    def test_startup_reads_original_catalog_totals_without_changing_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'catalog.sqlite'
            db=sqlite3.connect(path)
            db.execute('CREATE TABLE clips (wav TEXT, transcript TEXT)')
            db.executemany('INSERT INTO clips VALUES (?,?)',[
                ('one.wav','fala original'),('one.wav','fala repetida'),('two.wav','')
            ])
            db.commit();db.close()
            self.assertEqual(original_catalog_status(path),{'clips':3,'recordings':2})
            db=sqlite3.connect(path)
            self.assertEqual(db.execute('SELECT count(*) FROM clips').fetchone()[0],3)
            db.close()

    def test_startup_reports_missing_original_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                original_catalog_status(Path(temporary)/'missing.sqlite')


if __name__=='__main__':unittest.main()
