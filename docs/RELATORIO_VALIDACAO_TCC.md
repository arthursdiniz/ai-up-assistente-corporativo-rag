# Auditoria técnica e validação experimental do AI-Up

Execuções locais em 11 de novembro de 2026. O projeto mantém a arquitetura Python/FastAPI, PostgreSQL, ChromaDB e Ollama. As medições usam casos sintéticos. O banco operacional ficou fora dos experimentos.

## Estado inicial e alterações

O sistema já extraía texto e estruturas de TXT, PDF, DOCX e XLSX, com OCR em fluxos compatíveis. O chunking respeitava limites do tokenizador, preservava localizadores e mantinha sobreposição. Já existiam recuperação vetorial e lexical, reordenação, filtros de relevância, contexto de conversa, snapshots de fontes, renovação de sessão, jobs canceláveis, backups e testes. As principais lacunas eram a avaliação pequena e agregada, a perda de autorização em caminhos derivados, o tratamento de fluxo incompleto do modelo e a ausência de carga reproduzível.

| Crítica | Estado | Evidência |
|---|---|---|
| Acesso após perda de compartilhamento | IMPLEMENTADO / TESTADO | Revalidação de resposta, fontes, busca, exportação, replay e contexto, com teste de revogação durante a geração. |
| Geração interrompida e falhas documentais | IMPLEMENTADO / TESTADO | Fluxo Ollama sem evento final falha. Testes cobrem falta de modelo, indisponibilidade, erro em fluxo, cancelamento, reinício, saúde com falha de banco, arquivo inválido, indexação inicial e manutenção da versão anterior após falha de reprocessamento. |
| Citações e injeção documental | IMPLEMENTADO / TESTADO | Instrução de citação revisada com comparação pareada, referências inválidas removidas do texto final e checagem de literais nos trechos citados. O benchmark inclui tentativa de trocar regras, fechar a tag, forçar referência, executar comando e obter dado de outra equipe. A autorização é independente da resposta do modelo. |
| Qualidade da recuperação | TESTADO | 84 casos, sete grupos, sete variantes, métricas a K = 1, 3 e 5. Pesos e limiares mantidos. |
| Contexto insuficiente | TESTADO / PROPOSTO | A validação preserva fontes de respostas parcialmente sustentadas. O teste reservado mostra que o filtro de recuperação sozinho ainda aceita trechos nas perguntas sem resposta. Um classificador de suficiência exige avaliação separada antes de entrar no produto. |
| Comparação de modelos | TESTADO | 52 casos por modelo, duas versões da instrução de citação, medidas de latência e memória reportada pelo Ollama. Qwen permanece padrão. |
| Carga e concorrência | TESTADO | 144 operações HTTP com mock em SQLite temporário e oito gerações com Qwen pela API, incluindo dois clientes simultâneos. Carga prolongada e carga em PostgreSQL continuam PROPOSTAS. |
| Correção semântica, completude, qualidade do português e evidência por afirmação | PENDENTE DE VALIDAÇÃO HUMANA | Protocolo com perguntas inéditas, dois avaliadores e planilha CSV. |
| Retenção e cifragem | PROPOSTO | Inventário, aprovação dos responsáveis, teste de restauração e regras para dados legados. Ver [Segurança e retenção](SEGURANCA_E_RETENCAO.md). |

## Configuração experimental

Windows 11, build 26200, Intel Core i5-12400F, 31,8 GiB de RAM, NVIDIA GeForce RTX 4060 com 8.188 MiB de VRAM reportada e driver 610.88. Python 3.12.14, ChromaDB 1.5.9, Sentence Transformers 6.0.0, PyTorch 2.13.0, HTTPX 0.28.1 e Ollama 0.40.9. Os modelos locais medidos têm quantização Q4_K_M. Não houve download de modelo de linguagem durante o trabalho.

### Recuperação

Corpus com 12 políticas fictícias e 24 páginas sintéticas, indexadas como trechos rotulados `(documento, página)` em Chroma efêmero. Grupos de desenvolvimento e teste reservado têm 42 perguntas cada, seis por categoria e organizações distintas. Cada grupo contém 36 perguntas respondíveis e seis com informação ausente. As mesmas páginas ficaram disponíveis para todas as variantes. Os critérios foram definidos antes de rodar a comparação. O índice usa embeddings `paraphrase-multilingual-MiniLM-L12-v2`. O benchmark usa páginas curtas pré-extraídas para isolar a recuperação. O teste de carga e a suíte verificam a ingestão separadamente.

Hit@K verifica se apareceu ao menos uma página relevante. Precision@K divide o número de páginas relevantes retornadas por K. Recall@K divide pelo total rotulado para a pergunta. MRR usa o inverso da primeira posição relevante no conjunto retornado, limitado ao pool de 20 candidatos ou ao corte da variante. A métrica de cobertura completa exige todas as páginas rotuladas. As médias são por pergunta respondível, com páginas duplicadas contadas uma vez. Para casos sem resposta, medimos a fração que terminou sem trechos. As latências de recuperação da tabela não incluem o tempo de embedding, cuja mediana foi 13,5 ms. Criação e preenchimento do índice efêmero levaram 1.255,3 ms.

| Teste reservado, K=3 | Hit@3 | Precision@3 | Recall@3 | MRR | Sem trecho nos casos ausentes | Mediana / p95 busca |
|---|---:|---:|---:|---:|---:|---:|
| Vetorial | 97,22% | 43,52% | 97,22% | 0,9491 | 0/6 | 1,19 / 1,60 ms |
| BM25 com ajuste de cobertura | 100% | 44,44% | 100% | 1,0000 | 0/6 | 0,56 / 0,72 ms |
| Híbrida, peso semântico 0,25 | 100% | 44,44% | 100% | 1,0000 | 0/6 | 2,32 / 2,80 ms |
| Híbrida, peso 0,50 | 100% | 44,44% | 100% | 1,0000 | 0/6 | 2,26 / 2,78 ms |
| Híbrida, peso 0,65 | 100% | 44,44% | 100% | 1,0000 | 0/6 | 2,38 / 2,60 ms |
| Híbrida, peso 0,80 | 100% | 44,44% | 100% | 1,0000 | 0/6 | 2,33 / 2,54 ms |
| Pipeline atual, híbrida + filtro + reordenação | 100% | 44,44% | 100% | 1,0000 | 0/6 | 2,49 / 3,33 ms |

Na partição de desenvolvimento, o Hit@3 também foi 97,22% para vetorial e 100% nas demais abordagens. Os nomes, códigos e a estrutura repetida das políticas favorecem correspondência lexical. A amostra oferece pouca evidência para escolher outro peso ou abrir mão da busca vetorial. As quatro configurações híbridas empataram no teste reservado. No pipeline atual, 36/36 perguntas respondíveis tiveram todas as páginas esperadas no top 3. Já nos seis casos ausentes, havia páginas sobre o assunto, mas sem o fato solicitado. Essa diferença deve ser mantida na interpretação: recuperação de tópicos e verificação de suficiência factual são medidas distintas. O teste também não cobre expansão hierárquica de documentos longos.

Dados por pergunta, partição, categoria e K no [resultado de recuperação](../output/evaluation/retrieval_academic.json).

### Geração com Ollama

Cada modelo recebeu os mesmos 52 casos por rodada: 42 do teste reservado, cinco fixtures complementares e cinco adversariais. Os trechos relevantes foram selecionados pelo gabarito. Para perguntas sem resposta foram usadas páginas da política correspondente que tratam do assunto sem fornecer o fato. O teste usa o mesmo provedor e caminho de streaming da aplicação e coleta a saída bruta antes da validação do RAG. Temperatura 0, janela de 8.192 e limite de 1.200 tokens. Os modelos rodaram sequencialmente e a primeira chamada pode incluir carga de pesos. Primeiro texto é o tempo até o primeiro fragmento de resposta visível, sem incluir tokens internos de raciocínio.

Um caso passa se contém os literais previstos, omite marcadores proibidos, obedece ao gabarito de recusa, cita as fontes esperadas e não aciona o detector de incompatibilidade literal. Os critérios são automáticos e limitados a padrões explícitos. A instrução anterior usava `[N]` como exemplo de formato. A revisão trocou o exemplo por `[1]` e indicou de onde copiar o número. A segunda rodada mede a correção nos mesmos casos vistos, portanto é evidência de regressão. A generalização da revisão ainda exige a avaliação inédita.

| Modelo | Antes / depois | Ausência no reservado | Adversarial após revisão | Primeiro texto mediana / p95 | Total médio / mediana / p95 | VRAM residente após rodada |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3 4B Instruct | 41/52 → 52/52 | 6/6 | 5/5 | 68 / 122 ms | 803 / 332 / 2.481 ms | 3,61 GiB |
| Llama 3.1 8B | 39/52 → 45/52 | 6/6 | 4/5 | 84 / 151 ms | 1.051 / 504 / 3.257 ms | 5,42 GiB |

Nenhuma requisição falhou tecnicamente nas duas rodadas completas. Antes da revisão, o Qwen respondeu com `[999]` em um documento que solicitava essa referência e escreveu `[N]` em respostas factuais. Após a revisão, as seis perguntas factuais do Qwen passaram nos critérios automáticos. O Llama recusou indevidamente cinco das seis perguntas contextuais na segunda rodada e também recusou um caso adversarial que tinha resposta. A presença de números corretos em casos de divergência não confirma se o modelo interpretou a vigência corretamente. A memória é um snapshot da alocação reportada pelo Ollama, sem amostragem de pico, uso de GPU ou CPU do processo de geração. Consulte [contrato da API de chat](https://docs.ollama.com/api/chat) e [consulta de modelos em memória](https://docs.ollama.com/api/ps).

Saídas sintéticas completas da [rodada inicial](../output/evaluation/models_academic_full.json) e da [rodada revisada](../output/evaluation/models_academic_revised.json).

### Carga HTTP isolada

Um Uvicorn em porta efêmera, SQLite e Chroma em diretório temporário, embeddings hash e geração mock. Documentos TXT curtos são indexados de modo síncrono. Cada operação de um lote usa conta sintética própria. Executamos 12 operações de cada tipo para 1, 2 e 4 concorrentes, em ordem crescente. O teste contabiliza uma operação HTTP por amostra. O custo do cliente e do servidor é medido em conjunto no mesmo processo.

| Operação | Concorrência | Média / mediana / p95 em ms | Operações/s | Erros |
|---|---:|---:|---:|---:|
| Login | 1 | 49,46 / 49,35 / 50,87 | 20,19 | 0/12 |
| Login | 2 | 65,47 / 63,59 / 78,07 | 29,57 | 0/12 |
| Login | 4 | 105,98 / 105,75 / 124,82 | 35,97 | 0/12 |
| Listagem | 1 | 3,99 / 3,77 / 5,29 | 247,24 | 0/12 |
| Listagem | 2 | 6,19 / 6,22 / 7,50 | 312,55 | 0/12 |
| Listagem | 4 | 11,87 / 11,55 / 15,67 | 302,51 | 0/12 |
| Upload + índice | 1 | 32,09 / 31,82 / 36,02 | 31,11 | 0/12 |
| Upload + índice | 2 | 67,25 / 64,55 / 92,95 | 28,91 | 0/12 |
| Upload + índice | 4 | 134,86 / 143,55 / 170,22 | 27,00 | 0/12 |
| RAG com mock | 1 | 15,11 / 14,49 / 18,27 | 65,94 | 0/12 |
| RAG com mock | 2 | 29,35 / 24,13 / 49,88 | 66,27 | 0/12 |
| RAG com mock | 4 | 66,64 / 70,91 / 105,50 | 53,53 | 0/12 |

A mediana da etapa interna de recuperação foi 5 ms com um cliente, 8 ms com dois e 19,5 ms com quatro. A 4 concorrentes, o tempo de CPU do processo para 12 operações foi 2,81 s no login, 0,05 s na listagem, 0,33 s no upload e 0,25 s no RAG com mock. A tabela caracteriza apenas este ensaio local curto. Filas de geração, RAM de pico, OCR de arquivos grandes, conexão remota e carga em PostgreSQL precisam de medições próprias. Os dados completos estão no [resultado de carga HTTP](../output/evaluation/api_academic.json).

Um segundo ensaio usou Qwen real, duas threads de geração e a API de jobs e eventos SSE. O tempo total começa no envio da pergunta e termina no evento final, incluindo autenticação, fila, busca, geração e o intervalo de polling do servidor. O cliente observou um fragmento SSE em quatro das oito respostas. As demais terminaram antes da entrega de um fragmento e retornaram a resposta final. A latência ao primeiro texto do benchmark direto do Ollama cobre todas as respostas e mede uma etapa diferente.

| Clientes | Operações | Erros | Média / mediana / p95 total | Operações/s | Mediana até primeiro SSE |
|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 0 | 923 / 292 / 2.447 ms | 1,08 | 2.571 ms, 1 amostra |
| 2 | 4 | 0 | 488 / 534 / 561 ms | 3,62 | 280 ms, 3 amostras |

A primeira série inclui o carregamento inicial do modelo. A segunda rodou na sequência, com o modelo já utilizado. A ordem, o tamanho da amostra e o aquecimento impedem atribuir a diferença de latência à concorrência. Dados individuais no [resultado do ensaio com Ollama](../output/evaluation/api_ollama_academic.json).

## Reproduzir no Windows

Na raiz do projeto, com as dependências já instaladas no ambiente virtual:

```powershell
.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
node --test tests/scroll_navigation.test.cjs
.venv\Scripts\python.exe -B scripts/test_postgres_local.py

$env:HF_HUB_OFFLINE='1'  # quando o embedding já estiver em cache
$env:OMP_NUM_THREADS='2'
.venv\Scripts\python.exe -B scripts/benchmark_retrieval.py --output output/evaluation/retrieval_reexecucao.json
.venv\Scripts\python.exe -B scripts/benchmark_api.py --workers 1 2 4 --operations 12 --output output/evaluation/api_reexecucao.json
.venv\Scripts\python.exe -B scripts/benchmark_api.py --workers 1 2 --operations 4 --ollama-model qwen3:4b-instruct --output output/evaluation/api_ollama_reexecucao.json
.venv\Scripts\python.exe -B scripts/benchmark_models.py --models qwen3:4b-instruct llama3.1:8b --output output/evaluation/models_reexecucao.json
```

O script PostgreSQL exige o serviço e permissão para criar um banco novo `ai_up_test_*`. A cadeia chega a `20260910_0006` e compara as 14 tabelas com os modelos. O script preserva o banco de teste para inspeção. O benchmark HTTP não exige PostgreSQL. Para comparação sem cache do embedding, disponibilize-o primeiro e então reative o modo offline. O benchmark Ollama exige serviço em loopback, registra modelos ausentes como ignorados e não baixa pesos. A opção `--smoke` roda 12 casos por modelo para uma demonstração curta. Passe um caminho de saída novo para preservar os relatórios históricos.

A suíte final passou com 102 testes em SQLite e 102 em PostgreSQL isolado, com um aviso de depreciação do cliente de testes Starlette/HTTPX. Os cinco testes de navegação por rolagem também passaram.

## Ameaças à validade e próximos experimentos

As perguntas sintéticas compartilham estruturas e nomes fáceis de identificar. O gabarito fixa relevância em nível de página, não todas as possíveis redações equivalentes. A comparação de modelos usa contexto conhecido, uma execução por caso e verificações literais. A carga HTTP é curta e local. Esses limites impedem extrapolar os números para acurácia geral, ausência de alucinação ou capacidade em número de usuários. O próximo experimento é a [avaliação humana cega](PROTOCOLO_AVALIACAO_HUMANA.md), seguida de repetição em corpus com layouts diversos, carga gradual em PostgreSQL de teste e ensaios de geração mais longos com amostragem de CPU, RAM e GPU.
