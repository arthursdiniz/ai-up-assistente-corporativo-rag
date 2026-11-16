param([switch]$PackagesOnly)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $projectRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"
$supportedPython = "(3, 12) <= sys.version_info[:2] <= (3, 13) and platform.machine().lower() in ('amd64','x86_64')"

function Test-PythonVersion([string]$Executable, [string[]]$Prefix, [switch]$RequireVenv) {
    # Suppress probe failures, including a launcher without this Python version.
    $ErrorActionPreference = "Continue"
    $condition = $supportedPython
    if ($RequireVenv) {
        $condition += " and sys.prefix != sys.base_prefix"
    }
    & $Executable @Prefix -I -c "import sys, platform; raise SystemExit(0 if $condition else 1)" *> $null
    return $LASTEXITCODE -eq 0
}

function Find-BasePython {
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        try {
            $launcherList = & $launcher.Source -0p 2>$null
        } catch {
            $launcherList = @()
        }
        foreach ($option in @("-3.12", "-3.13")) {
            $version = [Regex]::Escape($option.Substring(1))
            if (($launcherList -match "^\s*-(?:V:)?$version(?:-64)?\s") -and (Test-PythonVersion $launcher.Source @($option))) {
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
    foreach ($root in @($env:LOCALAPPDATA, $env:ProgramFiles)) {
        if (-not $root) { continue }
        foreach ($relative in @('Programs\Python\Python312\python.exe', 'Programs\Python\Python313\python.exe', 'Python312\python.exe', 'Python313\python.exe')) {
            $candidate = Join-Path $root $relative
            if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-PythonVersion $candidate @())) {
                return @{ Executable = $candidate; Prefix = @() }
            }
        }
    }
}

function Install-BasePython {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget -and (Read-Host 'Instalar Python 3.12 oficial via WinGet? O Windows pode pedir consentimento e licencas [s/N]') -match '^(s|sim)$') {
        try {
            & $winget.Source install --id Python.Python.3.12 --exact --source winget
            if ($LASTEXITCODE -eq 0) { return }
        } catch {
            Write-Host 'O WinGet nao pode ser executado neste perfil.'
        }
        if (Find-BasePython) { return }
        Write-Host 'O WinGet nao concluiu a instalacao.'
    }
    if ((Read-Host 'Baixar e abrir o instalador x64 verificado de python.org? O instalador pode pedir licenca ou UAC [s/N]') -match '^(s|sim)$') {
        $url = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
        $expected = '67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb'
        $target = Join-Path ([IO.Path]::GetTempPath()) ("aiup-python-" + [Guid]::NewGuid().ToString('N') + '.exe')
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Write-Host 'Baixando Python oficial...'
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target -TimeoutSec 120
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash -ne $expected) {
                throw 'O instalador do Python falhou na verificacao SHA-256 e nao sera executado.'
            }
            $result = Start-Process -FilePath $target -Wait -PassThru
            if ($result.ExitCode -eq 0) { return }
            throw "O instalador do Python retornou codigo $($result.ExitCode). Se solicitado, reinicie o Windows."
        } finally {
            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
        }
    }
    throw 'Instale Python 3.12 x64 em https://www.python.org/downloads/windows/ e execute o atalho novamente.'
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

if ([Environment]::OSVersion.Version.Major -lt 10 -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Este instalador requer Windows 10 ou 11 x64 e PowerShell de 64 bits.'
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "requirements.txt nao encontrado. Mantenha o instalador na pasta do projeto."
}
$hasher = [Security.Cryptography.SHA256]::Create()
try {
    $rootBytes = [Text.Encoding]::UTF8.GetBytes($projectRoot.ToUpperInvariant())
    $projectId = [BitConverter]::ToString($hasher.ComputeHash($rootBytes)).Replace('-', '')
} finally {
    $hasher.Dispose()
}
$mutex = [Threading.Mutex]::new($false, "Local\AI-Up-PythonSetup-$projectId")
$locked = $false
try {
    try {
        $locked = $mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $locked = $true
    }
    if (-not $locked) { throw 'O Python esta sendo preparado em outra janela do AI-Up. Aguarde e tente novamente.' }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-PythonVersion $python @() -RequireVenv)) {
        $basePython = Find-BasePython
        if (-not $basePython) {
            Install-BasePython
            $basePython = Find-BasePython
        }
        if (-not $basePython) { throw 'Python ainda indisponivel. Reinicie o Windows se o instalador solicitar e tente novamente.' }
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($projectRoot))
        if ($drive.AvailableFreeSpace -lt 4GB) { throw 'Libere ao menos 4 GB na unidade do projeto para preparar .venv.' }
        if (Test-Path -LiteralPath $venv) {
            $backupName = '.venv.backup-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
            Rename-Item -LiteralPath $venv -NewName $backupName
            Write-Host "Ambiente anterior preservado como $backupName."
        }
        $executable = $basePython.Executable
        $prefix = $basePython.Prefix
        Write-Host "Criando o ambiente virtual .venv..."
        & $executable @prefix -I -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Falha ao criar o ambiente virtual." }
    }
    if (-not (Test-PythonVersion $python @() -RequireVenv)) {
        throw "O ambiente virtual nao iniciou. Confira bloqueios de acesso ou a instalacao do Python."
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
            $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($projectRoot))
            if ($drive.AvailableFreeSpace -lt 4GB) { throw 'Libere ao menos 4 GB na unidade do projeto para instalar os pacotes.' }
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
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
if (-not $PackagesOnly) {
    & $python (Join-Path $PSScriptRoot 'setup_windows.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Para abrir o AI-Up, use Iniciar.bat."
}
