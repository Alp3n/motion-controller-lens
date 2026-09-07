"""Nazwane punkty PTP — pozycje X/Y/Z zapisane pod nazwą, do wielokrotnego
użycia w programach technologa.

Kontekst: `docs/prowadzenie-za-reke.md`. Punkt zapisuje się na ekranie
`/nauczanie` (ręczne pozycjonowanie osi X/Y po zwolnieniu momentu — patrz
`docs/zmiany/luzowanie-osi.md` — plus Z wpisywane liczbowo) albo wpisuje
ręcznie na ekranie `/punkty`. W edytorze programu (`/editor`) operacja
PUNKT dostaje listę do wyboru: wybranie nazwy **jednorazowo wypełnia**
pola X/Y/Z tej operacji — świadomie bez trwałego wiązania po nazwie
(decyzja 2026-09-06): późniejsza zmiana punktu w tej bazie NIE zmienia
współrzędnych już zapisanych w plikach `.prg`.

Dane pomocnicze, nie parametr bezpieczeństwa — jak `kalibracja.py`, błędny
plik nie zatrzymuje startu serwera (w przeciwieństwie do `axes.py`/`smart.py`,
gdzie błąd może oznaczać pracę z niewłaściwym limitem).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

# Ta sama reguła co nazwy definicji SMART (app/smart.py) — bez spacji ani
# średnika, na wypadek gdyby nazwa punktu trafiła kiedyś do pliku .prg
# (dziś tylko wypełnia pola w edytorze, ale trzymamy się tej samej ostrożności).
_NAME_RE = re.compile(r"^[^\W\d_][\w-]*$", re.UNICODE)


def is_valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ""))


class PunktyError(Exception):
    """Błąd danych punktu — komunikat po polsku dla operatora."""


def _num(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise PunktyError(f"{what}: oczekiwano liczby, jest '{value}'")
    value = float(value)
    if not math.isfinite(value):
        raise PunktyError(f"{what}: liczba musi być skończona")
    return value


@dataclass
class NamedPoint:
    """Jeden nazwany punkt PTP — współrzędne X/Y/Z plus dowolna notatka."""

    name: str
    x: float
    y: float
    z: float
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
            "note": self.note,
        }

    @staticmethod
    def from_dict(name: str, data: dict) -> "NamedPoint":
        if not is_valid_name(name):
            raise PunktyError(
                f"nieprawidłowa nazwa punktu '{name}' — zacznij od litery, dalej "
                "litery, cyfry, podkreślenie albo myślnik (bez spacji i średnika)"
            )
        if not isinstance(data, dict):
            raise PunktyError(f"punkt '{name}': oczekiwano obiektu ze współrzędnymi")
        return NamedPoint(
            name=name,
            x=_num(data.get("x"), f"punkt '{name}': X"),
            y=_num(data.get("y"), f"punkt '{name}': Y"),
            z=_num(data.get("z"), f"punkt '{name}': Z"),
            note=str(data.get("note") or ""),
        )


def parse_points(data: dict) -> dict[str, NamedPoint]:
    """{'points': {nazwa: {...}}} -> punkty; rzuca `PunktyError`."""
    if not isinstance(data, dict):
        raise PunktyError("oczekiwano obiektu z punktami")
    raw = data.get("points", data)
    if not isinstance(raw, dict):
        raise PunktyError("points: oczekiwano obiektu {nazwa: punkt}")
    return {name: NamedPoint.from_dict(name, body) for name, body in raw.items()}


def load(path: Path) -> dict[str, NamedPoint]:
    """Wczytuje punkty z pliku; bez pliku albo przy błędzie — pusta lista.

    Jak kalibracja: dane pomocnicze do wygody edycji programu, nie parametr
    bezpieczeństwa — błędny plik nie może zatrzymać startu serwera.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    try:
        return parse_points(raw)
    except PunktyError:
        return {}


def save(path: Path, points: dict[str, NamedPoint]) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku."""
    payload = {"points": to_dict(points)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def to_dict(points: dict[str, NamedPoint]) -> dict:
    return {name: p.to_dict() for name, p in points.items()}
