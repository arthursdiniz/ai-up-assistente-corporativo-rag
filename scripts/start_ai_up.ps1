param([switch]$Demo)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$taskPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw "Ambiente virtual nao encontrado. Consulte o README."
}
$taskArguments = @("scripts/run_local.py")
if ($Demo) { $taskArguments += "--demo" }
& $taskPython @taskArguments
if ($LASTEXITCODE -ne 0) { throw "O AI-Up nao iniciou. Confira a mensagem acima." }
