"""Import ordinary artwork into the career calendar without hand-edited catalogues."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import threading
import time
import unicodedata

from PIL import Image, ImageOps

ICONS = Path('data/ui/imgAssets/careerCompetitionIcons')
COMP_OBJ = Path('dlc/dlc_FootballCompEng/dlc/FootballCompEng/data/compdata/compobj.txt')
ICON_MAP = Path('ModCarrerMode/data/catalogs/career_competition_icon_map.tsv')
FIELDS = ['visual_id', 'filename', 'source_big', 'dds_sha256', 'alpha_bounds', 'host_available']
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.dds'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalized(name):
    text = unicodedata.normalize('NFKD', name.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).strip()


def identities(game):
    """Follow the same explicit-map / TrophyName / C<ID> precedence as the host."""
    mapping, labels, aliases = {}, {}, {}
    path = game / COMP_OBJ
    if path.is_file():
        for row in csv.reader(path.read_text(encoding='utf-8-sig').splitlines()):
            if len(row) < 5 or row[1] != '3':
                continue
            explicit = re.search(r'TrophyName_Abbr15_(\d+)', row[3])
            generic = re.fullmatch(r'C(\d+)', row[2])
            match = explicit or generic
            if match and row[0].isdigit():
                mapping[int(row[0])] = int(match[1])
    path = game / ICON_MAP
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'\s*(\d+)\s*\|\s*(\d+)\s*', line)
            if match:
                mapping[int(match[1])] = int(match[2])
    mapping = {key: value for key, value in mapping.items() if 0 < key <= 65535 and 0 < value <= 65535}
    path = game / 'FSW/settings.ini'
    if path.is_file():
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        for section in ('Scoreboard', 'movies'):
            block = re.search(r'^\[' + section + r'\][ \t]*\r?\n(.*?)(?=^\[|\Z)', text, re.M | re.S | re.I)
            if not block:
                continue
            for line in block[1].splitlines():
                match = re.match(r'^\s*(\d+)\s*=(.*)', line)
                if not match or int(match[1]) not in mapping:
                    continue
                key, label = int(match[1]), match[2].split(',')[0].strip()
                if label and label.casefold() not in ('none', 'default'):
                    labels[key] = label
                    aliases.setdefault(normalized(label), set()).add(mapping[key])
    return mapping, labels, aliases


def resolve(stem, mapping, aliases):
    # Bare numbers are competition IDs. c<number> explicitly means a visual ID.
    match = re.fullmatch(r'c(\d+)', stem, re.I)
    if match and int(match[1]) in mapping.values():
        return int(match[1])
    match = re.match(r'^(\d+)(?:\s*[-_]\s*.+)?$', stem)
    if match and int(match[1]) in mapping:
        return mapping[int(match[1])]
    candidates = aliases.get(normalized(stem), set())
    if len(candidates) == 1:
        return next(iter(candidates))
    raise ValueError('competição não identificada ou nome ambíguo; use um nome da lista COMPETICOES.txt')


def convert(raw):
    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        image = ImageOps.exif_transpose(source).convert('RGBA')
    bounds = image.getchannel('A').getbbox()
    if not bounds:
        raise ValueError('imagem totalmente transparente')
    image = image.crop(bounds)
    image.thumbnail((46, 46), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (128, 128))
    canvas.paste(image, ((48 - image.width) // 2, (48 - image.height) // 2))
    output = io.BytesIO()
    canvas.save(output, format='DDS', pixel_format='DXT5')
    data = output.getvalue()
    if len(data) != 16512 or data[:4] != b'DDS ' or data[84:88] != b'DXT5':
        raise ValueError('a versão do Pillow instalada não produz DDS DXT5; atualize o Server16')
    return data, ','.join(map(str, canvas.getchannel('A').getbbox()))


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class CompetitionIconImporter:
    def __init__(self, game, log=print):
        self.game = Path(game)
        self.folder = self.game / ICONS
        self.log = log
        self.reported = set()
        self.observed = {}

    def _report(self, name, detail):
        key = (name, detail)
        if key not in self.reported:
            self.reported.add(key)
            self.log(f'Ícones da carreira: {name}: {detail}')

    def _instructions(self, mapping, labels):
        text = ('ÍCONES DAS COMPETIÇÕES\n\n'
                'Coloque aqui uma imagem PNG, JPG, WEBP ou BMP com um dos nomes da lista abaixo.\n'
                'Abra o Server16 atualizado e aguarde alguns segundos ANTES de abrir o FIFA.\n'
                'O Server converte, dimensiona e cadastra o ícone automaticamente. Não edite o index.tsv.\n'
                'Prefira PNG com fundo transparente. A imagem original fica preservada.\n'
                'Se o FIFA já estiver aberto, a aplicação fica para a próxima abertura do jogo.\n'
                'Não coloque duas imagens da mesma competição; substitua a imagem existente.\n'
                'Apenas o nome é usado para identificar a competição, não o desenho do logo.\n'
                'Esta função troca os ícones de competições existentes; não cria campeonatos.\n\n'
                'Exemplos de nomes aceitos (troque .png por .jpg se necessário):\n')
        for key in sorted(mapping):
            label = re.sub(r'[<>:"/\\|?*]', '-', labels.get(key, 'Competição ' + str(key)))
            text += f'{key} - {label}.png\n'
        path = self.folder / 'COMPETICOES.txt'
        data = text.encode('utf-8-sig')
        if not path.is_file() or path.read_bytes() != data:
            atomic_write(path, data)

    def _recover_missing_index(self, mapping):
        index = self.folder / 'index.tsv'
        if index.is_file():
            return
        canonical = set(mapping.values())
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=FIELDS, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        for path in sorted(self.folder.iterdir()):
            match = re.fullmatch(r'c(\d+)\.dds', path.name, re.I)
            if not match or not path.is_file() or not 0 < int(match[1]) <= 65535:
                continue
            raw = path.read_bytes()
            if (len(raw) < 16512 or raw[:4] != b'DDS ' or raw[84:88] != b'DXT5'
                    or struct.unpack_from('<I', raw, 4)[0] != 124
                    or struct.unpack_from('<II', raw, 12) != (128, 128)):
                continue
            writer.writerow(dict(visual_id=match[1], filename=path.name, source_big='existing DDS',
                                 dds_sha256=digest(raw), alpha_bounds='',
                                 host_available=str(int(int(match[1]) in canonical))))
        atomic_write(index, output.getvalue().encode('utf-8'))
        self.log('Ícones da carreira: índice interno reconstruído pelas competições instaladas.')

    def sync(self, force=False):
        mapping, labels, aliases = identities(self.game)
        if not mapping:
            return 0
        self.folder.mkdir(parents=True, exist_ok=True)
        self._instructions(mapping, labels)
        self._recover_missing_index(mapping)
        state_path = self.game / 'runtime/career_icons/state.json'
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else {}
        pending = {}
        for path in sorted(self.folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            # These are the native outputs, including legacy aliases: never re-import them.
            if path.suffix.lower() == '.dds' and re.fullmatch(r'c\d+', path.stem, re.I):
                continue
            try:
                visual = resolve(path.stem, mapping, aliases)
                pending.setdefault(visual, []).append(path)
            except ValueError as exc:
                self._report(path.name, str(exc))
        installed = 0
        for visual, paths in pending.items():
            if len(paths) != 1:
                self._report(str(visual), 'mais de uma imagem para a mesma competição: ' + ', '.join(p.name for p in paths))
                continue
            path = paths[0]
            try:
                stamp = (path.stat().st_size, path.stat().st_mtime_ns)
                old_stamp = self.observed.get(path.name)
                self.observed[path.name] = stamp
                # A periodic scan waits for two unchanged observations (file copy may be in progress).
                if not force and old_stamp != stamp:
                    continue
                raw = path.read_bytes()
                if (path.stat().st_size, path.stat().st_mtime_ns) != stamp:
                    continue
                target = self.folder / f'c{visual}.dds'
                index = self.folder / 'index.tsv'
                fields, rows = FIELDS, []
                if index.is_file():
                    reader = csv.DictReader(io.StringIO(index.read_text(encoding='utf-8-sig')), delimiter='\t')
                    fields = reader.fieldnames
                    if fields is None or not set(FIELDS).issubset(fields):
                        raise ValueError('índice interno inválido; o arquivo foi preservado')
                    rows = list(reader)
                    if any(None in row or any(value is None for value in row.values()) for row in rows):
                        raise ValueError('índice interno incompleto; o arquivo foi preservado')
                record = state.get(path.name, {})
                active_rows = [row for row in rows if row['visual_id'] == str(visual)]
                if (record.get('source') == digest(raw) and record.get('visual') == visual and target.is_file()
                        and record.get('output') == digest(target.read_bytes())
                        and len(active_rows) == 1 and active_rows[0]['host_available'] == '1'):
                    continue
                data, bounds = convert(raw)
                row = dict.fromkeys(fields, '')
                row.update(visual_id=str(visual), filename=target.name, source_big=path.name,
                           dds_sha256=digest(data), alpha_bounds=bounds, host_available='1')
                rows = [item for item in rows if item['visual_id'] != str(visual)] + [row]
                output = io.StringIO(newline='')
                writer = csv.DictWriter(output, fieldnames=fields, delimiter='\t', lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
                new_state = dict(state)
                new_state[path.name] = {'source': digest(raw), 'visual': visual, 'output': digest(data)}
                updates = {target: data, index: output.getvalue().encode('utf-8'),
                           state_path: json.dumps(new_state, ensure_ascii=False, indent=2).encode('utf-8')}
                before = {dest: dest.read_bytes() if dest.is_file() else None for dest in updates}
                backup = self.game / 'runtime/backups/career_competition_icons' / str(time.time_ns())
                for dest, content in before.items():
                    if content is not None:
                        atomic_write(backup / dest.relative_to(self.game), content)
                atomic_write(backup / 'manifest.json', json.dumps({
                    'source': path.name, 'sha256': digest(raw),
                    'files': {dest.relative_to(self.game).as_posix(): digest(value) if value is not None else None
                              for dest, value in before.items()}}, indent=2).encode('utf-8'))
                try:
                    for dest, content in updates.items():
                        atomic_write(dest, content)
                except Exception:
                    for dest, content in before.items():
                        if content is not None:
                            atomic_write(dest, content)
                        elif dest.is_file():
                            dest.unlink()
                    raise
                state = new_state
                installed += 1
                self.log(f'Ícones da carreira: {path.name} aplicado automaticamente ({target.name}).')
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                self._report(path.name, str(exc))
        return installed


class CompetitionIconService:
    """One worker, no Tk calls; writes only while FIFA is closed."""
    def __init__(self, log):
        self.log = log
        self.lock = threading.Lock()
        self.worker = None
        self.importer = None

    @property
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def prepare(self, game, force=False):
        with self.lock:
            if self.importer is None or self.importer.game != Path(game):
                self.importer = CompetitionIconImporter(game, self.log)
            try:
                return self.importer.sync(force=force)
            except Exception as exc:
                self.importer._report('serviço', str(exc))
                return 0

    def poll(self, game, game_running):
        if game_running or self.busy:
            return
        self.worker = threading.Thread(target=self.prepare, args=(Path(game),), name='career-icon-import', daemon=True)
        self.worker.start()
