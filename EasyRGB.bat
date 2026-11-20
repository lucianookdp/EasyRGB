@echo off
title EasyRGB
cd /d "%~dp0"

rem Python: "pythonw" (no PATH) ou o lancador "pyw" do python.org
set "PYW=pythonw"
where pythonw >nul 2>&1
if errorlevel 1 (
  where pyw >nul 2>&1
  if errorlevel 1 goto sempython
  set "PYW=pyw"
)

rem Ainda nao configurado pela IA? Mostra o caminho certo antes de seguir.
if exist "%~dp0app\pc.json" goto instalar
echo.
echo  ==========================================================================
echo   EasyRGB is not set up for this PC yet.  /  O EasyRGB ainda nao foi
echo   configurado para este PC.
echo.
echo   Best way / Melhor jeito:
echo    1. Open an AI agent in THIS folder (Claude Code, Codex, Gemini CLI...)
echo       Abra um agente de IA NESTA pasta (Claude Code, Codex, Gemini CLI...)
echo    2. Paste the prompt from START-HERE.txt
echo       Cole o prompt do arquivo START-HERE.txt
echo    3. Answer its questions. It installs and configures everything.
echo       Responda as perguntas. Ele instala e configura tudo.
echo  ==========================================================================
echo.
choice /c 12 /n /m "  [1] Show the prompt / Ver o prompt     [2] Open EasyRGB anyway / Abrir mesmo assim: "
if errorlevel 2 goto instalar
start "" notepad "%~dp0START-HERE.txt"
exit /b

:instalar
rem Primeira vez: baixa o OpenRGB, instala o driver e desliga o ASRock. Pede admin uma vez.
if exist "%~dp0configurado.ok" goto abrir
echo First run: installing... accept the administrator prompt. / Primeira vez: instalando... aceite o pedido de administrador.
set "SETUP=%~dp01-Configurar (admin).ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File \"' + $env:SETUP + '\"')"

:abrir
rem Abre escondido (fica no icone ao lado do relogio) e abre a pagina no navegador.
cd /d "%~dp0app"
start "" %PYW% rgb_controller.py
rem Na primeira vez com um Python novo ele instala as bibliotecas: pode levar ate 1-2 minutos.
powershell -NoProfile -Command "for($i=0;$i -lt 120;$i++){ if(Get-NetTCPConnection -State Listen -LocalPort 6750 -ErrorAction SilentlyContinue){ exit 0 }; Start-Sleep 1 }; exit 1"
if not errorlevel 1 exit /b
echo EasyRGB didn't start. Last log lines: / O EasyRGB nao abriu. Ultimas linhas do log:
powershell -NoProfile -Command "Get-Content '%~dp0app\easyrgb.log' -Tail 15 -ErrorAction SilentlyContinue"
pause
exit /b

:sempython
echo EasyRGB needs Python 3: https://www.python.org/downloads/  /  O EasyRGB precisa do Python 3.
echo Tip: your AI agent can install it for you. / Dica: o seu agente de IA pode instalar para voce.
pause
