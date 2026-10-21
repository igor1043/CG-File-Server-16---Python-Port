"""Brand the native career header without changing the career or online providers.

Requires the local ScoreboardStudio format/texture tools. No process writes,
DLL injection, game launch, or image generation is performed by this builder.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
OWNER = 'Server16CareerBrandOwner'
LOGO = 'mcFifaFriendsLogo'
HIDDEN = 'Server16CareerBrandHidden'
PRIOR = 'Server16CareerBrandPreviousVisible'
CAREER = ('game', 'components', 'CareerComponents', 'CareerHubWidget', 'prototype')
EASFC = ('pow', 'components', 'EASFCWidget', 'prototype')
MAIN = ('game', 'widgets', 'MainHubWidget', 'prototype')
BASELINES = {
    'careerhubwidget': '9fb40d261e9d04033d9e606507a7c1dc88f5ca6c0107e6cd4350e38e77707260',
    'easfcwidget': '192ef034f327914c055779e0163c5ddecfc1247b28d47a261a752e9b150dbf28',
    'mainhubwidget': 'ce6974096b1a5a1fa3ccd1b26a9312f965256ec476fa0ffbafab7804bc81cca3',
}


class Assembler:
    def __init__(self, data):
        self.data, self.fixups, self.labels = data, [], {}
        self.parameters = []

    def align(self): self.data.extend(bytes(-len(self.data) % 8))
    def op(self, value): self.data.append(value)
    def reg(self, n): self.data.extend((185, n))
    def string(self, value):
        self.op(161); self.align()
        at = len(self.data); self.data.extend(bytes(8))
        self.fixups.append((at, value))

    def member(self, name): self.string(name); self.op(78)
    def method(self, name): self.string(name); self.op(82)
    def path(self, *parts):
        self.string(parts[0]); self.op(28)
        for part in parts[1:]: self.member(part)

    def global_object(self):
        # FIFA's 0x58 pushes the STRING "_global"; 0x71 pushes its object.
        # SetMember on 0x58 cannot persist the hub owner between widgets.
        self.op(113)

    def branch(self, label, conditional=True):
        self.op(157 if conditional else 153); self.align()
        at = len(self.data); self.data.extend(bytes(4))
        self.fixups.append((at, ('branch', label)))

    def label(self, label): self.labels[label] = len(self.data)
    def store(self, register):
        self.op(135); self.align(); self.data.extend(struct.pack('<i', register)); self.op(23)

    def property(self, register, name, value):
        self.reg(register); self.string(name); self.op(115 if value else 116); self.op(79)

    def original(self, name, count=0):
        for register in reversed(range(2, count + 2)): self.reg(register)
        self.op(181); self.op(count); self.reg(1); self.method('Server16Original' + name)

    def finish(self):
        for pointer, count in self.parameters:
            self.align(); struct.pack_into('<Q', self.data, pointer, len(self.data))
            if not count: self.data.extend(bytes(16))
            for index in range(count):
                self.align(); self.data.extend(struct.pack('<I', index + 2)); self.align()
                at = len(self.data); self.data.extend(bytes(8)); self.fixups.append((at, 'argument' + str(index)))
        strings = {}
        for at, value in self.fixups:
            if isinstance(value, tuple):
                struct.pack_into('<i', self.data, at, self.labels[value[1]] - at - 4)
            else:
                if value not in strings:
                    strings[value] = len(self.data); self.data.extend(value.encode('ascii') + b'\0')
                struct.pack_into('<Q', self.data, at, strings[value])


def widget(a):
    a.path('pow', 'globalClasses', 'POWManager', 'm_widgetComponent'); a.store(6)


def hide_widget(a, label):
    a.reg(6); a.op(18); a.branch(label + '_done')
    a.reg(6); a.member(HIDDEN); a.branch(label + '_hide')
    a.reg(6); a.string(PRIOR); a.reg(6); a.member('_visible'); a.op(79)
    a.property(6, HIDDEN, True)
    a.label(label + '_hide'); a.property(6, '_visible', False)
    a.label(label + '_done')


def career_init(a):
    a.original('InitComponents'); a.op(23)
    a.reg(1); a.member(LOGO); a.string('_visible'); a.op(116); a.op(79)
    a.op(118); a.op(62)


def career_data(a):
    a.original('SetData'); a.op(23)
    # This native header is also used by tournament mode. Only career is branded.
    a.reg(1); a.member('m_objData'); a.member('IS_TOURNAMENTMODE'); a.op(74); a.op(90); a.op(73)
    a.branch('career_done')
    a.global_object(); a.string(OWNER); a.reg(1); a.op(79)
    a.reg(1); a.member(LOGO); a.string('_visible'); a.op(115); a.op(79)
    widget(a); hide_widget(a, 'career')
    a.label('career_done'); a.op(118); a.op(62)


def career_shutdown(a):
    # A delayed unload of an old instance must not clear a newer career header.
    a.global_object(); a.member(OWNER); a.reg(1); a.op(73); a.op(18); a.branch('shutdown_original')
    a.global_object(); a.string(OWNER); a.op(117); a.op(79)
    widget(a)
    a.reg(6); a.op(18); a.branch('shutdown_original')
    a.reg(6); a.member(HIDDEN); a.op(18); a.branch('shutdown_original')
    a.reg(6); a.string('_visible'); a.reg(6); a.member(PRIOR); a.op(79)
    a.property(6, HIDDEN, False)
    a.label('shutdown_original'); a.original('Shutdown'); a.op(62)


def easfc_body(name, count):
    def body(a):
        a.original(name, count); a.op(23)
        # The native banner must stay transparent even between hub owners.
        # Visibility restoration must never expose it while the next hub loads.
        a.reg(1); a.string('_alpha'); a.op(89); a.op(79)
        a.global_object(); a.member(OWNER); a.op(18); a.branch(name + '_done')
        a.reg(1); a.store(6); hide_widget(a, name)
        a.label(name + '_done'); a.op(118); a.op(62)
    return body


def suppress_banner_first_paint(apt):
    from formats import Placement
    roots = [control for frame in apt.root_frames for control in frame
             if isinstance(control, Placement) and control.name == 'Widget']
    if len(roots) != 1: raise ValueError('Unexpected native EA banner root')
    placement = roots[0]
    # APT PlaceObject colour is installed before the MovieClip constructor.
    # Keep the native instance, geometry and providers, but start its entire
    # subtree at zero opacity. Flag 8 enables the colour transform. Zero alpha
    # bias prevents any child from becoming visible through an additive tint.
    struct.pack_into('<I', apt.data, placement.offset + 8, placement.flags | 8)
    struct.pack_into('<II', apt.data, placement.matrix_offset + 24, 0x00ffffff, 0)


def main_enter(a):
    # A Function2 called by the actual constructor has an explicit native this
    # register. Timeline first-frame actions do not reliably provide this scope.
    a.global_object(); a.string(OWNER); a.reg(1); a.op(79)
    widget(a); hide_widget(a, 'main_enter')
    a.op(118); a.op(62)


def main_publish(a):
    a.original('Publish', 2); a.op(23)
    # A late publish from a fading old menu must not steal the career's owner.
    a.global_object(); a.member(OWNER); a.reg(1); a.op(73); a.op(18); a.branch('main_publish_done')
    widget(a); hide_widget(a, 'main_publish')
    a.label('main_publish_done'); a.op(118); a.op(62)


def copy_initializer(a, apt, block, constructor_hook=False):
    """Copy original code; optionally add one call at the constructor's end.

    The inserted tail is a multiple of eight bytes. Existing function/string
    pointers and operand alignment stay valid; only crossing root branches
    and that constructor's declared code length require updating.
    """
    from formats import Reader
    original = apt.entry.original
    start, end = block[0].end, block[-1].offset
    if not constructor_hook:
        a.data.extend(original[start:end]); return
    constructor = next(block[i + 1] for i, ins in enumerate(block[:-1])
                       if ins.value == 'MainHubWidget' and block[i + 1].op == 142)
    cut = constructor.end; destination = len(a.data)
    a.data.extend(original[start:cut])
    tail = len(a.data)
    a.op(89); a.reg(1); a.method('Server16ApplyHeader'); a.op(23)
    # Native relocation walks the bytecode and treats opcode 0 as End even
    # inside a function's declared code range. Zero padding here left every
    # following function's name/parameter pointers unrelocated (revision 4).
    # Keep the original constructor's implicit return and pad with valid,
    # stack-neutral instructions instead of raw zero bytes.
    while len(a.data) % 8:
        a.op(118); a.op(23)
    added = len(a.data) - tail
    assert added > 0 and added % 8 == 0
    a.data.extend(original[cut:end])
    reader = Reader(original, constructor.offset + 1, 8)
    reader.ptr(); reader.pos = (reader.pos + 3) // 4 * 4
    reader.i(); reader.read('h'); reader.read('H'); reader.ptr()
    size_at = reader.pos; size = reader.i()
    struct.pack_into('<I', a.data, destination + size_at - start, size + added)
    for instruction in block:
        if instruction.op not in (153, 157, 184): continue
        operand = (instruction.offset + 8) // 8 * 8
        new_operand = destination + operand - start + (added if operand >= cut else 0)
        new_end = instruction.end + (added if instruction.end >= cut else 0)
        new_target = instruction.value + (added if instruction.value >= cut else 0)
        struct.pack_into('<i', a.data, new_operand, new_target - new_end)


def wrap(a, parts, name, count, body):
    a.path(*parts); a.string('Server16Original' + name); a.path(*parts); a.member(name); a.op(79)
    a.path(*parts); a.string(name)
    a.op(142); a.align()
    name_at = len(a.data); a.data.extend(bytes(8)); a.fixups.append((name_at, ''))
    a.data.extend(struct.pack('<IHH', count, 8, 41))
    param_at = len(a.data); a.data.extend(bytes(8))
    size_at = len(a.data); a.data.extend(bytes(4)); a.align()
    a.data.extend(struct.pack('<I', 0x98765432)); a.align(); a.data.extend(struct.pack('<Q', 0x12345678))
    start = len(a.data); body(a)
    struct.pack_into('<I', a.data, size_at, len(a.data) - start); a.op(79)
    a.parameters.append((param_at, count))


def append_wrappers(apt, actions, parts, methods):
    start, block = next((s, b) for s, b in actions.cache.items()
                        if b[0].op == 136 and any(i.value == parts[-2] for i in b))
    assert block[-1].op == 0
    data = apt.data; a = Assembler(data); a.align(); new_start = len(data)
    # Guard the entire original class initializer too: this header already has
    # custom coach-stat wrappers which must not capture our wrapper on reload.
    data.extend(apt.entry.original[start:block[0].end])
    # The class may not exist on first startup. Never walk through an absent
    # namespace before the original initializer creates it.
    for count in range(1, len(parts) + 1):
        a.path(*parts[:count]); a.op(18); a.branch('initialize_original')
    a.path(*parts); a.member('Server16CareerBrandInstalled'); a.branch('wrappers_done')
    a.label('initialize_original')
    while len(data) % 8: a.op(89); a.op(23)
    copy_initializer(a, apt, block, constructor_hook=parts == MAIN)
    for name, count, body in methods: wrap(a, parts, name, count, body)
    a.path(*parts); a.string('Server16CareerBrandInstalled'); a.op(115); a.op(79)
    a.label('wrappers_done')
    a.op(0); a.finish()
    signature = struct.pack('<Q', start)
    refs = [at for at in range(0, len(apt.entry.original) - 7, 8)
            if apt.entry.original[at:at + 8] == signature]
    if len(refs) != 1: raise ValueError(f'Ambiguous initialization action: {refs}')
    struct.pack_into('<Q', data, refs[0], new_start)


def logo_characters(apt, image, component_id=13, origin=(109, 73)):
    from formats import Reader, Placement, BigFile
    from PIL import Image
    from texture_ops import _compress, validate_texture
    data = apt.data
    root = Reader(apt.big.entries['1'].data, 20, 8).ptr()
    count, table = struct.unpack_from('<I4xQ', data, root + 56)
    if count != (15 if component_id == 13 else 11): raise ValueError('Unexpected header character table')
    tex, shape, sprite = count, count + 1, count + 2

    def append(blob):
        data.extend(bytes(-len(data) % 8)); at = len(data); data.extend(blob); return at

    # Use the supplied transparent artwork, fitted to a 512x256 DXT5 texture.
    logo = image.convert('RGBA').resize((512, 167), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (512, 256)); canvas.paste(logo, (0, 0))
    texture_base = BigFile(HERE / 'originals/careerhubwidget.big').entries['7'].data
    header = bytearray(texture_base[:128])
    struct.pack_into('<III', header, 12, 256, 512, 512 * 256)
    dds = bytes(header) + _compress(canvas, 'DXT5'); validate_texture(dds)
    tex_blob = bytearray(data[apt.characters[1].offset:apt.characters[1].offset + 40])
    struct.pack_into('<I', tex_blob, 32, tex); tex_at = append(tex_blob)
    shape_blob = bytearray(data[apt.characters[2].offset:apt.characters[2].offset + 56])
    struct.pack_into('<I', shape_blob, 16, tex << 16)
    struct.pack_into('<4fI', shape_blob, 32, 0, 0, 512, 167, shape); shape_at = append(shape_blob)

    template = next(c for f in apt.root_frames for c in f if isinstance(c, Placement))
    inner = bytearray(data[template.offset:template.offset + 80])
    struct.pack_into('<iii6f', inner, 8, 6, 1, shape, 1, 0, 0, 1, 0, 0)
    struct.pack_into('<Q', inner, 56, 0); inner_at = append(inner)
    inner_list = append(struct.pack('<Q', inner_at)); frame_at = append(struct.pack('<I4xQ', 1, inner_list))
    sprite_blob = bytearray(data[apt.characters[5].offset:apt.characters[5].offset + 56])
    struct.pack_into('<I4xQ', sprite_blob, 32, 1, frame_at); sprite_at = append(sprite_blob)

    name_at = append(LOGO.encode() + b'\0')
    placement = bytearray(data[template.offset:template.offset + 80])
    scale = 79 / 167
    # Use the cards' right edge and the career header's top in both menus.
    logo_x, logo_y = 1811 - 512 * scale - origin[0], 73 - origin[1]
    struct.pack_into('<iii6f', placement, 8, 38, 30, sprite, scale, 0, 0, scale, logo_x, logo_y)
    struct.pack_into('<Q', placement, 56, name_at); place_at = append(placement)
    component = apt.characters[component_id]
    original_frames = struct.unpack_from('<Q', data, component.offset + 40)[0]
    controls_n, controls_p = struct.unpack_from('<I4xQ', data, original_frames)
    added_controls = [place_at]
    controls = append(bytes(data[controls_p:controls_p + controls_n * 8]) + struct.pack('<' + 'Q' * len(added_controls), *added_controls))
    frames_at = append(struct.pack('<I4xQ', controls_n + len(added_controls), controls))
    struct.pack_into('<Q', data, component.offset + 40, frames_at)
    new_table = append(bytes(data[table:table + count * 8]) + struct.pack('<3Q', tex_at, shape_at, sprite_at))
    struct.pack_into('<I4xQ', data, root + 56, count + 3, new_table)

    geo = bytearray(apt.big.entries['3'].data)
    struct.pack_into('<I', geo, 16 + 36, tex)
    struct.pack_into('<6f', geo, 16 + 48, 1, 0, 0, 1, 0, 0)
    for index, xy in enumerate(((0,167),(0,0),(512,0),(512,0),(512,167),(0,167))):
        struct.pack_into('<2f', geo, 96 + index * 32, *xy)
    return {str(shape + 1): bytes(geo), str(tex + 1): dds}


def write_big(big, path, additions=None):
    from formats import chunk_wrap
    additions = dict(additions or {}); entries = []
    for name, entry in big.entries.items():
        if name in ('sg1', 'sg2') and additions:
            key = next((k for k, v in additions.items() if v.startswith(b'DDS ') == (name == 'sg2')), None)
            if key is not None: entries.append((key, additions.pop(key)))
        raw = bytes(entry.data) if entry.data != entry.original else big.original[entry.offset:entry.offset + entry.length]
        entries.append((name, raw))
    if additions: raise ValueError('Unplaced resources')
    header = 16 + sum(9 + len(n.encode('latin1')) for n, _ in entries)
    offset = (header + 63) // 64 * 64; directory = bytearray(); payload = bytearray(bytes(offset - header))
    for name, blob in entries:
        pad = -offset % 64; payload.extend(bytes(pad)); offset += pad
        directory.extend(struct.pack('>II', offset, len(blob)) + name.encode('latin1') + b'\0')
        payload.extend(blob); offset += len(blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = b'BIGF' + struct.pack('<I', offset) + struct.pack('>II', len(entries), header) + directory + payload
    path.write_bytes(chunk_wrap(content, big.wrapper) if big.wrapper else content)


def build(output):
    from formats import AptFile, BigFile
    from apt_actions import Actions
    from PIL import Image
    report = []
    definitions = [
        ('careerhubwidget', 'data/ui/game/components/careercomponents', CAREER,
         [('InitComponents', 0, career_init), ('SetData', 0, career_data), ('Shutdown', 0, career_shutdown)]),
        ('easfcwidget', 'data/ui/pow/components', EASFC,
         [('InitializeLayout', 0, easfc_body('InitializeLayout', 0)),
          ('ChangeWidgetState', 3, easfc_body('ChangeWidgetState', 3))]),
        ('mainhubwidget', 'data/ui/game/widgets', MAIN,
         [('Server16ApplyHeader', 0, main_enter), ('Publish', 2, main_publish),
          ('Shutdown', 0, career_shutdown)]),
    ]
    for name, folder, parts, methods in definitions:
        source = HERE / 'originals' / (name + '.big')
        if hashlib.sha256(source.read_bytes()).hexdigest() != BASELINES[name]:
            raise ValueError('Base UI differs from the reviewed version: ' + str(source))
        big = BigFile(source); apt = AptFile(big); actions = Actions(apt).read_all()
        if actions.errors: raise ValueError(actions.errors)
        additions = None
        if name == 'careerhubwidget':
            additions = logo_characters(apt, Image.open(HERE / 'assets/logo.png'))
        elif name == 'mainhubwidget':
            additions = logo_characters(apt, Image.open(HERE / 'assets/logo.png'), 9, (122, 80))
        elif name == 'easfcwidget':
            suppress_banner_first_paint(apt)
        append_wrappers(apt, actions, parts, methods)
        dest = output / folder / (name + '.big'); write_big(big, dest, additions)
        checked = BigFile(dest); parsed = AptFile(checked); decoded = Actions(parsed).read_all()
        if decoded.errors: raise ValueError(decoded.errors)
        # Every preexisting resource other than APT must stay byte-identical.
        for key, entry in big.entries.items():
            if key != apt.entry.name and bytes(checked.entries[key].data) != entry.original:
                raise ValueError(f'Existing resource changed: {key}')
        report.append({'path': str(dest.relative_to(output)), 'bytes': dest.stat().st_size,
                       'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'apt_functions': len(decoded.functions)})
    (output / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--studio', type=Path, default=Path('U:/fifa 16/ScoreboardStudio'))
    args = parser.parse_args(); sys.path.insert(0, str(args.studio)); build(args.output)
