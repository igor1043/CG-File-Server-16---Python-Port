import tempfile,unittest
from pathlib import Path
from server16_py.stadium_metadata import count,read_custom_metadata

class MetadataTests(unittest.TestCase):
    def test_counts_are_not_percentages_or_guessed_native_capacities(self):
        for value,expected in [('78.838',78838),('78,838',78838),('54 662',54662),('0',0),('90.5',None),('50%',None),('-1',None),('3000000',None)]:self.assertEqual(count(value),expected)
    def test_missing_and_mismatched_package_keep_both_fields_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.assertEqual(read_custom_metadata(root,'A',root)['capacity'],None)
            (root/'stadium.ini').write_text('[stadium]\nname=B\ncapacity=50000\nattendance=10000\n')
            self.assertIsNone(read_custom_metadata(root,'A',root)['attendance'])
    def test_exact_stadium_identity_precedence_and_invalid_occupancy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'FSW').mkdir();(root/'ModCarrerMode/config').mkdir(parents=True)
            (root/'FSW/settings.ini').write_text('[stadiumcapacity]\nCustom A=20000\nCustom B=99000\n[stadiumattendance]\nCustom A=12000\n')
            (root/'stadium.ini').write_text('[stadium]\ncapacity=21000\n')
            (root/'ModCarrerMode/config/stadium_metadata.ini').write_text('[Custom A]\ncapacity=22000\nattendance=23000\n')
            result=read_custom_metadata(root,'Custom A',root)
            self.assertEqual(result['capacity'],22000);self.assertIsNone(result['attendance'])

if __name__=='__main__':unittest.main()
