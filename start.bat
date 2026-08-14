@echo off
rem Uruchomienie serwera maszyny w trybie symulacji (Windows).
rem Wymaga Pythona 3.10+ (https://www.python.org/downloads/ - zaznacz "Add to PATH").
cd /d "%~dp0server"

if not exist .venv (
  echo Pierwsze uruchomienie - tworze srodowisko i instaluje zaleznosci...
  python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
)

echo.
echo   Panel operatora:    http://localhost:8000/
echo   Edytor technologa:  http://localhost:8000/editor
echo   Dokumentacja API:   http://localhost:8000/docs
echo.
start "" http://localhost:8000/
set PROGRAMS_DIR=..\programs
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
