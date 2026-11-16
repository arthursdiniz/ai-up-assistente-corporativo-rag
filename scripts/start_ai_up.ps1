param([switch]$Demo, [switch]$Desktop)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$taskPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if ($Desktop) {
    & (Join-Path $PSScriptRoot 'install_ai_up.ps1') -PackagesOnly
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel preparar as dependencias Python.' }
}
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Ambiente virtual nao encontrado. Consulte o README."
}
$taskArguments = @("scripts/run_local.py")
if ($Desktop) { $taskArguments = @("scripts/setup_windows.py", "--start") }
if ($Demo) { $taskArguments += "--demo" }
& $taskPython -X utf8 -I @taskArguments
if ($LASTEXITCODE -ne 0) { throw "O AI-Up nao iniciou. Confira a mensagem acima." }
