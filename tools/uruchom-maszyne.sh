#!/usr/bin/env bash
# Uruchomienie całego środowiska maszyny jednym poleceniem (albo jednym
# kliknięciem w skrót z pulpitu — patrz tools/zainstaluj-skrot.sh).
#
#   1. przygotowuje środowisko Pythona przy pierwszym starcie,
#   2. uruchamia mostek SC4-Hub, jeśli jest zbudowany i widzi sprzęt,
#   3. uruchamia serwer maszyny,
#   4. otwiera panel operatora w przeglądarce.
#
# Tryb można wymusić:  ./uruchom-maszyne.sh sim     (symulator, bez sprzętu)
#                      ./uruchom-maszyne.sh maszyna (wymaga mostka i serw)
#
# Zamknięcie okna albo Ctrl+C zatrzymuje serwer i mostek.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# porty można podmienić na czas testów: SERVER_PORT=8123 ./uruchom-maszyne.sh
SERVER_PORT="${SERVER_PORT:-8000}"
BRIDGE_PORT="${BRIDGE_PORT:-8500}"
TRYB="${1:-auto}"

BRIDGE_PID=""
SERVER_PID=""

info()  { printf '\n\033[1;34m%s\033[0m\n' "$*"; }
warn()  { printf '\n\033[1;33mUWAGA: %s\033[0m\n' "$*"; }
err()   { printf '\n\033[1;31mBŁĄD: %s\033[0m\n' "$*"; }

# Zatrzymanie wszystkiego, cokolwiek by się nie działo — inaczej po zamknięciu
# okna mostek zostaje z otwartym portem szeregowym i kolejny start się nie uda.
sprzatanie() {
  trap - EXIT INT TERM
  info "zatrzymuję..."
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
  wait 2>/dev/null
}
trap sprzatanie EXIT INT TERM

port_otwarty() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3<&- && return 0
  return 1
}

czekaj_na_port() {  # port, sekundy, opis
  local i=0
  while [ "$i" -lt "$(( $2 * 10 ))" ]; do
    port_otwarty "$1" && return 0
    sleep 0.1
    i=$(( i + 1 ))
  done
  return 1
}

cd "$ROOT" || exit 1

# --- 1. środowisko Pythona -------------------------------------------------

if [ ! -d server/.venv ]; then
  info "Pierwsze uruchomienie — tworzę środowisko i instaluję zależności..."
  python3 -m venv server/.venv || { err "nie udało się utworzyć środowiska Pythona"; read -r; exit 1; }
  server/.venv/bin/pip install -q -r server/requirements.txt || {
    err "nie udało się zainstalować zależności"; read -r; exit 1; }
fi

# --- 2. mostek SC4-Hub -----------------------------------------------------

if port_otwarty "$BRIDGE_PORT"; then
  info "Mostek SC4-Hub już działa na porcie $BRIDGE_PORT — używam go."
  MODE="sc4hub"
elif [ "$TRYB" != "sim" ] && [ -x bridge/sc4hub_bridge ]; then
  info "Uruchamiam mostek SC4-Hub..."
  (
    cd bridge || exit 1
    set -a
    # shellcheck disable=SC1091
    [ -f machine.env ] && . ./machine.env
    set +a
    exec ./sc4hub_bridge
  ) &
  BRIDGE_PID=$!
  if czekaj_na_port "$BRIDGE_PORT" 10; then
    MODE="sc4hub"
  else
    kill "$BRIDGE_PID" 2>/dev/null
    wait "$BRIDGE_PID" 2>/dev/null
    BRIDGE_PID=""
    if [ "$TRYB" = "maszyna" ]; then
      err "mostek nie wystartował — sprawdź USB, zasilanie 24 V i tools/sc4hub-rebind.sh"
      read -r -p "Enter zamyka okno..."
      exit 1
    fi
    warn "mostek nie wystartował (brak sprzętu?) — przechodzę w tryb SYMULACJI"
    MODE="sim"
  fi
else
  [ "$TRYB" = "maszyna" ] && { err "brak zbudowanego mostka: bridge/sc4hub_bridge (make -C bridge)"; read -r; exit 1; }
  MODE="sim"
fi

# --- 3. serwer maszyny -----------------------------------------------------

if port_otwarty "$SERVER_PORT"; then
  err "port $SERVER_PORT jest zajęty — serwer maszyny już działa?"
  read -r -p "Enter zamyka okno..."
  exit 1
fi

if [ "$MODE" = "sim" ]; then
  info "TRYB SYMULACJI — maszyna się nie rusza, panel działa w całości."
else
  info "TRYB MASZYNY — ruchy wykonują serwa ClearPath przez SC4-Hub."
fi

(
  cd server || exit 1
  export PROGRAMS_DIR=../programs
  export AXES_CONFIG=../config/axes.json
  export MACHINE_MODE="$MODE"
  export BRIDGE_HOST=127.0.0.1
  export BRIDGE_PORT="$BRIDGE_PORT"
  exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "$SERVER_PORT"
) &
SERVER_PID=$!

if ! czekaj_na_port "$SERVER_PORT" 30; then
  err "serwer nie wystartował — komunikaty powyżej"
  read -r -p "Enter zamyka okno..."
  exit 1
fi

# --- 4. panel w przeglądarce ----------------------------------------------

cat <<EOF

  Panel operatora:    http://localhost:$SERVER_PORT/
  Konfiguracja osi:   http://localhost:$SERVER_PORT/axes
  Edytor technologa:  http://localhost:$SERVER_PORT/editor

  Zamknięcie tego okna (albo Ctrl+C) zatrzymuje maszynę i serwer.

EOF

command -v xdg-open >/dev/null && xdg-open "http://localhost:$SERVER_PORT/" >/dev/null 2>&1 &

wait "$SERVER_PID"
