"""Konfiguracja serwera maszyny — wszystko przez zmienne środowiskowe."""

from __future__ import annotations

import os
from pathlib import Path

# katalog z plikami programów (docelowo zasób sieciowy współdzielony z MES)
PROGRAMS_DIR = Path(os.environ.get("PROGRAMS_DIR", "programs")).resolve()

# Tryb warstwy maszyny: "sim" (symulator) albo "sc4hub" (sprzęt przez mostek
# `bridge/`). "clearcore" zostaje przyjmowane jako nazwa historyczna — hosty
# produkcyjne mają ją w `bridge/machine.env` i w usłudze systemd, a cicha
# zamiana sprzętu na symulator po aktualizacji byłaby groźna.
MACHINE_MODE_ALIASES = {"clearcore": "sc4hub"}
_mode = os.environ.get("MACHINE_MODE", "sim").strip().lower()
MACHINE_MODE = MACHINE_MODE_ALIASES.get(_mode, _mode)

# Adres mostka SC4-Hub (tryb "sc4hub"). Mostek działa na tym samym komputerze
# co serwer i słucha na 8500 — stąd 127.0.0.1. Poprzedni domyślny adres
# 192.168.0.50 pochodził z odrzuconej koncepcji ClearCore (sterownik po
# Ethernecie) i nie odpowiadał żadnemu istniejącemu urządzeniu.
# CLEARCORE_HOST/CLEARCORE_PORT dalej działają jako nazwy historyczne.
BRIDGE_HOST = os.environ.get("BRIDGE_HOST") or os.environ.get(
    "CLEARCORE_HOST", "127.0.0.1"
)
BRIDGE_PORT = int(
    os.environ.get("BRIDGE_PORT") or os.environ.get("CLEARCORE_PORT", "8500")
)

# plik konfiguracji osi (długości, limity, przełożenia, punkty bazowania).
# Zapisywany z ekranu „Konfiguracja osi"; po jego utworzeniu to on, a nie
# zmienne WORK_*, decyduje o obszarze roboczym.
AXES_FILE = Path(os.environ.get("AXES_CONFIG", "config/axes.json")).resolve()

# plik profili parametrów ruchu (prędkości, rampy, limit momentu) — zestawy
# nazwane, przełączane zależnie od kontekstu: cykl maszyny vs program technologa
PROFILES_FILE = Path(
    os.environ.get("PROFILES_CONFIG", "config/profiles.json")
).resolve()

# plik definicji cyklu maszyny (kroki poziomu admina wokół programu detalu)
CYCLE_FILE = Path(os.environ.get("CYCLE_CONFIG", "config/cycle.json")).resolve()

# Plik kont użytkowników (login, rola, skrót hasła). Zakładany narzędziem
# tools/konta.py. **Dopóki plik nie istnieje, logowanie jest wyłączone**
# i wszystkie ekrany są dostępne bez hasła — tak działa maszyna dziś i tak
# zostaje, dopóki ktoś świadomie nie założy kont (powód: app/users.py).
USERS_FILE = Path(os.environ.get("USERS_CONFIG", "config/users.json")).resolve()

# dziennik zmian konfiguracji (kto, kiedy, co) — app/audit.py
AUDIT_FILE = Path(os.environ.get("AUDIT_LOG", "config/dziennik-zmian.jsonl")).resolve()

# ważność sesji panelu [s] — liczona od ostatniego użycia, nie od zalogowania
SESSION_TTL = float(os.environ.get("SESSION_TTL", str(12 * 3600)))

# plik konfiguracji wrzeciona (kiedy się załącza i kiedy gaśnie)
SPINDLE_FILE = Path(
    os.environ.get("SPINDLE_CONFIG", "config/spindle.json")
).resolve()

# Wyjście huba sterujące wrzecionem — ustawienie MOSTKA (bridge/machine.env),
# nie serwera. Czytamy je tylko po to, żeby panel mógł ostrzec, że przy
# wartości "none" komendy wrzeciona nic fizycznie nie przełączają. None
# oznacza „serwer nie wie" (zmienna nie jest wyeksportowana do jego procesu).
SPINDLE_OUTPUT = os.environ.get("SPINDLE_OUTPUT")

# plik definicji SMART (nazwane zestawy parametrów procedur sterowanych siłą,
# np. „SMART-sila"); wspólne dla programu technologa i cyklu maszyny
SMART_FILE = Path(os.environ.get("SMART_CONFIG", "config/smart.json")).resolve()

# wartości startowe obszaru roboczego [mm] — używane tylko, dopóki nie ma
# pliku konfiguracji osi
WORK_AREA = {
    "x_min": float(os.environ.get("WORK_X_MIN", "-100")),
    "x_max": float(os.environ.get("WORK_X_MAX", "100")),
    "y_min": float(os.environ.get("WORK_Y_MIN", "-100")),
    "y_max": float(os.environ.get("WORK_Y_MAX", "100")),
    "z_min": float(os.environ.get("WORK_Z_MIN", "-20")),
    "z_max": float(os.environ.get("WORK_Z_MAX", "50")),
}

# maksymalny skok pojedynczego ruchu JOG [mm]
JOG_MAX_STEP = float(os.environ.get("JOG_MAX_STEP", "10"))
