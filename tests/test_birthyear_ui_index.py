"""Exercise the shipped PowerShell installer on isolated FIFA BIG/BH fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools/birthyear_ui/Enable-BirthyearUI.ps1"
TARGET = "data/ui/game/screens/virtualpro/vpro_proinfo.big"
PAYLOAD = Path(os.environ.get("FIFA_BIRTHYEAR_PAYLOAD", r"U:\mods\FIFA Friends V12\ModCarrerMode\mods\career_birthdate_2006\payload\vpro_proinfo.big"))
SHELL = shutil.which("pwsh") or shutil.which("powershell")


def fixture(root, target_index=1, stem="data_front_end_extra"):
    names = ["data/ui/other.big", TARGET, "data/ui/unrelated.big"]
    names[1], names[target_index] = names[target_index], names[1]
    body = bytearray()
    records = []
    for i, name in enumerate(names):
        offset, size = 512 + i * 32, 16
        body.extend(struct.pack(">II", offset, size) + name.encode() + b"\0")
        records.append(struct.pack(">IIIQ", offset, size, i, 0x123456789ABCDE00 + i))
    big = bytearray(b"BIG4" + struct.pack("<I", 608) + struct.pack(">II", 3, 16 + len(body)) + body)
    big.extend(bytes(608 - len(big)))
    bh = bytearray(b"ViV4" + struct.pack("<I", 76) + struct.pack(">II", 3, 76) + b"".join(records))
    (root / (stem + ".big")).write_bytes(big)
    index = root / (stem + ".bh")
    index.write_bytes(bh)
    return index, 16 + target_index * 20 + 12


@unittest.skipUnless(SHELL and PAYLOAD.exists(), "Windows PowerShell and validated UI payload required")
class BirthyearUiIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fifa_birthyear_test_")
        self.root = Path(self.temp.name)
        dest = self.root / TARGET
        dest.parent.mkdir(parents=True)
        shutil.copyfile(PAYLOAD, dest)

    def tearDown(self):
        self.temp.cleanup()

    def run_helper(self, *args, success=True):
        runner = self.root / "run.ps1"
        # Literal script paths and script arguments avoid shell interpolation.
        escaped = str(HELPER).replace("'", "''")
        runner.write_text(f"param([string]$Game)\n$ErrorActionPreference='Stop'\n& '{escaped}' -GameDirectory $Game {' '.join(args)} | ConvertTo-Json -Depth 5", encoding="utf-8-sig")
        result = subprocess.run([SHELL, "-NoProfile", "-File", str(runner), str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr + result.stdout)
        return json.loads(result.stdout) if success else result

    def test_verify_is_read_only(self):
        index, _ = fixture(self.root)
        before = index.read_bytes()
        result = self.run_helper("-VerifyOnly")
        self.assertEqual(result["Status"], "ActivationRequired")
        self.assertEqual(index.read_bytes(), before)
        self.assertFalse((self.root / "ModCarrerMode/backups").exists())

    def test_only_target_hash_changes_and_backup_is_exact(self):
        index, at = fixture(self.root, target_index=2)
        before = index.read_bytes()
        result = self.run_helper()
        expected = before[:at] + bytes(8) + before[at + 8:]
        self.assertEqual(index.read_bytes(), expected)
        self.assertEqual((Path(result["Backup"]) / index.name).read_bytes(), before)
        self.assertEqual(result["Entries"][0]["Entry"], 2)
        self.assertEqual(result["Entries"][0]["AfterSha256"], hashlib.sha256(expected).hexdigest().upper())
        self.assertTrue(result["RestartRequired"])

    def test_already_active_is_idempotent(self):
        index, at = fixture(self.root, target_index=0)
        before = bytearray(index.read_bytes())
        before[at:at+8] = bytes(8)
        index.write_bytes(before)
        result = self.run_helper()
        self.assertEqual(result["Changed"], 0)
        self.assertEqual(result["Status"], "LooseInterfaceActive")
        self.assertEqual(index.read_bytes(), before)
        self.assertFalse((self.root / "ModCarrerMode/backups").exists())

    def test_mismatched_index_is_rejected_without_mutation(self):
        index, _ = fixture(self.root)
        data = bytearray(index.read_bytes())
        data[16] ^= 1
        index.write_bytes(data)
        self.run_helper(success=False)
        self.assertEqual(index.read_bytes(), data)

    def test_unknown_layout_is_rejected(self):
        index, _ = fixture(self.root)
        data = b"????" + index.read_bytes()[4:]
        index.write_bytes(data)
        self.run_helper(success=False)
        self.assertEqual(index.read_bytes(), data)

    def test_bad_loose_payload_is_rejected(self):
        index, _ = fixture(self.root)
        before = index.read_bytes()
        (self.root / TARGET).write_bytes(b"unknown APT")
        self.run_helper(success=False)
        self.assertEqual(index.read_bytes(), before)

    def test_missing_bh_is_rejected(self):
        index, _ = fixture(self.root)
        index.unlink()
        self.run_helper(success=False)
        self.assertFalse(index.exists())

    def test_missing_archives_are_explicit_for_package_fixture(self):
        self.assertEqual(self.run_helper("-VerifyOnly")["Status"], "BaseArchivesAbsent")

    def test_patch_archive_is_also_activated(self):
        index, at = fixture(self.root, stem="data_patch")
        before = index.read_bytes()
        self.run_helper()
        self.assertEqual(index.read_bytes(), before[:at] + bytes(8) + before[at+8:])

    def test_validation_of_all_indexes_precedes_any_write(self):
        first, _ = fixture(self.root)
        second, _ = fixture(self.root, stem="data_patch")
        before = first.read_bytes()
        second.write_bytes(b"broken")
        self.run_helper(success=False)
        self.assertEqual(first.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
