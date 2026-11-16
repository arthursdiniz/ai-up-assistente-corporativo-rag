# Instalação e recuperação no Windows

Extraia o ZIP para uma pasta local gravável e abra `Iniciar.bat` com sua conta normal. Quando faltar um componente, confirme a instalação no assistente e conclua a interface do fornecedor. O Windows pode exibir UAC. Se você não puder autorizar, peça ao administrador para instalar o componente, depois retome com sua conta. `Instalar.bat` prepara o ambiente e repete diagnósticos sem iniciar o FastAPI. Em caso de falha, a janela permanece aberta.

| Etapa | Comportamento |
|---|---|
| Python e Visual C++ | Reutiliza Python 3.12 ou 3.13 x64, preferindo 3.12. Detecta o runtime Visual C++. Para componentes ausentes, oferece WinGet e fallback com executável oficial e SHA-256 fixado. |
| Pacotes Python | Verifica a resolução offline com pip. Instala somente quando há requisitos faltantes ou incompatíveis. Renomeia `.venv` inválida para `.venv.backup-*` antes de criar outra. |
| PostgreSQL | Reutiliza credenciais explícitas. Em instalação nova, reaproveita binários encontrados ou baixa o ZIP oficial EDB com SHA-256 verificado. Prepara um cluster privado com SCRAM em `127.0.0.1` numa porta livre entre 55432 e 55451. O usuário `aiup_app` possui seu banco e não tem os privilégios globais `SUPERUSER`, `CREATEDB` ou `CREATEROLE`. |
| Configuração | Gera `.env` com padrões públicos. Credenciais e chave geradas ficam em `settings.env` sob `%LOCALAPPDATA%\AI-Up\installations`, com ACL da conta Windows e SYSTEM. Preserva configurações existentes. Uma chave vazia ou de exemplo recebe uma chave privada persistente ao usar o atalho. |
| IA e OCR | Valida Ollama e modelo local. Baixa somente o necessário com consentimento. O OCR usa o Tesseract e o idioma `por`, com dados de idioma oficiais e verificados quando faltam. Testa uma imagem sintética, embeddings, ChromaDB em memória e uma geração curta do Ollama. |
| Inicialização | Valida o banco e aplica migrations sem criar contas demo. Testa os diretórios de dados e abre o navegador depois que a API responde com saúde em `127.0.0.1:8000`. Reutiliza uma instância AI-Up já ativa e sinaliza conflito com outro aplicativo. |

Reserve **10–15 GB** para instalar e espaço adicional para documentos e índices. O Qwen padrão ocupa cerca de **2,5 GB**. O modo completo pode rodar na CPU, com desempenho variável. Recomenda-se 16 GB de RAM. Em uma instalação nova, a pergunta sobre modo básico permite escolher embeddings de teste e respostas simuladas para hardware limitado. Uma falha no modo completo não alterna automaticamente para esse modo. Configurações explícitas de projetos anteriores continuam valendo.

## Diagnóstico, atualização e remoção

- Reabra o atalho após corrigir falhas de internet, espaço ou permissões. O assistente reaproveita etapas concluídas. Se um instalador pedir reinício ou sofrer bloqueio do Windows, confira a mensagem do fornecedor antes de retomar.
- Para uma pasta no OneDrive, mantenha o ZIP extraído disponível localmente. Se houver problemas com sincronização ou proteção de pastas, teste uma pasta local NTFS gravável. O instalador recusa caminhos de rede e unidades de rede mapeadas.
- Se você configurou um PostgreSQL externo ao instalador, inicie seu serviço habitual quando ele estiver parado. O atalho inicia automaticamente apenas o cluster privado que gerencia. Se o `.env` estiver perdido e existirem uploads ou índice, recupere as credenciais ou o `.env` original antes de continuar.
- Se uma porta do banco privado estiver ocupada e o cluster estiver parado, o atalho pode escolher outra porta da faixa privada e reaproveitar o mesmo banco. Conexões configuradas explicitamente exigem liberar a porta ou revisar a configuração. Se `database.json` estiver ilegível, restaure a cópia correspondente antes de prosseguir.
- O atalho verifica se as pastas de dados são graváveis e se o índice ChromaDB pode ser lido. Em caso de índice bloqueado, feche as outras instâncias. Em caso de modelo trocado ou de índice corrompido, faça backup e siga o [guia de operação e reindexação](OPERACAO.md).
- Confira `setup.log` e `postgresql.log` na subpasta correspondente em `%LOCALAPPDATA%\AI-Up\installations`. O primeiro registra etapas e códigos sem registrar credenciais. Falhas anteriores à preparação do perfil aparecem no terminal. Não publique `settings.env` ou `database.json`.
- Use o mesmo caminho do checkout ao atualizar. A pasta privada é identificada pelo caminho da instalação. Faça backup do banco, dos uploads, do ChromaDB e da configuração privada antes de mover ou remover a pasta. Encerre o aplicativo com `Ctrl+C`. Para parar o cluster privado, use os binários PostgreSQL correspondentes com `pg_ctl stop -D <pasta-privada>\cluster -m fast -w`. O atalho não registra serviço global e não remove dados ou componentes compartilhados automaticamente.
- Para congelar a distribuição, gere um `requirements-win-x64-py312.lock` com versões transitivas e hashes em uma VM limpa. Valide com `pip install --require-hashes -r requirements-win-x64-py312.lock` e rode a suíte antes de distribuir. O assistente usa as faixas atuais de `requirements.txt` até existir um lock validado nesse ambiente.

## Aceite em VM Windows limpa

1. Tire um snapshot e entre com uma conta normal. Extraia o ZIP numa pasta com espaços e acentos. Rode `Iniciar.bat` sem Python, Ollama, Tesseract ou PostgreSQL. Repita com e sem WinGet. Verifique confirmação, termos, UAC e a recusa sem execução do instalador.
2. Interrompa a preparação durante um download e reabra o atalho. Repita com rede indisponível, pouco espaço e `.venv` incompleta. Confira recuperação e preservação da `.venv` anterior. Teste a versão portátil da EDB também num perfil do Windows cujo nome tem acentos.
3. No modo completo, confira `/api/health`, crie o primeiro administrador, entre e envie um TXT e um PNG com uma frase em português. Confira OCR, indexação, resposta real do Ollama e fonte original. Confirme que nenhuma conta demo foi criada automaticamente.
4. Feche, reabra e reinicie a VM. Verifique que não há reinstalação e que a conta, os documentos, a conversa e o segredo de sessão persistem. Teste a porta 8000 ocupada por outro aplicativo e confirme que ele permanece ativo.
5. Em uma segunda VM com banco existente de teste, compare inventários de contas, arquivos e índice antes e depois da atualização. Confira a reutilização do `.env` e das credenciais existentes.

O teste automatizado usa executáveis simulados para instalação de terceiros. Os prompts reais de UAC/licenças e a instalação integral do ZIP em VM são verificações manuais.

Resultados, limitações e matriz de testes na [auditoria do instalador](AUDITORIA_INSTALACAO_WINDOWS.md).

Referências oficiais: [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/install), [PostgreSQL para Windows](https://www.postgresql.org/download/windows/), [checksum EDB](https://get.enterprisedb.com/postgresql/postgresql-18.7-1-windows-x64-binaries.zip.sha256), [modelo Qwen](https://ollama.com/library/qwen3:4b-instruct) e [Tesseract para Windows](https://github.com/UB-Mannheim/tesseract/wiki).
