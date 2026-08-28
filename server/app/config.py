"""Konfiguracja serwera maszyny — wszystko przez zmienne środowiskowe."""

from __future__ import annotations

import os
from pathlib import Path

# katalog z plikami programów (docelowo zasób sieciowy współdzielony z MES)
PROGRAMS_DIR = Path(os.environ.get("PROGRAMS_DIR", "programs")).resolve()

# tryb warstwy maszyny: "sim" (symulator) lub "clearcore" (sprzęt)
MACHINE_MODE = os.environ.get("MACHINE_MODE", "sim")

# adres sterownika ClearCore (tryb "clearcore")
CLEARCORE_HOST = os.environ.get("CLEARCORE_HOST", "192.168.0.50")
CLEARCORE_PORT = int(os.environ.get("CLEARCORE_PORT", "8500"))

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
