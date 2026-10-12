"""Inspect the packaged code and DLLs without executing the Server or FIFA."""
import hashlib
import json
import types
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def strings(code):
    for value in code.co_consts:
        if isinstance(value, str):
            yield value
        elif isinstance(value, types.CodeType):
            yield from strings(value)


archive = CArchiveReader(str(ROOT/'dist/Server16Python.exe'))
pyz = archive.open_embedded_archive('PYZ.pyz')
for name in ('input_hints', 'match_settings_panel', 'match_presentation', 'prematch_panel', 'match_audio_panel'):
    assert 'server16_py.'+name in pyz.toc, name
colors = set(strings(pyz.extract('server16_py.input_hints')))
assert '#52616f' in colors and 'mm' in colors
assert not colors.intersection(('#168444', '#c63237', '#1263bb', '#b88600'))
dll_name = next(key for key in archive.toc if key.endswith('cgfs16_overlay.dll'))
assert archive.extract(dll_name) == (ROOT/'bin/cgfs16_overlay.dll').read_bytes()
for language in ('pt', 'en', 'es'):
    key = next(key for key in archive.toc if key.replace('\\', '/').endswith('locales/'+language+'.json'))
    catalog = json.loads(archive.extract(key).decode('utf-8'))
    assert 'dialog.fifa_location.title' in catalog
    assert 'message.warning.missing_fifa_settings' in catalog
assert 'message.warning.missing_fifa_settings' in set(strings(pyz.extract('server16_py.app')))
package = ROOT/'dist/MatchPresentation'
manifest = json.loads((package/'manifest.json').read_text())
for entry in manifest['files']:
    assert hashlib.sha256((package/entry['relative']).read_bytes()).hexdigest().upper() == entry['sha256']
print('Verified: monochrome glyphs, settings modules, exact native overlay and all package checksums.')
