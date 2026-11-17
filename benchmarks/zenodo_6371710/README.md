# Amostra com gabarito: Zenodo 6371710

Fonte: [Cruz e Castelli, *Dataset of invoices and receipts including annotation of relevant fields*](https://zenodo.org/records/6371710), DOI `10.5281/zenodo.6371710`.

O dataset contém 813 imagens de notas e recibos de Portugal. Esta pasta traz 12 fotos selecionadas e seus rótulos originais. As imagens estão em `images/`; os arquivos `labels_original/*.txt` contêm JSON exatamente como veio do dataset. O `manifest.json` relaciona imagem, anotação, valores e hashes SHA-256. A planilha do gabarito está em `../../outputs/01a1a6d6-4588-7dc3-bb10-0b8e2c58aec5/gabarito_zenodo_6371710.xlsx`.

Para ampliar ou refazer a amostra, execute `python3 benchmarks/zenodo_6371710/download_sample.py` a partir da raiz do projeto. O script usa HTTP Range para obter só as imagens selecionadas do ZIP de 410 MB, confere o MD5 do ZIP de anotações publicado pelo Zenodo e valida o CRC32 de cada imagem no ZIP.

## Campos do gabarito

| Campo original | Significado |
| --- | --- |
| `company` | Nome do vendedor/emitente |
| `date` | Data do documento, como anotada |
| `address` | Endereço do vendedor/emitente |
| `total` | Total, como anotado |
| `invoice_number` | Referência/número do documento |
| `nif_buyer` | Número fiscal do comprador em Portugal |
| `iva_amount` | Valor do IVA, como anotado |
| `nif_seller` | Número fiscal do vendedor em Portugal |

Os valores foram preservados como texto. Um campo vazio significa que o dataset não fornece um valor para aquela imagem; não significa necessariamente que a informação esteja ausente na foto. Algumas anotações têm pontuação ou formato de data distintos. Para avaliar o modelo, normalize apenas numa etapa de comparação e guarde sempre o rótulo bruto.

Este conjunto serve para testar OCR e extração de campos gerais em fotos reais. Ele não contém gabarito de itens, CNPJ, CPF, NCM, CFOP ou chave de acesso da NF-e brasileira. NIF e IVA são conceitos fiscais portugueses; não devem ser tratados como CNPJ e ICMS. Para avaliar esses campos brasileiros, será preciso outro conjunto com rótulos verificados, por exemplo fotos próprias ligadas ao XML oficial da mesma nota.
