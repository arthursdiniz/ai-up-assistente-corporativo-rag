# Avaliação da IA do AI-Up

## Objetivo e método

A avaliação reproduzível compara a recuperação vetorial anterior com o pipeline híbrido atual. O corpus sintético contém regulamento em três páginas, dados institucionais, datas, valores, um código exato, uma tentativa de injeção e um documento pertencente a outro usuário.

Os treze casos cobrem pergunta factual, sinônimo, número, código, continuação por pronome, continuação vaga, mudança de assunto, linha do tempo, comparação entre documentos, resposta em páginas distintas, informação ausente e injeção de prompt. O relatório completo é salvo em `output/evaluation/latest.json`.

```powershell
.venv\Scripts\python.exe scripts\evaluate_ai.py --embedding-provider sentence_transformers
```

## Resultado em 8 de setembro de 2026

| Métrica | Busca anterior | Pipeline atual |
|---|---:|---:|
| Hit@3 incluindo recusa correta | 92,31% | 100,00% |
| Precisão média das fontes no Top 3 | 51,28% | 74,36% |
| Acerto da primeira fonte | — | 100,00% |
| Resolução de perguntas contextuais | — | 100,00% |
| Recusa correta da informação ausente | — | 100,00% |
| Latência média de recuperação | 1,75 ms | 2,93 ms |
| Trechos de outro usuário retornados | — | 0 |

O acréscimo médio de 1,18 ms ocorreu no corpus pequeno e representa o custo da busca lexical, fusão e reranking. A latência varia entre execuções conforme a máquina; para a demonstração local, a diferença é imperceptível diante do tempo de geração do modelo.

## Leitura honesta do resultado

O ganho mais importante não é apenas o Hit@3: a fonte correta passa a ocupar a primeira posição e há menos páginas irrelevantes. O caso ausente também é recusado antes de oferecer uma evidência fraca.

Este conjunto é pequeno, sintético e conhecido; portanto, 100% não significa precisão universal. Ele serve como teste de regressão da recuperação e das decisões de fundamentação, não como prova automática de que toda redação gerada estará correta. A qualidade final do texto do Ollama, documentos escaneados difíceis, grandes coleções e perguntas fora do domínio ainda exigem avaliação humana e um corpus institucional maior.

## Critérios para validação humana

- a resposta contém somente fatos sustentados pelos excertos;
- nomes, datas, valores e unidades são preservados;
- pergunta contextual mantém o assunto correto;
- mudança explícita de tema ignora o histórico irrelevante;
- fonte exibida permite conferir a afirmação;
- informação ausente gera recusa clara, sem invenção.
