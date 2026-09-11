"""Nazwane kanały I/O modułów Waveshare Modbus RTU (temat L).

Zgłoszenie użytkownika (2026-09-11): lampy sygnalizacyjne (LG/LR/LY),
osłona/drzwi, Start/Stop, sterowanie i pomiary wrzeciona, watchdog
impulsów drzwi współpracujący z wejściem osłony. Wzorem `app/outputs.py`
(BRAKE_0/BRAKE_1 SC4-Hub) — tylko więcej kanałów: 8 wyjść cyfrowych (DO),
8 wejść cyfrowych (DI), 8 wejść analogowych (AI), z dwóch modułów Waveshare
zamiast huba Teknica.

**Adresy modułów na TEJ maszynie** (ustalone fizycznie 2026-09-11): moduł
cyfrowy (SKU 26244) = adres 1 (fabryczny), moduł analogowy (SKU 25821) =
adres 2 (zmieniony z fabrycznego 1, żeby oba mogły współistnieć na jednej
magistrali — patrz `docs/zmiany/modbus-io-waveshare.md`).

**PRZYPISANIE KANAŁÓW DO NAZW W `default_io()` TO ZAŁOŻENIE, NIE
POTWIERDZONE OKABLOWANIE.** Kolejność 1:1 z listy zgłoszonej przez
użytkownika (LG→do0, LR→do1, ... ), żeby dało się zacząć pracę nad kodem
zamiast czekać, aż ktoś opisze każdy zacisk. **Do skorygowania w pliku
konfiguracyjnym**, jeśli nie zgadza się z rzeczywistym okablowaniem —
edycja pliku JSON, bez zmiany kodu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DIGITAL_MODULE_ADDRESS = 1
ANALOG_MODULE_ADDRESS = 2

DO_COUNT = 8
DI_COUNT = 8
AI_COUNT = 8


class IoConfigError(Exception):
    """Błąd konfiguracji I/O Modbus — komunikat po polsku dla operatora."""


@dataclass
class ChannelConfig:
    label: str = ""  # pusta etykieta = kanał nieużywany

    def to_dict(self) -> dict:
        return {"label": self.label}

    @classmethod
    def from_dict(cls, data: dict) -> ChannelConfig:
        if not isinstance(data, dict):
            raise IoConfigError("oczekiwano obiektu {label: ...}")
        return cls(label=str(data.get("label", "")).strip())


@dataclass
class WatchdogConfig:
    """Watchdog impulsów drzwi (`drzwi_impulsy`) współpracujący z wejściem
    osłony (`osłona_1`) — zgłoszenie: „co jakiś czas np. 1 sekunda i
    czytanie współpracuje z wejściem osłona_1 (zasada watchdog) z
    możliwością wyłączenia i włączenia w konfiguracji".

    UWAGA: to NIE jest certyfikowana funkcja bezpieczeństwa (jak żaden
    odczyt sygnału drzwi programowo w tym projekcie — patrz temat E,
    `docs/plan-rozwoju.md`). To diagnostyka: wykrywa, czy sygnał impulsowy
    w ogóle się zmienia (heartbeat), nie zastępuje sprzętowego Global Stop.
    """

    enabled: bool = False
    pulse_channel: str = "di4"   # nazwa kanału DI z impulsami drzwi
    guard_channel: str = "di0"   # nazwa kanału DI z osłoną
    interval_s: float = 1.0      # co ile sprawdzać
    stale_after_s: float = 3.0   # brak zmiany impulsu przez tyle = watchdog "martwy"

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "pulse_channel": self.pulse_channel,
            "guard_channel": self.guard_channel,
            "interval_s": self.interval_s,
            "stale_after_s": self.stale_after_s,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WatchdogConfig:
        if not isinstance(data, dict):
            raise IoConfigError("watchdog: oczekiwano obiektu")
        defaults = cls()
        return cls(
            enabled=bool(data.get("enabled", defaults.enabled)),
            pulse_channel=str(data.get("pulse_channel", defaults.pulse_channel)),
            guard_channel=str(data.get("guard_channel", defaults.guard_channel)),
            interval_s=float(data.get("interval_s", defaults.interval_s)),
            stale_after_s=float(data.get("stale_after_s", defaults.stale_after_s)),
        )


@dataclass
class IoConfig:
    do: dict[str, ChannelConfig] = field(default_factory=dict)
    di: dict[str, ChannelConfig] = field(default_factory=dict)
    ai: dict[str, ChannelConfig] = field(default_factory=dict)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)

    def to_dict(self) -> dict:
        return {
            "do": {k: v.to_dict() for k, v in self.do.items()},
            "di": {k: v.to_dict() for k, v in self.di.items()},
            "ai": {k: v.to_dict() for k, v in self.ai.items()},
            "watchdog": self.watchdog.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> IoConfig:
        if not isinstance(data, dict):
            raise IoConfigError("oczekiwano obiektu z konfiguracją I/O")

        def _group(key: str, count: int, prefix: str) -> dict[str, ChannelConfig]:
            raw = data.get(key, {})
            if not isinstance(raw, dict):
                raise IoConfigError(f"{key}: oczekiwano obiektu {{kanał: {{label}}}}")
            result = {f"{prefix}{i}": ChannelConfig() for i in range(count)}
            for name, fields in raw.items():
                if name not in result:
                    raise IoConfigError(
                        f"{key}: nieznany kanał '{name}' — dozwolone: "
                        + ", ".join(sorted(result))
                    )
                result[name] = ChannelConfig.from_dict(fields)
            return result

        return cls(
            do=_group("do", DO_COUNT, "do"),
            di=_group("di", DI_COUNT, "di"),
            ai=_group("ai", AI_COUNT, "ai"),
            watchdog=WatchdogConfig.from_dict(data.get("watchdog", {})),
        )

    def channel_by_label(self, group: dict[str, ChannelConfig], label: str) -> str | None:
        for name, cfg in group.items():
            if cfg.label == label:
                return name
        return None


def default_io() -> IoConfig:
    """Przypisanie z listy zgłoszonej 2026-09-11 — patrz zastrzeżenie w
    docstring modułu, DO SKORYGOWANIA po potwierdzeniu okablowania."""
    do_labels = [
        "LG", "LR", "LY", "wrzeciono_OUT", "wrzeciono_start", "wrzeciono-stop", "", "",
    ]
    di_labels = [
        "osłona_1", "drzwi_podajnika", "Start", "Stop", "drzwi_impulsy", "", "", "",
    ]
    ai_labels = [
        "temperatura_wrzeciona", "prąd_wrzeciona", "", "", "", "", "", "",
    ]
    return IoConfig(
        do={f"do{i}": ChannelConfig(label=lbl) for i, lbl in enumerate(do_labels)},
        di={f"di{i}": ChannelConfig(label=lbl) for i, lbl in enumerate(di_labels)},
        ai={f"ai{i}": ChannelConfig(label=lbl) for i, lbl in enumerate(ai_labels)},
        watchdog=WatchdogConfig(enabled=False, pulse_channel="di4", guard_channel="di0"),
    )


def load(path: Path) -> IoConfig:
    """Wczytuje konfigurację; bez pliku — przypisanie domyślne z
    `default_io()`. Błędny plik zatrzymuje start, jak reszta konfiguracji
    maszyny — błędnie opisany kanał (np. Start pomylony ze Stop) jest
    gorszy niż brak startu."""
    if not path.exists():
        return default_io()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IoConfigError(f"nie można odczytać pliku konfiguracji I/O {path}: {exc}")
    return IoConfig.from_dict(raw)


def save(path: Path, cfg: IoConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
