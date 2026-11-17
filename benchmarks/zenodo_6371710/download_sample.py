"""Baixa uma amostra reproduzível do dataset Zenodo 6371710.

O ZIP de imagens tem 410 MB. Este script lê o índice ZIP via HTTP Range e
transfere somente os arquivos selecionados, preservando as anotações originais.
"""

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


RECORD = "https://zenodo.org/records/6371710"
IMAGE_URL = f"{RECORD}/files/1_Images.zip?download=1"
ANNOTATION_URL = f"{RECORD}/files/2_Annotations_Json.zip?download=1"
ANNOTATION_MD5 = "941deec66609f158cfd7ce5add75a17b"
SAMPLE_IDS = (
    "20210316_223932",  # sem NIF do comprador e IVA
    "20210318_111551",
    "20210318_111820",
    "20210318_113425",  # campos ausentes no gabarito
    "20210318_122114",
    "20210318_122424",
    "20210318_172300",
    "20210318_172420",
    "20210318_201052",
    "20210318_201242",
    "20210318_201429",
    "20210318_201639",
)
ROOT = Path(__file__).resolve().parent


def request_bytes(url: str, byte_range: tuple[int, int] | None = None) -> bytes:
    headers = {"User-Agent": "fiscal-reader-dataset-sampler/1.0"}
    if byte_range is not None:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=120
            ) as response:
                data = response.read()
                if byte_range is not None:
                    expected = byte_range[1] - byte_range[0] + 1
                    if response.status != 206 or len(data) != expected:
                        raise RuntimeError(
                            f"HTTP Range inesperado: {response.status}, {len(data)} bytes"
                        )
                return data
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    annotation_path = ROOT / "annotations_original.zip"
    if not annotation_path.exists():
        annotation_path.write_bytes(request_bytes(ANNOTATION_URL))
    digest = hashlib.md5(annotation_path.read_bytes()).hexdigest()
    if digest != ANNOTATION_MD5:
        raise ValueError(f"MD5 das anotações não confere: {digest}")

    with zipfile.ZipFile(annotation_path) as labels_zip:
        labels = {
            sample_id: labels_zip.read(
                f"2_Annotations_Json/{sample_id}.txt"
            )
            for sample_id in SAMPLE_IDS
        }

    size = 410_222_137  # tamanho publicado no cabeçalho HTTP
    tail_start = size - 1024
    tail = request_bytes(IMAGE_URL, (tail_start, size - 1))
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("Fim do ZIP não encontrado")
    _, _, _, _, _, directory_size, directory_offset, _ = struct.unpack_from(
        "<4s4H2LH", tail, eocd
    )
    directory = request_bytes(
        IMAGE_URL,
        (directory_offset, directory_offset + directory_size - 1),
    )

    # Um ZIP esparso permite usar zipfile para validar CRC sem transferir as
    # imagens não selecionadas. Seu tamanho físico é só o dos blocos baixados.
    with tempfile.TemporaryDirectory(prefix="fiscal-reader-zip-") as tempdir:
        sparse_path = Path(tempdir) / "images.zip"
        with sparse_path.open("wb") as sparse:
            sparse.truncate(size)
            sparse.seek(directory_offset)
            sparse.write(directory)
            sparse.seek(tail_start)
            sparse.write(tail)

        with zipfile.ZipFile(sparse_path) as archive:
            infos = archive.infolist()
            by_name = {info.filename: info for info in infos}
            ordered = sorted(infos, key=lambda info: info.header_offset)
            next_offset = {
                info.filename: ordered[index + 1].header_offset
                if index + 1 < len(ordered)
                else directory_offset
                for index, info in enumerate(ordered)
            }
            selected = [
                by_name[f"1_Images/{sample_id}.jpg"]
                for sample_id in SAMPLE_IDS
            ]

        with sparse_path.open("r+b") as sparse:
            for info in selected:
                start = info.header_offset
                end = next_offset[info.filename] - 1
                block = request_bytes(IMAGE_URL, (start, end))
                sparse.seek(start)
                sparse.write(block)

        image_dir = ROOT / "images"
        label_dir = ROOT / "labels_original"
        image_dir.mkdir(exist_ok=True)
        label_dir.mkdir(exist_ok=True)
        manifest = []
        with zipfile.ZipFile(sparse_path) as archive:
            for sample_id, info in zip(SAMPLE_IDS, selected, strict=True):
                image = archive.read(info)  # verifica CRC32 do ZIP original
                image_path = image_dir / f"{sample_id}.jpg"
                image_path.write_bytes(image)
                label_path = label_dir / f"{sample_id}.txt"
                label_path.write_bytes(labels[sample_id])
                manifest.append(
                    {
                        "id": sample_id,
                        "image": str(image_path.relative_to(ROOT)),
                        "image_sha256": hashlib.sha256(image).hexdigest(),
                        "label": str(label_path.relative_to(ROOT)),
                        "label_sha256": hashlib.sha256(labels[sample_id]).hexdigest(),
                        "fields": json.loads(labels[sample_id]),
                    }
                )
                print(f"OK {sample_id}.jpg ({len(image)} bytes)")

    (ROOT / "manifest.json").write_text(
        json.dumps(
            {"source": RECORD, "doi": "10.5281/zenodo.6371710", "samples": manifest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
