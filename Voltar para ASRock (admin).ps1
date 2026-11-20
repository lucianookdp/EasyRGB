# Desfaz o EasyRGB: reativa o ASRock Polychrome na inicialização e fecha o OpenRGB.
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
Get-Process OpenRGB -ErrorAction SilentlyContinue | Stop-Process -Force
Enable-ScheduledTask -TaskName AsrPolychromeRGB | Out-Null
Start-Process 'C:\Program Files (x86)\ASRock Utility\ASRRGBLED\Bin\AsrPolychromeRGB.exe'
Write-Host "ASRock Polychrome turned back on." -ForegroundColor Green
Write-Host "(The PawnIO driver can stay installed; to remove it: Settings > Apps > PawnIO)"
Read-Host "Press Enter to close"
