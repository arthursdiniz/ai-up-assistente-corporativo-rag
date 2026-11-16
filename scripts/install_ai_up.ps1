$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $projectRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"
$checkVersion = "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"

function Test-PythonVersion([string]$Executable, [string[]]$Prefix, [switch]$RequireVenv) {
    # Suppress probe failures, including a launcher without this Python version.
    $ErrorActionPreference = "Continue"
    $check = $checkVersion
    if ($RequireVenv) {
        $check = "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) and sys.prefix != sys.base_prefix else 1)"
    }
    & $Executable @Prefix -I -c $check *> $null
    return $LASTEXITCODE -eq 0
}

function Find-BasePython {
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        foreach ($option in @("-3.12", "-3")) {
            if (Test-PythonVersion $launcher.Source @($option)) {
                return @{ Executable = $launcher.Source; Prefix = @($option) }
            }
        }
    }
    foreach ($name in @("python.exe", "python3.exe")) {
        foreach ($candidate in (Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            # Windows Store aliases can open the Store instead of executing Python.
            if ($candidate.Source -notlike "*\Microsoft\WindowsApps\*" -and (Test-PythonVersion $candidate.Source @())) {
                return @{ Executable = $candidate.Source; Prefix = @() }
            }
        }
    }
    throw "Python 3.12 ou superior nao encontrado. Instale o Python e execute Instalar.bat novamente."
}

function Test-Requirements {
    $ErrorActionPreference = "Continue"
    & $python -I -m pip --isolated --disable-pip-version-check install --dry-run --no-index -q -r $requirements *> $null
    return $LASTEXITCODE -eq 0
}

function Test-Pip {
    $ErrorActionPreference = "Continue"
    & $python -I -m pip --version *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "requirements.txt nao encontrado. Mantenha o instalador na pasta do projeto."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    if (Test-Path -LiteralPath $venv) {
        throw "A pasta .venv existe, mas esta incompleta. Renomeie a pasta .venv e tente novamente."
    }
    $basePython = Find-BasePython
    $executable = $basePython.Executable
    $prefix = $basePython.Prefix
    Write-Host "Criando o ambiente virtual .venv..."
    & $executable @prefix -I -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente virtual." }
}
if (-not (Test-PythonVersion $python @() -RequireVenv)) {
    throw "A pasta .venv deve conter um ambiente virtual funcional com Python 3.12 ou superior. Renomeie a pasta e tente novamente."
}

# Use the project's requirements and Python environment rather than pip settings for other projects.
$previousPipConfig = $env:PIP_CONFIG_FILE
$env:PIP_CONFIG_FILE = "nul"
try {
    if (-not (Test-Pip)) {
        & $python -I -m ensurepip
        if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar o pip no ambiente virtual." }
    }
    Write-Host "Verificando as dependencias instaladas..."
    if (Test-Requirements) {
        Write-Host "Todas as dependencias do projeto ja estao instaladas. Nenhum download foi feito."
    } else {
        Write-Host "Instalando dependencias faltantes ou incompativeis..."
        & $python -I -m pip --isolated --disable-pip-version-check install -r $requirements
        if ($LASTEXITCODE -ne 0 -or -not (Test-Requirements)) {
            throw "Nao foi possivel preparar todas as dependencias. Confira as mensagens do pip."
        }
        Write-Host "Dependencias instaladas com sucesso."
    }
} finally {
    $env:PIP_CONFIG_FILE = $previousPipConfig
}
Write-Host "Para abrir o AI-Up, use Iniciar.bat."
