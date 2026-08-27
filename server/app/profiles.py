"""Profile parametrów ruchu — nazwane zestawy prędkości, ramp i limitu momentu.

Te same osie fizyczne pracują z różnymi parametrami zależnie od kontekstu:
inaczej w cyklu maszyny (poziom admina), inaczej w programie technologa.
Profil jest nazwanym zestawem tych parametrów — przełączenie profilu zmienia
zachowanie osi bez ruszania konfiguracji samych osi (`axes.py`).

Trzy profile powstają domyślnie, z wartościami ustalonymi w
`zbyszek/NOTATKI_FUNKCJONALNE.md` §2:

    globalny  — 20% momentu, wartość wyjściowa maszyny
    cykl      — 15% momentu, ruchy cyklu maszyny
    program   — 10% momentu, ruchy programu technologa

Model zapisu jest celowo taki sam jak w `axes.py`: dataclass + `to_dict`/
`from_dict`, plik JSON, zapis atomowy, komunikaty błędów po polsku.

OGRANICZENIE, które trzeba znać: limit momentu **nie jest dziś wysyłany do
sprzętu** — protokół mostka (`bridge/sc4hub_bridge.cpp`) nie ma komendy
momentu. Patrz `docs/zmiany/profile-parametrow-etap2.md`.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

# nazwy profili zakładanych domyślnie i ich limity momentu [%]
PROFILE_GLOBAL = "globalny"
PROFILE_CYCLE = "cykl"
PROFILE_PROGRAM = "program"

DEFAULT_TORQUE_PCT = {
    PROFILE_GLOBAL: 20.0,
    PROFILE_CYCLE: 15.0,
    PROFILE_PROGRAM: 10.0,
}

# wartości startowe ruchu, gdy nie ma jeszcze pliku profili
DEFAULT_VEL_MAX = 3000.0    # mm/min
DEFAULT_ACCEL = 500.0       # mm/s²

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

EPS = 1e-9


class ProfileError(Exception):
    """Błąd konfiguracji profilu — komunikat po polsku dla operatora."""


def _num(value, what: str) -> float:
    """Liczba z JSON-a albo z formularza (dopuszczamy przecinek dziesiętny)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise ProfileError(f"{what}: oczekiwano liczby, jest '{value}'")
    value = float(value)
    if not math.isfinite(value):
        raise ProfileError(f"{what}: liczba musi być skończona")
    return value


@dataclass
class AxisParams:
    """Parametry ruchu jednej osi w ramach jednego profilu."""

    vel_max: float      # prędkość maksymalna [mm/min]
    accel: float        # przyspieszenie [mm/s²]
    decel: float        # hamowanie [mm/s²]
    torque_pct: float   # limit momentu [% maksymalnego momentu silnika]

    def to_dict(self) -> dict:
        return {
            "vel_max": round(self.vel_max, 4),
            "accel": round(self.accel, 4),
            "decel": round(self.decel, 4),
            "torque_pct": round(self.torque_pct, 3),
        }

    @classmethod
    def from_dict(cls, profile: str, axis: str, data: dict) -> AxisParams:
        label = f"profil '{profile}', oś {axis.upper()}"
        if not isinstance(data, dict):
            raise ProfileError(f"{label}: oczekiwano obiektu z parametrami")
        missing = [
            key for key in ("vel_max", "accel", "decel", "torque_pct") if key not in data
        ]
        if missing:
            raise ProfileError(f"{label}: brak pól: " + ", ".join(missing))
        params = cls(
            vel_max=_num(data["vel_max"], f"{label}: prędkość maksymalna"),
            accel=_num(data["accel"], f"{label}: przyspieszenie"),
            decel=_num(data["decel"], f"{label}: hamowanie"),
            torque_pct=_num(data["torque_pct"], f"{label}: limit momentu"),
        )
        params.validate(profile, axis)
        return params

    def validate(self, profile: str, axis: str) -> None:
        label = f"profil '{profile}', oś {axis.upper()}"
        if self.vel_max <= 0:
            raise ProfileError(f"{label}: prędkość maksymalna musi być większa od zera")
        if self.accel <= 0:
            raise ProfileError(f"{label}: przyspieszenie musi być większe od zera")
        if self.decel <= 0:
            raise ProfileError(f"{label}: hamowanie musi być większe od zera")
        # 0% zablokowałoby ruch całkowicie — to nie jest „bezpieczniej", tylko
        # maszyna, która nie rusza i nie mówi dlaczego
        if not (0 < self.torque_pct <= 100):
            raise ProfileError(
                f"{label}: limit momentu musi mieścić się w przedziale (0, 100] %, "
                f"jest {self.torque_pct:g}"
            )


@dataclass
class ParameterProfile:
    """Nazwany zestaw parametrów ruchu — po jednym komplecie na oś."""

    name: str
    axes: dict[str, AxisParams]

    def to_dict(self) -> dict:
        return {"axes": {axis: p.to_dict() for axis, p in self.axes.items()}}

    @classmethod
    def from_dict(cls, name: str, data: dict) -> ParameterProfile:
        if not _NAME_RE.match(name):
            raise ProfileError(
                f"nieprawidłowa nazwa profilu '{name}' — małe litery, cyfry, "
                "podkreślenie, zaczynając od litery"
            )
        if not isinstance(data, dict):
            raise ProfileError(f"profil '{name}': oczekiwano obiektu z osiami")
        axes_raw = data.get("axes", data)
        if not isinstance(axes_raw, dict) or not axes_raw:
            raise ProfileError(f"profil '{name}': brak parametrów osi")
        return cls(
            name=name,
            axes={
                axis: AxisParams.from_dict(name, axis, params)
                for axis, params in axes_raw.items()
            },
        )


# --- wartości startowe -----------------------------------------------------


def default_profiles(axis_names) -> dict[str, ParameterProfile]:
    """Trzy standardowe profile dla podanych osi — wartości z notatek §2."""
    axis_names = list(axis_names)
    if not axis_names:
        raise ProfileError("nie można utworzyć profili bez zdefiniowanych osi")
    profiles: dict[str, ParameterProfile] = {}
    for name, torque in DEFAULT_TORQUE_PCT.items():
        profiles[name] = ParameterProfile(
            name=name,
            axes={
                axis: AxisParams(
                    vel_max=DEFAULT_VEL_MAX,
                    accel=DEFAULT_ACCEL,
                    decel=DEFAULT_ACCEL,
                    torque_pct=torque,
                )
                for axis in axis_names
            },
        )
    return profiles


# --- plik konfiguracyjny ---------------------------------------------------


def parse_profiles(data: dict) -> tuple[dict[str, ParameterProfile], str]:
    """{'active': nazwa, 'profiles': {...}} -> (profile, aktywny).

    Zwraca też nazwę aktywnego profilu, bo to jest część tego samego stanu —
    profil aktywny musi istnieć wśród zdefiniowanych.
    """
    if not isinstance(data, dict):
        raise ProfileError("oczekiwano obiektu z profilami")
    raw = data.get("profiles")
    if not isinstance(raw, dict) or not raw:
        raise ProfileError("brak zdefiniowanych profili")
    profiles = {name: ParameterProfile.from_dict(name, body) for name, body in raw.items()}

    active = data.get("active", PROFILE_GLOBAL)
    if active not in profiles:
        raise ProfileError(
            f"aktywny profil '{active}' nie istnieje — dostępne: "
            + ", ".join(sorted(profiles))
        )
    return profiles, active


def load(path: Path, axis_names) -> tuple[dict[str, ParameterProfile], str]:
    """Wczytuje profile z pliku; bez pliku — wartości startowe.

    Błędny plik zatrzymuje start serwera, tak samo jak przy konfiguracji osi:
    limit momentu jest parametrem ochronnym i praca na cicho podstawionym
    jest gorsza niż brak startu.
    """
    if not path.exists():
        return default_profiles(axis_names), PROFILE_GLOBAL
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProfileError(f"nie można odczytać pliku profili {path}: {exc}")
    return parse_profiles(raw)


def save(path: Path, profiles: dict[str, ParameterProfile], active: str) -> None:
    """Zapis atomowy — przerwany zapis nie zostawia obciętego pliku."""
    payload = {
        "active": active,
        "profiles": {name: p.to_dict() for name, p in profiles.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def to_dict(profiles: dict[str, ParameterProfile]) -> dict:
    return {name: p.to_dict() for name, p in profiles.items()}


def missing_axes(profiles: dict[str, ParameterProfile], axis_names) -> dict[str, list[str]]:
    """Osie skonfigurowane w maszynie, których dany profil nie opisuje.

    Nie jest to błąd — profil bez danej osi po prostu jej nie ogranicza —
    ale operator powinien to zobaczyć, zamiast się domyślać.
    """
    gaps: dict[str, list[str]] = {}
    for name, profile in profiles.items():
        absent = [axis for axis in axis_names if axis not in profile.axes]
        if absent:
            gaps[name] = absent
    return gaps
