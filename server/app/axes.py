"""Konfiguracja osi maszyny — długość fizyczna, limity programowe, przełożenie.

Ekran „Konfiguracja osi" (/axes) zapisuje te dane do pliku JSON (AXES_CONFIG).
Plik jest źródłem prawdy dla walidacji programów, ruchu ręcznego i mostka —
zastępuje dawne zmienne WORK_*, które służą już tylko za wartości startowe,
gdy pliku jeszcze nie ma.

Zakresu fizycznego nie podaje się wprost — wynika z długości osi i punktu
bazowego, czyli miejsca, w którym po bazowaniu leży zero osi:

    minus  ->  0 .. długość            (zero na końcu „minusowym")
    plus   ->  -długość .. 0           (zero na końcu „plusowym")
    srodek ->  -długość/2 .. +długość/2

Limity programowe muszą mieścić się w zakresie fizycznym — to one ograniczają
maszynę w praktyce; zakres fizyczny jest tylko granicą, której nie da się
przekroczyć mechanicznie.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

AXIS_NAMES = ("x", "y", "z")

HOME_MINUS = "minus"
HOME_PLUS = "plus"
HOME_CENTER = "srodek"
HOME_POINTS = (HOME_MINUS, HOME_PLUS, HOME_CENTER)

# tolerancja porównań [mm] — chroni przed odrzuceniem limitu równego granicy
# zakresu tylko dlatego, że 300/2 zapisało się jako 149.99999999999997
EPS = 1e-6


class AxisConfigError(Exception):
    """Błąd konfiguracji osi — komunikat po polsku dla operatora."""


def _num(value, what: str) -> float:
    """Liczba z JSON-a albo z formularza (dopuszczamy przecinek dziesiętny)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise AxisConfigError(f"{what}: oczekiwano liczby, jest '{value}'")
    value = float(value)
    if not math.isfinite(value):
        raise AxisConfigError(f"{what}: liczba musi być skończona")
    return value


@dataclass
class AxisConfig:
    length: float       # długość fizyczna osi [mm]
    home: str           # punkt bazowy: minus | plus | srodek
    soft_min: float     # limit programowy dolny [mm]
    soft_max: float     # limit programowy górny [mm]
    mm_per_rev: float   # przełożenie posuwu: mm na obrót silnika

    # --- zakres fizyczny (wynika z długości i punktu bazowego) -------------

    def physical_range(self) -> tuple[float, float]:
        if self.home == HOME_MINUS:
            return 0.0, self.length
        if self.home == HOME_PLUS:
            return -self.length, 0.0
        return -self.length / 2.0, self.length / 2.0

    # --- (de)serializacja --------------------------------------------------

    def to_dict(self) -> dict:
        lo, hi = self.physical_range()
        return {
            "length": round(self.length, 4),
            "home": self.home,
            "soft_min": round(self.soft_min, 4),
            "soft_max": round(self.soft_max, 4),
            "mm_per_rev": round(self.mm_per_rev, 6),
            # pola wyliczane — tylko do odczytu, dla panelu i dokumentacji
            "phys_min": round(lo, 4),
            "phys_max": round(hi, 4),
        }

    @classmethod
    def from_dict(cls, axis: str, data: dict) -> AxisConfig:
        label = f"oś {axis.upper()}"
        if not isinstance(data, dict):
            raise AxisConfigError(f"{label}: oczekiwano obiektu z parametrami osi")
        missing = [
            key
            for key in ("length", "home", "soft_min", "soft_max", "mm_per_rev")
            if key not in data
        ]
        if missing:
            raise AxisConfigError(f"{label}: brak pól: " + ", ".join(missing))
        cfg = cls(
            length=_num(data["length"], f"{label}: długość fizyczna"),
            home=str(data["home"]).strip().lower(),
            soft_min=_num(data["soft_min"], f"{label}: limit programowy MIN"),
            soft_max=_num(data["soft_max"], f"{label}: limit programowy MAX"),
            mm_per_rev=_num(data["mm_per_rev"], f"{label}: przełożenie posuwu"),
        )
        cfg.validate(axis)
        return cfg

    # --- walidacja ---------------------------------------------------------

    def validate(self, axis: str) -> None:
        label = f"oś {axis.upper()}"
        if self.length <= 0:
            raise AxisConfigError(f"{label}: długość fizyczna musi być większa od zera")
        if self.home not in HOME_POINTS:
            raise AxisConfigError(
                f"{label}: nieznany punkt bazowania '{self.home}' — dozwolone: "
                + ", ".join(HOME_POINTS)
            )
        if self.mm_per_rev <= 0:
            raise AxisConfigError(
                f"{label}: przełożenie posuwu (mm na obrót) musi być większe od zera"
            )
        if self.soft_max - self.soft_min <= EPS:
            raise AxisConfigError(
                f"{label}: limit programowy MIN ({_mm(self.soft_min)}) musi być "
                f"mniejszy od MAX ({_mm(self.soft_max)})"
            )
        lo, hi = self.physical_range()
        if self.soft_min < lo - EPS or self.soft_max > hi + EPS:
            raise AxisConfigError(
                f"{label}: limity programowe {_mm(self.soft_min)}..{_mm(self.soft_max)} "
                f"wychodzą poza zakres fizyczny {_mm(lo)}..{_mm(hi)} — zmień długość "
                f"osi albo punkt bazowania"
            )


def _mm(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


# --- wartości startowe -----------------------------------------------------


def default_axes(work_area: dict) -> dict[str, AxisConfig]:
    """Konfiguracja startowa z dawnych zmiennych WORK_* — bez zmiany zachowania.

    Punkt bazowania wybieramy tak, żeby zakres z WORK_* mieścił się w zakresie
    fizycznym: zero na końcu osi, jeśli tam wypada, w przeciwnym razie środek
    i długość dobrana do dalszego z krańców.
    """
    axes: dict[str, AxisConfig] = {}
    for axis in AXIS_NAMES:
        lo = float(work_area[f"{axis}_min"])
        hi = float(work_area[f"{axis}_max"])
        if abs(lo) < EPS:
            home, length = HOME_MINUS, hi
        elif abs(hi) < EPS:
            home, length = HOME_PLUS, -lo
        else:
            home, length = HOME_CENTER, 2.0 * max(abs(lo), abs(hi))
        axes[axis] = AxisConfig(
            length=length,
            home=home,
            soft_min=lo,
            soft_max=hi,
            mm_per_rev=float(os.environ.get("MM_PER_REV", "5.0")),
        )
        axes[axis].validate(axis)
    return axes


# --- plik konfiguracyjny ---------------------------------------------------


def parse_axes(data: dict) -> dict[str, AxisConfig]:
    """Słownik {oś: parametry} -> konfiguracja; rzuca AxisConfigError."""
    if not isinstance(data, dict):
        raise AxisConfigError("oczekiwano obiektu z osiami X, Y, Z")
    missing = [a for a in AXIS_NAMES if a not in data]
    if missing:
        raise AxisConfigError(
            "brak konfiguracji osi: " + ", ".join(a.upper() for a in missing)
        )
    return {axis: AxisConfig.from_dict(axis, data[axis]) for axis in AXIS_NAMES}


def load(path: Path, fallback_work_area: dict) -> dict[str, AxisConfig]:
    """Wczytuje konfigurację z pliku; bez pliku — wartości startowe.

    Błędny plik zatrzymuje serwer zamiast cicho podstawiać wartości domyślne:
    limity osi są parametrem bezpieczeństwa i praca na niewłaściwych jest
    gorsza niż brak startu.
    """
    if not path.exists():
        return default_axes(fallback_work_area)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AxisConfigError(f"nie można odczytać pliku konfiguracji osi {path}: {exc}")
    return parse_axes(raw.get("axes", raw))


def save(path: Path, axes: dict[str, AxisConfig]) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku limitów."""
    payload = {"axes": {axis: axes[axis].to_dict() for axis in AXIS_NAMES}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def work_area(axes: dict[str, AxisConfig]) -> dict:
    """Obszar roboczy do walidacji programów — z limitów programowych."""
    area = {}
    for axis in AXIS_NAMES:
        area[f"{axis}_min"] = axes[axis].soft_min
        area[f"{axis}_max"] = axes[axis].soft_max
    return area


def to_dict(axes: dict[str, AxisConfig]) -> dict:
    return {axis: axes[axis].to_dict() for axis in AXIS_NAMES}
