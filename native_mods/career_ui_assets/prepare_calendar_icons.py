"""Copy the exact working DDS payloads from calendar BIGs into the dedicated directory."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import struct
from pathlib import Path

from PIL import Image


def big_entries(data: bytes):
    if data[:4] not in (b"BIGF", b"BIG4"):
        raise ValueError("Not a BIG archive")
    count, index_end = struct.unpack_from(">II", data, 8)
    if count > 10000 or not 16 <= index_end <= len(data):
        raise ValueError("Invalid BIG index")
    pos = 16
    for _ in range(count):
        if pos + 9 > index_end:
            raise ValueError("Truncated BIG index")
        offset, size = struct.unpack_from(">II", data, pos)
        pos += 8
        end = data.index(0, pos, index_end)
        name = data[pos:end].decode("ascii")
        pos = end + 1
        if offset + size > len(data):
            raise ValueError("BIG entry outside archive")
        yield name, data[offset:offset + size]


def validate_dds(data: bytes):
    if len(data) < 16512 or data[:4] != b"DDS " or struct.unpack_from("<I", data, 4)[0] != 124:
        raise ValueError("Incomplete DDS")
    if struct.unpack_from("<II", data, 12) != (128, 128) or data[84:88] != b"DXT5":
        raise ValueError("Expected 128x128 DXT5")
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    bounds = image.getchannel("A").getbbox()
    if bounds and (bounds[2] > 48 or bounds[3] > 48):
        raise ValueError(f"Logo outside the upper-left 48x48 area: {bounds}")
    return bounds


def prepare(source: Path, destination: Path):
    packages = source / "data/ui/artassets/cmCalendarCompetitions"
    target = destination / "data/ui/imgAssets/careerCompetitionIcons"
    records = []
    payloads = {}
    for package in sorted(packages.glob("cmcomp_*.big")):
        match = re.fullmatch(r"cmcomp_([1-9][0-9]*)", package.stem)
        if not match or int(match[1]) > 65535:
            continue
        images = [data for _, data in big_entries(package.read_bytes()) if data.startswith(b"DDS ")]
        if len(images) != 1:
            raise ValueError(f"Expected one DDS in {package}")
        ident = int(match[1])
        data = images[0]
        bounds = validate_dds(data)
        name = f"c{ident}.dds"
        existing = target / name
        if existing.exists() and existing.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite an edited icon: {existing}")
        payloads[name] = data
        records.append({
            "visual_id": ident,
            "filename": name,
            "source_big": package.relative_to(source).as_posix(),
            "dds_sha256": hashlib.sha256(data).hexdigest(),
            "alpha_bounds": ",".join(map(str, bounds)) if bounds else "transparent",
            "host_available": int((source / f"data/ui/imgAssets/cmCalendarCompetitions/cmCalendarCompetitions{ident}.dds").exists()),
        })
    if not records:
        raise ValueError(f"No usable calendar packages in {packages}")
    target.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (target / name).write_bytes(data)
    records.sort(key=lambda row: row["visual_id"])
    with (target / "index.tsv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(records)
    (target / "README.txt").write_text(
        "Icones das celulas do calendario da carreira.\n"
        "Nome: c<ID_VISUAL>.dds; ID visual, nao necessariamente ID da liga ou da competicao.\n"
        "DDS DXT5/BC3, canvas 128x128, logo proporcional dentro dos primeiros 48x48 pixels.\n"
        "Todo o resto transparente. Nao centralizar o logo no canvas de 128x128.\n"
        "Substitua o DDS diretamente. Nao e necessario reconstruir cmcomp_<ID>.big.\n"
        "index.tsv registra a origem e o hash das copias iniciais.\n"
        "host_available preserva a disponibilidade original dos IDs (1=aceito; 0=alias antigo nao aceito).\n"
        "IDs novos ausentes do indice sao aceitos quando existe um DDS valido.\n"
        "Requer career_ui_assets versao 3 para redirecionar o carregamento.\n",
        encoding="utf-8",
    )
    return {"copied": len(records), "directory": str(target), "byte_identical_to_big": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source.resolve(), args.destination.resolve()), ensure_ascii=False))
