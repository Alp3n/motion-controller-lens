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
import re
from dataclasses import dataclass
from pathlib import Path

# Osie wymagane zawsze — geometria cięcia (.prg) jest zdefiniowana w X/Y/Z
# i bez nich maszyna nie działa. Konfiguracja może zawierać dodatkowe osie
# ponad te trzy (np. podajnik, docisk) — patrz docs/model-cyklu-maszyny.md.
REQUIRED_AXES = ("x", "y", "z")

_AXIS_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

HOME_MINUS = "minus"
HOME_PLUS = "plus"
HOME_CENTER = "srodek"
HOME_POINTS = (HOME_MINUS, HOME_PLUS, HOME_CENTER)

# Sposób bazowania osi (ekran /homing).
#   hardstop  — dojazd do mechanicznego ogranicznika z limitem momentu, czyli
#               wbudowana funkcja bazowania serwa ClearPath-SC. Same parametry
#               (Homing Torque Limit, Offset Move) ustawia się WYŁĄCZNIE
#               w ClearView — serwer ich nie wysyła, trzyma je jako zapis tego,
#               co ma być w serwie.
#   programowe — brak fizycznego bazowania: bieżąca pozycja staje się zerem.
#               To jest dzisiejsze zachowanie symulatora i osi bez ogranicznika.
HOME_MODE_HARDSTOP = "hardstop"
HOME_MODE_SOFT = "programowe"
HOME_MODES = (HOME_MODE_HARDSTOP, HOME_MODE_SOFT)

# tolerancja porównań [mm] — chroni przed odrzuceniem limitu równego granicy
# zakresu tylko dlatego, że 300/2 zapisało się jako 149.99999999999997
EPS = 1e-6

# wartości startowe dla plików sprzed etapu prędkości JOG/bazowania — te same
# liczby, które wcześniej były wpisane na sztywno w main.py i machine.py
DEFAULT_VEL_JOG = 500.0     # mm/min
DEFAULT_VEL_HOME = 1000.0   # mm/min

# Kolejność bazowania dla plików sprzed ekranu /homing — odtwarza sekwencję,
# którą symulator wykonywał wcześniej na sztywno: najpierw X i Y na wysokości
# bezpiecznej, dopiero potem Z w dół. Osie dodatkowe (podajnik, docisk) domyślnie
# nie są bazowane — symulator i mostek i tak nimi nie ruszają.
DEFAULT_HOME_ORDER = {"x": 1, "y": 1, "z": 2}
DEFAULT_HOME_TORQUE = 20.0  # % momentu — tyle, ile domyślna siła globalna


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
    vel_jog: float = DEFAULT_VEL_JOG    # prędkość ruchu ręcznego (JOG) [mm/min]
    vel_home: float = DEFAULT_VEL_HOME  # prędkość bazowania [mm/min] — tylko symulator,
                                         # na sprzęcie bazowaniem steruje ClearView
    # --- bazowanie (ekran /homing) ---
    home_order: int = 1                 # kolejność bazowania; 0 = oś nie jest bazowana
    home_mode: str = HOME_MODE_SOFT     # hardstop | programowe
    home_torque: float = DEFAULT_HOME_TORQUE  # Homing Torque Limit [%] — zapis dla ClearView
    home_offset: float = 0.0            # Offset Move [mm] — zapis dla ClearView

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
            "vel_jog": round(self.vel_jog, 4),
            "vel_home": round(self.vel_home, 4),
            "home_order": int(self.home_order),
            "home_mode": self.home_mode,
            "home_torque": round(self.home_torque, 3),
            "home_offset": round(self.home_offset, 4),
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
            # opcjonalne — pliki sprzed tego pola dostają dawną stałą wartość,
            # zamiast odmawiać startu serwera z powodu brakującego pola
            vel_jog=(
                _num(data["vel_jog"], f"{label}: prędkość JOG")
                if "vel_jog" in data
                else DEFAULT_VEL_JOG
            ),
            vel_home=(
                _num(data["vel_home"], f"{label}: prędkość bazowania")
                if "vel_home" in data
                else DEFAULT_VEL_HOME
            ),
            # pola bazowania — jak wyżej, plik sprzed ekranu /homing dostaje
            # wartości odtwarzające dotychczasową sekwencję zamiast błędu
            home_order=(
                int(_num(data["home_order"], f"{label}: kolejność bazowania"))
                if "home_order" in data
                else DEFAULT_HOME_ORDER.get(axis, 0)
            ),
            home_mode=(
                str(data["home_mode"]).strip().lower()
                if "home_mode" in data
                else HOME_MODE_SOFT
            ),
            home_torque=(
                _num(data["home_torque"], f"{label}: limit momentu przy bazowaniu")
                if "home_torque" in data
                else DEFAULT_HOME_TORQUE
            ),
            home_offset=(
                _num(data["home_offset"], f"{label}: offset po bazowaniu")
                if "home_offset" in data
                else 0.0
            ),
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
        if self.vel_jog <= 0:
            raise AxisConfigError(f"{label}: prędkość JOG musi być większa od zera")
        if self.vel_home <= 0:
            raise AxisConfigError(f"{label}: prędkość bazowania musi być większa od zera")
        if self.home_order < 0:
            raise AxisConfigError(
                f"{label}: kolejność bazowania nie może być ujemna (0 = oś nie jest bazowana)"
            )
        if self.home_mode not in HOME_MODES:
            raise AxisConfigError(
                f"{label}: nieznany tryb bazowania '{self.home_mode}' — dozwolone: "
                + ", ".join(HOME_MODES)
            )
        if not (0.0 < self.home_torque <= 100.0):
            raise AxisConfigError(
                f"{label}: limit momentu przy bazowaniu musi być w zakresie (0, 100] %"
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
    for axis in REQUIRED_AXES:
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
            home_order=DEFAULT_HOME_ORDER.get(axis, 0),
        )
        axes[axis].validate(axis)
    return axes


# --- plik konfiguracyjny ---------------------------------------------------


def parse_axes(data: dict) -> dict[str, AxisConfig]:
    """Słownik {oś: parametry} -> konfiguracja; rzuca AxisConfigError.

    Wymaga co najmniej osi z `REQUIRED_AXES` (X, Y, Z) — reszta kluczy w
    `data` to osie dodatkowe (np. podajnik, docisk) i zostaje zachowana.
    """
    if not isinstance(data, dict):
        raise AxisConfigError("oczekiwano obiektu z osiami X, Y, Z")
    missing = [a for a in REQUIRED_AXES if a not in data]
    if missing:
        raise AxisConfigError(
            "brak konfiguracji osi: " + ", ".join(a.upper() for a in missing)
        )
    for axis in data:
        if not _AXIS_NAME_RE.match(axis):
            raise AxisConfigError(
                f"nieprawidłowa nazwa osi '{axis}' — małe litery, cyfry, "
                "podkreślenie, zaczynając od litery"
            )
    return {axis: AxisConfig.from_dict(axis, data[axis]) for axis in data}


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
    payload = {"axes": {name: cfg.to_dict() for name, cfg in axes.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def work_area(axes: dict[str, AxisConfig]) -> dict:
    """Obszar roboczy do walidacji programów — z limitów programowych.

    Tylko X/Y/Z: to jest zakres cięcia dla plików `.prg`, nie dotyczy osi
    dodatkowych (podajnik, docisk).
    """
    area = {}
    for axis in REQUIRED_AXES:
        area[f"{axis}_min"] = axes[axis].soft_min
        area[f"{axis}_max"] = axes[axis].soft_max
    return area


def to_dict(axes: dict[str, AxisConfig]) -> dict:
    return {name: cfg.to_dict() for name, cfg in axes.items()}


# --- bazowanie -------------------------------------------------------------


HOMING_FIELDS = ("home_order", "home_mode", "home_torque", "home_offset", "vel_home")

# Pola opcjonalne w pliku konfiguracji: brak któregoś oznacza wartość domyślną.
# Dla zapisu z ekranu to za mało — ekran, który danego pola nie edytuje, wcale
# go nie przysyła, a wtedy „domyślna" skasowałaby ustawienie z innego ekranu.
OPTIONAL_FIELDS = ("vel_jog",) + HOMING_FIELDS


def with_current_values(data: dict, current: dict[str, AxisConfig]) -> dict:
    """Uzupełnia brakujące pola opcjonalne wartościami z obecnej konfiguracji.

    Ekran konfiguracji osi nie edytuje parametrów bazowania (i odwrotnie).
    Bez tego zapis z jednego ekranu po cichu resetowałby ustawienia z drugiego —
    dokładnie ten błąd zdarzył się już przy prędkościach JOG/bazowania, patrz
    `docs/zmiany/predkosci-jog-bazowanie.md`.
    """
    if not isinstance(data, dict):
        return data
    merged = {}
    for name, fields in data.items():
        if not isinstance(fields, dict) or name not in current:
            merged[name] = fields
            continue
        known = current[name].to_dict()
        filled = dict(fields)
        for key in OPTIONAL_FIELDS:
            filled.setdefault(key, known[key])
        merged[name] = filled
    return merged


def home_groups(axes: dict[str, AxisConfig]) -> list[list[str]]:
    """Osie do zbazowania, pogrupowane po `home_order` i uszeregowane rosnąco.

    Osie z tym samym numerem bazują się razem (jednym ruchem), grupy —
    jedna po drugiej. `home_order == 0` znaczy „nie bazuj tej osi".
    """
    groups: dict[int, list[str]] = {}
    for name, cfg in axes.items():
        if cfg.home_order > 0:
            groups.setdefault(cfg.home_order, []).append(name)
    return [sorted(groups[order]) for order in sorted(groups)]


def merge_homing(axes: dict[str, AxisConfig], data: dict) -> dict[str, AxisConfig]:
    """Nakłada pola bazowania z ekranu /homing na istniejącą konfigurację osi.

    Ekran bazowania nie zna długości, limitów ani przełożeń — gdyby wysyłał
    całą konfigurację, pomyłka w nim mogłaby skasować limity programowe.
    Dlatego przyjmuje wyłącznie `HOMING_FIELDS`, a reszta zostaje nietknięta.
    """
    if not isinstance(data, dict):
        raise AxisConfigError("oczekiwano obiektu z osiami")
    unknown = [name for name in data if name not in axes]
    if unknown:
        raise AxisConfigError(
            "nieznane osie: "
            + ", ".join(a.upper() for a in sorted(unknown))
            + " — dodaj je najpierw na ekranie konfiguracji osi"
        )
    merged = {}
    for name, cfg in axes.items():
        fields = data.get(name)
        if fields is None:
            merged[name] = cfg
            continue
        if not isinstance(fields, dict):
            raise AxisConfigError(f"oś {name.upper()}: oczekiwano obiektu z parametrami")
        payload = cfg.to_dict()
        for key in HOMING_FIELDS:
            if key in fields:
                payload[key] = fields[key]
        merged[name] = AxisConfig.from_dict(name, payload)
    return merged


def homing_warnings(axes: dict[str, AxisConfig], hardware: bool) -> list[str]:
    """Ostrzeżenia o konfiguracji bazowania, która jest poprawna, ale myli.

    Główne z nich: parametry trybu HardStop żyją w serwie (ClearView), a nie
    w tym pliku — serwer ich nigdzie nie wysyła.
    """
    result: list[str] = []
    groups = home_groups(axes)
    if not groups:
        result.append(
            "żadna oś nie ma ustawionej kolejności bazowania — przycisk "
            "„BAZUJ wszystkie osie” nie ruszy niczym"
        )
    not_homed = sorted(
        name for name in REQUIRED_AXES if axes.get(name) and axes[name].home_order == 0
    )
    if not_homed:
        result.append(
            "osie "
            + ", ".join(a.upper() for a in not_homed)
            + " nie są bazowane (kolejność 0), a geometria programów jest w nich "
            "zdefiniowana — po starcie maszyny ich zero będzie przypadkowe"
        )
    hardstop = sorted(
        name for name, cfg in axes.items() if cfg.home_mode == HOME_MODE_HARDSTOP
    )
    if hardstop:
        result.append(
            "tryb HardStop dla osi "
            + ", ".join(a.upper() for a in hardstop)
            + ": limit momentu i offset z tego ekranu to ZAPIS tego, co ma być "
            "ustawione w ClearView — serwer ich nigdzie nie wysyła i sam ich "
            "nie egzekwuje"
        )
    extra = sorted(
        name
        for name, cfg in axes.items()
        if cfg.home_order > 0 and name not in REQUIRED_AXES
    )
    if extra:
        result.append(
            "osie "
            + ", ".join(a.upper() for a in extra)
            + " mają ustawioną kolejność bazowania, ale nie pojadą — symulator "
            "i mostek obsługują ruch tylko dla X/Y/Z (temat C planu rozwoju)"
        )
    if hardware:
        result.append(
            "na sprzęcie bazowanie wykonuje komenda HOME mostka wg ustawień serwa — "
            "kolejność, prędkość i offset z tego ekranu działają dziś tylko "
            "w symulatorze"
        )
    return result
