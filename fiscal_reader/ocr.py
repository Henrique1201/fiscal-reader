"""OCR local para fotos e páginas digitalizadas."""

from __future__ import annotations

import os
import sys
from contextlib import redirect_stdout
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _paddle_model():
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "paddlex"))
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise ValueError(
            "PaddleOCR não instalado. Veja a instalação no README ou use --ocr tesseract"
        ) from exc
    try:
        return PaddleOCR(
            ocr_version="PP-OCRv5",
            lang="pt",
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
        )
    except Exception as exc:
        raise ValueError(f"Não foi possível carregar o modelo PaddleOCR: {exc}") from exc


def read_image(path: Path) -> list[dict]:
    """Retorna linhas com texto, confiança e posição, na ordem do modelo."""
    try:
        with redirect_stdout(sys.stderr):
            predictions = list(_paddle_model().predict(str(path)))
        output = []
        for prediction in predictions:
            data = prediction.json
            if "res" in data:
                data = data["res"]
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_boxes", [])
            if len(texts) != len(scores):
                raise ValueError("PaddleOCR retornou textos e confianças incompatíveis")
            for index, (text, score) in enumerate(zip(texts, scores, strict=True)):
                if not text.strip():
                    continue
                if index >= len(boxes):
                    box = None
                elif hasattr(boxes[index], "tolist"):
                    box = boxes[index].tolist()
                else:
                    box = list(boxes[index])
                output.append({
                    "texto": text.strip(),
                    "confianca": round(float(score), 3),
                    "caixa": box,
                })
        return output
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Falha no PaddleOCR ao ler {path.name}: {exc}") from exc
