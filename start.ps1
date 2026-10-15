# Velg tunnel, dataimport (load) eller app. Uten argument startes appen.
param([ValidateSet('app', 'tunnel', 'load')][string]$Mode = 'app')

$ErrorActionPreference = 'Stop'
if ($Mode -eq 'tunnel') {
    # ponytail: OpenSSH handles login; keep this terminal open.
    ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:3307:127.0.0.1:3306 krcc@192.168.184.129
    exit $LASTEXITCODE
}

$projectPython = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Python environment missing. Follow the Python setup in README.md.'
}
$env:DB_USER = 'krcc'
$env:DB_PORT = '3307'
# Bruk prosjektmappen som arbeidsmappe; finally går tilbake selv om kjøringen feiler.
Push-Location $PSScriptRoot
try {
    # -B hindrer at Python oppretter nye __pycache__-mapper blant leveringsfilene.
    if ($Mode -eq 'load') { & $projectPython -B src/main.py load }
    else { & $projectPython -B -m streamlit run app.py --server.address 127.0.0.1 }
    $runExitCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $runExitCode
