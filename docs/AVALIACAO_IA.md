# Avaliação do AI-Up — 9 de setembro de 2026

## Resultados reproduzidos

A busca foi avaliada com embeddings reais, em 20 perguntas sobre um corpus sintético pequeno.

| Métrica | Vetorial | Híbrida |
|---|---:|---:|
| Hit@3, incluindo ausência correta de resultados | 85% | 90% |
| Precisão média dos trechos retornados (até 3) | 45,83% | 66,67% |
| Primeiro resultado correto | — | 90% |
| Recuperação contextual nos 3 casos de contexto | — | 100% |
| Ausência de resultados nos 3 casos sem resposta | — | 33,33% |
| Trechos retornados de outro usuário | — | 0 |

A nomenclatura before/after do JSON compara os dois algoritmos **na mesma execução**, não uma experiência longitudinal. Latências do JSON medem somente busca e ordenação, excluindo embeddings, ingestão e geração.

A busca ainda retorna contexto semelhante em duas perguntas cuja resposta não existe. Por isso não basta reduzir um limiar e declarar a IA mais inteligente: o modelo precisa reconhecer que o fato pedido está ausente.

Na avaliação separada de geração real, Ollama qwen3:4b-instruct passou em **6/6 fixtures**: código literal, dois casos de informação ausente, injeção documental, comparação com duas fontes e continuação curta. São verificações literais controladas, não prova de robustez contra toda injeção nem estimativa de precisão em documentos reais.

## Reprodução

Execute na raiz:

~~~powershell
.venv\Scripts\python.exe scripts\evaluate_ai.py
.venv\Scripts\python.exe scripts\evaluate_generation.py
.venv\Scripts\python.exe -m pytest -q
~~~

Resultados completos: output/evaluation/latest.json e output/evaluation/generation.json. Fixtures e protocolo humano: evals/.

## Limitações explícitas

- Nenhuma porcentagem acima representa “precisão da IA” em geral.
- Citação existente não prova que uma afirmação é semanticamente sustentada. A interface permite conferência; referências inválidas/ausentes geram aviso.
- Resumos longos usam condensação hierárquica e podem perder detalhes.
- A análise de assunto é heurística, não memória humana. Um escopo explícito reduz ambiguidades.
- OCR depende da qualidade da imagem e do idioma instalado.
- Resultados antigos de 100% em 13 perguntas foram substituídos pela avaliação ampliada, com correção da checagem de página singular.
