"""Interface de linha de comando e tabela CSV padrão."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .extract import extract
from .llm import HEADER_FIELDS, ITEM_FIELDS, MODEL, OLLAMA_MODEL, interpret

CSV_FIELDS = ("arquivo", "formato", "motor_ocr", "confianca_ocr_media", *HEADER_FIELDS, *ITEM_FIELDS, "observacoes", "status_revisao")
AUTHORITATIVE_ITEM_FIELDS = tuple(name for name in ITEM_FIELDS if name != "categoria_item")
SUPPORTED_SUFFIXES = {".xml", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _expand_inputs(paths: list[Path]) -> list[Path]:
    expanded = []
    seen = set()
    for path in paths:
        candidates = (sorted(file for file in path.rglob("*") if file.is_file() and file.suffix.lower() in SUPPORTED_SUFFIXES)
                      if path.is_dir() else [path])
        for candidate in candidates:
            identity = candidate.resolve()
            if identity not in seen:
                expanded.append(candidate)
                seen.add(identity)
    return expanded


def _rows(path: Path, features: dict, result: dict) -> list[dict]:
    header = result["cabecalho"].copy()
    items = result["itens"]
    if features["formato"] == "xml_nfe":
        header.update(features["cabecalho"])
        if header["data_emissao"]:
            header["data_emissao"] = header["data_emissao"][:10]
        items = [
            {**item, **{name: original.get(name) for name in AUTHORITATIVE_ITEM_FIELDS}}
            for item, original in zip(items, features["itens"], strict=True)
        ]
    if not items:
        items = [{name: None for name in ITEM_FIELDS}]
    status = "conferir_categoria" if features["formato"] == "xml_nfe" else "revisar_extracao"
    scores = [line["confianca"] for line in features.get("linhas_ocr", []) if isinstance(line.get("confianca"), (int, float))]
    average = f"{sum(scores) / len(scores):.3f}" if scores else None
    return [
        {"arquivo": str(path), "formato": features["formato"], "motor_ocr": features.get("motor_ocr"),
         "confianca_ocr_media": average, **header, **item,
         "observacoes": result["observacoes"], "status_revisao": status}
        for item in items
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extrai notas fiscais e gera tabela CSV com apoio de LLM")
    parser.add_argument("arquivos", nargs="+", type=Path, help="XML, PDF, imagem ou pasta com notas")
    parser.add_argument("-o", "--saida", type=Path, default=Path("notas.csv"), help="CSV de saída (padrão: notas.csv)")
    local_modes = parser.add_mutually_exclusive_group()
    local_modes.add_argument("--features-only", action="store_true", help="mostra JSON extraído localmente; não usa API nem cria CSV")
    local_modes.add_argument("--ocr-text", action="store_true", help="mostra somente o texto OCR; não usa API nem cria CSV")
    parser.add_argument("--ocr", choices=("paddle", "tesseract"), default="paddle", help="motor para fotos e PDFs digitalizados (padrão: paddle)")
    parser.add_argument("--provider", choices=("gemini", "ollama"), default="gemini", help="provedor LLM (padrão: gemini)")
    parser.add_argument("--model", help=f"modelo do provedor (padrões: Gemini {MODEL}; Ollama {OLLAMA_MODEL})")
    args = parser.parse_args(argv)
    rows = []
    had_error = False
    files = _expand_inputs(args.arquivos)
    if not files:
        print("ERRO: nenhuma nota encontrada", file=sys.stderr)
        return 1
    for path in files:
        try:
            features = extract(path, ocr=args.ocr)
            if args.ocr_text:
                if features["formato"] == "xml_nfe":
                    raise ValueError("--ocr-text é para imagem/PDF; use --features-only para XML")
                if len(files) > 1:
                    print(f"### {path}")
                print(features["texto"])
                continue
            if args.features_only:
                print(json.dumps({"arquivo": str(path), "features": features}, ensure_ascii=False))
                continue
            rows.extend(_rows(path, features, interpret(features, model=args.model, provider=args.provider)))
            print(f"OK: {path}", file=sys.stderr)
        except (ValueError, OSError) as exc:
            had_error = True
            print(f"ERRO: {path}: {exc}", file=sys.stderr)
    if args.features_only or args.ocr_text:
        return 1 if had_error else 0
    if rows:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        with args.saida.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} linha(s) gravadas em {args.saida}", file=sys.stderr)
    return 1 if had_error or not rows else 0
