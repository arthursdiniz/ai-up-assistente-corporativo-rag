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

PostgreSQL: usuários, documentos/seções/versões, conversas, mensagens, snapshots de fontes, jobs e auditoria. Chroma: vetores e metadados. Arquivos originais ficam em armazenamento local.

Reprocessamento prepara uma nova geração de vetores antes da substituição. A limpeza ocorre depois do commit; falhas preservam a geração anterior. Excluir um documento não apaga trechos já citados: a FK vira nula e o snapshot do nome/excerto permanece.

Jobs têm estado persistido e transmissão parcial em memória. Reconexão repete o texto acumulado; a interface reconstrói a resposta desde o início. Um reinício interrompe o job e permite recuperar a pergunta. O cancelamento é cooperativo: o modelo pode permanecer ocupado durante uma chamada bloqueante até devolver controle.

## Segurança

- Conversas, fontes e gerações são pessoais; leitura documental aceita propriedade ou compartilhamento explícito na mesma organização/equipe.
- Alteração, reprocessamento e exclusão continuam reservados ao proprietário do documento.
- Usuários, métricas e auditoria são filtrados por organização, inclusive para administradores.
- JWT contém versão revogável; logout, troca de senha e mudança de permissões invalidam sessões.
- Último administrador ativo não pode ser rebaixado ou desativado.
- Limitador de login em memória com limites por IP/identidade.
- Conteúdo dos documentos é delimitado e o prompt manda ignorar instruções nele; isto reduz risco, não garante imunidade a injeção.
- Markdown é convertido em nós DOM seguros, sem inserir HTML do modelo.
- Ollama é restrito a loopback e modelos locais. Downloads iniciais de dependências/modelos exigem internet; o processamento documental não envia prompts a APIs externas.
- Backups e exportações não são criptografados pelo aplicativo.

## Escala e fronteiras

Aplicação local, um processo Uvicorn, até dois workers de geração por padrão e um escritor de índice. Não suporta coordenação de jobs entre réplicas. BM25 percorre/cacheia até RAG_LEXICAL_SCAN_LIMIT trechos, padrão 5000. Avaliar filas externas, índice lexical próprio, quotas e governança antes de exposição organizacional.
