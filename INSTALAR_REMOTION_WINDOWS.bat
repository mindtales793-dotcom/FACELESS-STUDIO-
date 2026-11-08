@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js nao encontrado.
  echo Instale Node.js 20 LTS ou superior e execute este instalador novamente.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm nao encontrado. Reinstale o Node.js incluindo o npm.
  pause
  exit /b 1
)

echo.
echo Instalando dependencias do Remotion...
cd /d "%~dp0remotion"
call npm install
if errorlevel 1 (
  echo Falha ao instalar as dependencias do Remotion.
  pause
  exit /b 1
)

echo.
echo Preparando o navegador Chromium do Remotion...
call npx remotion browser ensure
if errorlevel 1 (
  echo Nao foi possivel preparar o Chromium automaticamente.
  echo Tente novamente em uma janela de terminal com internet.
  pause
  exit /b 1
)

echo.
echo Remotion instalado. Volte para a pasta principal e inicie o Faceless Studio.
pause
