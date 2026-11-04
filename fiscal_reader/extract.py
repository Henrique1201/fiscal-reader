"""Extração local, sem envio de dados à API."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .ocr import read_image

MAX_FILE_BYTES = 20_000_000
MAX_TEXT_CHARS = 100_000


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((part for part in element if _tag(part) == name), None)


def _value(element: ET.Element | None, *names: str) -> str | None:
    for name in names:
        element = _child(element, name)
    return element.text.strip() if element is not None and element.text else None


def _xml(path: Path) -> dict:
    data = path.read_bytes()
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML com DTD/entidade não é aceito")
    root = ET.fromstring(data)
    inf = next((node for node in root.iter() if _tag(node) == "infNFe"), None)
    if inf is None:
        raise ValueError("XML não contém infNFe (NF-e)")
    ide = _child(inf, "ide")
    emit = _child(inf, "emit")
    dest = _child(inf, "dest")
    total = _child(_child(inf, "total"), "ICMSTot")
    access_key = inf.get("Id", "").removeprefix("NFe") or None
    items = []
    for det in (node for node in inf if _tag(node) == "det"):
        prod = _child(det, "prod")
        items.append({
            "item_numero": det.get("nItem"),
            "codigo": _value(prod, "cProd"),
            "descricao": _value(prod, "xProd"),
            "ncm": _value(prod, "NCM"),
            "cfop": _value(prod, "CFOP"),
            "unidade": _value(prod, "uCom"),
            "quantidade": _value(prod, "qCom"),
            "valor_unitario": _value(prod, "vUnCom"),
            "valor_total_item": _value(prod, "vProd"),
        })
    return {
        "formato": "xml_nfe",
        "cabecalho": {
            "chave_acesso": access_key,
            "numero": _value(ide, "nNF"),
            "serie": _value(ide, "serie"),
            "data_emissao": _value(ide, "dhEmi") or _value(ide, "dEmi"),
            "emitente_nome": _value(emit, "xNome"),
            "emitente_cnpj": _value(emit, "CNPJ") or _value(emit, "CPF"),
            "destinatario_nome": _value(dest, "xNome"),
            "destinatario_cnpj": _value(dest, "CNPJ") or _value(dest, "CPF"),
            "valor_total_nota": _value(total, "vNF"),
        },
        "itens": items,
    }


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except FileNotFoundError as exc:
        raise ValueError(f"Programa necessário não encontrado: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Tempo esgotado ao executar {command[0]}") from exc
    if result.returncode:
        raise ValueError(f"Falha em {command[0]}: {result.stderr.strip()[:300]}")
    return result.stdout


def _pdf(path: Path, engine: str) -> tuple[str, list[dict] | None, str]:
    info = _run(["pdfinfo", str(path)])
    pages_match = re.search(r"^Pages:\s*(\d+)", info, re.MULTILINE)
    if not pages_match:
        raise ValueError("Não foi possível identificar o número de páginas do PDF")
    page_count = int(pages_match.group(1))
    extracted = _run(["pdftotext", "-layout", str(path), "-"]).split("\f")
    text_parts = []
    lines = []
    ocr_pages = 0
    with tempfile.TemporaryDirectory() as temporary:
        for number in range(1, page_count + 1):
            page_text = extracted[number - 1] if number <= len(extracted) else ""
            if len(page_text.strip()) >= 40:
                text_parts.append(page_text.strip())
                continue
            ocr_pages += 1
            if ocr_pages > 20:
                raise ValueError("PDF com mais de 20 páginas digitalizadas; divida o documento")
            prefix = Path(temporary) / f"pagina-{number}"
            _run(["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-r", "200", "-png", str(path), str(prefix)])
            page = prefix.with_suffix(".png")
            if not page.exists():
                raise ValueError(f"Não foi possível renderizar a página {number} do PDF")
            if engine == "paddle":
                page_lines = [{**line, "pagina": number} for line in read_image(page)]
                lines.extend(page_lines)
                text_parts.append("\n".join(line["texto"] for line in page_lines))
            else:
                text_parts.append(_run(["tesseract", str(page), "stdout", "-l", _ocr_language()]).strip())
    text = "\n\n".join(text_parts)
    return text, lines if engine == "paddle" and ocr_pages else None, engine if ocr_pages else "texto_pdf"


def _ocr_language() -> str:
    languages = set(_run(["tesseract", "--list-langs"]).splitlines())
    if "por" in languages:
        return "por"
    if "eng" in languages:
        return "eng"
    raise ValueError("Tesseract precisa do pacote de idioma por ou eng")


def _text(path: Path, engine: str) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, lines, method = _pdf(path, engine)
    elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        method = engine
        if engine == "paddle":
            lines = read_image(path)
            text = "\n".join(line["texto"] for line in lines)
        else:
            lines = None
            text = _run(["tesseract", str(path), "stdout", "-l", _ocr_language()])
    else:
        raise ValueError(f"Formato não suportado: {suffix}")
    text = text.strip()
    if not text:
        raise ValueError("Nenhum texto foi extraído")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Texto extraído excede 100 mil caracteres; divida o documento")
    keys = re.findall(r"(?<!\d)(?:\d[\s.-]?){44}(?!\d)", text)
    keys = [re.sub(r"\D", "", key) for key in keys]
    return {
        "formato": suffix.lstrip("."),
        "motor_ocr": method,
        "candidatos": {"chaves_acesso": keys[:5]},
        "texto": text,
        **({"linhas_ocr": lines} if lines is not None else {}),
    }


def extract(path: Path, *, ocr: str = "paddle") -> dict:
    if ocr not in {"paddle", "tesseract"}:
        raise ValueError("OCR deve ser paddle ou tesseract")
    if not path.is_file():
        raise ValueError("Arquivo não encontrado")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Arquivo excede 20 MB")
    if path.suffix.lower() == ".xml":
        return _xml(path)
    return _text(path, ocr)
