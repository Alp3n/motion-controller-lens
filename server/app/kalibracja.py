"""Kalibracja moment -> siła — część etapu 2 tematu K bez ruchu automatycznego.

Ekran `/sila` z pełnej specyfikacji (`docs/funkcje-smart.md`) ma trzy zadania:
podgląd momentu na żywo (już działa — status ma `torque`/`torque_source` od
etapu 0), **kalibrację siłomierzem** (ten moduł) i **automatyczną próbę
przejazdu** wyznaczającą charakterystykę bazową tarcia/ciężaru osi.

Świadomie zaimplementowana jest tylko kalibracja ręczna: operator dociska
narzędzie do siłomierza przy nieruchomej osi, odczytuje moment z panelu i
wpisuje parę (moment %, siła N) tutaj. To jedyny uczciwy sposób, żeby dostać
niutony zamiast procentów — wzór `F = 2πM/p` ze źródła pomija sprawność
śruby (`docs/funkcje-smart.md`, ryzyko 2).

Automatyczna próba przejazdu (przejazd osi w zadanym zakresie z zapisem
przebiegu momentu) **NIE jest tu zaimplementowana** — rusza maszyną, więc
wymaga ustalenia bezpiecznego profilu ruchu (zakres, prędkość, TrqGlobal
próby) z operatorem przy maszynie, nie zdalnie. Do zrobienia osobno.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

AXES = ("x", "y", "z")

# wolny tekst, ale bez średnika/nowej linii — te pliki i tak nie trafiają do
# `.prg`, ale trzymamy się tej samej ostrożności co reszta repo
_UWAGI_RE = re.compile(r"^[^\n;]*$")


class KalibracjaError(Exception):
    """Błąd kalibracji — komunikat po polsku dla operatora."""


def _num(value, what: str) -> float:
    """Liczba z JSON-a albo formularza (dopuszczamy przecinek dziesiętny)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise KalibracjaError(f"{what}: oczekiwano liczby, jest '{value}'")
    value = float(value)
    if not math.isfinite(value):
        raise KalibracjaError(f"{what}: liczba musi być skończona")
    return value


@dataclass
class PunktKalibracji:
    """Jedna para pomiarowa moment (%) -> siła (N), zmierzona siłomierzem."""

    moment_pct: float
    sila_n: float
    kierunek: str = ""   # wolny tekst, np. "plus"/"minus" — nieoznaczony = ""
    data: str = ""       # ISO 8601; uzupełniane przy zapisie, jeśli puste
    uwagi: str = ""

    def to_dict(self) -> dict:
        return {
            "moment_pct": round(self.moment_pct, 3),
            "sila_n": round(self.sila_n, 3),
            "kierunek": self.kierunek,
            "data": self.data,
            "uwagi": self.uwagi,
        }

    @staticmethod
    def from_dict(data: dict) -> "PunktKalibracji":
        if not isinstance(data, dict):
            raise KalibracjaError("punkt kalibracji: oczekiwano obiektu")
        moment = _num(data.get("moment_pct"), "moment_pct")
        if not (0 < moment <= 100):
            raise KalibracjaError("moment_pct musi być w zakresie (0, 100]")
        sila = _num(data.get("sila_n"), "sila_n")
        if sila < 0:
            raise KalibracjaError("sila_n nie może być ujemna")
        uwagi = str(data.get("uwagi") or "")
        if not _UWAGI_RE.match(uwagi):
            raise KalibracjaError("uwagi: bez średnika ani nowej linii")
        data_pomiaru = str(data.get("data") or "")
        return PunktKalibracji(
            moment_pct=moment,
            sila_n=sila,
            kierunek=str(data.get("kierunek") or ""),
            data=data_pomiaru or _now_iso(),
            uwagi=uwagi,
        )


@dataclass
class KalibracjaOsi:
    punkty: list[PunktKalibracji] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"punkty": [p.to_dict() for p in self.punkty]}

    @staticmethod
    def from_dict(data: dict) -> "KalibracjaOsi":
        if not isinstance(data, dict):
            raise KalibracjaError("kalibracja osi: oczekiwano obiektu")
        punkty_raw = data.get("punkty", [])
        if not isinstance(punkty_raw, list):
            raise KalibracjaError("punkty: oczekiwano listy")
        return KalibracjaOsi(punkty=[PunktKalibracji.from_dict(p) for p in punkty_raw])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_kalibracja() -> dict[str, KalibracjaOsi]:
    return {axis: KalibracjaOsi() for axis in AXES}


def parse_kalibracja(data: dict) -> dict[str, KalibracjaOsi]:
    """Słownik {oś: {punkty: [...]}} -> model; rzuca `KalibracjaError`.

    W przeciwieństwie do `axes.py` brak osi w danych nie jest błędem — brak
    kalibracji to normalny, początkowy stan każdej osi.
    """
    if not isinstance(data, dict):
        raise KalibracjaError("oczekiwano obiektu z osiami X, Y, Z")
    result = default_kalibracja()
    for axis, value in data.items():
        if axis not in AXES:
            raise KalibracjaError(f"nieznana oś '{axis}' — oczekiwano x, y, z")
        result[axis] = KalibracjaOsi.from_dict(value)
    return result


def load(path: Path) -> dict[str, KalibracjaOsi]:
    """Wczytuje kalibrację z pliku; bez pliku — brak punktów dla każdej osi.

    W przeciwieństwie do limitów osi błędny plik kalibracji NIE zatrzymuje
    serwera — to dane pomocnicze do dobierania progów, nie parametr
    bezpieczeństwa; brak kalibracji oznacza po prostu pracę na procentach
    zamiast na niutonach (patrz `docs/funkcje-smart.md`).
    """
    if not path.exists():
        return default_kalibracja()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_kalibracja()
    try:
        return parse_kalibracja(raw)
    except KalibracjaError:
        return default_kalibracja()


def save(path: Path, cfg: dict[str, KalibracjaOsi]) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku."""
    payload = to_dict(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def to_dict(cfg: dict[str, KalibracjaOsi]) -> dict:
    return {axis: osi.to_dict() for axis, osi in cfg.items()}
