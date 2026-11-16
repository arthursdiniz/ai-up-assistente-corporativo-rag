$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$accent = [char]0x00E7
$sandbox = Join-Path ([IO.Path]::GetTempPath()) ('AI-Up instala' + $accent + 'ao ' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path (Join-Path $sandbox 'scripts')
Copy-Item (Join-Path $repo 'scripts\install_ai_up.ps1') (Join-Path $sandbox 'scripts')
Copy-Item (Join-Path $repo 'Iniciar.bat') $sandbox
Copy-Item (Join-Path $repo 'Instalar.bat') $sandbox
Set-Content -LiteralPath (Join-Path $sandbox 'requirements.txt') -Value '# already satisfied in any environment' -Encoding Ascii
$null = New-Item -ItemType Directory -Path (Join-Path $sandbox '.venv')
Set-Content -LiteralPath (Join-Path $sandbox '.venv\recover.txt') -Value 'must survive repair' -Encoding Ascii
# Stub only the project entry point. No external installer or service can be invoked by this fixture.
Set-Content -LiteralPath (Join-Path $sandbox 'scripts\setup_windows.py') -Value 'import sys; print("SETUP_STUB", sys.argv[1:])' -Encoding Ascii
Copy-Item (Join-Path $repo 'scripts\start_ai_up.ps1') (Join-Path $sandbox 'scripts')
Push-Location -LiteralPath $sandbox
try {
    $first = cmd.exe /d /c 'Iniciar.bat < nul'
    if ($LASTEXITCODE -ne 0 -or ($first -join "`n") -notmatch 'SETUP_STUB.*--start') { throw 'Iniciar.bat did not hand off to setup.' }
    if (-not (Get-ChildItem -Directory -Filter '.venv.backup-*' | Where-Object { Test-Path (Join-Path $_.FullName 'recover.txt') })) {
        throw 'The incomplete environment was not preserved.'
    }
    $second = cmd.exe /d /c 'Instalar.bat < nul'
    if ($LASTEXITCODE -ne 0 -or ($second -join "`n") -notmatch 'Nenhum download foi feito\.' -or
        ($second -join "`n") -notmatch 'SETUP_STUB \[\]') { throw 'Instalar.bat did not reuse the prepared environment.' }
    Write-Output 'Windows smoke passed: both BATs, offline repeat, accented path and incomplete venv recovery.'
} finally {
    Pop-Location
    # Only the known temporary tree created by this test may be removed.
    $candidate = (Resolve-Path -LiteralPath $sandbox).Path
    $tempRoot = (Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path.TrimEnd('\') + '\'
    if ($candidate.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and $candidate -eq $sandbox) {
        Remove-Item -LiteralPath $candidate -Recurse -Force
    }
}
