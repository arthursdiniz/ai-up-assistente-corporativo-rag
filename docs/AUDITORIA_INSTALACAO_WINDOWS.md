# Auditoria da instalação do AI-Up no Windows

## Dependências e pontos de entrada

- Os três atalhos de entrada chegam ao PowerShell 5.1. A instalação exige Windows 10 ou 11 x64, armazenamento local gravável e espaço nas unidades do checkout, do perfil e do cache de modelos. O modo completo usa modelos locais e requer memória suficiente para carregar o Qwen e os embeddings.
- O bootstrap reutiliza Python 3.12/3.13 x64 por launcher, PATH, registro ou diretórios padrão. Usa `venv`, `ensurepip`, o resolvedor do pip e PyPI para os pacotes faltantes. Uma instalação nova também pode precisar do Visual C++ Redistributable para executáveis e extensões nativas.
- `requirements.txt` lista as dependências diretas, incluindo FastAPI/Uvicorn, Pydantic, SQLAlchemy/Alembic/psycopg, Argon2/JWT, HTTPX, PyMuPDF, Pillow, python-docx, openpyxl, ChromaDB, Sentence Transformers e pytest. Entre as transitivas estão Starlette/AnyIO, pydantic-core, psycopg-binary/libpq, lxml, PyTorch, NumPy/SciPy, Transformers, tokenizers, safetensors e huggingface-hub. Para inventariar a resolução completa de uma instalação, use `python -m pip inspect --local` no ambiente virtual. As faixas permitem versões transitivas diferentes entre instalações.
- O PostgreSQL privado usa os binários existentes ou o ZIP x64 verificado da EDB, um cluster local SCRAM e migrations em ordem. A aplicação usa SQLAlchemy e psycopg para persistência, SQLite interno ao ChromaDB para o catálogo vetorial e arquivos locais para uploads e vetores. Ollama serve a API local e baixa o Qwen. Hugging Face fornece os artefatos de Sentence Transformers. Tesseract carrega o idioma português do pacote nativo ou do arquivo oficial verificado. O navegador carrega os arquivos estáticos diretamente do FastAPI.
- WinGet é opcional. O fluxo normal também funciona sem Git, Node.js, IDE ou Docker. Os instaladores externos podem exigir acesso à internet, aceitação de termos ou UAC.

## Achados e correções

| Gravidade | Causa e reprodução | Correção |
| --- | --- | --- |
| Alta | O diagnóstico de OCR passava caminhos diretamente, enquanto a aplicação inseria aspas numa string posteriormente reinterpretada por outra biblioteca. Reproduzido com o pacote `por` em pasta acentuada e com espaços. O erro do executável ainda podia ser mascarado pela decodificação de stderr. | O teste e a aplicação usam o mesmo caminho de execução. O PNG vai pela entrada padrão do Tesseract e a pasta de idioma é um argumento literal. Falhas do processo ganham mensagens em português. |
| Alta | Com o cluster parado e outro processo na porta memorizada, o PostgreSQL privado falhava na retomada. Estado incompleto ou credenciais ilegíveis também produziam erro genérico. | O bootstrap valida a estrutura do registro, diferencia cluster parado de inacessível e realoca a porta apenas quando controla a conexão. O cluster e a senha são preservados. Uma conexão explícita permanece sob controle do operador. |
| Alta | O comando de ACL anterior preservava concessões explícitas já presentes. Uma junção em pasta intermediária ou um link em arquivo privado podia redirecionar a leitura/gravação. | A pasta e os arquivos privados preexistentes recebem ACL com a conta atual e SYSTEM. O bootstrap rejeita links/junções nos caminhos controlados. Gravações são publicadas atomicamente e uma exclusão mútua protege a preparação. |
| Alta | Dois checkouts usando o mesmo PostgreSQL podiam tentar atualizar o esquema em paralelo. Erros de conexão ou migration precisavam de diagnóstico mais específico. | Alembic usa lock consultivo de sessão por banco PostgreSQL. A conexão de diagnóstico tem timeout e os erros são comunicados sem registrar DSNs. |
| Alta | O diagnóstico descartável do ChromaDB podia passar quando o índice de uso real estava bloqueado ou ilegível. Um pacote `por.traineddata` corrompido também podia continuar aparecendo na lista de idiomas. | O instalador testa as pastas reais e abre o catálogo existente em modo somente leitura. O reparo inclui `quick_check`. Para dados de OCR gerenciados pelo instalador, o hash é conferido e o arquivo pode ser baixado novamente com consentimento. |
| Média | Um arquivo parcial, uma resposta HTML de proxy, um certificado inválido ou um artefato indisponível podiam confluir para diagnósticos pouco específicos. O ZIP admitia nomes problemáticos em NTFS. | Downloads validam HTTPS, tamanho e SHA-256 antes da publicação. Erros de HTTP, certificado e truncamento têm ações distintas. A extração rejeita colisões de caixa, nomes reservados, travessia e links. O ZIP verificado pode ser reaproveitado se a extração for interrompida. |
| Média | Uma resposta HTTP 200 de serviço incompatível podia parecer uma lista válida do Ollama. A porta local personalizada não era usada pelo início e pelo download. Mudanças nos arquivos do modelo ou no digest podiam reaproveitar um diagnóstico desatualizado. | A detecção exige o formato da API, usa o endereço local configurado no CLI e revalida a geração após mudança do digest. O diagnóstico também observa a identidade e a data dos arquivos do cache de embeddings. |
| Média | Um segundo checkout podia abrir uma instância já existente de outro checkout na porta 8000. | O iniciador verifica identidade da instalação e saúde do banco antes de abrir o navegador. |
| Média | Python compatível instalado em pasta personalizada sem PATH dependia do launcher. A resolução offline do pip não verificava todos os conflitos entre pacotes já instalados. | Foi acrescentada descoberta pelo registro, verificação com `pip check` e isolamento de variáveis globais do Python no atalho. |

## Validação e evidências

Execute na raiz do checkout:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\windows_installer_smoke.ps1
node --test tests/scroll_navigation.test.cjs
.\.venv\Scripts\python.exe -I -m pip check
```

- Os testes automatizados cobrem recuperação da `.venv`, downloads recusados e truncados, erro de certificado, hash errado, 404, caminhos perigosos no ZIP, estado do banco ilegível, porta ocupada, retenção das credenciais de bootstrap, configuração preservada, ACL no Windows, falhas de OCR, permissões de diretório e ChromaDB corrompido. Verificam também que o diagnóstico exige geração do Ollama e repete o teste após troca de digest.
- No Windows 11 com Python 3.12, passaram 153 testes Python e cinco testes JavaScript. O Starlette emitiu um aviso de depreciação e o `pip check` reportou zero conflitos. O smoke dos três atalhos também passou no PowerShell 5.1 com PATH restrito, pasta acentuada, `.venv` incompleta e segunda execução offline.
- No Windows 11 de desenvolvimento, o pacote oficial PostgreSQL 18.7 foi baixado, verificado por SHA-256, extraído em pasta descartável e iniciado como cluster privado. A segunda conexão reutilizou mesmo banco e credenciais. Outro teste ocupou a porta anterior e confirmou a retomada do mesmo cluster, com a mesma senha, em outra porta.
- Em ambiente isolado, foram testados migrations, API FastAPI, criação do primeiro administrador, login, OCR de um PNG enviado, embeddings locais, ChromaDB, resposta real do Ollama com citação, disponibilidade da conversa ao reabrir a aplicação de teste e `pg_dump`. Também foram exercitados JPEG, PNG, PDF digital e digitalizado, DOCX e XLSX com nomes acentuados.
- O lock do Alembic foi exercitado com duas conexões PostgreSQL reais. Depois de liberar o lock, aplicamos e repetimos as migrations. O Uvicorn também respondeu pela rede em porta local isolada e acionou o ponto de abertura do navegador após receber o health check. A chamada ao navegador foi simulada nesse teste.
- Os hashes foram reconferidos nos bytes de Python, Visual C++, Tesseract e dados de OCR em português, no ZIP da EDB e no digest publicado pelo release do Ollama. A disponibilidade dos endereços e os IDs de WinGet também foram verificados. O download oficial de programas de terceiros permanece condicionado a consentimento.
- A matriz Windows foi definida para Python 3.12 e 3.13. A execução da matriz nas novas alterações depende da publicação autorizada. [Manifestos do WinGet](https://github.com/microsoft/winget-pkgs) · [PostgreSQL para Windows](https://www.postgresql.org/download/windows/) · [hash publicado pela EDB](https://get.enterprisedb.com/postgresql/postgresql-18.7-1-windows-x64-binaries.zip.sha256) · [release do Ollama](https://github.com/ollama/ollama/releases/tag/v0.40.16)

## Aceite pendente em VM

Use snapshots distintos de Windows 10 e Windows 11. Comece com uma conta padrão e sem dependências. Repita com e sem WinGet, Python incompatível, Python 3.12/3.13 instalado sem PATH e aliases da Store habilitados. Teste o ZIP sujeito a SmartScreen, os diálogos de licenças e UAC, os fallbacks de Python/VC++/Ollama/Tesseract, cancelamento de download, reinício solicitado pelo fornecedor e retomada. Use o [roteiro de aceite](INSTALACAO_WINDOWS.md#aceite-em-vm-windows-limpa) para conferir OCR, primeira conta, RAG e persistência.

Repita também com perfil acentuado, pasta OneDrive disponível offline, unidade externa NTFS, rede corporativa com proxy/certificados próprios, volume quase cheio, falhas simuladas por antivírus e pouco hardware para o Ollama. A política corporativa pode exigir que o administrador libere o executável ou instale o software. O aplicativo não altera a política de segurança do Windows.

Para banco existente, use uma cópia e compare contas, organizações, conversas, documentos, permissões e índice antes e depois. Com índice vetorial já populado, trocar o modelo exige backup e reindexação. A verificação do catálogo SQLite cobre o catálogo e a validação dos segmentos HNSW exige consultas representativas. Se o registro de credenciais estiver perdido, é necessária uma cópia da configuração e dos dados do cluster.

Os testes comprovam os componentes exercitados no Windows 11 e a retomada em ambiente isolado. O aceite completo do caminho ZIP → instalação → navegador em Windows limpo ainda depende dessa matriz manual.
