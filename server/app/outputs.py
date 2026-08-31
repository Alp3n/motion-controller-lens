"""Wyjścia cyfrowe maszyny — do czego służą i co się z nimi dzieje przy STOP.

SC4-Hub ma dwa wyjścia, `BRAKE_0` i `BRAKE_1`. Nominalnie są hamulcowe, ale
przy silnikach **bez hamulców** to zwykłe wyjścia 24 VDC / 500 mA i używamy ich
do funkcji maszyny: podajnik, wyrzutnik, lampka sygnalizacyjna, sygnał błędu.
Jedno z nich może być zajęte przez wrzeciono (`SPINDLE_OUTPUT` w
`bridge/machine.env`) — wtedy zostaje jedno.

Zgodnie z decyzją z tematu J przeznaczenie wyjścia definiuje się **w konfiguracji
maszyny**, a nie w programie technologa: program detalu (`.prg`) z tych wyjść nie
korzysta, steruje nimi wyłącznie krok `WYJSCIE` cyklu maszyny.

## Ograniczenia, których ta konfiguracja nie zdejmuje

- **Obciążalność 500 mA / 24 VDC na wyjście** (instrukcja ClearPath-SC rev. 1.45,
  str. 47). Stycznika nie wolno podłączać bezpośrednio — tylko przez przekaźnik
  pośredniczący.
- **Wyjścia SC4-HUB wymagają osobnego zasilania 24 V** doprowadzonego do płytki.
  Bez niego komendy przechodzą, a fizycznie nic się nie przełącza.
- **To nie jest obwód bezpieczeństwa.** Producent ostrzega, że system operacyjny
  może przypadkowo załączyć wyjście, gdy aplikacja nie trzyma portu — u nas ten
  scenariusz realnie występuje przy ponownej enumeracji USB (ryzyko A
  w `docs/mozliwosci-clearpath-sc.md`). Wszystko, co może zranić przy
  przypadkowym załączeniu, musi iść **szeregowo przez styk obwodu osłon**.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .cycle import OUTPUT_NAMES

# Przeznaczenia z decyzji tematu J. "inne" zostaje celowo: lista ma nie blokować
# zastosowania, którego jeszcze nie przewidzieliśmy.
PURPOSE_NONE = "nieuzywane"
PURPOSES = (
    PURPOSE_NONE,
    "podajnik",
    "wyrzutnik",
    "docisk",
    "lampka",
    "blad",
    "inne",
)

# Przeznaczenia, przy których zgaszenie wyjścia po STOP jest sensowne domyślnie.
# Docisk i podajnik celowo NIE są na tej liście: zdjęcie docisku przy STOP
# potrafi upuścić detal, a to gorsze niż zostawienie wyjścia załączonego.
DEFAULT_OFF_ON_STOP = {"wyrzutnik"}


class OutputConfigError(Exception):
    """Błąd konfiguracji wyjść — komunikat po polsku dla operatora."""


def _flag(value, what: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "tak"):
        return True
    if text in ("0", "false", "nie"):
        return False
    raise OutputConfigError(f"{what}: oczekiwano tak/nie, jest '{value}'")


@dataclass
class OutputConfig:
    label: str = ""              # etykieta na ekranie, np. „podajnik detali"
    purpose: str = PURPOSE_NONE  # z listy PURPOSES
    off_on_stop: bool = False    # gasić przy STOP, błędzie i końcu cyklu

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "purpose": self.purpose,
            "off_on_stop": self.off_on_stop,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> OutputConfig:
        if not isinstance(data, dict):
            raise OutputConfigError(f"{name}: oczekiwano obiektu z parametrami wyjścia")
        purpose = str(data.get("purpose", PURPOSE_NONE)).strip().lower()
        if purpose not in PURPOSES:
            raise OutputConfigError(
                f"{name}: nieznane przeznaczenie '{purpose}' — dozwolone: "
                + ", ".join(PURPOSES)
            )
        cfg = cls(
            label=str(data.get("label", "")).strip(),
            purpose=purpose,
            off_on_stop=(
                _flag(data["off_on_stop"], f"{name}: gaszenie przy STOP")
                if "off_on_stop" in data
                else purpose in DEFAULT_OFF_ON_STOP
            ),
        )
        return cfg

    def display(self, name: str) -> str:
        """Nazwa dla operatora: etykieta, przeznaczenie albo nazwa techniczna."""
        return self.label or (self.purpose if self.purpose != PURPOSE_NONE else name)


def default_outputs() -> dict[str, OutputConfig]:
    return {name: OutputConfig() for name in OUTPUT_NAMES}


def parse_outputs(data) -> dict[str, OutputConfig]:
    if isinstance(data, dict) and "outputs" in data:
        data = data["outputs"]
    if not isinstance(data, dict):
        raise OutputConfigError("oczekiwano obiektu z wyjściami")
    unknown = sorted(set(data) - set(OUTPUT_NAMES))
    if unknown:
        raise OutputConfigError(
            "nieznane wyjścia: " + ", ".join(unknown) + " — maszyna ma tylko "
            + ", ".join(OUTPUT_NAMES)
        )
    result = default_outputs()
    for name, fields in data.items():
        result[name] = OutputConfig.from_dict(name, fields)
    return result


def load(path: Path) -> dict[str, OutputConfig]:
    """Wczytuje konfigurację; bez pliku — wyjścia nieużywane, bez etykiet.

    Błędny plik zatrzymuje serwer, jak reszta konfiguracji: wyjście opisane
    jako „lampka", a podłączone do podajnika, to gorsze niż brak startu.
    """
    if not path.exists():
        return default_outputs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OutputConfigError(f"nie można odczytać pliku konfiguracji wyjść {path}: {exc}")
    return parse_outputs(raw)


def save(path: Path, outputs: dict[str, OutputConfig]) -> None:
    """Zapis atomowy — jak przy osiach, profilach i cyklu."""
    payload = {"outputs": {name: cfg.to_dict() for name, cfg in outputs.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def to_dict(outputs: dict[str, OutputConfig]) -> dict:
    return {name: cfg.to_dict() for name, cfg in outputs.items()}


def spindle_output_name(spindle_output: str | None) -> str | None:
    """Nazwa logiczna wyjścia zajętego przez wrzeciono (`SPINDLE_OUTPUT`)."""
    mapping = {"brake0": "wyjscie_0", "brake1": "wyjscie_1"}
    if not spindle_output:
        return None
    return mapping.get(spindle_output.strip().lower())


def warnings(
    outputs: dict[str, OutputConfig],
    cycle_uses: set[str],
    hardware: bool,
    spindle_output: str | None,
) -> list[str]:
    """Ostrzeżenia o konfiguracji, która jest poprawna, ale nie robi tego, co widać.

    `cycle_uses` to nazwy wyjść, którymi faktycznie steruje zdefiniowany cykl —
    stąd wiadomo, czy opis wyjścia zgadza się z tym, co maszyna z nim robi.
    """
    result: list[str] = []
    taken = spindle_output_name(spindle_output)

    if taken and taken in cycle_uses:
        result.append(
            f"cykl steruje wyjściem {taken}, a mostek ma je przypisane do wrzeciona "
            f"(SPINDLE_OUTPUT={spindle_output}) — sterownik odrzuci taki krok; "
            "użyj drugiego wyjścia albo przestaw SPINDLE_OUTPUT"
        )

    for name in cycle_uses:
        cfg = outputs.get(name)
        if cfg is not None and cfg.purpose == PURPOSE_NONE:
            result.append(
                f"cykl steruje wyjściem {name}, które jest opisane jako nieużywane "
                "— ustaw jego przeznaczenie, żeby było wiadomo, co się załącza"
            )

    for name, cfg in outputs.items():
        if cfg.purpose != PURPOSE_NONE and name not in cycle_uses and name != taken:
            result.append(
                f"wyjście {name} ma przeznaczenie „{cfg.display(name)}”, ale żaden "
                "krok cyklu nim nie steruje — nic go nie załączy"
            )

    if hardware:
        result.append(
            "wyjścia SC4-HUB wymagają osobnego zasilania 24 V doprowadzonego do "
            "płytki huba — bez niego komendy przechodzą, a fizycznie nic się nie "
            "przełącza"
        )
        result.append(
            "obciążalność wyjścia: 500 mA / 24 VDC — stycznik tylko przez "
            "przekaźnik pośredniczący, nigdy bezpośrednio"
        )
        if any(cfg.purpose != PURPOSE_NONE for cfg in outputs.values()):
            result.append(
                "to nie jest obwód bezpieczeństwa: system może przypadkowo załączyć "
                "wyjście przy ponownej enumeracji USB — wszystko, co może zranić, "
                "musi iść szeregowo przez styk obwodu osłon"
            )
    return result
