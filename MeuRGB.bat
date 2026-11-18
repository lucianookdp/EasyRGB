@echo off
title MeuRGB
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto sempython

rem Ainda nao configurado pela IA? Mostra o caminho certo antes de seguir.
if exist "%~dp0app\pc.json" goto instalar
echo.
echo  ==========================================================================
echo   MeuRGB is not set up for this PC yet.  /  O MeuRGB ainda nao foi
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
choice /c 12 /n /m "  [1] Show the prompt / Ver o prompt     [2] Open MeuRGB anyway / Abrir mesmo assim: "
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
cd /d "%~dp0app"
echo Opening MeuRGB... keep this window open. / Abrindo o MeuRGB... deixe esta janela aberta.
python rgb_controller.py
echo.
echo MeuRGB closed. If you see an error above, take a screenshot. / O MeuRGB fechou. Se apareceu um erro acima, tire um print.
pause
exit /b

:sempython
echo MeuRGB needs Python 3: https://www.python.org/downloads/  /  O MeuRGB precisa do Python 3.
echo Tip: your AI agent can install it for you. / Dica: o seu agente de IA pode instalar para voce.
pause
