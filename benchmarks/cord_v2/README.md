# Gabarito de itens: CORD v2

Fonte principal: [CORD v2, NAVER CLOVA](https://huggingface.co/datasets/naver-clova-ix/cord-v2), revisão `7f0115a4b758a71d6473b8d085751692da2fef98`, split `test`. [Definição oficial dos campos](https://github.com/clovaai/cord#data-specification-for-the-whole-dataset). Licença indicada pelos autores: CC BY 4.0.

Esta amostra contém 10 fotos de recibos reais e 29 itens rotulados. `images/` guarda as fotos, `labels_original/` guarda a string `ground_truth` fornecida pela API do dataset, e `manifest.json` guarda o índice original, a revisão e os hashes SHA-256. A planilha está em `../../outputs/01a1a6d6-4588-7dc3-bb10-0b8e2c58aec5/gabarito_itens_cord_v2.xlsx`. Para baixar novamente: `python3 benchmarks/cord_v2/download_sample.py` a partir da raiz do projeto.

Cada linha da planilha representa um elemento de `gt_parse.menu`, na ordem publicada. Os campos vieram diretamente do rótulo:

| Coluna da planilha | Campo CORD | Significado |
| --- | --- | --- |
| Item | `menu.nm` | Texto do item |
| Quantidade | `menu.cnt` | Quantidade como impressa, por exemplo `2`, `2x` ou `x2` |
| Preço unitário | `menu.unitprice` | Preço unitário, quando anotado |
| Preço da linha | `menu.price` | Preço total do item antes de eventual desconto de linha |

Os preços foram preservados como texto, inclusive `Rp`, pontos e vírgulas. Não normalize valores na planilha de referência. Faça a normalização somente no comparador, mantendo o rótulo bruto para auditoria. Alguns recibos têm descontos e `itemsubtotal`; esses campos continuam disponíveis no JSON original caso você queira avaliar o preço após desconto.

**Data:** CORD v2 não fornece rótulo de data. A coluna fica vazia e não deve entrar no cálculo de acurácia. Os recibos são da Indonésia; para medir o desempenho em cupons brasileiros e validar datas, complemente com fotos brasileiras ligadas aos respectivos XMLs ou com anotações manuais revisadas.

`resultado_ollama_082_039.csv` é uma execução de demonstração do leitor local, não parte do gabarito. Na foto `082`, os três itens, quantidades e preços saíram corretamente após normalização dos separadores. Na foto escura `039`, o OCR/modelo recuperou apenas um dos três nomes e deixou quantidade e preços vazios. Mantenha esses erros visíveis ao avaliar o sistema; não preencha o resultado com valores do gabarito.
