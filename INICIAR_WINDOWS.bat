@echo off
cd /d "%~dp0"
where ffmpeg >nul 2>nul || (echo FFmpeg nao encontrado. Instale com: winget install Gyan.FFmpeg  e abra este arquivo de novo. & pause & exit /b)
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
start "" http://localhost:3000
python -m uvicorn main:app --port 3000
pause
