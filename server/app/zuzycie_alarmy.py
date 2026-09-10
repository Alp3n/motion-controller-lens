"""Definicje alarmów zużycia — krok 4 tematu M (`docs/analiza-zuzycia-osi.md`).

Nazwany próg: oś + metryka + okres + wartość graniczna. Sprawdzany PO
KAŻDYM zakończonym przebiegu, w tym samym miejscu co zapis danych
(`main.py::_poll_loop`, zaraz po `zuzycie.record_run()`) — zgodnie z
zasadą „obrabiamy dane po cyklu, na spokojnie" z tematu K.

**Świadomie poza zakresem tego modułu** (krok 5, nieustalone): wysyłka
e-mail i zgłoszenia do modułu FAP systemu MES — to robi wMES, nie nasz
serwer (decyzja 2026-09-10). Ten moduł tylko DEFINIUJE progi i OCENIA je;
wynik oceny (`AlarmStatus`) jest dziś widoczny wyłącznie na ekranie
`/zuzycie` — udostępnienie go systemowi MES do odczytu to osobny krok.

Wzorowane na `app/smart.py` (ten sam styl: dataclass + walidacja +
plik JSON atomowy), ale prostsze — jedna logika oceny, nie rejestr
wielu procedur.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

_NAME_RE = re.compile(r"^[^\W\d_][\w-]*$", re.UNICODE)

METRYKA_DYSTANS = "dystans_mm_suma"
METRYKA_MOMENT_MAX = "moment_max_pct"
METRYKI = (METRYKA_DYSTANS, METRYKA_MOMENT_MAX)
METRYKA_LABELS = {
    METRYKA_DYSTANS: "dystans [mm]",
    METRYKA_MOMENT_MAX: "moment maksymalny [%]",
}

OKRES_DZIEN = "dzien"
OKRES_TYDZIEN = "tydzien"
OKRESY = (OKRES_DZIEN, OKRES_TYDZIEN)


class AlarmError(Exception):
    """Błąd definicji alarmu — komunikat po polsku dla operatora."""


@dataclass
class AlarmDefinition:
    name: str
    os: str
    metryka: str
    okres: str
    prog: float
    aktywny: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "os": self.os,
            "metryka": self.metryka,
            "okres": self.okres,
            "prog": self.prog,
            "aktywny": self.aktywny,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> AlarmDefinition:
        if not _NAME_RE.match(name):
            raise AlarmError(
                f"nieprawidłowa nazwa alarmu '{name}' — zacznij od litery, dalej "
                "litery, cyfry, podkreślenie albo myślnik"
            )
        if not isinstance(data, dict):
            raise AlarmError(f"alarm '{name}': oczekiwano obiektu z parametrami")

        os_ = str(data.get("os", "")).strip().lower()
        metryka = str(data.get("metryka", "")).strip()
        okres = str(data.get("okres", "")).strip()
        prog = data.get("prog")

        if metryka not in METRYKI:
            raise AlarmError(
                f"alarm '{name}': nieznana metryka '{metryka}' — dostępne: "
                + ", ".join(METRYKI)
            )
        if okres not in OKRESY:
            raise AlarmError(
                f"alarm '{name}': nieznany okres '{okres}' — dostępne: "
                + ", ".join(OKRESY)
            )
        if isinstance(prog, bool) or not isinstance(prog, (int, float)):
            try:
                prog = float(str(prog).strip().replace(",", "."))
            except (TypeError, ValueError):
                raise AlarmError(f"alarm '{name}': próg ma być liczbą, jest '{prog}'")
        prog = float(prog)
        if not math.isfinite(prog) or prog <= 0:
            raise AlarmError(f"alarm '{name}': próg musi być liczbą dodatnią")

        definition = cls(
            name=name,
            os=os_,
            metryka=metryka,
            okres=okres,
            prog=prog,
            aktywny=bool(data.get("aktywny", True)),
            note=str(data.get("note", "")),
        )
        return definition


# --- ocena progów ------------------------------------------------------------


@dataclass
class AlarmStatus:
    name: str
    os: str
    metryka: str
    okres: str
    prog: float
    wartosc: float | None
    przekroczony: bool
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "os": self.os,
            "metryka": self.metryka,
            "okres": self.okres,
            "prog": self.prog,
            "wartosc": self.wartosc,
            "przekroczony": self.przekroczony,
            "note": self.note,
        }


def _tydzien_wartosc(trend: list[dict], os_: str, metryka: str, dzisiaj: dict) -> float | None:
    """Suma/maksimum z ostatnich 7 dni trendu + dzisiaj, zależnie od metryki.

    Dystans sumuje się (zużycie kumuluje); moment maksymalny bierze się
    jako największa wartość bezwzględna z całego okresu (szczyt
    obciążenia w tygodniu, nie suma — sumowanie procentów nie ma sensu)."""
    days = [e for e in trend if e.get("os") == os_][:7]  # trend jest od najnowszych
    values = [e.get(metryka) for e in days if e.get(metryka) is not None]
    today_val = dzisiaj.get(os_, {}).get(metryka)
    if today_val is not None:
        values.append(today_val)
    if not values:
        return None
    if metryka == METRYKA_DYSTANS:
        return round(sum(values), 1)
    return max(values, key=abs)  # moment_max_pct


def evaluate(
    definitions: dict[str, AlarmDefinition],
    dzisiaj: dict[str, dict],
    trend: list[dict],
) -> list[AlarmStatus]:
    """Ocena wszystkich AKTYWNYCH definicji względem bieżących danych.

    `dzisiaj`/`trend` mają dokładnie kształt zwracany przez
    `zuzycie.summarize_today()`/`zuzycie.read_trend()` (patrz `GET /api/zuzycie`).
    """
    out: list[AlarmStatus] = []
    for definition in definitions.values():
        if not definition.aktywny:
            continue
        if definition.okres == OKRES_DZIEN:
            wartosc = dzisiaj.get(definition.os, {}).get(definition.metryka)
        else:
            wartosc = _tydzien_wartosc(trend, definition.os, definition.metryka, dzisiaj)
        przekroczony = wartosc is not None and abs(wartosc) >= definition.prog
        out.append(
            AlarmStatus(
                name=definition.name,
                os=definition.os,
                metryka=definition.metryka,
                okres=definition.okres,
                prog=definition.prog,
                wartosc=wartosc,
                przekroczony=przekroczony,
                note=definition.note,
            )
        )
    return out


# --- plik konfiguracyjny -----------------------------------------------------


def default_definitions() -> dict[str, AlarmDefinition]:
    return {}


def parse_definitions(data: dict) -> dict[str, AlarmDefinition]:
    if not isinstance(data, dict):
        raise AlarmError("oczekiwano obiektu z definicjami alarmów")
    raw = data.get("alarmy", data)
    if not isinstance(raw, dict):
        raise AlarmError("alarmy: oczekiwano obiektu {nazwa: definicja}")
    return {name: AlarmDefinition.from_dict(name, body) for name, body in raw.items()}


def load(path: Path) -> dict[str, AlarmDefinition]:
    """Wczytuje definicje; bez pliku — brak alarmów (nie parametr
    bezpieczeństwa, więc pusty start jest bezpieczny, w przeciwieństwie
    do np. konfiguracji osi)."""
    if not path.exists():
        return default_definitions()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AlarmError(f"nie można odczytać pliku alarmów zużycia {path}: {exc}")
    return parse_definitions(raw)


def save(path: Path, definitions: dict[str, AlarmDefinition]) -> None:
    payload = {"alarmy": {n: d.to_dict() for n, d in definitions.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def to_dict(definitions: dict[str, AlarmDefinition]) -> dict:
    return {name: d.to_dict() for name, d in definitions.items()}
