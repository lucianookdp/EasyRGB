@echo off
title MeuRGB
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto sempython

rem Primeira vez: baixa o OpenRGB, instala o driver e desliga o ASRock. Pede admin uma vez.
if exist "%~dp0configurado.ok" goto abrir
echo Primeira vez: configurando... aceite o pedido de administrador.
set "SETUP=%~dp01-Configurar (admin).ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -Wait -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File \"' + $env:SETUP + '\"')"

:abrir
cd /d "%~dp0app"
echo Abrindo o MeuRGB... deixe esta janela aberta enquanto usa.
python rgb_controller.py
echo.
echo O MeuRGB fechou. Se apareceu algum erro acima, tire um print desta janela.
pause
exit /b

:sempython
echo O MeuRGB precisa do Python 3. Instale em https://www.python.org/downloads/ e abra de novo.
pause
