#!/usr/bin/env bash
# Uruchomienie serwera maszyny w trybie symulacji (Linux/macOS).
# Tworzy lokalne środowisko Pythona przy pierwszym starcie.
set -e
cd "$(dirname "$0")/server"

if [ ! -d .venv ]; then
  echo "Pierwsze uruchomienie — tworzę środowisko i instaluję zależności..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

echo
echo "  Panel operatora:    http://localhost:8000/"
echo "  Konfiguracja osi:   http://localhost:8000/axes"
echo "  Edytor technologa:  http://localhost:8000/editor"
echo "  Dokumentacja API:   http://localhost:8000/docs"
echo
export PROGRAMS_DIR=../programs
export AXES_CONFIG=../config/axes.json
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
