"""Baixa imagens e ground truth por item do split de teste CORD v2."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATASET = "naver-clova-ix/cord-v2"
API = (
    "https://datasets-server.huggingface.co/rows?"
    "dataset=naver-clova-ix%2Fcord-v2&config=default&split=test&offset=0&length=100"
)
ROW_IDS = (13, 21, 24, 39, 47, 60, 61, 79, 81, 82)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "fiscal-reader-benchmark/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def main() -> None:
    payload = json.loads(fetch(API))
    if any(entry["truncated_cells"] for entry in payload["rows"] if entry["row_idx"] in ROW_IDS):
        raise ValueError("A API truncou um dos rótulos selecionados")
    by_index = {entry["row_idx"]: entry["row"] for entry in payload["rows"]}
    if len(by_index) != 100 or payload["partial"]:
        raise ValueError("Resposta incompleta da API do dataset")
    image_dir = ROOT / "images"
    label_dir = ROOT / "labels_original"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    samples = []
    for index in ROW_IDS:
        row = by_index[index]
        raw_label = row["ground_truth"]
        if not isinstance(raw_label, str):
            raise ValueError(f"Rótulo CORD da linha {index} não é texto")
        ground_truth = json.loads(raw_label)
        menu = ground_truth["gt_parse"].get("menu", [])
        menu = menu if isinstance(menu, list) else [menu]
        if not menu or any(not all(key in item for key in ("nm", "cnt", "price")) for item in menu):
            raise ValueError(f"Linha {index} não tem os campos por item esperados")

        name = f"cord_test_{index:03d}"
        image_path = image_dir / f"{name}.jpg"
        label_path = label_dir / f"{name}.json"
        image = fetch(row["image"]["src"])
        image_path.write_bytes(image)
        label_path.write_text(raw_label + "\n", encoding="utf-8")
        label_bytes = label_path.read_bytes()
        samples.append(
            {
                "id": name,
                "row_idx": index,
                "split": "test",
                "image": str(image_path.relative_to(ROOT)),
                "image_sha256": hashlib.sha256(image).hexdigest(),
                "label": str(label_path.relative_to(ROOT)),
                "label_sha256": hashlib.sha256(label_bytes).hexdigest(),
                "item_count": len(menu),
            }
        )
        print(f"OK {name}: {len(menu)} itens", flush=True)

    manifest = {
        "source": "https://huggingface.co/datasets/naver-clova-ix/cord-v2",
        "api": API,
        "dataset": DATASET,
        "revision": by_index[ROW_IDS[0]]["image"]["src"].split("/--/")[1].split("/")[0],
        "split": "test",
        "samples": samples,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
