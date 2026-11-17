# Instala a skill "cortes-live-igreen" nesta máquina (Windows, Claude Code / app Claude desktop).
# Uso (PowerShell, dentro da pasta descompactada):   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
# O que faz:
#   1. copia esta pasta para %USERPROFILE%\.claude\skills\cortes-live-igreen  (skill pessoal: vale em qualquer projeto)
#   2. instala as versões EXATAS dos pacotes Python (requirements.txt) no Python 3.12
#   3. confere FFmpeg e roda scripts\checar_ambiente.py
param([switch]$SemPip)

$ErrorActionPreference = "Stop"
$origem = Split-Path -Parent $MyInvocation.MyCommand.Path
$destino = Join-Path $env:USERPROFILE ".claude\skills\cortes-live-igreen"

Write-Host "== 1/3 Copiando a skill para $destino"
if (Test-Path $destino) {
    $bk = "$destino.bak_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    Move-Item $destino $bk
    Write-Host "   versão anterior guardada em $bk"
}
New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
Copy-Item $origem $destino -Recurse
Get-ChildItem $destino -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "== 2/3 Python 3.12 e pacotes"
$pyExe = $null; $pyArgs = @()
try { $v = & py -3.12 --version 2>$null; if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-3.12") } } catch {}
if (-not $pyExe) {
    try { $v = & python --version 2>$null; if ($v -match "3\.12") { $pyExe = "python" } } catch {}
}
if (-not $pyExe) {
    Write-Host "   Python 3.12 não encontrado. Instale com:  winget install Python.Python.3.12   e rode este script de novo." -ForegroundColor Yellow
    exit 1
}
if (-not $SemPip) {
    & $pyExe @pyArgs -m pip install -r (Join-Path $destino "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Host "   pip falhou — veja a mensagem acima." -ForegroundColor Yellow; exit 1 }
}

Write-Host "== 3/3 FFmpeg e checagem final"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "   FFmpeg não está no PATH. Instale com:  winget install Gyan.FFmpeg   (feche e reabra o terminal)." -ForegroundColor Yellow
}
& $pyExe @pyArgs (Join-Path $destino "scripts\checar_ambiente.py")
Write-Host ""
Write-Host "Pronto. Abra o Claude (Code) e peça, por exemplo: 'faça os cortes da live X no padrão iGreen'." -ForegroundColor Green
Write-Host "Teste de reprodução idêntica: veja INSTALAR.md, seção 'Conferir que ficou idêntico'."
