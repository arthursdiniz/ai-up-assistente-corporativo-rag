$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Import-UserEnvironmentVariable {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "User")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        Set-Item -Path "Env:$Name" -Value $value
    }
}

$requiredEnvironment = @(
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_NAME",
    "SECRET_KEY"
)
foreach ($name in $requiredEnvironment) {
    Import-UserEnvironmentVariable -Name $name
}

if ([string]::IsNullOrWhiteSpace($env:DATABASE_USERNAME) -or
    [string]::IsNullOrWhiteSpace($env:DATABASE_PASSWORD)) {
    throw "As credenciais do PostgreSQL não estão configuradas nas variáveis do usuário do Windows."
}
if ([string]::IsNullOrWhiteSpace($env:SECRET_KEY) -or $env:SECRET_KEY.Length -lt 32) {
    $secretBytes = New-Object byte[] 48
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($secretBytes)
    } finally {
        $random.Dispose()
    }
    $env:SECRET_KEY = [Convert]::ToBase64String($secretBytes)
    Write-Host "Chave de sessão segura gerada para esta execução." -ForegroundColor DarkGray
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Ambiente virtual não encontrado. Execute a instalação descrita no README."
}

$postgres = Get-Service -Name "postgresql-x64-18" -ErrorAction SilentlyContinue
if ($null -eq $postgres -or $postgres.Status -ne "Running") {
    throw "O serviço PostgreSQL 18 não está em execução. Inicie-o antes de abrir o AI-Up."
}

try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
} catch {
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not (Test-Path -LiteralPath $ollama)) {
        throw "O Ollama não foi encontrado. Consulte a seção de instalação no README."
    }
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10
}

if ($tags.models.name -notcontains "qwen3:4b-instruct") {
    throw "O modelo qwen3:4b-instruct não está disponível no Ollama."
}

Write-Host "Preparando o banco de dados..." -ForegroundColor Cyan
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Falha ao aplicar migrations." }

& $python scripts\seed.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar os usuários locais." }

Write-Host "AI-Up pronto em http://localhost:8000" -ForegroundColor Green
Write-Host "Pressione Ctrl+C para encerrar." -ForegroundColor DarkGray
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
