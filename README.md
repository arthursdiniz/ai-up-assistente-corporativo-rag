# AI-Up

O AI-Up é um assistente corporativo local que responde perguntas usando exclusivamente os documentos enviados pelo usuário. O fluxo principal é gratuito, privado e executado na própria máquina com arquitetura RAG (*Retrieval-Augmented Generation*).

```text
Upload → extração/OCR → chunks → embeddings → ChromaDB
Pergunta + histórico → análise → busca híbrida → reranking → Ollama → resposta + evidências
```

## Estado do projeto

O projeto local contém:

- API FastAPI com Swagger e ReDoc;
- PostgreSQL via SQLAlchemy 2 e migration Alembic reproduzível;
- access token JWT curto, refresh token rotativo em cookie `HttpOnly`, senhas Argon2 e RBAC (`USER`, `MANAGER`, `IT_ADMIN`);
- conversas, histórico e isolamento por proprietário;
- upload validado de PDF, TXT, DOCX, XLSX, PNG, JPG e JPEG;
- extração local, OCR com Tesseract e página de origem para PDFs;
- chunking configurável, Sentence Transformers e ChromaDB persistente;
- memória contextual seletiva, com mudança de assunto sem contaminar a nova pergunta;
- RAG híbrido com embeddings + BM25, deduplicação, reranking e política de suficiência;
- respostas orientadas por tarefa e fontes com documento, página/planilha e excerto;
- provedores `mock` e `ollama` desacoplados;
- auditoria, estatísticas e gerenciamento de usuários;
- interface web em português com sugestões, progresso, copiar, tentar novamente e feedback;
- testes sem API externa nem modelo pago.

## Requisitos no Windows

- [Git](https://git-scm.com/download/win)
- Python 3.12 ou superior
- [PostgreSQL](https://www.postgresql.org/download/windows/)
- [Ollama](https://ollama.com/download/windows)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) com o idioma português instalado

O Ollama e o Tesseract só são obrigatórios para geração real e OCR. O modo `mock` e documentos digitais TXT/PDF/DOCX/XLSX funcionam sem eles.

## Instalação

No PowerShell, na raiz do projeto:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Troque `SECRET_KEY` no `.env` por uma chave aleatória local com pelo menos 32 bytes. O arquivo `.env` já está ignorado pelo Git.

## PostgreSQL

Crie o banco `ai_up` usando pgAdmin ou `psql`:

```sql
CREATE DATABASE ai_up;
```

Confirme no `.env` que usuário, senha, host e porta correspondem à instalação:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ai_up
```

No Windows, a opção recomendada é guardar a credencial fora do arquivo. O AI-Up aceita as variáveis de usuário `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT` e `DATABASE_NAME`. Quando usuário e senha estão presentes, elas substituem a URL de exemplo do `.env` e caracteres especiais são codificados automaticamente.

Crie as tabelas exclusivamente pela migration e depois gere os usuários locais:

```powershell
.venv\Scripts\python.exe scripts/run_local.py --migrate-only
.venv\Scripts\python.exe scripts/seed.py
```

Para uma instalação real, não execute o seed. Inicie a aplicação com o banco vazio e use **Configurar primeiro administrador** na tela de login. Esse cadastro só funciona enquanto não existe nenhum usuário e cria exclusivamente uma conta `IT_ADMIN`. Em desenvolvimento ele é aceito apenas a partir da própria máquina; fora de desenvolvimento, configure um `BOOTSTRAP_TOKEN` forte e informe-o na tela. Depois da primeira conta, novos usuários são criados pelo painel administrativo autenticado.

Usuários de demonstração:

| E-mail | Função |
|---|---|
| `usuario@aiup.local` | USER |
| `gerente@aiup.local` | MANAGER |
| `admin@aiup.local` | IT_ADMIN |

A senha inicial é `AiUp@2026`, somente para desenvolvimento. Para usar outra senha durante o seed:

```powershell
$env:SEED_PASSWORD="uma-senha-local-forte"
python scripts/seed.py
Remove-Item Env:SEED_PASSWORD
```

## Embeddings locais

O padrão é `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, modelo multilíngue Apache 2.0. No primeiro uso ele é baixado; depois fica no cache local e pode funcionar sem internet.

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

`EMBEDDING_PROVIDER=hash` existe apenas para testes leves. Não o use na demonstração semântica do TCC.

## Ollama

1. Instale o Ollama.
2. Baixe um modelo local pequeno e multilíngue:

   ```powershell
   ollama pull qwen3:4b-instruct
   ```

3. Verifique o serviço:

   ```powershell
   ollama list
   ```

4. Configure o `.env`:

   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen3:4b-instruct
   ```

O `qwen3:4b-instruct` ocupa aproximadamente 2,5 GB na quantização padrão e é adequado para uma primeira demonstração em português. É possível trocar o modelo sem alterar código. O projeto usa somente a API local do Ollama; não configure modelos com sufixo `-cloud`.

Para desenvolver sem carregar um LLM:

```env
LLM_PROVIDER=mock
```

Nesse modo, a busca no ChromaDB continua real; apenas a redação final é previsível.

## Tesseract no Windows

Instale o Tesseract com o pacote de idioma português. Se o executável não estiver no `PATH`, configure:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Quando um PDF tiver menos de 40 caracteres extraíveis em uma página, o AI-Up renderiza a página e tenta OCR. Imagens sempre passam pelo OCR.

## Executar

### Inicialização recomendada no Windows

O script abaixo importa as variáveis do usuário, verifica PostgreSQL, Ollama e o modelo local, aplica migrations, prepara os usuários e inicia a aplicação:

```powershell
.\scripts\start_ai_up.ps1
```

Se `SECRET_KEY` não estiver definida no Windows, o inicializador cria uma chave criptograficamente segura apenas para a execução atual. Nesse caso, usuários devem fazer login novamente depois de reiniciar a aplicação.

### Inicialização manual

```powershell
.venv\Scripts\activate
uvicorn app.main:app --reload
```

Abra:

- Aplicação: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Saúde: <http://localhost:8000/api/health>

O health check retorna `degraded` quando a API está ativa, mas o PostgreSQL não está acessível.

## Testes

```powershell
pytest
```

Os testes usam SQLite apenas como banco efêmero, embeddings determinísticos e `MockLLM`. A aplicação normal continua configurada para PostgreSQL, Sentence Transformers e Ollama.

Para comparar a busca vetorial anterior com o pipeline híbrido atual:

```powershell
.venv\Scripts\python.exe scripts\evaluate_ai.py --embedding-provider sentence_transformers
```

O relatório reproduzível fica em `output/evaluation/latest.json`. A metodologia, os resultados e suas limitações estão em `docs/AVALIACAO_IA.md`.

## Demonstração para a banca

O arquivo `output/pdf/regulamento_empresa_demo.pdf` contém um regulamento fictício de três páginas preparado para validar recuperação semântica e indicação de fontes. O passo a passo e as perguntas esperadas estão em `docs/ROTEIRO_APRESENTACAO.md`.

## Configurações principais

| Variável | Finalidade | Padrão sugerido |
|---|---|---|
| `MAX_UPLOAD_SIZE_MB` | Limite por arquivo | `20` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duração do access token mantido apenas na aba | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Duração máxima da sessão renovável | `14` |
| `CORS_ALLOWED_ORIGINS` | Lista JSON de origens web autorizadas | `[]` |
| `BOOTSTRAP_TOKEN` | Segredo temporário para criar o primeiro administrador fora de desenvolvimento | vazio |
| `CHUNK_SIZE` | Tamanho aproximado do trecho | `1200` |
| `CHUNK_OVERLAP` | Sobreposição entre trechos | `200` |
| `RAG_TOP_K` | Máximo de trechos recuperados | `5` |
| `RAG_MIN_RELEVANCE` | Limiar para aceitar contexto | `0.25` |
| `RAG_BROAD_TOP_K` | Contextos usados em resumos, comparações e linhas do tempo | `8` |
| `RAG_CANDIDATE_POOL` | Candidatos antes do reranking | `20` |
| `RAG_SEMANTIC_WEIGHT` | Peso semântico na fusão híbrida | `0.65` |
| `RAG_SEMANTIC_ONLY_MIN_RELEVANCE` | Similaridade exigida sem apoio lexical | `0.50` |
| `RAG_LEXICAL_SCAN_LIMIT` | Máximo de chunks do usuário na busca BM25 local | `5000` |
| `CONVERSATION_HISTORY_MESSAGES` | Mensagens recentes usadas para continuidade | `6` |
| `CONVERSATION_HISTORY_CHAR_LIMIT` | Limite de caracteres do histórico enviado ao modelo | `6000` |
| `UPLOAD_DIR` | Arquivos originais | `./data/uploads` |
| `CHROMA_DIR` | Índice vetorial persistente | `./data/chroma` |

## Persistência e privacidade

- PostgreSQL guarda usuários, chats, mensagens, documentos, fontes e auditoria.
- ChromaDB persiste embeddings em `data/chroma/`.
- Arquivos ficam em `data/uploads/` com nome interno UUID.
- A busca sempre filtra `user_id`; funções administrativas não recebem acesso automático ao conteúdo privado.
- Nenhum documento, embedding ou prompt é enviado para APIs comerciais.

Ao apagar um documento, o arquivo local e seus vetores também são removidos. Ao apagar uma conversa, suas mensagens e relações de fontes são excluídas em cascata.

## Segurança

- senhas com Argon2;
- JWT assinado, curto e com expiração configurável;
- refresh tokens opacos, armazenados somente como hash, rotacionados a cada uso e enviados em cookie `HttpOnly` com `SameSite=Strict`;
- access token mantido em `sessionStorage`, sem persistência entre sessões do navegador;
- logout, troca de senha, alteração de função e bloqueio revogam sessões renováveis;
- autorização no backend;
- validação de conteúdo real e extensão do upload;
- limite lido antes de persistir o arquivo;
- nomes internos UUID e proteção contra *path traversal*;
- consultas parametrizadas pelo ORM;
- ausência de segredos nos logs;
- CORS fechado por padrão, sem wildcard, e credenciais liberadas somente para origens HTTP(S) explícitas;
- configuração inicial de uso único, limitada ao banco vazio, ao acesso local em desenvolvimento ou a um token forte nos demais ambientes.
- respostas de erro com código estável e identificador de requisição para diagnóstico, sem exposição de stack trace;
- tentativas de login recusadas auditadas por IP e impressão digital irreversível do identificador, sem armazenar a senha ou o e-mail informado;
- verificação de senha de custo equivalente para e-mails inexistentes, reduzindo enumeração de contas por tempo de resposta;
- eventos distintos para bloqueio, desbloqueio e troca de perfil de acesso.

O logout incrementa a versão de segurança da conta, revoga os refresh tokens no PostgreSQL e remove o cookie da sessão. A renovação usa rotação de uso único: um token antigo não pode ser reutilizado depois de emitir o próximo.

Para um frontend hospedado em outra origem, configure uma lista JSON exata, sem barras finais ou caminhos:

```env
CORS_ALLOWED_ORIGINS=["https://assistente.empresa.com"]
```

Não use `*`: o AI-Up transporta credenciais e rejeita curingas na inicialização.

Erros da API mantêm o campo legado `detail` e também retornam `error`, `message` e `request_id`. O mesmo identificador aparece no cabeçalho `X-Request-ID`, permitindo correlacionar um erro apresentado ao usuário com o log técnico sem revelar dados internos. Respostas da API usam `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` e `X-Frame-Options: DENY`.

## Custo do projeto e licenças

| Componente | Uso local | Licença/observação |
|---|---|---|
| Python, FastAPI, SQLAlchemy, Alembic | Gratuito | Open source |
| PostgreSQL | Gratuito | PostgreSQL License |
| ChromaDB | Gratuito e local | Apache 2.0 |
| Sentence Transformers | Gratuito e local | Apache 2.0; cada modelo também deve ser conferido |
| Modelo MiniLM configurado | Gratuito e local | Apache 2.0 |
| Ollama local | Gratuito | O modelo escolhido possui licença própria |
| Qwen3 4B Instruct | Gratuito e local | Apache 2.0 |
| Tesseract | Gratuito e local | Apache 2.0 |
| python-docx, openpyxl, Pillow | Gratuito | Open source |
| PyMuPDF | Gratuito sob AGPL-3.0 | Também oferece licença comercial |
| HTML, CSS e JavaScript | Gratuito | Tecnologias web abertas |

### Atenção à licença do PyMuPDF

O PyMuPDF é distribuído sob AGPL-3.0 ou licença comercial. Para uso acadêmico local, a opção AGPL pode ser adequada. Antes de publicar ou distribuir o AI-Up, confirme com a instituição se o trabalho será licenciado de forma compatível; caso contrário, substitua o adaptador de PDF por uma alternativa permissiva. A extração está isolada em `ExtractionService` para tornar essa troca simples.

## Estrutura

```text
app/
├── api/           # rotas e dependências HTTP
├── core/          # configuração, JWT e permissões
├── db/            # Base e sessões SQLAlchemy
├── models/        # entidades relacionais
├── repositories/  # consultas orientadas a domínio
├── schemas/       # contratos Pydantic
├── services/      # extração, RAG, embeddings, Chroma e auditoria
│   └── llm/       # mock e Ollama
└── static/        # interface web
migrations/        # evolução reproduzível do PostgreSQL
scripts/seed.py    # usuários de desenvolvimento
scripts/evaluate_ai.py # avaliação reproduzível da recuperação
evals/             # corpus e casos de regressão da IA
docs/              # arquitetura, diagnóstico, avaliação e roteiro da banca
tests/             # testes locais e sem custo
data/              # uploads e vetores persistentes (não versionados)
```

## Limitações conscientes do MVP

- processamento em segundo plano e jobs de geração são locais e monoprocesso; reinícios exigem nova tentativa dos trabalhos interrompidos;
- a busca BM25 local examina até `RAG_LEXICAL_SCAN_LIMIT` chunks por usuário e deve migrar para um índice dedicado em bases muito grandes;
- revogação de tokens é por conta; sair encerra todas as sessões dessa conta;
- não há compartilhamento de documentos entre usuários;
- não há Docker, cloud, filas, Redis ou microsserviços;
- qualidade e velocidade do texto gerado dependem do modelo local e do hardware.
- os 20 casos de recuperação e seis fixtures de geração são sintéticos e devem ser ampliados com documentos inéditos e revisão humana antes de uso em produção.

Essas escolhas mantêm o sistema simples, gratuito, defensável no TCC e pronto para evolução posterior.


## Evolução de usabilidade e confiabilidade (setembro de 2026)

- Chat com criação automática, rascunhos por conta, busca, favoritos, histórico paginado e navegação móvel.
- Escopo por conversa, streaming real, cancelamento, retomada e repetição sem duplicar o turno.
- Biblioteca com upload múltiplo/drop, processamento em segundo plano, progresso por etapa, filtros, categorias, duplicatas, versões e reprocessamento.
- Visualização de páginas PDF no servidor, extração estruturada de DOCX/XLSX e fontes históricas preservadas.
- Chunks limitados pelos tokens do modelo; consultas longas divididas em janelas, sem descartar silenciosamente o final.
- Resumos, comparação, checklist, plano de ação e exportações Markdown/HTML/JSON com fontes.
- Troca de senha, revogação, limite de login, proteção do último administrador e seed não destrutivo.
- Sessões renováveis com refresh token rotativo, cookie `HttpOnly` e revogação centralizada.
- Diagnóstico, painel de qualidade, backup verificável e validação de migrations em PostgreSQL.

Início habitual: .\scripts\start_ai_up.ps1 (abra o Ollama antes). Primeira instalação com contas demo: acrescente -Demo. A senha demo é somente inicial; contas existentes nunca são redefinidas automaticamente.

Leia docs/OPERACAO.md para recuperação e limites, docs/AVALIACAO_IA.md para os resultados atuais e docs/ROTEIRO_APRESENTACAO.md para a demonstração. O sistema é local, monoprocesso e não oferece bases compartilhadas entre equipes.
