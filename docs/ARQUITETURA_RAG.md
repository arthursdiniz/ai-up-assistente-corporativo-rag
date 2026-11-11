# Arquitetura do AI-Up

## Ingestão

Upload validado → registro PostgreSQL → extração em segundo plano → divisão por tokens → embeddings → geração nova de vetores → troca do ponteiro do índice.

O PDF mantém página; OCR parcial preserva texto digital mesmo se uma página falha. O DOCX é percorrido na ordem de parágrafos/tabelas. O XLSX conserva relações de cabeçalho/valor e células vazias. Seções extraídas ficam disponíveis para visualização e tarefas amplas.

O limite de chunks considera o tokenizer real (modelo atual: 128 tokens máximos; padrão de chunks: 120 incluindo tokens especiais). Perguntas longas são divididas em janelas e seus vetores combinados. Há sobreposição sem ultrapassar o teto de tokens.

## Consulta

1. API autentica, valida o acesso documental pela organização/equipe e registra um job com UUID idempotente.
2. Análise heurística identifica tarefa, continuação, quantidade pedida e formato.
3. Define escopo: seleção da conversa, arquivos nomeados, fontes da resposta anterior ou documentos ativos acessíveis. Uma nova entidade nomeada não herda automaticamente o tema anterior.
4. Busca híbrida combina embeddings e BM25 usando somente IDs autorizados no PostgreSQL e a geração ativa de cada índice. O ChromaDB não decide permissões.
5. Política de relevância e reranking ordenam candidatos. O score é sinal de recuperação, não probabilidade de verdade.
6. Resumos/checklists/planos/comparações com escopo explícito usam todas as seções desse escopo. Sem seleção, expandem os documentos mais relevantes. Documentos extensos usam sínteses hierárquicas com referências originais e orçamento de contexto, incluindo o tamanho dos rótulos.
7. Ollama local produz texto em streaming. O histórico ajuda a resolver referências, mas não é evidência documental nova.
8. As referências citadas selecionam os trechos registrados; sem referências explícitas há correspondência lexical por afirmação. Ausência ou identificadores inválidos geram aviso. Isso não é verificação automática de implicação semântica.
9. Pergunta e resposta são salvas juntas ao final; Refazer substitui apenas a última resposta. Cancelar impede o commit. A interface recebe estágios reais e deltas via SSE.

## Persistência e recuperação

PostgreSQL: organizações, equipes, convites, usuários, documentos/seções/versões, conversas, mensagens, snapshots de fontes, jobs, auditoria e as quatro tabelas do Auditor documental. Chroma: vetores e metadados. Arquivos originais ficam em armazenamento local.

Reprocessamento prepara uma nova geração de vetores antes da substituição. A limpeza ocorre depois do commit e falhas preservam a geração anterior. No chat, a FK de fontes excluídas vira nula e há regras de retenção para snapshots próprios e legados. Respostas derivadas de fontes compartilhadas dependem da ACL e da proveniência conhecida. A exclusão de uma fonte remove regras, alertas e revisões dependentes do Auditor. [Segurança e retenção](SEGURANCA_E_RETENCAO.md)

Jobs de chat têm estado persistido e transmissão parcial em memória. Durante a geração, a reconexão repete o texto acumulado sob a ACL atual. Uma conexão que chega após conclusão recebe o estado final. Um reinício interrompe o job e permite recuperar a pergunta. O cancelamento é cooperativo e uma chamada bloqueante pode permanecer ocupada até devolver controle.

## Auditor documental

Os fluxos de chat e auditoria compartilham a biblioteca, extração, OCR, versões e autorização. A auditoria não usa a resposta do chat como evidência. Seu worker separado extrai regras validadas e reusa conjuntos por geração do índice. Compara o escopo atual e versões acessíveis, revalida o acesso antes de salvar e registra decisões humanas. Veja o [pipeline, diagrama relacional e contratos](AI_UP_AUDITOR.md).

## Segurança

- Conversas, fontes e gerações são pessoais; leitura documental aceita propriedade ou compartilhamento explícito na mesma organização/equipe.
- Alteração, reprocessamento e exclusão continuam reservados ao proprietário do documento.
- Usuários, métricas e auditoria são filtrados por organização, inclusive para administradores.
- Convites são credenciais temporárias aleatórias, persistidas somente como hash e consumidas sob bloqueio transacional.
- Desativação com documentos transfere a propriedade antes de revogar as sessões, em uma única transação.
- JWT contém versão revogável; logout, troca de senha e mudança de permissões invalidam sessões.
- Último administrador ativo não pode ser rebaixado ou desativado.
- Limitador de login em memória com limites por IP/identidade.
- Conteúdo dos documentos é delimitado e o prompt manda ignorar instruções nele; isto reduz risco, não garante imunidade a injeção.
- Markdown é convertido em nós DOM seguros, sem inserir HTML do modelo.
- Ollama é restrito a loopback e modelos locais. Downloads iniciais de dependências/modelos exigem internet; o processamento documental não envia prompts a APIs externas.
- Backups e exportações não são criptografados pelo aplicativo.

## Escala e fronteiras

Aplicação local, um processo Uvicorn, até dois workers de geração por padrão, um worker do Auditor e um escritor de índice. A fila é coordenada no processo. BM25 percorre/cacheia até RAG_LEXICAL_SCAN_LIMIT trechos, padrão 5000. Filas externas, índice lexical próprio, quotas e governança precisam de avaliação antes de exposição organizacional.
