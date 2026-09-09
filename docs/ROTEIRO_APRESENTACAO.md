# Roteiro de apresentação do AI-Up — 5 minutos

## Preparação

Execute `./scripts/start_ai_up.ps1`, abra `http://localhost:8000` e entre com `usuario@aiup.local`. A senha inicial local é `AiUp@2026`. Envie `output/pdf/regulamento_empresa_demo.pdf` em **Documentos** e aguarde **Pronto**.

## 0:00–0:40 — problema e proposta

“Empresas acumulam regulamentos e contratos, mas localizar uma resposta verificável consome tempo. O AI-Up é um assistente corporativo privado: consulta os documentos do próprio usuário, executa a IA localmente e mostra a evidência.”

Mostre rapidamente **Documentos** e destaque tipos aceitos, status e isolamento por usuário.

## 0:40–1:35 — pergunta direta e evidência

Pergunte:

> Quantos dias de férias o colaborador possui e com qual antecedência deve fazer o pedido?

Mostre a resposta esperada — 30 dias e pedido com 30 dias corridos —, expanda **Fonte 1**, aponte nome do documento, página e excerto. Use **Copiar** para demonstrar utilidade prática.

## 1:35–2:25 — memória contextual

Na mesma conversa, pergunte:

> E o que mais é importante saber sobre elas?

Explique que a pergunta isolada é vaga, mas o AI-Up identifica “elas” como férias, usa somente o histórico recente necessário e refaz a busca. Mostre que o título “Nova conversa” também foi criado automaticamente pela primeira pergunta.

## 2:25–3:10 — exatidão e tarefas

Pergunte:

> Liste os prazos e valores mais importantes do regulamento.

Explique que o classificador escolhe uma extração ampla, busca mais páginas e pede ao modelo uma lista estruturada. A busca híbrida combina significado com BM25 para não perder números, siglas ou códigos.

## 3:10–3:45 — ausência de informação

Pergunte:

> Qual é o valor do vale-alimentação oferecido pela empresa?

Mostre a recusa esperada. Explique que uma política de suficiência impede que uma página apenas parecida seja apresentada como prova.

## 3:45–4:20 — experiência e melhoria contínua

Mostre os estados de processamento, **Tentar novamente**, 👍/👎 e sugestões iniciais. Explique que o feedback já é persistido por mensagem e forma a base de uma avaliação futura sem permitir que um usuário altere mensagens de outro.

## 4:20–5:00 — arquitetura e números

Abra `docs/ARQUITETURA_RAG.md` e resuma: extração/OCR, chunks, embeddings, ChromaDB, busca híbrida, reranking, Ollama e fontes no PostgreSQL. Feche com os resultados: 100% de Hit@3 e Top‑1 nos treze casos locais, precisão média das fontes de 51,28% para 74,36% e zero vazamento entre usuários.

## Perguntas prováveis da banca

**A IA pode inventar?** Pode haver erro de geração; por isso o prompt limita fatos ao contexto, a recuperação rejeita evidência fraca e a interface mostra o excerto para conferência.

**Por que não usar ChatGPT na nuvem?** O objetivo é privacidade, ausência de custo recorrente e funcionamento local. A camada de provedor permite outra integração futura sem reescrever o RAG.

**Por que PostgreSQL e ChromaDB?** PostgreSQL guarda entidades, permissões e auditoria; ChromaDB é otimizado para vetores. Cada ferramenta resolve uma responsabilidade diferente.

**O resultado de 100% é definitivo?** Não. É um teste de regressão pequeno e sintético. O documento de avaliação registra essa limitação e propõe ampliar o corpus e a validação humana.

**Como o sistema protege os dados?** Autorização é validada no backend e ambas as buscas são filtradas por `user_id`; documentos e prompts não saem da máquina.

**Como evoluiria para produção?** Processamento assíncrono, índice lexical escalável, revogação de tokens, monitoramento, conjunto de avaliação real e governança de retenção.
