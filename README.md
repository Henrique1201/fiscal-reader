# Leitor de nota fiscal

Interface local para transformar fotos, PDFs e XMLs de NF-e em uma tabela de itens. O resultado registra **descrição, quantidade, preço unitário (quando aparece no documento), preço total do item** e **data (opcional)**. Você confere e corrige os campos antes de baixar o CSV.

Fluxo: **foto/PDF → PaddleOCR local → Qwen3 no Ollama local → revisão na interface → CSV**. Para XML de NF-e, os itens são lidos diretamente, sem OCR nem LLM. O [Gemini](#opcional-usar-gemini) é uma alternativa ao Ollama.

## Reproduzir do zero no Ubuntu 24.04

Este é o ambiente em que o projeto foi testado: **Python 3.12.3, PaddlePaddle 3.2.0 e PaddleOCR 3.7.0**, com processamento em CPU. Execute os comandos abaixo na pasta que contém `README.md` e `fiscal_reader/`. Em outros sistemas, adapte a instalação do Python e do Poppler.

### 1. Instalar as ferramentas do sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip poppler-utils
python3 --version
```

O `poppler-utils` fornece `pdftotext`, `pdfinfo` e `pdftoppm`, usados para PDFs. Para fotos e XMLs, esses programas não são necessários.

### 2. Criar o ambiente Python e instalar o OCR

```bash
python3 -m venv .venv
.venv/bin/python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.venv/bin/python -m pip install paddleocr==3.7.0
.venv/bin/python -m pip check
```

O primeiro comando segue a [documentação do PaddlePaddle](https://www.paddleocr.ai/main/en/version3.x/paddlepaddle_installation.html); o segundo instala a versão do [PaddleOCR](https://www.paddleocr.ai/latest/en/version3.x/installation.html) usada neste projeto. O código usa PP-OCRv5 em português e tenta corrigir orientação e deformação do documento. **Na primeira foto**, os pesos são baixados para `.cache/paddlex` dentro do projeto; essa etapa precisa de internet e pode demorar. Depois, a inferência OCR funciona localmente.

### 3. Instalar o Ollama e baixar o modelo

Instale o [Ollama para Linux](https://ollama.com/download/linux) se ainda não estiver instalado. Com o serviço ativo, execute:

```bash
ollama pull qwen3:4b-instruct
ollama list
```

Confira se `qwen3:4b-instruct` aparece na lista. O modelo é gerenciado pelo Ollama; **não coloque seus arquivos na raiz do projeto**. Se `ollama list` não conseguir se conectar, inicie `ollama serve` em outro terminal e tente novamente. Se `ollama serve` mostrar `bind: address already in use`, o serviço provavelmente já está ativo: confirme com `ollama list`.

### 4. Abrir a interface

```bash
.venv/bin/python -m fiscal_reader.web
```

Abra [http://127.0.0.1:8765](http://127.0.0.1:8765) caso o navegador não abra sozinho. Mantenha esse terminal aberto enquanto usa a interface; `Ctrl+C` encerra o servidor. Se a porta estiver ocupada, use `.venv/bin/python -m fiscal_reader.web --port 8766`. A opção `--no-browser` impede a abertura automática do navegador.

Na interface:

1. Arraste uma ou várias imagens, PDFs ou XMLs (até **20 MB por arquivo**).
2. Deixe **Qwen local (Ollama)** e **PaddleOCR** selecionados e clique em **Processar arquivos**.
3. Compare cada linha com a foto, o PDF ou o texto do OCR. Corrija as células, adicione ou exclua itens e marque os conferidos.
4. Clique em **Baixar CSV**. O arquivo revisado é salvo pelo navegador.

O servidor aceita apenas conexões em `127.0.0.1` e apaga o arquivo temporário de cada upload após processá-lo. O CSV baixado fica no local padrão de downloads do seu navegador.

## Primeiro teste reproduzível

### Foto com gabarito

Use `benchmarks/cord_v2/images/cord_test_082.jpg` na interface. Se a pasta `images/` não estiver na sua cópia, execute `python3 benchmarks/cord_v2/download_sample.py` para baixar as fotos e os rótulos; essa etapa precisa de internet. O [rótulo original do CORD v2](benchmarks/cord_v2/labels_original/cord_test_082.json) contém **três itens**:

| Item | Quantidade | Preço unitário | Preço do item |
| --- | ---: | ---: | ---: |
| Chocolate Log Cake | 1 | 115000 | 115000 |
| Snowman Cake Chocolate | 1 | 60000 | 60000 |
| Strawberry Log Cake | 2 | 105000 | 210000 |

Os preços da tabela acima estão normalizados para o formato de saída do leitor; o gabarito preserva `115,000`, `1x` etc. O CORD não rotula data, portanto ela deve ficar vazia. **Compare o resultado obtido com o gabarito; a LLM pode errar**, especialmente em fotos difíceis. Esse recibo é indonésio e serve para validar o fluxo, não para medir a qualidade em notas brasileiras.

### XML sem OCR nem LLM

Para verificar apenas o parser de XML, crie este arquivo sintético de teste (não é uma NF-e válida para fins fiscais):

```bash
cat > /tmp/nfe-exemplo.xml <<'XML'
<nfeProc><NFe><infNFe>
  <ide><dhEmi>2026-11-16T12:30:00-03:00</dhEmi></ide>
  <det nItem="1"><prod><xProd>Arroz 1 kg</xProd><qCom>2.0000</qCom><vUnCom>5.50</vUnCom><vProd>11.00</vProd></prod></det>
</infNFe></NFe></nfeProc>
XML
.venv/bin/python -m fiscal_reader /tmp/nfe-exemplo.xml -o /tmp/itens-xml.csv
```

O CSV deve conter **uma linha** com `Arroz 1 kg`, quantidade `2.0000`, preço unitário `5.50`, preço do item `11.00` e data `2026-11-16`. Você também pode enviar `/tmp/nfe-exemplo.xml` pela interface. O XML é extraído mesmo sem Ollama ativo.

## Uso pela linha de comando

A interface usa Ollama por padrão. **Na linha de comando, escolha `--provider ollama` explicitamente**; o padrão da CLI é Gemini.

```bash
# Uma foto, com CSV na pasta atual
.venv/bin/python -m fiscal_reader --provider ollama notas/cpf_na_cupom-fiscal-contabilidade-vila-velha-es.jpg -o notas.csv

# Pasta inteira (busca arquivos recursivamente)
.venv/bin/python -m fiscal_reader --provider ollama notas/ -o notas.csv

# Conferir somente o texto reconhecido, sem LLM nem CSV
.venv/bin/python -m fiscal_reader --ocr-text notas/cpf_na_cupom-fiscal-contabilidade-vila-velha-es.jpg

# Ver texto, caixas e confiança do OCR em JSON, sem LLM nem CSV
.venv/bin/python -m fiscal_reader --features-only notas/cpf_na_cupom-fiscal-contabilidade-vila-velha-es.jpg
```

`--model` seleciona outro modelo instalado no Ollama. Para usar Tesseract em vez de PaddleOCR, instale `tesseract-ocr` e `tesseract-ocr-por`, depois passe `--ocr tesseract` na CLI ou selecione Tesseract na interface. O inglês (`eng`) é usado se o idioma português não estiver disponível.

O CSV usa UTF-8 com BOM e `;` como separador, para abrir em planilhas brasileiras. Cada item ocupa uma linha. As colunas são `arquivo`, `formato`, `motor_ocr`, `confianca_ocr_media`, `data_emissao`, `descricao`, `quantidade`, `valor_unitario`, `valor_total_item`, `observacoes` e `status_revisao`. Campos ausentes ficam vazios; itens de imagem/PDF começam com status `revisar_extracao`.

## Opcional: usar Gemini

Obtenha uma chave no [Google AI Studio](https://aistudio.google.com/app/apikey), defina a variável de ambiente **antes de iniciar** a interface e escolha Gemini no seletor:

```bash
export GEMINI_API_KEY='sua-chave'
.venv/bin/python -m fiscal_reader.web
```

Na CLI, use `--provider gemini`. O modelo padrão do código é `gemini-3.1-flash-lite`; disponibilidade e cota gratuita dependem da sua conta. Consulte [preços](https://ai.google.dev/gemini-api/docs/pricing) e [limites](https://ai.google.dev/gemini-api/docs/rate-limits). O texto extraído é enviado à API. Em erro HTTP 503, o programa tenta novamente até três vezes e informa a falha se o serviço continuar ocupado.

## Testes e avaliação

```bash
python3 -m unittest discover -s tests -q
```

Os testes automatizados verificam o parser, a padronização da saída e a API da interface sem precisar consultar um modelo. Para medir qualidade em fotos, veja o [gabarito CORD v2](benchmarks/cord_v2/README.md): 10 recibos, 29 itens e os rótulos originais. O conjunto [Zenodo 6371710](benchmarks/zenodo_6371710/README.md) contém apenas campos gerais e não mede extração de itens. Para avaliar cupons brasileiros e datas, crie uma amostra brasileira com rótulos revisados.

## Problemas comuns

| Sintoma | O que verificar |
| --- | --- |
| `ollama serve`: `address already in use` | Execute `ollama list`; o serviço pode já estar ativo. |
| `Modelo Ollama não encontrado` | Execute `ollama pull qwen3:4b-instruct` e confira com `ollama list`. |
| `PaddleOCR não instalado` | Confirme que usa `.venv/bin/python` e refaça a etapa 2. |
| Primeira foto demora | O PaddleOCR baixa os pesos na primeira execução; confira internet e a pasta `.cache/paddlex`. |
| `Nenhum texto foi extraído` | Confira a legibilidade da foto e use `--ocr-text` para examinar o OCR antes da interpretação. |
| Porta `8765` ocupada | Inicie a interface com `--port 8766` e abra a URL mostrada no terminal. |
| Gemini HTTP 503 | Aguarde e tente novamente ou selecione o Ollama local. |

## Limites e privacidade

O parser XML aceita NF-e com `infNFe`; outros tipos de XML não estão implementados. PDFs mistos mantêm a ordem das páginas; PDFs digitalizados são limitados a 20 páginas por documento. O limite de upload é 20 MB por arquivo. O modelo não deve inventar quantidade nem preço ausentes, mas suas respostas ainda precisam de revisão humana.

Com **Ollama**, OCR e interpretação acontecem localmente após o download dos modelos. Com **Gemini**, as features extraídas podem conter nomes, CNPJ e valores e são enviadas ao provedor; leia a [política de preços e dados](https://ai.google.dev/gemini-api/docs/pricing) antes de usar notas sensíveis.
