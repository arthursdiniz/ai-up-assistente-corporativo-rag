# Operação local e recuperação

## Iniciar sem redefinir contas

Abra o Ollama. No PowerShell, na raiz do projeto:

~~~powershell
.\scripts\start_ai_up.ps1
~~~

O iniciador usa a conexão e o modelo configurados, valida PostgreSQL, aplica migrations e abre o servidor em 127.0.0.1:8000. Não exige nome ou versão específica do serviço PostgreSQL. Não inicia o seed automaticamente.

Na primeira instalação, use .\scripts\start_ai_up.ps1 -Demo para criar contas ausentes. O seed preserva nomes, senhas, funções e bloqueios existentes. --reset-demo é uma operação explícita de recuperação/desenvolvimento; não use em dados reais. Senhas demo são públicas.

Para uma instalação sem contas de demonstração, execute as migrations e inicie normalmente. Quando o banco estiver vazio, a tela de login oferece **Configurar primeiro administrador**. Em desenvolvimento, faça isso em `localhost`; em homologação ou produção, defina antes um `BOOTSTRAP_TOKEN` com pelo menos 24 caracteres. O servidor não grava esse token e o fluxo é encerrado definitivamente assim que a primeira conta `IT_ADMIN` é criada.

Se a interface estiver em outro domínio, autorize somente suas origens exatas em `CORS_ALLOWED_ORIGINS`, no formato de lista JSON. O padrão `[]` mantém acessos entre origens desativados. Wildcards, caminhos, credenciais embutidas e protocolos diferentes de HTTP(S) são rejeitados ao iniciar.

SECRET_KEY forte pode ser guardada nas variáveis de usuário do Windows. Se ausente/fraca em desenvolvimento, uma chave temporária é gerada e sessões terminam ao reiniciar. Em produção uma chave configurada forte é obrigatória.

## Diagnóstico

Abra Diagnóstico e conta para conferir banco, Ollama/modelo, OCR, busca e disco. A troca de senha encerra todas as sessões. Sair também revoga os tokens existentes da conta. O limite de tentativas de login fica em memória e reinicia com o processo.

Quando a API devolver um erro, anote o `request_id` do corpo ou o cabeçalho `X-Request-ID`. Ele identifica aquela requisição sem incluir senha, token ou conteúdo documental. Tentativas de login recusadas registram somente IP e uma impressão digital curta e irreversível do e-mail normalizado. O painel administrativo apresenta eventos específicos de bloqueio, desbloqueio e mudança de perfil.

Use apenas um processo Uvicorn. Jobs e delta de streaming usam memória local; estado final é persistido no PostgreSQL. Reabrir a conversa retoma a transmissão. Reiniciar o servidor marca trabalhos interrompidos para nova tentativa. Parar impede salvar a resposta, mas uma chamada Ollama em pré-processamento pode demorar até devolver controle.

## Backup e restauração

Encerre o servidor antes de criar um backup consistente:

~~~powershell
.venv\Scripts\python.exe scripts\backup.py create
.venv\Scripts\python.exe scripts\backup.py verify --backup data\backups\PASTA_DO_BACKUP
~~~

Inclui dump PostgreSQL, uploads, Chroma e manifesto SHA-256. Arquivos não são criptografados: proteja a pasta e não a publique.

Restaure sempre em banco e pasta novos:

~~~powershell
.venv\Scripts\python.exe scripts\backup.py restore --backup data\backups\PASTA_DO_BACKUP --database ai_up_restore_novo --destination data\restore_novo
~~~

O banco ai_up_restore_novo e a pasta não podem existir. A ferramenta não sobrescreve o banco atual. Para usar a cópia, configure DATABASE_URL ou DATABASE_NAME, UPLOAD_DIR e CHROMA_DIR apontando para os novos destinos; aplique migrations antes de iniciar. Mantenha o original até validar contagens e consultas. A migration de evolução não oferece downgrade destrutivo: restaure a cópia separada.

## Reindexação

Após mudanças de modelo/tokenização, faça backup e, com o servidor encerrado:

~~~powershell
.venv\Scripts\python.exe scripts\reindex_documents.py --backup data\backups\PASTA_DO_BACKUP
~~~

Na biblioteca, Reprocessar atualiza um único arquivo. Uma geração nova de vetores fica pronta antes da troca do ponteiro. Se o reprocessamento falhar, o índice anterior continua disponível; o arquivo nunca é reescrito. Enquanto o documento está processando, ele fica fora de novas consultas.

## Limites e privacidade

Máximo padrão: 20 MB por arquivo, 500 páginas PDF, 2 milhões de caracteres extraídos; XLSX com até 500 mil células na dimensão declarada. Até 50 documentos podem ser escolhidos por conversa. Arquivos idênticos do mesmo dono são rejeitados; uma nova versão de mesmo nome arquiva as anteriores após sucesso.

Arquivar não apaga nada. Excluir remove arquivo e índice sem lixeira; só um backup anterior recupera o original. Trechos já citados e conversas permanecem. Exportações também podem conter informação sensível.

Biblioteca e conversas são isoladas por proprietário. Não há base compartilhada de equipes, múltiplos servidores ou fila distribuída. A busca lexical examina no máximo RAG_LEXICAL_SCAN_LIMIT trechos; bases maiores exigem outro índice lexical e testes de escala. Não exponha este servidor diretamente à internet.
