"""Interface local no navegador para revisar itens antes de exportar o CSV."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from .cli import SUPPORTED_SUFFIXES, _result_for_features, _rows
from .extract import MAX_FILE_BYTES, extract


STATIC_DIR = Path(__file__).with_name("static")
MAX_REQUEST_BYTES = 28_000_000
PROCESS_LOCK = threading.Lock()
MODEL_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


def process_document(
    filename: str,
    content: bytes,
    *,
    ocr: str = "paddle",
    provider: str = "ollama",
    model: str | None = None,
) -> dict:
    """Processa um upload sem manter o documento no disco após a resposta."""
    if not isinstance(filename, str) or not isinstance(content, bytes):
        raise ValueError("Arquivo inválido")
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."} or "\x00" in name:
        raise ValueError("Nome de arquivo inválido")
    if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Formato não suportado. Envie JPG, PNG, TIFF, PDF ou XML")
    if not content:
        raise ValueError("O arquivo está vazio")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Arquivo excede 20 MB")
    if not isinstance(ocr, str) or ocr not in {"paddle", "tesseract"}:
        raise ValueError("OCR deve ser PaddleOCR ou Tesseract")
    if not isinstance(provider, str) or provider not in {"ollama", "gemini"}:
        raise ValueError("Provedor deve ser Ollama ou Gemini")
    if model is not None and (not isinstance(model, str) or not MODEL_NAME.fullmatch(model)):
        raise ValueError("Nome de modelo inválido")

    with PROCESS_LOCK, tempfile.TemporaryDirectory(prefix="fiscal-reader-upload-") as directory:
        path = Path(directory) / name
        path.write_bytes(content)
        features = extract(path, ocr=ocr)
        result = _result_for_features(features, provider=provider, model=model)
        rows = _rows(Path(name), features, result) if result["itens"] else []
    return {
        "filename": name,
        "rows": rows,
        "item_count": len(result["itens"]),
        "ocr_text": features.get("texto", ""),
        "observacoes": result.get("observacoes"),
        "format": features["formato"],
    }


def _ollama_status() -> tuple[bool, list[str]]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            data = json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return False, []
    return True, [item["name"] for item in data.get("models", []) if isinstance(item.get("name"), str)]


class Handler(BaseHTTPRequestHandler):
    server_version = "FiscalReader/1.0"

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route == "/api/status":
            online, models = _ollama_status()
            self._json(HTTPStatus.OK, {
                "ollama_online": online,
                "ollama_models": models,
                "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
            })
            return
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        }
        if route not in files:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Página não encontrada"})
            return
        name, content_type = files[route]
        self._send(HTTPStatus.OK, (STATIC_DIR / name).read_bytes(), content_type)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/process":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada"})
            return
        origin = self.headers.get("Origin")
        port = self.server.server_port
        if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            self._json(HTTPStatus.FORBIDDEN, {"error": "Origem não permitida"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Envie JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "Corpo da requisição ausente"})
            return
        if length > MAX_REQUEST_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Arquivo excede 20 MB"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON inválido")
            encoded = payload.get("content_base64")
            if not isinstance(encoded, str):
                raise ValueError("Conteúdo do arquivo ausente")
            content = base64.b64decode(encoded, validate=True)
            result = process_document(
                payload.get("filename", ""),
                content,
                ocr=payload.get("ocr", "paddle"),
                provider=payload.get("provider", "ollama"),
                model=payload.get("model") or None,
            )
        except ET.ParseError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"XML inválido: {exc}"})
            return
        except (ValueError, binascii.Error) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except OSError as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, result)


def create_server(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interface local do leitor de comprovantes")
    parser.add_argument("--port", type=int, default=8765, help="porta local (padrão: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="não abrir o navegador automaticamente")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("a porta deve estar entre 0 e 65535")
    try:
        server = create_server(args.port)
    except OSError as exc:
        parser.error(f"não foi possível iniciar a interface: {exc}")
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Leitor de comprovantes: {address}", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
