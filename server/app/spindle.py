"""Konfiguracja wrzeciona — kiedy się załącza i kiedy gaśnie.

Ekran Start/Stop (panel operatora) i ekran cyklu maszyny zapisują te ustawienia
do pliku JSON (SPINDLE_CONFIG). Odpowiadają na dwa pytania z
`NOTATKI_FUNKCJONALNE.md` §4:

- czy wrzeciono ma ruszać razem z maszyną (przełącznik przy START/STOP),
- co robi wrzeciono na granicach programu technologa (dwie opcje w konfiguracji
  maszyny: załączenie na starcie programu i wyłączenie po jego zakończeniu).

**Czego tu nie ma i nie będzie bez dodatkowego sprzętu:** prędkości wrzeciona.
SC4-Hub ma tylko wyjścia dwustanowe `BRAKE_0`/`BRAKE_1` — nie ma wyjścia PWM
ani analogowego. Obroty generuje zewnętrzny regulator, a my możemy go wyłącznie
załączyć albo wyłączyć (decyzja: `docs/plan-rozwoju.md`, temat J). Pole
`default_rpm` jest więc **wartością informacyjną** — trafia do komendy
`SPINDLE` mostka, ale realnie nie zmienia obrotów.

**Ograniczenie, którego nie wolno konfigurować:** na zakończenie pracy maszyny
(koniec cyklu, błąd, STOP) wrzeciono gaśnie zawsze, niezależnie od tych
ustawień — to jest w `finally` warstwy maszyny, nie tutaj.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


class SpindleConfigError(Exception):
    """Błąd konfiguracji wrzeciona — komunikat po polsku dla operatora."""


DEFAULT_RPM = 12000.0


def _num(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip().replace(",", "."))
        except (TypeError, ValueError):
            raise SpindleConfigError(f"{what}: oczekiwano liczby, jest '{value}'")
    value = float(value)
    if not math.isfinite(value):
        raise SpindleConfigError(f"{what}: liczba musi być skończona")
    return value


def _flag(value, what: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "tak"):
        return True
    if text in ("0", "false", "nie"):
        return False
    raise SpindleConfigError(f"{what}: oczekiwano tak/nie, jest '{value}'")


@dataclass
class SpindleConfig:
    # przełącznik na ekranie Start/Stop: wrzeciono rusza razem z maszyną
    # (START programu albo cyklu) i chodzi przez całą pracę
    start_with_machine: bool = False
    # wrzeciono załącza się na starcie programu technologa — dzisiejsze
    # zachowanie warstwy maszyny, dlatego domyślnie włączone
    start_with_program: bool = True
    # wrzeciono gaśnie po zakończeniu programu technologa. Domyślnie NIE:
    # w cyklu maszyny program detalu jest tylko jednym z kroków i dotąd
    # wrzeciono chodziło do końca całego przebiegu. Włączenie tej opcji
    # oszczędza wrzeciono kosztem czasu rozpędzania przy każdym detalu.
    stop_after_program: bool = False
    # obroty wpisywane do komendy SPINDLE przy załączaniu poza programem
    # (start maszyny). Informacyjne — patrz docstring modułu.
    default_rpm: float = DEFAULT_RPM

    def to_dict(self) -> dict:
        return {
            "start_with_machine": self.start_with_machine,
            "start_with_program": self.start_with_program,
            "stop_after_program": self.stop_after_program,
            "default_rpm": round(self.default_rpm, 1),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SpindleConfig:
        if not isinstance(data, dict):
            raise SpindleConfigError("oczekiwano obiektu z ustawieniami wrzeciona")
        cfg = cls()
        if "start_with_machine" in data:
            cfg.start_with_machine = _flag(
                data["start_with_machine"], "wrzeciono przy starcie maszyny"
            )
        if "start_with_program" in data:
            cfg.start_with_program = _flag(
                data["start_with_program"], "wrzeciono przy starcie programu"
            )
        if "stop_after_program" in data:
            cfg.stop_after_program = _flag(
                data["stop_after_program"], "wyłączenie po zakończeniu programu"
            )
        if "default_rpm" in data:
            cfg.default_rpm = _num(data["default_rpm"], "obroty domyślne")
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.default_rpm < 0:
            raise SpindleConfigError("obroty domyślne nie mogą być ujemne")

    def merged(self, data: dict) -> SpindleConfig:
        """Nowa konfiguracja z nałożonymi polami z `data` (zapis częściowy).

        Ustawienia wrzeciona edytują dwa ekrany: panel operatora (przełącznik
        przy START/STOP) i ekran cyklu maszyny (granice programu). Żaden nie
        wysyła pól tego drugiego, więc zapis musi być scalaniem, nie podmianą.
        """
        if not isinstance(data, dict):
            raise SpindleConfigError("oczekiwano obiektu z ustawieniami wrzeciona")
        unknown = sorted(set(data) - set(self.to_dict()))
        if unknown:
            raise SpindleConfigError(
                "nieznane ustawienia wrzeciona: " + ", ".join(unknown)
            )
        return SpindleConfig.from_dict({**self.to_dict(), **data})


def load(path: Path) -> SpindleConfig:
    """Wczytuje konfigurację; bez pliku — wartości odtwarzające dawne zachowanie.

    Błędny plik zatrzymuje serwer zamiast po cichu podstawiać wartości domyślne —
    tak samo jak przy osiach i profilach: „wrzeciono rusza z maszyną" włączone
    przez pomyłkę to obracające się narzędzie, którego operator się nie spodziewa.
    """
    if not path.exists():
        return SpindleConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpindleConfigError(
            f"nie można odczytać pliku konfiguracji wrzeciona {path}: {exc}"
        )
    return SpindleConfig.from_dict(raw.get("spindle", raw))


def save(path: Path, cfg: SpindleConfig) -> None:
    """Zapis atomowy — jak przy osiach i profilach."""
    payload = {"spindle": cfg.to_dict()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def warnings(cfg: SpindleConfig, hardware: bool, spindle_output: str | None) -> list[str]:
    """Ostrzeżenia o ustawieniach, które są poprawne, ale nie robią tego, co widać."""
    result: list[str] = []
    if cfg.start_with_machine:
        result.append(
            "wrzeciono rusza razem z maszyną — narzędzie zacznie się obracać "
            "od razu po naciśnięciu START, jeszcze przed pierwszym ruchem"
        )
    if not cfg.start_with_program and not cfg.start_with_machine:
        result.append(
            "wrzeciono nie załącza się ani przy starcie maszyny, ani przy starcie "
            "programu — zostaje wyłącznie operacja WRZECIONO w programie technologa"
        )
    if hardware:
        result.append(
            "obroty (RPM) nie docierają do sprzętu — SC4-Hub ma tylko wyjście "
            "włącz/wyłącz, prędkość ustawia zewnętrzny regulator PWM (temat J)"
        )
        if spindle_output is None:
            result.append(
                "serwer nie zna ustawienia SPINDLE_OUTPUT mostka — sprawdź "
                "bridge/machine.env; przy wartości 'none' komendy wrzeciona nie "
                "przełączają żadnego wyjścia i nic się fizycznie nie dzieje"
            )
        elif spindle_output == "none":
            result.append(
                "mostek ma SPINDLE_OUTPUT=none — komendy wrzeciona nie przełączają "
                "żadnego wyjścia; ustaw brake0 albo brake1 w bridge/machine.env"
            )
    return result
