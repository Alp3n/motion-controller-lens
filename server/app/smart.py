"""Definicje SMART — nazwane zestawy parametrów procedur sterowanych siłą.

Trzy poziomy, opisane w `docs/funkcje-smart.md`:

    procedura        algorytm reagujący na siłę (C++ w mostku), np.
                     „ciecie_adaptacyjne"; deklaruje, jakie ma parametry
    definicja SMART  nazwany zestaw wartości tych parametrów, np.
                     „SMART-sila"; edytowana na ekranie /smart
    użycie           wiersz programu technologa albo krok cyklu maszyny,
                     wskazujący definicję po nazwie

Ten moduł odpowiada za środkowy poziom: rejestr procedur (żeby ekran wiedział,
jakie pola narysować), model definicji, walidację i plik `config/smart.json`.

DLACZEGO REJESTR JEST TU, A NIE TYLKO W MOSTKU: bez własnego, wbudowanego
opisu procedur ekran `/smart` i edytor nie działałyby bez podłączonego
sprzętu — czyli nie dałoby się ich zbudować ani przetestować przed pracą przy
maszynie. Mostek ma swój rejestr w C++; komenda `SMARTLIST` pozwoli porównać
oba i **ostrzec** przy rozjeździe, zamiast wywalić się dopiero przy starcie
cyklu.

OGRANICZENIE, które trzeba znać: sama procedura (pętla odczytu momentu
i reakcji) **nie istnieje jeszcze w mostku** — to etap 4 tematu K. Do tego
czasu definicje można tworzyć i zapisywać, a symulator wykonuje krok SMART
jako zwykły ruch, bez kontroli siły. Patrz `docs/funkcje-smart.md`.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

# Nazwa definicji: zaczyna się literą, dalej litery/cyfry/`_`/`-`.
# Świadomie dopuszczamy wielkie litery i myślnik (chcemy nazwy w rodzaju
# „SMART-sila"), ale nie spacje ani średnik — nazwa trafia do pliku `.prg`,
# gdzie średnik rozdziela kolumny.
_NAME_RE = re.compile(r"^[^\W\d_][\w-]*$", re.UNICODE)

# oś, na której działa procedura — dziś mostek rusza tylko X/Y/Z
AXES = ("x", "y", "z")


class SmartError(Exception):
    """Błąd definicji SMART — komunikat po polsku dla operatora."""


@dataclass(frozen=True)
class ParamSpec:
    """Opis jednego parametru procedury — źródło prawdy dla walidacji i UI."""

    name: str
    label: str                       # co widzi technolog na ekranie
    default: float | str
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] | None = None
    help: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "default": self.default,
            "unit": self.unit,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "choices": list(self.choices) if self.choices else None,
            "help": self.help,
        }

    def check(self, value, procedure: str):
        """Sprawdza jedną wartość; zwraca ją znormalizowaną albo rzuca."""
        label = f"procedura '{procedure}', {self.label}"
        if self.choices is not None:
            text = str(value).strip().lower()
            if text not in self.choices:
                raise SmartError(
                    f"{label}: dozwolone wartości to " + ", ".join(self.choices)
                    + f", jest '{value}'"
                )
            return text

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(str(value).strip().replace(",", "."))
            except (TypeError, ValueError):
                raise SmartError(f"{label}: oczekiwano liczby, jest '{value}'")
        value = float(value)
        if not math.isfinite(value):
            raise SmartError(f"{label}: liczba musi być skończona")
        if self.minimum is not None and value < self.minimum:
            raise SmartError(
                f"{label}: wartość nie może być mniejsza niż {_fmt(self.minimum)}"
                f"{' ' + self.unit if self.unit else ''}, jest {_fmt(value)}"
            )
        if self.maximum is not None and value > self.maximum:
            raise SmartError(
                f"{label}: wartość nie może być większa niż {_fmt(self.maximum)}"
                f"{' ' + self.unit if self.unit else ''}, jest {_fmt(value)}"
            )
        return value


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Procedure:
    """Algorytm reagujący na siłę — implementowany w mostku (C++)."""

    name: str
    label: str
    description: str
    params: tuple[ParamSpec, ...]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "params": [p.to_dict() for p in self.params],
        }

    def spec(self, param: str) -> ParamSpec | None:
        for p in self.params:
            if p.name == param:
                return p
        return None


# --- rejestr procedur ------------------------------------------------------
#
# Parametry `ciecie_adaptacyjne` odpowiadają algorytmowi „smart cutting"
# z `zbyszek/kontrola-sily.md`. Wartości domyślne są z tamtego materiału
# (30% siły, 5 mm dojazdu, 1 mm cofnięcia, progi 0.8/0.5, kolizja 2.0×),
# przeliczone tam, gdzie trzymamy inne jednostki: prędkości w mm/min, tak jak
# posuwy w całym projekcie, a nie w mm/s.

_CIECIE_ADAPTACYJNE = Procedure(
    name="ciecie_adaptacyjne",
    label="Cięcie adaptacyjne",
    description=(
        "Jedzie zadaną oś do przodu, obserwując moment silnika. Zwalnia, gdy "
        "obciążenie rośnie, przyspiesza, gdy maleje. Po przekroczeniu progu "
        "siły zatrzymuje ruch i cofa narzędzie. Nagły skok obciążenia traktuje "
        "jako kolizję i cofa mocniej."
    ),
    params=(
        ParamSpec(
            "os", "Oś ruchu", default="z", choices=AXES,
            help="oś, którą procedura dosuwa narzędzie; mostek rusza dziś tylko X/Y/Z",
        ),
        ParamSpec(
            "sila_pct", "Próg siły", default=30.0, unit="%",
            minimum=0.1, maximum=100.0,
            help="procent maksymalnego momentu silnika, przy którym uznajemy "
                 "cięcie za wykonane i cofamy narzędzie",
        ),
        ParamSpec(
            "dojazd_mm", "Dojazd", default=5.0, unit="mm",
            minimum=0.001, maximum=500.0,
            help="o ile oś ma pojechać do przodu, licząc od bieżącej pozycji",
        ),
        ParamSpec(
            "cofniecie_mm", "Cofnięcie", default=1.0, unit="mm",
            minimum=0.0, maximum=500.0,
            help="o ile cofnąć narzędzie po przekroczeniu progu siły",
        ),
        ParamSpec(
            "v_szybka", "Prędkość szybka", default=600.0, unit="mm/min",
            minimum=1.0, maximum=20000.0,
            help="posuw przy małym obciążeniu (dojazd do materiału)",
        ),
        ParamSpec(
            "v_wolna", "Prędkość wolna", default=120.0, unit="mm/min",
            minimum=1.0, maximum=20000.0,
            help="posuw po wejściu w materiał, przy dużym obciążeniu",
        ),
        ParamSpec(
            "prog_zwolnienia", "Próg zwolnienia", default=0.8, unit="× próg siły",
            minimum=0.05, maximum=1.0,
            help="ułamek progu siły, powyżej którego procedura zwalnia do "
                 "prędkości wolnej",
        ),
        ParamSpec(
            "prog_przyspieszenia", "Próg przyspieszenia", default=0.5, unit="× próg siły",
            minimum=0.0, maximum=1.0,
            help="ułamek progu siły, poniżej którego procedura wraca do "
                 "prędkości szybkiej",
        ),
        ParamSpec(
            "wsp_kolizji", "Współczynnik kolizji", default=2.0, unit="× próg siły",
            minimum=1.0, maximum=10.0,
            help="nagły skok obciążenia powyżej tej wielokrotności progu jest "
                 "traktowany jako kolizja — większe cofnięcie i alarm",
        ),
        ParamSpec(
            "probkowanie_ms", "Okres próbkowania", default=20.0, unit="ms",
            minimum=1.0, maximum=1000.0,
            help="co ile mostek odczytuje moment; realny koszt odczytu trzeba "
                 "zmierzyć na maszynie (patrz docs/funkcje-smart.md)",
        ),
    ),
)

PROCEDURES: dict[str, Procedure] = {p.name: p for p in (_CIECIE_ADAPTACYJNE,)}

# nazwa definicji zakładanej, gdy nie ma jeszcze pliku — z Twojego opisu
DEFAULT_DEFINITION = "SMART-sila"


def procedures_to_dict() -> list[dict]:
    return [p.to_dict() for p in PROCEDURES.values()]


# --- definicja SMART -------------------------------------------------------


@dataclass
class SmartDefinition:
    """Nazwany zestaw parametrów jednej procedury."""

    name: str
    procedure: str
    params: dict[str, float | str] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "procedure": self.procedure,
            "params": dict(self.params),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> SmartDefinition:
        if not _NAME_RE.match(name):
            raise SmartError(
                f"nieprawidłowa nazwa definicji '{name}' — zacznij od litery, "
                "dalej litery, cyfry, podkreślenie albo myślnik (bez spacji "
                "i średnika)"
            )
        if not isinstance(data, dict):
            raise SmartError(f"definicja '{name}': oczekiwano obiektu z parametrami")

        procedure = str(data.get("procedure", "")).strip()
        proc = PROCEDURES.get(procedure)
        if proc is None:
            raise SmartError(
                f"definicja '{name}': nieznana procedura '{procedure}' — "
                "dostępne: " + ", ".join(sorted(PROCEDURES))
            )

        raw = data.get("params") or {}
        if not isinstance(raw, dict):
            raise SmartError(f"definicja '{name}': params ma być obiektem")

        unknown = [k for k in raw if proc.spec(k) is None]
        if unknown:
            raise SmartError(
                f"definicja '{name}': procedura '{procedure}' nie ma parametrów: "
                + ", ".join(sorted(unknown))
            )

        # Brakujące pola uzupełniamy wartością domyślną procedury zamiast
        # odrzucać definicję: po dopisaniu nowego parametru w rejestrze stare
        # definicje mają dalej działać, a nie blokować start serwera.
        params: dict[str, float | str] = {}
        for spec in proc.params:
            value = raw[spec.name] if spec.name in raw else spec.default
            params[spec.name] = spec.check(value, procedure)

        definition = cls(
            name=name,
            procedure=procedure,
            params=params,
            note=str(data.get("note", "")),
        )
        definition.validate()
        return definition

    def validate(self) -> None:
        """Sprawdza zależności między parametrami, nie tylko zakresy."""
        if self.procedure != "ciecie_adaptacyjne":
            return
        zwolnienie = float(self.params["prog_zwolnienia"])
        przyspieszenie = float(self.params["prog_przyspieszenia"])
        if przyspieszenie >= zwolnienie:
            raise SmartError(
                f"definicja '{self.name}': próg przyspieszenia "
                f"({_fmt(przyspieszenie)}) musi być mniejszy od progu zwolnienia "
                f"({_fmt(zwolnienie)}) — inaczej procedura przełączałaby "
                "prędkość w kółko przy tym samym obciążeniu"
            )
        if float(self.params["v_wolna"]) > float(self.params["v_szybka"]):
            raise SmartError(
                f"definicja '{self.name}': prędkość wolna nie może być większa "
                "od szybkiej"
            )


# --- wartości startowe -----------------------------------------------------


def default_definitions() -> dict[str, SmartDefinition]:
    """Jedna definicja startowa, żeby ekran nie był pusty przy pierwszym wejściu."""
    proc = PROCEDURES["ciecie_adaptacyjne"]
    return {
        DEFAULT_DEFINITION: SmartDefinition(
            name=DEFAULT_DEFINITION,
            procedure=proc.name,
            params={p.name: p.default for p in proc.params},
            note="wartości startowe — dobierz doświadczalnie na odpadzie",
        )
    }


# --- plik konfiguracyjny ---------------------------------------------------


def parse_definitions(data: dict) -> dict[str, SmartDefinition]:
    """{'definitions': {nazwa: {...}}} -> definicje; rzuca SmartError."""
    if not isinstance(data, dict):
        raise SmartError("oczekiwano obiektu z definicjami SMART")
    raw = data.get("definitions", data)
    if not isinstance(raw, dict):
        raise SmartError("definitions: oczekiwano obiektu {nazwa: definicja}")
    return {name: SmartDefinition.from_dict(name, body) for name, body in raw.items()}


def load(path: Path) -> dict[str, SmartDefinition]:
    """Wczytuje definicje z pliku; bez pliku — jedna definicja startowa.

    Błędny plik zatrzymuje start serwera, tak samo jak przy osiach i profilach:
    parametry SMART decydują o sile dociskanej do materiału, więc praca na
    cicho podstawionych wartościach jest gorsza niż brak startu.
    """
    if not path.exists():
        return default_definitions()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SmartError(f"nie można odczytać pliku definicji SMART {path}: {exc}")
    return parse_definitions(raw)


def save(path: Path, definitions: dict[str, SmartDefinition]) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku."""
    payload = {"definitions": {n: d.to_dict() for n, d in definitions.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def to_dict(definitions: dict[str, SmartDefinition]) -> dict:
    return {name: d.to_dict() for name, d in definitions.items()}


def warnings(definitions: dict[str, SmartDefinition], machine_mode: str) -> list[str]:
    """Ostrzeżenia o tym, co jest poprawne, ale jeszcze nie działa naprawdę.

    Procedury nie ma dziś w mostku (etap 4 tematu K) — technolog, który
    zapisuje definicję z progiem siły 30%, musi wiedzieć, że na maszynie
    nic jej jeszcze nie pilnuje.
    """
    out: list[str] = []
    if definitions:
        out.append(
            "procedury SMART nie ma jeszcze w mostku — definicje da się zapisać, "
            "ale krok SMART wykona zwykły ruch bez kontroli siły "
            "(docs/funkcje-smart.md, etap 4)"
        )
    if machine_mode != "sim":
        out.append(
            "tryb sprzętowy: dopóki mostek nie zna komendy SMART, uruchomienie "
            "kroku SMART na maszynie zakończy się błędem sterownika"
        )
    return out
