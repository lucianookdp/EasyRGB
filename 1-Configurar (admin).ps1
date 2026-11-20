# EasyRGB - configuração inicial (roda uma vez, como administrador; o EasyRGB.bat chama sozinho)
# 1) Baixa o OpenRGB 1.1 oficial (codeberg.org/OpenRGB) para a pasta OpenRGB\, se ainda não existir
# 2) Instala as bibliotecas dentro de app\lib\pyXY (uma pasta por versão do Python)
# 3) Fecha e desativa (NÃO apaga) a inicialização do ASRock Polychrome, para não brigar com o OpenRGB
# 4) Instala o driver PawnIO (assinado; usado pelo OpenRGB para falar com o chip RGB da placa e das RAMs)
# Para desfazer: "Voltar para ASRock (admin).ps1"

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    # -Wait: quem chamou (o EasyRGB.bat ou um agente de IA) espera a instalação terminar
    Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$base = Split-Path -Parent $PSCommandPath
$dl = Join-Path $base 'download'
New-Item -ItemType Directory -Force $dl | Out-Null

try {
    Write-Host "`nEasyRGB setup`n" -ForegroundColor White
    Write-Host "[1/4] OpenRGB..." -ForegroundColor Cyan
    $exe = Join-Path $base 'OpenRGB\OpenRGB Windows 64-bit\OpenRGB.exe'
    if (Test-Path $exe) { Write-Host "      already here." }
    else {
        $zip = Join-Path $dl 'OpenRGB_1.1.zip'
        Invoke-WebRequest -UseBasicParsing 'https://codeberg.org/OpenRGB/OpenRGB/releases/download/release_1.1/OpenRGB_1.1_Windows_64_8e16de2.zip' -OutFile $zip
        Expand-Archive $zip -DestinationPath (Join-Path $base 'OpenRGB') -Force
        Write-Host "      OK" -ForegroundColor Green
    }

    Write-Host "[2/4] Libraries..." -ForegroundColor Cyan
    if (Test-Path (Join-Path $base 'EasyRGB.exe')) { Write-Host "      included in EasyRGB.exe." } else {
    # usa o Python que existir: "python" ou o lançador "py" do python.org
    $py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { $null }
    if (-not $py) { throw "Python 3 not found. Install it from https://www.python.org/downloads/ and run this again." }
    & $py (Join-Path $base 'app\rgb_controller.py') bibliotecas
    if ($LASTEXITCODE -ne 0) { throw "Could not install the libraries (this step needs internet)." }
    Write-Host "      OK" -ForegroundColor Green
    }

    Write-Host "[3/4] Turning off ASRock Polychrome at startup (reversible)..." -ForegroundColor Cyan
    Get-Process AsrPolychromeRGB -ErrorAction SilentlyContinue | Stop-Process -Force
    if (Get-ScheduledTask -TaskName AsrPolychromeRGB -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName AsrPolychromeRGB | Out-Null
        Write-Host "      OK - disabled (nothing deleted)." -ForegroundColor Green
    } else { Write-Host "      not installed, skipping." }

    Write-Host "[4/4] PawnIO driver..." -ForegroundColor Cyan
    if (Get-Service PawnIO -ErrorAction SilentlyContinue) { Write-Host "      already installed." }
    else {
        $setup = Join-Path $dl 'PawnIO_setup.exe'
        if (-not (Test-Path $setup)) {
            $rel = Invoke-RestMethod 'https://api.github.com/repos/namazso/PawnIO.Setup/releases/latest'
            $url = ($rel.assets | Where-Object name -eq 'PawnIO_setup.exe').browser_download_url
            Invoke-WebRequest -UseBasicParsing $url -OutFile $setup
        }
        $sig = Get-AuthenticodeSignature $setup
        if ($sig.Status -ne 'Valid') { throw "PawnIO_setup.exe signature is not valid: $($sig.Status)" }
        $p = Start-Process $setup -ArgumentList '-install', '-silent' -Wait -PassThru
        Write-Host "      OK (code $($p.ExitCode))" -ForegroundColor Green
    }

    Set-Content -Path (Join-Path $base 'configurado.ok') -Value (Get-Date) -Encoding utf8
    Write-Host "`nDone! EasyRGB is ready." -ForegroundColor Green
    Start-Sleep 2
}
catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to close"
}
