"""Verificações do fluxo de upload da interface local."""

import base64
import io
import json
import unittest
from email.message import Message
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch

from fiscal_reader.web import Handler, process_document


XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc><NFe><infNFe>
<ide><dhEmi>2026-11-16T12:30:00-03:00</dhEmi></ide>
<det nItem="1"><prod><xProd>Arroz</xProd><qCom>2.0000</qCom><vUnCom>5.50</vUnCom><vProd>11.00</vProd></prod></det>
</infNFe></NFe></nfeProc>"""


class WebTests(unittest.TestCase):
    def test_xml_upload_returns_items_without_llm(self):
        with patch("fiscal_reader.cli.interpret") as model:
            result = process_document("nota.xml", XML)
        model.assert_not_called()
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["rows"][0]["arquivo"], "nota.xml")
        self.assertEqual(result["rows"][0]["descricao"], "Arroz")
        self.assertEqual(result["rows"][0]["quantidade"], "2.0000")
        self.assertEqual(result["rows"][0]["data_emissao"], "2026-11-16")

    def test_image_upload_keeps_original_filename_and_ocr_text(self):
        features = {
            "formato": "jpg", "motor_ocr": "paddle", "texto": "Arroz 2 5,50 11,00",
            "linhas_ocr": [{"texto": "Arroz 2 5,50 11,00", "confianca": 0.9}],
        }
        result = {
            "cabecalho": {"data_emissao": None},
            "itens": [{"descricao": "Arroz", "quantidade": "2", "valor_unitario": "5.50", "valor_total_item": "11.00"}],
            "observacoes": None,
        }
        with patch("fiscal_reader.web.extract", return_value=features) as extract, patch(
            "fiscal_reader.web._result_for_features", return_value=result
        ) as model:
            output = process_document("/tmp/foto.jpg", b"imagem", provider="ollama")
        self.assertEqual(extract.call_args.kwargs["ocr"], "paddle")
        self.assertEqual(model.call_args.kwargs["provider"], "ollama")
        self.assertEqual(output["rows"][0]["arquivo"], "foto.jpg")
        self.assertEqual(output["ocr_text"], "Arroz 2 5,50 11,00")

    def test_upload_rejects_unsupported_and_oversized_files(self):
        with self.assertRaisesRegex(ValueError, "Formato não suportado"):
            process_document("arquivo.exe", b"x")
        with self.assertRaisesRegex(ValueError, "excede 20 MB"):
            process_document("foto.jpg", b"x" * 20_000_001)
        with self.assertRaisesRegex(ValueError, "Nome de modelo inválido"):
            process_document("foto.jpg", b"x", model="../../modelo")

    def test_invalid_xml_returns_json_error_instead_of_closing_connection(self):
        body = json.dumps({
            "filename": "nota.xml",
            "content_base64": base64.b64encode(b"<nfeProc>").decode("ascii"),
        }).encode("utf-8")
        handler = Handler.__new__(Handler)
        handler.path = "/api/process"
        handler.server = SimpleNamespace(server_port=8765)
        handler.headers = Message()
        handler.headers["Content-Type"] = "application/json"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        responses = []
        handler._json = lambda status, payload: responses.append((status, payload))
        handler.do_POST()
        self.assertEqual(responses[0][0], HTTPStatus.BAD_REQUEST)
        self.assertIn("XML inválido", responses[0][1]["error"])


if __name__ == "__main__":
    unittest.main()
