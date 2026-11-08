"""Select the native background and startup assets for the chosen aspect."""
from pathlib import Path
import os
import struct
from tempfile import NamedTemporaryFile

NATIVE = Path('data/ui/imgAssets/backgroundstadiums/st_bootflow.DDS')
VARIANTS = Path('ModCarrerMode/data/ultrawide')
STANDARD = 'st_bootflow_standard.dds'
WIDE = 'st_bootflow_ultrawide.dds'
NOTFOUND = NATIVE.with_name('notfound.dds')
PRESSSTART = Path('data/ui/game/screens/bootflow/pressstart.big')


def read_dds(path):
    data = Path(path).read_bytes()
    return data, _dds_size(data)


def _dds_size(data):
    if (len(data) < 128 or data[:4] != b'DDS ' or
            struct.unpack_from('<I', data, 4)[0] != 124 or
            struct.unpack_from('<I', data, 76)[0] != 32):
        raise ValueError('Imagem DDS de fundo inválida.')
    height, width = struct.unpack_from('<II', data, 12)
    fourcc = data[84:88]
    block = {b'DXT1': 8, b'DXT3': 16, b'DXT5': 16}.get(fourcc)
    if not block or not 64 <= width <= 16384 or not 64 <= height <= 16384:
        raise ValueError('Formato DDS de fundo não suportado.')
    if len(data) < 128 + ((width+3)//4) * ((height+3)//4) * block:
        raise ValueError('Imagem DDS de fundo incompleta.')
    return width, height


def _validate_pressstart(data):
    # The image is packed into a square atlas in both versions. Validate the
    # archive and its DDS, rather than testing the aspect of the atlas itself.
    if len(data) < 16 or data[:4] not in (b'BIG4', b'BIGF'):
        raise ValueError('Pacote pressstart.big inválido.')
    if len(data) not in (struct.unpack_from('<I', data, 4)[0], struct.unpack_from('>I', data, 4)[0]):
        raise ValueError('Tamanho do pressstart.big inválido.')
    count, directory_end = struct.unpack_from('>II', data, 8)
    if not 16 <= directory_end <= len(data) or not 1 <= count <= (directory_end - 16) // 9:
        raise ValueError('Diretório do pressstart.big inválido.')
    position = 16
    entries = {}
    for _ in range(count):
        end = data.find(b'\0', position + 8, directory_end)
        if end == -1 or end == position + 8:
            raise ValueError('Entrada do pressstart.big inválida.')
        offset, size = struct.unpack_from('>II', data, position)
        name = data[position + 8:end]
        if name in entries or not directory_end <= offset <= offset + size <= len(data):
            raise ValueError('Entrada do pressstart.big fora do pacote.')
        entries[name] = (offset, size)
        position = end + 1
    if not all(entries.get(name, (0, 0))[1] for name in (b'0', b'1', b'2')):
        raise ValueError('Layout ou imagem ausente no pressstart.big.')
    offset, size = entries[b'2']
    _dds_size(memoryview(data)[offset:offset + size])


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=path.name + '.background-',
                                suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply_background(game_directory, enabled, *, commit=None):
    """Validate all available presets, then publish the assets and switch."""
    root = Path(game_directory)
    folder = root / VARIANTS
    suffix = 'ultrawide' if enabled else 'standard'
    presets = (
        (NATIVE, folder / (WIDE if enabled else STANDARD)),
        (NOTFOUND, folder / f'notfound_{suffix}.dds'),
        (PRESSSTART, folder / f'pressstart_{suffix}.big'),
    )
    selected = False
    changes = []
    for relative, source in presets:
        # The new assets are optional for installations with older packs.
        # Require the complete pair before changing either new native file.
        if relative != NATIVE and not all(
            (folder / f'{relative.stem}_{mode}{relative.suffix}').is_file()
            for mode in ('standard', 'ultrawide')
        ):
            continue
        if not source.is_file():
            continue
        data = source.read_bytes()
        if relative == PRESSSTART:
            _validate_pressstart(data)
        else:
            width, height = _dds_size(data)
            if (width / height > 16 / 9 + .001) != bool(enabled):
                raise ValueError(f'A proporção de {source.name} não corresponde à versão selecionada.')
        selected = True
        target = root / relative
        previous = target.read_bytes() if target.is_file() else None
        if previous != data:
            changes.append((target, data, previous))

    installed = []
    try:
        for target, data, previous in changes:
            _atomic(target, data)
            installed.append((target, previous))
        if commit is not None:
            commit()
    except (OSError, ValueError):
        for target, previous in reversed(installed):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                _atomic(target, previous)
        raise
    return selected
