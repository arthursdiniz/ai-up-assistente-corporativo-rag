# Avaliação e revisão humana

Os arquivos corpus.json e cases.json são sintéticos e públicos no repositório. Nunca substitua esses fixtures por documentos privados.

As avaliações originais continuam disponíveis:

- evaluate_ai.py: busca vetorial/híbrida em 20 casos. Usa seções já extraídas; não mede OCR, chunking da ingestão, qualidade textual ou tempo total.
- evaluate_generation.py: seis fixtures controlados com Ollama. Mede preservação literal, resposta ausente, continuidade e uma tentativa de injeção. Não mede robustez geral.

O conjunto acadêmico ampliado está em `academic_cases.py`. Execute `scripts/benchmark_retrieval.py`, `scripts/benchmark_models.py` e `scripts/benchmark_api.py` conforme o [relatório de validação](../docs/RELATORIO_VALIDACAO_TCC.md). Os procedimentos separam recuperação, geração e carga. A etapa com pessoas usa o [protocolo de avaliação humana](../docs/PROTOCOLO_AVALIACAO_HUMANA.md).

O Auditor usa `auditor_cases.py` e `scripts/evaluate_auditor.py`. Os arquivos em `auditor_demo/` são exemplos para a apresentação. A [avaliação do Auditor](../docs/AVALIACAO_AUDITOR.md) separa desenvolvimento, avaliação reservada e estresse.
