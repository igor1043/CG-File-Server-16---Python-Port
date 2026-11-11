"""Stage a visual menu pack while checking the installed navigation contract.

Only active hub XMLs and tile DDSs are inputs. Archives and alternative layouts
stay in the author's folder. Staging never writes to the game or a career save.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import xml.etree.ElementTree as ET

LAYOUTS = frozenset(('careermanagerhubcfg.xml', 'careerplayerhubcfg.xml',
    'mainhubcfg.xml', 'pauseendgamehubcfg.xml', 'pausehubcfg.xml', 'tournamenthubcfg.xml'))
VISUAL = frozenset(('X', 'Y', 'WIDTH', 'HEIGHT', 'FORMAT', 'FG_PATH', 'BG_ICON',
    'UHLALPHA', 'HLALPHA', 'COLOR', 'COLOUR'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def contract(node):
    """Keep functional layout bindings exact while allowing visual image layers."""
    # Incoming menu packs may add, remove, or resize image-only layers (for
    # example a custom tile illustration). They cannot dispatch actions or
    # carry data providers, so exclude them from the functional contract.
    if node.tag == 'data' and node.get('TYPE') == 'image':
        return None
    ignored = set(VISUAL)
    if node.tag == 'data':
        if node.get('TYPE') in ('text', 'title'):
            ignored.update(('PARAM', 'TRANSLATE'))
        if node.get('TYPE') in ('asset', 'image'):
            ignored.add('PATH')
    children = tuple(item for child in node if (item := contract(child)) is not None)
    return (node.tag, tuple(sorted((k, v) for k, v in node.attrib.items() if k not in ignored)),
            (node.text or '').strip(), children)


def checked_layout(current, incoming):
    before, after = ET.fromstring(current), ET.fromstring(incoming)
    if contract(before) != contract(after):
        raise ValueError('O layout altera IDs, destinos, providers ou a estrutura dos mods instalados')
    return incoming


def checked_dds(raw):
    if len(raw) < 128 or raw[:4] != b'DDS ' or struct.unpack_from('<I', raw, 4)[0] != 124:
        raise ValueError('DDS inválido')
    height, width = struct.unpack_from('<II', raw, 12)
    if not width or not height or width > 16384 or height > 16384:
        raise ValueError('Dimensões DDS inválidas')
    return raw


def stage(pack, game, output):
    pack, game, output = map(lambda p: Path(p).resolve(), (pack, game, output))
    if output == game or game in output.parents or pack == output or pack in output.parents:
        raise ValueError('A saída de preparação deve ficar fora do jogo e do pack recebido')
    rows, skipped = [], []
    for source in sorted(pack.rglob('*')):
        if not source.is_file():
            continue
        rel = source.relative_to(pack)
        is_layout = rel.parent.as_posix().lower() == 'data/ui/layout' and rel.name in LAYOUTS
        is_icon = (rel.parent.as_posix().lower() == 'data/ui/imgassets/tileicons'
                   and source.suffix.lower() == '.dds' and ' - copia' not in source.name.lower())
        if not (is_layout or is_icon):
            skipped.append(rel.as_posix())
            continue
        raw = source.read_bytes()
        previous = (game/rel).read_bytes() if (game/rel).is_file() else None
        if is_layout:
            if previous is None:
                raise ValueError(f'Layout instalado ausente: {rel}')
            checked_layout(previous, raw)
        else:
            checked_dds(raw)
        target = output/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append(dict(path=rel.as_posix(), bytes=len(raw), sha256=digest(raw),
                         previous_sha256=digest(previous) if previous is not None else None,
                         changed=previous != raw))
    if not rows or not any(row['path'].endswith('careermanagerhubcfg.xml') for row in rows):
        raise ValueError('Pack incompleto: falta o layout da carreira')
    report = dict(schema=1, files=rows, skipped=skipped)
    (output/'menu-layout-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = stage(args.pack, args.game, args.output)
    print(f"Preparados {len(report['files'])} arquivos; {sum(r['changed'] for r in report['files'])} diferentes; {len(report['skipped'])} arquivos de autoria ignorados")


if __name__ == '__main__':
    main()
