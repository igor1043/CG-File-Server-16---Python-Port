"""Create an external, resident-SPS intro music profile for FIFA 16.

The script only reads the game's BIG banks. It writes the source track, one
quad-channel EALayer3 asset, and an offset map under <game>/IntroMusic.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from server16_py.narration_bank import BigArchive, HarmonyBank, sps_size  # noqa: E402

DEFAULT_GAME = Path(r'U:\fifa 16')
DEFAULT_SX = Path(r'J:\mods\fifa 16\02_Ferramentas\FIFA16AudioTool\FIFA16AudioTool\tools\ea_soundexchange\sx_6.00.00\sx\sx.exe')
DEFAULT_VGM = Path(r'J:\mods\fifa 16\02_Ferramentas\FIFA16AudioTool\FIFA16AudioTool\vgmstream-cli.exe')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def u32(value: int) -> bytes:
    return struct.pack('<I', value)


def safe_name(value: str) -> str:
    value = value.strip().rstrip(' .')
    if not value or value in ('.', '..') or not re.fullmatch(r'[\w .()\-]+', value, re.UNICODE):
        raise ValueError('Use um nome simples para o perfil, sem caminho ou caracteres de arquivo.')
    return value


def find_bank(game_root: Path, archive_name: str, bank_path: str):
    archive = BigArchive(game_root / archive_name)
    wanted = bank_path.casefold()
    matches = [entry for entry in archive.entries if entry.name.replace('\\', '/').casefold() == wanted]
    if len(matches) != 1:
        raise ValueError(f'{archive_name}: esperado um banco {bank_path}, encontrados {len(matches)}')
    bank = HarmonyBank(archive.read(matches[0]))
    offsets = sorted({row['offset'] for row in bank.rows if row['storage'] == 'sbs'})
    references = sum(1 for row in bank.rows if row['storage'] == 'sbs')
    if not offsets:
        raise ValueError(f'O banco {bank_path} não contém referências SBS.')
    return offsets, references


def run_checked(args, *, cwd=None, timeout=180):
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    if result.returncode:
        detail = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        raise RuntimeError(f'Falha ao executar {Path(args[0]).name}: {detail[-3000:]}')
    return result


def encode_track(source: Path, stage: Path, ffmpeg: str, sx: Path, vgm: Path):
    work = stage / '.work'
    work.mkdir()
    stereo = work / 'stereo48.wav'
    quad = work / 'quad48.wav'
    sps = work / 'intro_track.sps'
    decoded = work / 'verify.wav'
    run_checked([
        ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
        '-vn', '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', str(stereo),
    ])
    run_checked([
        ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(stereo),
        '-af', 'pan=quad|c0=c0|c1=c1|c2=c0|c3=c1', '-ar', '48000',
        '-c:a', 'pcm_s16le', str(quad),
    ])
    run_checked([
        str(sx), '-sndplayer', '-fileformatversion1', '-ealayer3pcm_int',
        '-playlocram', '-rs48000', '-noprogress', '-v1', str(quad), '-=intro_track',
    ], cwd=work)
    # SX derives the output basename from the final -=<name> option.
    if not sps.is_file():
        candidates = list(work.glob('intro_track*.sps'))
        if len(candidates) != 1:
            raise RuntimeError('O encoder não criou um único SPS de saída.')
        sps = candidates[0]
    run_checked([str(vgm), '-i', '-o', str(decoded), str(sps)], timeout=120)
    with wave.open(str(quad), 'rb') as expected, wave.open(str(decoded), 'rb') as actual:
        if (expected.getnchannels(), expected.getframerate()) != (4, 48000):
            raise RuntimeError('A fonte preparada não ficou em 4 canais / 48 kHz.')
        expected_duration = expected.getnframes() / expected.getframerate()
        actual_duration = actual.getnframes() / actual.getframerate()
        if (actual.getnchannels(), actual.getframerate()) != (4, 48000):
            raise RuntimeError('O SPS decodificado não ficou em 4 canais / 48 kHz.')
        if abs(expected_duration - actual_duration) > 0.05:
            raise RuntimeError(f'Duração SPS divergente: {expected_duration:.3f}s vs {actual_duration:.3f}s')
    payload = sps.read_bytes()
    _start, length = sps_size(payload)
    if length != len(payload):
        raise RuntimeError('O SPS contém bytes fora do áudio codificado.')
    details = {'duration_seconds': round(actual_duration, 3), 'sample_rate': 48000,
               'channels': 4, 'sps_bytes': len(payload)}
    shutil.rmtree(work)
    return payload, details


def write_package(package: Path, payload: bytes, banks: dict[str, list[int]]):
    # F16NPK3 stores the full SPS once; every physical bank offset references
    # pool item 0. SBR aliases remain handled by their shared SBS offset.
    out = bytearray(b'F16NPK3\0' + u32(1) + u32(len(payload)) + payload + u32(len(banks)))
    for bank_path, offsets in sorted(banks.items()):
        encoded_path = bank_path.encode('utf-16le')
        out += u32(len(encoded_path) // 2) + encoded_path + u32(len(offsets))
        for offset in offsets:
            out += struct.pack('<QI', offset, 0)
    package.write_bytes(out)


def validate_package(package: Path, payload: bytes, banks: dict[str, list[int]]):
    data = package.read_bytes()
    if data[:8] != b'F16NPK3\0':
        raise RuntimeError('Assinatura do pacote inesperada.')
    position = 8

    def take_u32():
        nonlocal position
        if position + 4 > len(data):
            raise RuntimeError('Pacote truncado ao ler u32.')
        value = struct.unpack_from('<I', data, position)[0]
        position += 4
        return value

    if take_u32() != 1:
        raise RuntimeError('O pacote deveria conter um único SPS compartilhado.')
    payload_size = take_u32()
    if payload_size != len(payload) or data[position:position + payload_size] != payload:
        raise RuntimeError('O SPS dentro do pacote difere do áudio validado.')
    position += payload_size
    if take_u32() != len(banks):
        raise RuntimeError('Quantidade de bancos divergente no pacote.')
    seen = set()
    for _ in range(len(banks)):
        path_length = take_u32()
        byte_length = path_length * 2
        if position + byte_length > len(data):
            raise RuntimeError('Caminho de banco truncado.')
        bank_path = data[position:position + byte_length].decode('utf-16le')
        position += byte_length
        if bank_path in seen or bank_path not in banks:
            raise RuntimeError(f'Banco inesperado/duplicado: {bank_path}')
        seen.add(bank_path)
        if take_u32() != len(banks[bank_path]):
            raise RuntimeError(f'Quantidade de offsets divergente em {bank_path}.')
        actual = []
        for _ in banks[bank_path]:
            if position + 12 > len(data):
                raise RuntimeError('Referência a SPS truncada.')
            offset, pool_index = struct.unpack_from('<QI', data, position)
            position += 12
            if pool_index != 0:
                raise RuntimeError('A referência não aponta para o SPS compartilhado.')
            actual.append(offset)
        if actual != banks[bank_path]:
            raise RuntimeError(f'Offsets divergentes em {bank_path}.')
    if position != len(data):
        raise RuntimeError('O pacote contém bytes restantes após a tabela de bancos.')


def build(source: Path, game_root: Path, name: str, ffmpeg: str, sx: Path, vgm: Path):
    source = source.resolve()
    game_root = game_root.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not (game_root / 'fifa16.exe').is_file():
        raise FileNotFoundError(f'Raiz FIFA 16 não encontrada: {game_root}')
    for tool in (sx, vgm):
        if not tool.is_file():
            raise FileNotFoundError(f'Ferramenta não encontrada: {tool}')
    name = safe_name(name)
    root = game_root / 'IntroMusic'
    root.mkdir(parents=True, exist_ok=True)
    destination = root / name
    stage = root / ('.' + name + '.building')
    if destination.exists() or stage.exists():
        raise FileExistsError(f'O perfil já existe: {destination}')
    stage.mkdir()
    try:
        source_copy = stage / ('source' + source.suffix.lower())
        shutil.copy2(source, source_copy)
        payload, audio = encode_track(source, stage, ffmpeg, sx, vgm)
        bank_specs = {
            'audiodata/sfx/intromusic_01.sbs': ('data_audio3.big', 'audiodata/sfx/intromusic_01.sbr'),
            'audiodata/sfx/intromusic_02.sbs': ('data_audio3_extra.big', 'audiodata/sfx/intromusic_02.sbr'),
        }
        bank_offsets = {}
        references = {}
        for sbs_path, (archive, sbr_path) in bank_specs.items():
            offsets, count = find_bank(game_root, archive, sbr_path)
            bank_offsets[sbs_path] = offsets
            references[sbs_path] = {'sbr_archive': archive, 'sbr_path': sbr_path,
                                    'unique_sbs_offsets': len(offsets), 'logical_references': count}
        write_package(stage / 'profile.npack', payload, bank_offsets)
        validate_package(stage / 'profile.npack', payload, bank_offsets)
        metadata = {
            'name': name,
            'version': 1,
            'package': 'profile.npack',
            'source_audio': source_copy.name,
            'source_sha256': hashlib.sha256(source_copy.read_bytes()).hexdigest(),
            'encoding': 'EA EALayer3 SPS, 4 channels, 48000 Hz',
            'audio': audio,
            'banks': references,
            'mapped_unique_offsets': sum(len(offsets) for offsets in bank_offsets.values()),
            'original_fallback': True,
            'archive_policy': 'Read-only. Original .big/.bh banks are unchanged; runtime redirects matching in-memory playback events.',
        }
        (stage / 'profile.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        (stage / 'LEIA-ME.txt').write_text(
            'Perfil de música de entrada do FIFA 16\n\n'
            'Este perfil guarda a faixa fonte e um pacote SPS externo. O Server16 carrega o perfil em memória e direciona as duas banks intromusic para esta faixa antes do jogo.\n'
            'Os arquivos originais data_audio*.big e .bh permanecem intactos. Para voltar à música original, defina enabled como false em settings.json.\n',
            encoding='utf-8')
        # Validate the exact package bytes before activating the default.
        if (stage / 'profile.npack').stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError('Pacote passou do limite por SPS do hook nativo.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage.replace(destination)

        settings_path = root / 'settings.json'
        try:
            settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.is_file() else {}
            if not isinstance(settings, dict):
                settings = {}
        except ValueError:
            settings = {}
        settings.update(version=1, enabled=True, default_profile=name)
        temporary = settings_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(settings_path)
        readme = root / 'LEIA-ME.txt'
        if not readme.exists():
            readme.write_text(
                'Música de entrada externa do FIFA 16\n\n'
                'O Server16 carrega o perfil definido em settings.json quando a partida está na tela de pré-jogo.\n'
                'A troca redireciona as referências da música em memória; os arquivos originais .big/.bh não são alterados.\n'
                'Para voltar à música original, altere enabled para false em settings.json e abra novamente a prévia/pré-jogo.\n'
                'Cada perfil mantém source.* (áudio de origem), profile.npack (SPS pronto) e profile.json (inventário dos bancos).\n',
                encoding='utf-8')
        print(json.dumps({'profile': str(destination), 'settings': str(settings_path), **metadata}, ensure_ascii=False, indent=2))
        return destination
    except Exception:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--game-root', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--name', default='Teste Libertadores 2025')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg') or 'ffmpeg')
    parser.add_argument('--sx', type=Path, default=DEFAULT_SX)
    parser.add_argument('--vgm', type=Path, default=DEFAULT_VGM)
    args = parser.parse_args()
    build(args.source, args.game_root, args.name, args.ffmpeg, args.sx, args.vgm)


if __name__ == '__main__':
    main()
