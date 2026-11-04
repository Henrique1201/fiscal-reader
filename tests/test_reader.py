import csv
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

from fiscal_reader.cli import CSV_FIELDS, _expand_inputs, _rows, main
from fiscal_reader.extract import extract
from fiscal_reader.llm import HEADER_FIELDS, ITEM_FIELDS, interpret


XML = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe12345678901234567890123456789012345678901234">
<ide><serie>1</serie><nNF>42</nNF><dhEmi>2026-11-04T10:00:00-03:00</dhEmi></ide>
<emit><CNPJ>12345678000190</CNPJ><xNome>Loja Exemplo</xNome></emit>
<dest><CPF>12345678909</CPF><xNome>Cliente Exemplo</xNome></dest>
<det nItem="1"><prod><cProd>ABC</cProd><xProd>Papel A4</xProd><NCM>48025610</NCM><CFOP>5102</CFOP><uCom>PCT</uCom><qCom>2.0000</qCom><vUnCom>10.00</vUnCom><vProd>20.00</vProd></prod></det>
<total><ICMSTot><vNF>20.00</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>"""


class ReaderTests(unittest.TestCase):
    def test_xml_extracts_authoritative_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nota.xml"
            path.write_text(XML, encoding="utf-8")
            features = extract(path)
        self.assertEqual(features["cabecalho"]["numero"], "42")
        self.assertEqual(features["cabecalho"]["emitente_cnpj"], "12345678000190")
        self.assertEqual(features["itens"][0]["valor_total_item"], "20.00")

    def test_xml_data_wins_over_model_and_csv_has_one_row_per_item(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nota.xml"
            path.write_text(XML, encoding="utf-8")
            features = extract(path)
            output = {
                "cabecalho": {name: "inventado" for name in HEADER_FIELDS},
                "itens": [{name: "inventado" for name in ITEM_FIELDS}],
                "observacoes": None,
            }
            output["itens"][0]["categoria_item"] = "Papelaria"
            rows = _rows(path, features, output)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["numero"], "42")
        self.assertEqual(rows[0]["descricao"], "Papel A4")
        self.assertEqual(rows[0]["categoria_item"], "Papelaria")
        self.assertEqual(set(rows[0]), set(CSV_FIELDS))

    def test_structured_api_response_and_local_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nota.xml"
            csv_path = Path(folder) / "resultado.csv"
            path.write_text(XML, encoding="utf-8")
            result = {
                "cabecalho": {name: None for name in HEADER_FIELDS},
                "itens": [{name: None for name in ITEM_FIELDS}],
                "observacoes": None,
            }
            result["itens"][0]["categoria_item"] = "Papelaria"
            response = {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}
            fake = io.BytesIO(json.dumps(response).encode())
            with patch.dict(os.environ, {"GEMINI_API_KEY": "teste"}), patch("urllib.request.urlopen", return_value=fake) as urlopen:
                self.assertEqual(main([str(path), "-o", str(csv_path)]), 0)
            request = urlopen.call_args.args[0]
            self.assertIn(b"Papel A4", request.data)
            self.assertEqual(request.headers["X-goog-api-key"], "teste")
            with csv_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file, delimiter=";"))
            self.assertEqual(rows[0]["valor_total_nota"], "20.00")
            self.assertEqual(rows[0]["categoria_item"], "Papelaria")

    def test_paddle_lines_are_passed_as_features(self):
        class Prediction:
            json = {"res": {"rec_texts": ["NOTA FISCAL", "TOTAL 20,00"],
                            "rec_scores": [0.98, 0.75], "rec_boxes": [[1, 2, 30, 10], [1, 20, 40, 30]]}}

        class Model:
            def predict(self, path):
                return [Prediction()]

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foto.jpg"
            path.write_bytes(b"imagem simulada")
            with patch("fiscal_reader.ocr._paddle_model", return_value=Model()):
                features = extract(path)
        self.assertEqual(features["motor_ocr"], "paddle")
        self.assertEqual(features["texto"], "NOTA FISCAL\nTOTAL 20,00")
        self.assertEqual(features["linhas_ocr"][1]["confianca"], 0.75)
        self.assertEqual(features["linhas_ocr"][1]["caixa"], [1, 20, 40, 30])

    def test_folder_input_recurses_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "sub").mkdir()
            (root / "a.xml").write_text(XML, encoding="utf-8")
            (root / "sub" / "b.xml").write_text(XML, encoding="utf-8")
            (root / "readme.txt").write_text("ignore", encoding="utf-8")
            self.assertEqual(len(_expand_inputs([root, root / "a.xml"])), 2)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["--features-only", str(root)]), 0)
            objects = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([obj["features"]["formato"] for obj in objects], ["xml_nfe", "xml_nfe"])

    def test_ocr_text_mode_does_not_call_gemini(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foto.jpg"
            path.write_bytes(b"imagem simulada")
            output = io.StringIO()
            with patch("fiscal_reader.extract.read_image", return_value=[
                {"texto": "TOTAL R$ 20,00", "confianca": 0.9, "caixa": [1, 2, 3, 4]}
            ]), patch("fiscal_reader.cli.interpret") as gemini, redirect_stdout(output):
                self.assertEqual(main(["--ocr-text", str(path)]), 0)
            gemini.assert_not_called()
            self.assertEqual(output.getvalue().strip(), "TOTAL R$ 20,00")

    def test_mixed_pdf_keeps_page_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "misto.pdf"
            path.write_bytes(b"pdf simulado")

            def fake_run(command):
                if command[0] == "pdfinfo":
                    return "Pages: 2\n"
                if command[0] == "pdftotext":
                    return "NOTA FISCAL ELETRONICA NUMERO 42 EMITENTE LOJA EXEMPLO\f\f"
                if command[0] == "pdftoppm":
                    Path(command[-1] + ".png").write_bytes(b"pagina")
                    return ""
                raise AssertionError(command)

            with patch("fiscal_reader.extract._run", side_effect=fake_run), patch(
                "fiscal_reader.extract.read_image",
                return_value=[{"texto": "TOTAL 20,00", "confianca": 0.9, "caixa": [1, 2, 3, 4]}],
            ):
                features = extract(path)
        self.assertEqual(features["motor_ocr"], "paddle")
        self.assertLess(features["texto"].index("NUMERO 42"), features["texto"].index("TOTAL 20,00"))
        self.assertEqual(features["linhas_ocr"][0]["pagina"], 2)

    def test_gemini_503_retries_then_succeeds(self):
        answer = {
            "cabecalho": {name: None for name in HEADER_FIELDS},
            "itens": [],
            "observacoes": None,
        }
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}
        busy = lambda: urllib.error.HTTPError("https://example.invalid", 503, "Unavailable", {}, io.BytesIO(b"{}"))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "teste"}), patch(
            "urllib.request.urlopen",
            side_effect=[busy(), busy(), io.BytesIO(json.dumps(response).encode())],
        ) as urlopen, patch("fiscal_reader.llm.time.sleep") as sleep:
            result = interpret({"formato": "jpg", "texto": "nota"})
        self.assertEqual(result, answer)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

    def test_gemini_503_stops_after_bounded_retries(self):
        def busy(*_args, **_kwargs):
            raise urllib.error.HTTPError("https://example.invalid", 503, "Unavailable", {}, io.BytesIO(b"{}"))

        with patch.dict(os.environ, {"GEMINI_API_KEY": "teste"}), patch(
            "urllib.request.urlopen", side_effect=busy
        ) as urlopen, patch("fiscal_reader.llm.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "após 4 tentativas"):
                interpret({"formato": "jpg", "texto": "nota"})
        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4, 8])

    def test_ollama_provider_generates_csv_without_gemini_key(self):
        answer = {
            "cabecalho": {name: None for name in HEADER_FIELDS},
            "itens": [{name: None for name in ITEM_FIELDS}],
            "observacoes": None,
        }
        response = {"message": {"content": json.dumps(answer)}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "nota.xml"
            csv_path = Path(folder) / "notas.csv"
            path.write_text(XML, encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), patch(
                "urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())
            ) as urlopen:
                self.assertEqual(main(["--provider", "ollama", str(path), "-o", str(csv_path)]), 0)
            request = urlopen.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
            self.assertEqual(body["model"], "qwen3:4b-instruct")
            self.assertEqual(body["format"]["type"], "object")
            self.assertFalse(body["stream"])
            with csv_path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file, delimiter=";"))
            self.assertEqual(rows[0]["numero"], "42")

    def test_ollama_missing_model_message(self):
        def missing(*_args, **_kwargs):
            raise urllib.error.HTTPError("http://127.0.0.1:11434/api/chat", 404, "Not Found", {}, io.BytesIO(b"{}"))

        with patch("urllib.request.urlopen", side_effect=missing):
            with self.assertRaisesRegex(ValueError, "ollama pull qwen3:4b-instruct"):
                interpret({"formato": "jpg", "texto": "nota"}, provider="ollama")


if __name__ == "__main__":
    unittest.main()
