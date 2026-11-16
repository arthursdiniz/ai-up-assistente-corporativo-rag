# Acesso temporário para testes

As credenciais abaixo são públicas e destinadas ao uso local com dados de demonstração.

## AI-Up padrão

Em um computador novo, dê dois cliques em **Iniciar_Demo.bat** para criar as contas de teste e abrir o AI-Up. Se a janela do AI-Up já estiver aberta, encerre com `Ctrl+C` antes de usar esse atalho. Se a cópia do projeto for anterior ao atalho, execute na pasta do projeto pelo PowerShell:

```powershell
.\scripts\start_ai_up.ps1 -Desktop -Demo
```

Abra [localhost:8000](http://localhost:8000/). A senha inicial padrão é `AiUp@2026` para os três perfis:

| Perfil | E-mail |
| --- | --- |
| Usuário | `usuario@aiup.local` |
| Gerente | `gerente@aiup.local` |
| Administrador | `admin@aiup.local` |

O atalho cria as contas de demonstração que estiverem faltando. Contas existentes mantêm suas senhas. Se `SEED_PASSWORD` estiver definida, as novas contas recebem o valor dessa variável. Para usar uma conta própria em um banco novo, abra `Iniciar.bat` e escolha **Configurar primeiro administrador**.

Se o chat responder com `[MOCK]`, feche o AI-Up, defina `LLM_PROVIDER=ollama` no arquivo `.env` e abra `Iniciar.bat` novamente. O inicializador verifica se o Ollama e o modelo configurado estão disponíveis.

## AI-Up Auditor

Após preparar o AI-Up com o Ollama e o modelo `qwen3:4b-instruct`, mantenha o Ollama aberto e execute na pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -B scripts\demo_auditor.py --sample --ollama
```

Abra o [Auditor de demonstração](http://127.0.0.1:8013/auditor.html). Use `auditor@demo.aiup.local` com a senha `Demo-Auditor-2026!`. A conta `externo@demo.aiup.local` usa a mesma senha e permite testar a visão de outra organização.

O Auditor de demonstração abre uma instância local separada, com documentos fictícios já carregados.

A opção `--ollama` habilita respostas reais no chat. Para testar apenas a análise documental sem baixar um modelo de geração, execute sem essa opção. Nesse modo, o chat lista os trechos encontrados e identifica a resposta com `[MOCK]`.
