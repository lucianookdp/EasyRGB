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
    Write-Host "`n[1/4] OpenRGB..." -ForegroundColor Cyan
    $exe = Join-Path $base 'OpenRGB\OpenRGB Windows 64-bit\OpenRGB.exe'
    if (Test-Path $exe) { Write-Host "      ja instalado." }
    else {
        $zip = Join-Path $dl 'OpenRGB_1.1.zip'
        Invoke-WebRequest -UseBasicParsing 'https://codeberg.org/OpenRGB/OpenRGB/releases/download/release_1.1/OpenRGB_1.1_Windows_64_8e16de2.zip' -OutFile $zip
        Expand-Archive $zip -DestinationPath (Join-Path $base 'OpenRGB') -Force
        Write-Host "      OK" -ForegroundColor Green
    }

    Write-Host "[2/4] Bibliotecas (openrgb-python, Pillow, bandeja, audio)..." -ForegroundColor Cyan
    if (Test-Path (Join-Path $base 'EasyRGB.exe')) { Write-Host "      ja vem dentro do EasyRGB.exe." } else {
    # usa o Python que existir: "python" ou o lançador "py" do python.org
    $py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { $null }
    if (-not $py) { throw "Python 3 nao encontrado. Instale em https://www.python.org/downloads/ e rode de novo." }
    & $py (Join-Path $base 'app\rgb_controller.py') bibliotecas
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar as bibliotecas (precisa de internet nesta etapa)." }
    Write-Host "      OK" -ForegroundColor Green
    }

    Write-Host "[3/4] Desligando o ASRock Polychrome da inicializacao (reversivel)..." -ForegroundColor Cyan
    Get-Process AsrPolychromeRGB -ErrorAction SilentlyContinue | Stop-Process -Force
    if (Get-ScheduledTask -TaskName AsrPolychromeRGB -ErrorAction SilentlyContinue) {
        Disable-ScheduledTask -TaskName AsrPolychromeRGB | Out-Null
        Write-Host "      OK - desativado (nada foi apagado)." -ForegroundColor Green
    } else { Write-Host "      nao encontrado, seguindo." }

    Write-Host "[4/4] Driver PawnIO..." -ForegroundColor Cyan
    if (Get-Service PawnIO -ErrorAction SilentlyContinue) { Write-Host "      ja instalado." }
    else {
        $setup = Join-Path $dl 'PawnIO_setup.exe'
        if (-not (Test-Path $setup)) {
            $rel = Invoke-RestMethod 'https://api.github.com/repos/namazso/PawnIO.Setup/releases/latest'
            $url = ($rel.assets | Where-Object name -eq 'PawnIO_setup.exe').browser_download_url
            Invoke-WebRequest -UseBasicParsing $url -OutFile $setup
        }
        $sig = Get-AuthenticodeSignature $setup
        if ($sig.Status -ne 'Valid') { throw "Assinatura do PawnIO_setup.exe invalida: $($sig.Status)" }
        $p = Start-Process $setup -ArgumentList '-install', '-silent' -Wait -PassThru
        Write-Host "      OK (codigo $($p.ExitCode))" -ForegroundColor Green
    }

    Set-Content -Path (Join-Path $base 'configurado.ok') -Value (Get-Date) -Encoding utf8
    Write-Host "`nPronto! O EasyRGB vai abrir agora." -ForegroundColor Green
    Start-Sleep 2
}
catch {
    Write-Host "`nERRO: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Enter para fechar"
}
