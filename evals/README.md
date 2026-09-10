# Avaliação e revisão humana

Os arquivos corpus.json e cases.json são sintéticos e públicos no repositório. Nunca substitua esses fixtures por documentos privados.

Há duas avaliações distintas:

- evaluate_ai.py: busca vetorial/híbrida em 20 casos. Usa seções já extraídas; não mede OCR, chunking da ingestão, qualidade textual ou tempo total.
- evaluate_generation.py: seis fixtures controlados com Ollama. Mede preservação literal, resposta ausente, continuidade e uma tentativa de injeção. Não mede robustez geral.

Protocolo humano recomendado para a banca: selecionar 30 perguntas inéditas sobre documentos de demonstração; incluir perguntas factuais, continuação, mudança de assunto, comparação, resumo e informação ausente. Dois avaliadores independentes atribuem 0–2 a cada critério: fidelidade, completude, utilidade e verificabilidade. Registrar divergências, latência total, versão/modelo/configuração e exemplos de falha. Não publicar uma média sem informar amostra, rubrica e quantidade de recusas. Feedback no aplicativo é útil para priorizar problemas, mas não substitui esse protocolo.
