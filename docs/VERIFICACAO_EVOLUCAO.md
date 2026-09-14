# Verificação da evolução — 9 de setembro de 2026

## Onboarding empresarial — 10 de setembro de 2026

- Migration `20260910_0006` validada desde um PostgreSQL vazio, com 14 tabelas e nenhuma divergência em relação aos modelos SQLAlchemy.
- 83 testes passaram em SQLite e no PostgreSQL isolado `ai_up_test_20260910_211149_362623`.
- Convites armazenam somente SHA-256 do token, expiram, podem ser revogados e falham após o primeiro aceite.
- O link mantém o token no fragmento `#`; inspeção e aceite o enviam no corpo de requisições POST para evitar exposição em access logs.
- Perfil e equipes são aplicados no cadastro; convites não permitem reutilização nem e-mail já cadastrado.
- Renomear equipes preserva vínculos. Excluir equipe mantém documentos e os converte para privados.
- Desativar uma conta com documentos exige um novo proprietário ativo da mesma organização; transferência, bloqueio e revogação de sessões ocorrem no mesmo commit.
- A base principal foi protegida pelo backup verificado `data/backups/20260910T211344839269Z` e migrada para `20260910_0006` sem usuários ou documentos órfãos.
- No navegador, a página de convite apresentou corretamente o estado inválido, sem erro de console ou overlay; o access log registrou apenas `/invite.html`, sem o fragmento usado no teste.
- A página principal renovou a sessão, carregou 16 conversas e documentos com respostas HTTP 200; o rascunho existente na aba original não foi alterado.

## Organizações e bases compartilhadas — 10 de setembro de 2026

- Migration `20260910_0005` validada desde um PostgreSQL vazio, com 12 tabelas e nenhuma divergência em relação aos modelos SQLAlchemy.
- 79 testes passaram em SQLite e no PostgreSQL isolado `ai_up_test_20260910_173509_647699`.
- Documentos podem permanecer privados ou ser compartilhados com toda a organização ou com uma equipe; somente o proprietário pode alterá-los ou excluí-los.
- O escopo da conversa e a recuperação RAG aceitam documentos compartilhados somente após autorização no PostgreSQL, incluindo teste real de resposta e fonte.
- Usuários, estatísticas, qualidade e auditoria foram isolados por organização; administradores não gerenciam contas externas.
- A base principal foi protegida pelo backup verificado `data/backups/20260910T172628180574Z` e migrada sem usuários ou documentos órfãos.
- A interface administrativa ganhou gestão de empresa, equipes e integrantes; a biblioteca identifica a origem do acesso e permite escolher o escopo de compartilhamento.

## Segurança e auditoria operacional — 10 de setembro de 2026

- 76 testes passaram em SQLite e no PostgreSQL isolado `ai_up_test_20260910_045706_536513`.
- Respostas HTTP, validações e falhas internas usam contrato consistente com `error`, `message`, `detail` compatível e `request_id`.
- Os cabeçalhos originais de exceções são preservados; o limite de login continua enviando `Retry-After`.
- Toda resposta recebe `X-Request-ID`, proteção contra MIME sniffing e enquadramento; respostas da API não podem ser armazenadas em cache.
- Tentativas de login inválidas geram `LOGIN_FAILED` sem persistir e-mail ou senha, somente IP e impressão digital irreversível.
- E-mails inexistentes percorrem uma verificação Argon2 fictícia para reduzir diferenças de tempo observáveis na autenticação.
- Bloqueio, desbloqueio e mudança de perfil geram `USER_BLOCKED`, `USER_UNBLOCKED` e `USER_ROLE_CHANGED` com alvo e mudanças mínimas.
- O painel traduz os novos eventos para nomes compreensíveis em português.

## Configuração inicial e CORS — 10 de setembro de 2026

- 72 testes passaram em SQLite e no PostgreSQL isolado `ai_up_test_20260910_043438_679600`.
- A cadeia completa de migrations continua compatível com os modelos, sem alteração de schema nesta etapa.
- O CORS permanece desativado por padrão e aceita somente origens HTTP(S) explícitas; wildcard, caminhos e credenciais embutidas são rejeitados.
- O cadastro público continua fechado. A rota de configuração cria somente o primeiro `IT_ADMIN`, inicia sua sessão, audita a operação e retorna conflito após existir qualquer usuário.
- Em desenvolvimento sem token, a configuração inicial é restrita ao endereço de loopback. Nos demais ambientes, `BOOTSTRAP_TOKEN` com pelo menos 24 caracteres é obrigatório.
- A concorrência do primeiro cadastro é protegida por trava no processo e advisory lock transacional no PostgreSQL.
- Sintaxe Python/JavaScript e whitespace foram validados; permanece apenas o aviso conhecido de depreciação do TestClient.

## Evolução de sessão — 10 de setembro de 2026

- Migration `20260910_0004` validada desde um PostgreSQL vazio, sem divergências entre schema e modelos.
- 64 testes passaram tanto em SQLite quanto no PostgreSQL isolado `ai_up_test_20260910_040758_304703`.
- Login, rotação do refresh token, acesso com o novo JWT e revogação no logout foram conferidos também na API local real.
- O refresh token é opaco, persiste somente como SHA-256 no banco e viaja em cookie `HttpOnly`, `SameSite=Strict`; o access token passou de armazenamento local persistente para a sessão da aba.

## Resultado

Escopo local aprovado implementado: confiabilidade documental, inteligência contextual e usabilidade. Nenhuma conta existente foi redefinida. Nenhum documento original foi excluído. As alterações desta tarefa ainda não foram enviadas ao GitHub.

## Evidências

| Camada | Verificação | Resultado |
|---|---|---|
| Testes isolados | pytest com SQLite, arquivos temporários, mock/hash | 62 passaram |
| PostgreSQL real | Banco novo ai_up_test_20260909_212717_552512, cadeia completa de migrations + modelos + pytest | 62 passaram; modelos compatíveis |
| Dependências | pip check | Sem dependências quebradas |
| JavaScript | node --check nos arquivos JS | Sem erros sintáticos |
| Git | git diff --check | Sem erros de whitespace; avisos normais LF/CRLF |
| Backup | Manifesto SHA-256, dump, uploads e Chroma | Verificado |
| Restauração | Novo banco ai_up_restore_validation_20260909 e data/restore_validation_20260909 | Funcionou; cópia mantida para inspeção |
| Migração principal | Alembic 20260909_0003 | Aplicada |
| Reindexação | Nove documentos originais | Nove prontos, zero falhas |
| Tokenização real | 258 trechos após acrescentar o fixture de demonstração | Máximo 120 tokens, limite 120; consultas com finais distintos mantêm vetores distintos |
| Recuperação real | 20 casos sintéticos | 90% Hit@3; não é precisão textual geral |
| Geração real | Seis fixtures Ollama | 6/6 verificações controladas |

Aviso de testes: há uma depreciação emitida por Starlette/TestClient sobre httpx. Não impediu os testes e não foi feita atualização ampla de dependências por esse aviso.

## Fluxos verificados no navegador

- Login na conta de demonstração existente.
- Criação automática de conversa com documento selecionado.
- Pedido de resumo em dois tópicos e continuação “Qual é o prazo?” sobre férias.
- Citação abre o trecho correto; a página PDF original é renderizada como imagem com navegação.
- Biblioteca exibe metadados e progresso real: arquivo fictício demo_checklist.txt passou por Extraindo texto e terminou Pronto.
- Favorito e feedback positivo persistidos.
- Refazer manteve quatro mensagens na conversa de validação: nenhuma pergunta duplicada.
- Cancelamento durante Redigindo a resposta não acrescentou mensagens e recuperou a pergunta no campo de edição.
- Exportação HTML gerou C:\Users\arthu\Downloads\ai-up-conversa.html, com fontes e excertos. O evento de download do instrumento de automação expirou, mas o arquivo e o GET 200 foram confirmados.
- Layout verificado nas larguras de 1280 e 390 pixels, com histórico e saída acessíveis no menu móvel.
- Diagnóstico respondeu com banco, Ollama, OCR português, modelo em cache e disco disponíveis.
- Console da aba sem erros de JavaScript nas verificações realizadas.
- Rotas administrativas de qualidade, estatísticas e auditoria verificadas via HTTP autenticado. A criação de usuário e a troca de senha não foram executadas sobre contas reais; estão cobertas pelos testes isolados.

As skills de verificação orientaram a checagem UI → API → dados → resposta. A automação disponível foi o navegador integrado, pois agent-browser não estava instalado. A inspeção visual da skill PDF identificou um iframe em branco; a implementação passou a renderizar a página no servidor e a nova imagem foi conferida.

## Preservação

Backup anterior: data/backups/20260909T163732499396Z. A cópia restaurada contém quatro usuários, nove documentos, 14 conversas e 103 mensagens. Na conferência após os testes de interface, a base principal continha as quatro contas, os nove documentos originais mais um fixture, uma conversa adicional e quatro mensagens adicionais. Refazer/cancelar não aumentaram o total dessa conversa.

O banco de teste, a restauração e o backup foram mantidos. Uploads, índices, backups e restaurações estão ignorados no Git. Exportações podem conter dados sensíveis e devem ser guardadas com cuidado.

## Fronteiras

Citações podem estar incorretas e precisam de conferência. Resumos hierárquicos podem perder detalhes. O cancelamento é cooperativo; o modelo pode continuar ocupado até devolver controle. Não há validação humana independente concluída, avaliação de carga, servidor distribuído ou base compartilhada entre equipes. Consulte OPERACAO.md e AVALIACAO_IA.md.
