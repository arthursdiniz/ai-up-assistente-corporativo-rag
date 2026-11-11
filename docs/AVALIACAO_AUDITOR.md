# Avaliação experimental do AI-Up Auditor

## Metodologia e resultados

O conjunto em `evals/auditor_cases.py` tem 50 casos sintéticos em três partições. Desenvolvimento usa 16 casos. O conjunto reservado tem 26 casos com famílias diferentes e inclui redação compatível, conflitos, exceções, mudanças, ausência, períodos distintos, números e condições. O conjunto de estresse tem oito casos de linguagem implícita, formatos alternativos ou dependências externas ao trecho. O algoritmo foi congelado antes das execuções reservada e de estresse. A data de referência é 11/11/2026. Cada caso foi executado cinco vezes, com detecção determinística e sem embeddings/Ollama.

A unidade de medição é o caso e sua classificação esperada, que pode estar vazia. O acerto exato exige que o conjunto de tipos emitidos corresponda ao gabarito. Precisão, recall e F1 usam as contagens de tipos previstos por caso. A taxa de falso positivo é o número de casos negativos com ao menos um alerta dividido pelo número de negativos. A integridade das evidências verifica se os deslocamentos reproduzem o trecho literal na página indicada. Esse teste de localização não mede se o trecho sustenta a interpretação.

| Partição | Casos exatos | TP / FP / FN | Precisão | Recall | F1 | Falsos positivos nos negativos | Evidências localizáveis | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Desenvolvimento | 16/16 | 9 / 0 / 0 | 100% | 100% | 1,000 | 0/7 | 16/16 | 0,283 ms |
| Reservado | 26/26 | 15 / 0 / 0 | 100% | 100% | 1,000 | 0/11 | 30/30 | 0,238 ms |
| Estresse | 4/8 | 1 / 0 / 4 | 100% | 20% | 0,333 | 0/3 | 2/2 | 0,117 ms |

As classificações e localizações coincidiram nas cinco repetições em todos os 50 casos. O conjunto de estresse mostrou quatro falsos negativos: número por extenso, referência a anexo, obrigação implícita e data por extenso. A precisão no estresse usa apenas um alerta emitido. O resultado reservado é de regressão sintética para os padrões avaliados. O benchmark inclui extração de regras a partir de texto em memória e comparação. Não inclui ingestão, OCR, banco, fila ou chamadas ao Ollama.

Execução em Windows 11, Python 3.12.14, Intel Core i5‑12400F, 31,8 GiB de RAM e RTX 4060. O benchmark determinístico foi executado no mesmo computador dos testes locais. O relatório bruto registra as classificações, as evidências, o ambiente e as versões do extrator e do detector. [Resultado medido](../output/evaluation/auditor.json)

## Verificação da integração e da autorização

Os testes integrados cobrem upload, diferenças de escopo, estado da fila, tentativa após cancelamento, idempotência, reuso de regras, revisão, versões, evidências originais e chat. Para isolamento, são criados proprietário, membro de equipe e conta de outra organização. As asserções exigem `404` em consulta, revisão ou início sem autorização e ausência de títulos/trechos em listagem e exportação. A revogação foi exercitada após a persistência de um alerta. A exclusão remove o alerta derivado. Não houve falha de autorização nos cenários de regressão executados.

No navegador, a central foi aberta a partir da navegação do chat. O teste analisou o conjunto de demonstração, abriu as duas prévias de origem, confirmou a inconsistência com justificativa e verificou o histórico. Em instâncias isoladas, o modo vetorial usou o modelo multilíngue local, e o Qwen devolveu duas opiniões de escopo em dois candidatos de esclarecimento. A nova versão acionou a auditoria automaticamente, produziu duas alterações, tornou o conflito anterior histórico e deixou a lista de conflitos atuais vazia. Outra organização recebeu `404` no alerta e lista vazia. O chat real respondeu `R$ 200,00 [1]` e citou a versão 2. Nenhum desses ensaios mede generalização do modelo.

Validação final: 113 testes Python passaram em SQLite e 113 no PostgreSQL de teste. A cadeia de migrations chegou à revisão `20261111_0007` e correspondeu a 18 tabelas sem divergências de esquema. Os cinco testes de navegação por rolagem também passaram. O aviso do cliente de testes Starlette/HTTPX permaneceu.

## Protocolo humano cego

**Pendente de validação.** Selecionar novos documentos e 30 pares independentes, incluindo negativos difíceis, diferentes formatos, exceções, versões, datas, condições e termos implícitos. Fixar o escopo autorizado e as evidências disponíveis. Antes de rodar o Auditor, dois avaliadores devem classificar os pares de modo independente, sem ver os alertas do sistema ou o rótulo do outro avaliador. Cada um deve registrar o tipo, os documentos e páginas esperados, escopo, vigência e justificativa. Se o fato depende de anexo indisponível ou há dúvida genuína, marcar esclarecimento.

Usar uma segunda rodada cega para pontuar a fidelidade dos trechos e a justificativa de alertas em escala de 0 a 2: 0 para sem apoio ou contrário ao texto, 1 para suporte parcial e 2 para evidência suficiente. Misturar candidatos e controles sem informar a origem de cada item. Relatar concordância entre avaliadores, adjudicação, matriz de confusão, métricas com denominadores e exemplos de falhas. Usar identificadores sintéticos no [CSV de avaliação](AVALIACAO_HUMANA_AUDITOR.csv).

## Reexecução

```powershell
.venv\Scripts\python.exe -B scripts/evaluate_auditor.py --repetitions 5 --output output/evaluation/auditor_reexecucao.json
.venv\Scripts\python.exe -B -m pytest tests/test_auditor.py -q -p no:cacheprovider
.venv\Scripts\python.exe -B scripts/test_postgres_local.py
```
