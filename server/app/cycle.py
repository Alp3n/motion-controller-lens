"""Cykl maszyny — kroki poziomu admina, ponad programem detalu.

Program technologa (`.prg`) opisuje **co wyciąć w detalu**. Cykl maszyny
opisuje **co maszyna robi wokół tego**: podanie detalu, docisk, wywołanie
programu detalu, wyrzut. To dwie warstwy na tych samych osiach fizycznych,
z różnymi parametrami ruchu — stąd pole `profile` w kroku i mechanizm
snapshot/restore w `machine.py`.

Podział wynika z `zbyszek/DECYZJE_2026-08-25.md` §3; model:
`docs/model-cyklu-maszyny.md`.

Rodzaje kroków:

    RUCH     — przejazd wskazanych osi do zadanych pozycji
    PROGRAM  — wywołanie załadowanego programu detalu (12NC)
    WYJSCIE  — ustawienie wyjścia cyfrowego (podajnik, wyrzutnik, lampka)
    SMART    — wywołanie definicji SMART (ruch reagujący na siłę, temat K)
    PAUZA    — zatrzymanie do potwierdzenia przez operatora

Świadomie **nie ma** kroku „czekaj na wejście": dziś nie mamy żadnego
czytelnego wejścia poza Global Stop, więc taki krok nigdy by się nie
odblokował. Wraca, gdy wejścia A/B węzłów będą dostępne przez mostek
(patrz `docs/mozliwosci-clearpath-sc.md`).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .smart import is_valid_name

STEP_MOVE = "RUCH"
STEP_PROGRAM = "PROGRAM"
STEP_OUTPUT = "WYJSCIE"
# Krok SMART wskazuje definicję po nazwie — te same definicje, których używa
# program technologa (kolumna SMART w `.prg`), żeby nazwa znaczyła w obu
# miejscach dokładnie to samo. Model: `app/smart.py`, opis: docs/funkcje-smart.md
STEP_SMART = "SMART"
STEP_PAUSE = "PAUZA"

STEP_KINDS = (STEP_MOVE, STEP_PROGRAM, STEP_OUTPUT, STEP_SMART, STEP_PAUSE)

# Wyjścia cyfrowe maszyny. Odpowiadają wyjściom BRAKE_0/BRAKE_1 na SC4-Hub —
# jedno z nich zajmuje wrzeciono, drugie jest do dyspozycji cyklu (decyzja
# zapisana w docs/plan-rozwoju.md, temat J).
OUTPUT_NAMES = ("wyjscie_0", "wyjscie_1")

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CycleError(Exception):
    """Błąd definicji cyklu — komunikat po polsku dla operatora."""

    def __init__(self, message: str, lp: int | None = None):
        self.lp = lp
        prefix = f"krok {lp}: " if lp else ""
        super().__init__(prefix + message)


def _num(value, what: str, lp: int | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise CycleError(f"{what}: oczekiwano liczby, jest '{value}'", lp)
    value = float(value)
    if not math.isfinite(value):
        raise CycleError(f"{what}: liczba musi być skończona", lp)
    return value


@dataclass
class CycleStep:
    lp: int
    kind: str
    # profil parametrów ruchu na czas tego kroku; None = zostaw aktywny
    profile: str | None = None
    # RUCH: oś -> pozycja docelowa [mm]
    targets: dict[str, float] = field(default_factory=dict)
    feed: float | None = None          # RUCH: posuw [mm/min]
    output: str | None = None          # WYJSCIE: nazwa wyjścia
    output_on: bool | None = None      # WYJSCIE: stan do ustawienia
    smart: str | None = None           # SMART: nazwa definicji
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "lp": self.lp,
            "kind": self.kind,
            "profile": self.profile,
            "targets": {a: round(v, 4) for a, v in self.targets.items()},
            "feed": self.feed,
            "output": self.output,
            "output_on": self.output_on,
            "smart": self.smart,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CycleStep:
        if not isinstance(data, dict):
            raise CycleError("oczekiwano obiektu z opisem kroku")
        try:
            lp = int(data["lp"])
        except (KeyError, TypeError, ValueError):
            raise CycleError(f"niepoprawny numer LP: '{data.get('lp')}'")

        kind = str(data.get("kind", "")).upper()
        if kind not in STEP_KINDS:
            raise CycleError(
                f"nieznany rodzaj kroku '{data.get('kind')}' — dozwolone: "
                + ", ".join(STEP_KINDS),
                lp,
            )

        profile = data.get("profile") or None
        if profile is not None and not _NAME_RE.match(str(profile)):
            raise CycleError(f"nieprawidłowa nazwa profilu '{profile}'", lp)

        raw_targets = data.get("targets") or {}
        if not isinstance(raw_targets, dict):
            raise CycleError("targets: oczekiwano obiektu {oś: pozycja}", lp)
        targets = {
            str(axis).lower(): _num(value, f"pozycja osi {str(axis).upper()}", lp)
            for axis, value in raw_targets.items()
        }

        feed = data.get("feed")
        feed = None if feed in (None, "") else _num(feed, "posuw", lp)

        output = data.get("output") or None
        output_on = data.get("output_on")
        smart = data.get("smart") or None

        step = cls(
            lp=lp,
            kind=kind,
            profile=None if profile is None else str(profile),
            targets=targets,
            feed=feed,
            output=None if output is None else str(output),
            output_on=None if output_on is None else bool(output_on),
            smart=None if smart is None else str(smart).strip(),
            note=str(data.get("note", "")),
        )
        step.validate()
        return step

    def validate(self) -> None:
        if self.kind == STEP_MOVE:
            if not self.targets:
                raise CycleError("RUCH wymaga co najmniej jednej osi docelowej", self.lp)
            if self.feed is not None and self.feed <= 0:
                raise CycleError("posuw musi być większy od zera", self.lp)
        else:
            if self.targets:
                raise CycleError(f"{self.kind} nie przyjmuje pozycji osi", self.lp)
            if self.feed is not None:
                raise CycleError(f"{self.kind} nie przyjmuje posuwu", self.lp)

        if self.kind == STEP_OUTPUT:
            if self.output not in OUTPUT_NAMES:
                raise CycleError(
                    f"nieznane wyjście '{self.output}' — dozwolone: "
                    + ", ".join(OUTPUT_NAMES),
                    self.lp,
                )
            if self.output_on is None:
                raise CycleError("WYJSCIE wymaga stanu (output_on)", self.lp)
        elif self.output is not None or self.output_on is not None:
            raise CycleError(
                f"{self.kind} nie steruje wyjściem — pola output dotyczą WYJSCIE",
                self.lp,
            )

        if self.kind == STEP_SMART:
            if not self.smart:
                raise CycleError(
                    "SMART wymaga wskazania definicji (ekran „Funkcje SMART”)",
                    self.lp,
                )
            if not is_valid_name(self.smart):
                raise CycleError(
                    f"nieprawidłowa nazwa definicji SMART '{self.smart}' — "
                    "zacznij od litery, dalej litery, cyfry, podkreślenie "
                    "albo myślnik",
                    self.lp,
                )
        elif self.smart:
            raise CycleError(
                f"{self.kind} nie wywołuje funkcji SMART — pole SMART dotyczy "
                "kroku SMART",
                self.lp,
            )


@dataclass
class Cycle:
    name: str
    steps: list[CycleStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": [s.to_dict() for s in self.steps]}

    def uses_program(self) -> bool:
        return any(s.kind == STEP_PROGRAM for s in self.steps)


def parse_cycle(data: dict) -> Cycle:
    """{'name': ..., 'steps': [...]} -> Cycle; rzuca CycleError."""
    if not isinstance(data, dict):
        raise CycleError("oczekiwano obiektu z definicją cyklu")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        raise CycleError("brak listy kroków (steps)")
    steps = [CycleStep.from_dict(s) for s in raw_steps]
    for i, step in enumerate(steps, start=1):
        if step.lp != i:
            raise CycleError(f"numeracja LP musi być ciągła od 1 — oczekiwano {i}, jest {step.lp}")
    return Cycle(name=str(data.get("name", "")), steps=steps)


def empty_cycle() -> Cycle:
    """Pusty cykl — stan startowy, dopóki admin go nie zdefiniuje."""
    return Cycle(name="", steps=[])


def load(path: Path) -> Cycle:
    """Wczytuje cykl z pliku; bez pliku — pusty cykl.

    Błędny plik przerywa start serwera, tak samo jak błędna konfiguracja osi
    czy profili: cykl porusza maszyną i praca na cicho podstawionym byłaby
    gorsza niż brak startu.
    """
    if not path.exists():
        return empty_cycle()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CycleError(f"nie można odczytać pliku cyklu {path}: {exc}")
    return parse_cycle(raw)


def save(path: Path, cycle: Cycle) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cycle.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def warnings(cycle: Cycle, profile_names, axis_names, smart_names=()) -> list[str]:
    """Rzeczy poprawne składniowo, ale które nie zadziałają tak, jak wygląda."""
    out: list[str] = []
    profile_names = set(profile_names)
    axis_names = set(axis_names)
    smart_names = set(smart_names)
    for step in cycle.steps:
        if step.kind == STEP_SMART and step.smart not in smart_names:
            out.append(
                f"krok {step.lp}: nie ma definicji SMART '{step.smart}' — "
                "cykl zatrzyma się na tym kroku, dopóki jej nie dodasz"
            )
        if step.profile and step.profile not in profile_names:
            out.append(
                f"krok {step.lp}: profil '{step.profile}' nie istnieje — "
                "krok wykona się na profilu aktywnym"
            )
        unknown = sorted(a for a in step.targets if a not in axis_names)
        if unknown:
            out.append(
                f"krok {step.lp}: osie nieskonfigurowane w maszynie: "
                + ", ".join(a.upper() for a in unknown)
            )
    return out
