# Desfaz o EasyRGB: reativa o ASRock Polychrome na inicialização e fecha o OpenRGB.
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
Get-Process OpenRGB -ErrorAction SilentlyContinue | Stop-Process -Force
Enable-ScheduledTask -TaskName AsrPolychromeRGB | Out-Null
Start-Process 'C:\Program Files (x86)\ASRock Utility\ASRRGBLED\Bin\AsrPolychromeRGB.exe'
Write-Host "ASRock Polychrome reativado." -ForegroundColor Green
Write-Host "(O driver PawnIO pode ficar instalado sem problema; para remover: Configuracoes > Apps > PawnIO)"
Read-Host "Enter para fechar"
