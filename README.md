# Leitor de nota fiscal

MVP de linha de comando para notas fiscais brasileiras. Extrai campos do XML ou texto de fotos/PDF com OCR local, envia essas **features** ao Gemini ou Ollama para interpretação e grava uma tabela CSV padronizada (uma linha por item).

## Pré-requisitos

- Python 3.10+.
- Para PDF: `pdftotext` (Poppler). Para PDF digitalizado: também `pdfinfo` e `pdftoppm` (Poppler).
- Para fotos e PDFs digitalizados, o padrão é **PaddleOCR PP-OCRv5 em português**, executado localmente. Seu pré-processamento tenta corrigir orientação e deformação do documento. Na primeira execução, os pesos do modelo são baixados para `.cache/paddlex` no projeto. Veja a [instalação oficial](https://www.paddleocr.ai/latest/en/quick_start.html).
- Chave da [API Gemini](https://aistudio.google.com/app/apikey). O modelo padrão é `gemini-3.1-flash-lite`, com cota gratuita sujeita aos limites da sua conta. Consulte [preços](https://ai.google.dev/gemini-api/docs/pricing) e [limites](https://ai.google.dev/gemini-api/docs/rate-limits).
- Para usar o Qwen3 localmente: [Ollama](https://ollama.com/download). Não é necessária chave de API.

Instalação para CPU, em ambiente virtual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.venv/bin/python -m pip install paddleocr
```

Instale também o Poppler pelo gerenciador de pacotes do seu sistema para processar PDFs. Para usar o Tesseract no lugar do PaddleOCR, instale o programa e seu pacote de idioma português (`por`); o inglês (`eng`) é usado como alternativa.

## Uso

```bash
export GEMINI_API_KEY='sua-chave'
.venv/bin/python -m fiscal_reader nota.xml -o notas.csv
.venv/bin/python -m fiscal_reader notas/ -o notas.csv
.venv/bin/python -m fiscal_reader nota1.xml nota2.pdf foto.jpg -o notas.csv
```

### Qwen3 local com Ollama

O Ollama gerencia os arquivos do modelo; não coloque os pesos na raiz do projeto. Inicie o aplicativo/serviço Ollama. Se não houver serviço ativo no Linux, execute `ollama serve` em outro terminal. Se aparecer `bind: address already in use`, verifique com `ollama list`: o serviço provavelmente já está ativo e não precisa ser iniciado de novo. Depois baixe o [Qwen3 4B Instruct](https://ollama.com/library/qwen3:4b-instruct) uma vez:

```bash
ollama pull qwen3:4b-instruct
ollama list
```

Na pasta do projeto, execute:

```bash
.venv/bin/python -m fiscal_reader --provider ollama notas/cpf_na_cupom-fiscal-contabilidade-vila-velha-es.jpg -o notas.csv
```

Para outras notas, troque o caminho do arquivo por uma imagem, PDF, XML ou pasta. `--model` permite escolher outro modelo instalado no Ollama. O Qwen3 4B Instruct recebe **texto**: a foto passa primeiro pelo PaddleOCR e o texto extraído é interpretado localmente pelo Qwen3. A saída continua exigindo revisão dos campos incertos.

Para examinar a extração antes do envio à API:

```bash
.venv/bin/python -m fiscal_reader --features-only foto.jpg
python3 -m fiscal_reader --ocr tesseract --features-only foto.jpg
```

Para conferir somente a imagem de exemplo presente neste projeto, sem usar Gemini:

```bash
.venv/bin/python -m fiscal_reader --ocr-text notas/cpf_na_cupom-fiscal-contabilidade-vila-velha-es.jpg
```

Use `--features-only` se quiser também posições e confiança de cada trecho reconhecido.

Quando a API Gemini retorna 503 por alta demanda, o programa tenta novamente três vezes, com pausas de 2, 4 e 8 segundos. Se continuar indisponível, o erro é informado sem criar dados inventados.

Uma pasta de entrada é percorrida recursivamente; cada arquivo XML, PDF ou imagem vira uma ou mais linhas no CSV. O modelo OCR é carregado uma vez por execução. `--features-only` escreve um objeto JSON por linha, com texto, posição e confiança das linhas reconhecidas pelo PaddleOCR. O CSV usa UTF-8 com BOM e `;` como separador, para facilitar a abertura em planilhas brasileiras. Campos ausentes ficam vazios. As colunas incluem `motor_ocr`, `confianca_ocr_media`, dados da nota, emitente, destinatário, produto, valores, categoria sugerida e `status_revisao`.

No XML, número, chave, partes, totais e itens são lidos diretamente e prevalecem sobre a resposta do modelo; a categoria é sugestão do LLM. Para PDF/imagem, o texto extraído é interpretado pelo modelo e todas as linhas ficam marcadas `revisar_extracao`. A saída **não substitui conferência fiscal**. Este MVP lê XML de NF-e (`infNFe`); não inclui outros tipos de documento fiscal. PDFs mistos preservam a ordem das páginas; até 20 páginas digitalizadas são processadas por OCR. Documentos extensos são recusados com mensagem explícita, sem corte silencioso.

**Privacidade:** as features enviadas à API podem conter CNPJ, nomes e valores. Segundo a [tabela de preços do Gemini](https://ai.google.dev/gemini-api/docs/pricing), dados do plano gratuito podem ser usados para melhorar os produtos do provedor. Avalie isso antes de processar notas sensíveis.
