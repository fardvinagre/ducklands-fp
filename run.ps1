param([Parameter(ValueFromRemainingArguments=$true)][string[]]$GameArgs)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente virtual.' }
}
& $pythonPath -c "import importlib.util,sys; sys.exit(not all(importlib.util.find_spec(name) for name in ('panda3d','numpy')))"
if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias. Consulte o README.' }
}
Push-Location $projectRoot
try {
    & $pythonPath -m game.main @GameArgs
    $gameExitCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $gameExitCode
