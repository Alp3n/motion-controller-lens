"""Lampy sygnalizacyjne I/O Modbus sterowane automatycznie wg stanu
maszyny (zamówienie 2026-09-12: "LR ma się włączać adekwatnie do swojej
roli" — czerwona = ALARM). Bez prawdziwego portu, ModbusDriver
podstawiony fake'iem (jak test_io_modbus_cycle.py)."""

from __future__ import annotations

import asyncio
import os

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import io_modbus  # noqa: E402
from app import main  # noqa: E402
from app.machine import MachineState  # noqa: E402
from app.modbus_protocol import ModbusError  # noqa: E402


class _FakeModbusDriver:
    def __init__(self, calls, raises=None):
        self.calls = calls
        self.raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def write_digital_output(self, slave_id, channel, on):
        if self.raises:
            raise self.raises
        self.calls.append((slave_id, channel, on))


def _with_io_cfg(cfg, fn):
    original = main.io_modbus_cfg
    main.io_modbus_cfg = cfg
    try:
        fn()
    finally:
        main.io_modbus_cfg = original


def _with_state(state, fn):
    original = main.machine.status.state
    main.machine.status.state = state
    try:
        fn()
    finally:
        main.machine.status.state = original


# --- _signal_lamp_targets (czysta funkcja) ---------------------------------


def test_lr_wlaczona_w_alarmie():
    assert main._signal_lamp_targets(MachineState.ALARM)["LR"] is True


def test_lr_wylaczona_poza_alarmem():
    for state in (MachineState.READY, MachineState.RUNNING, MachineState.PAUSED):
        assert main._signal_lamp_targets(state)["LR"] is False


def test_lg_wlaczona_gdy_gotowa():
    """Dopełnienie zamówienia 2026-09-12: "zielona lampa powinna włączyć
    się, jeśli maszyna jest gotowa"."""
    assert main._signal_lamp_targets(MachineState.READY)["LG"] is True


def test_lg_wylaczona_poza_gotowa():
    for state in (MachineState.ALARM, MachineState.RUNNING, MachineState.PAUSED, MachineState.HOMING):
        assert main._signal_lamp_targets(state)["LG"] is False


def test_lr_i_lg_nigdy_jednoczesnie():
    """Stany ALARM i READY się wykluczają — obie lampy nigdy nie powinny
    wypadać 'włączone' dla tego samego stanu."""
    for state in MachineState:
        targets = main._signal_lamp_targets(state)
        assert not (targets["LR"] and targets["LG"])


# --- _apply_signal_lamps ----------------------------------------------------


def test_apply_zapala_lr_w_alarmie(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    # LR (etykieta domyślna do1) odczytana jako zgaszona — niezgodna z ALARM;
    # LG (do0) już zgaszona — zgodna ze stanem ALARM (LG tylko w READY), bez
    # zapisu, żeby test skupiał się wyłącznie na LR
    result = {
        "do": {
            "do0": {"label": "LG", "value": False},
            "do1": {"label": "LR", "value": False},
        }
    }

    def run():
        _with_state(MachineState.ALARM, lambda: asyncio.run(main._apply_signal_lamps(result)))

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == [(io_modbus.DIGITAL_MODULE_ADDRESS, 1, True)]


def test_apply_gasi_lr_poza_alarmem(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    # stan READY: LG już zapalona (zgodna), LR zapalona (niezgodna, ma zgasnąć)
    result = {
        "do": {
            "do0": {"label": "LG", "value": True},
            "do1": {"label": "LR", "value": True},
        }
    }

    def run():
        _with_state(MachineState.READY, lambda: asyncio.run(main._apply_signal_lamps(result)))

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == [(io_modbus.DIGITAL_MODULE_ADDRESS, 1, False)]


def test_apply_zapala_lg_gdy_gotowa(monkeypatch):
    """Dopełnienie zamówienia 2026-09-12: zielona lampa przy READY."""
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    result = {
        "do": {
            "do0": {"label": "LG", "value": False},
            "do1": {"label": "LR", "value": False},
        }
    }

    def run():
        _with_state(MachineState.READY, lambda: asyncio.run(main._apply_signal_lamps(result)))

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == [(io_modbus.DIGITAL_MODULE_ADDRESS, 0, True)]


def test_apply_nic_nie_pisze_gdy_juz_zgadza_sie_z_odczytem(monkeypatch):
    """Samonaprawiający się mechanizm (patrz docstring main._apply_signal_
    lamps) nie generuje zbędnych zapisów, gdy odczytana wartość już
    zgadza się z tym, co powinna być."""
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    result = {
        "do": {
            "do0": {"label": "LG", "value": False},
            "do1": {"label": "LR", "value": True},
        }
    }

    def run():
        _with_state(MachineState.ALARM, lambda: asyncio.run(main._apply_signal_lamps(result)))

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == []


def test_apply_pomija_nieskonfigurowane_etykiety(monkeypatch):
    """Brak kanału z daną etykietą w konfiguracji nie jest błędem — po
    prostu nic się nie dzieje (lampa 'jeszcze nie podłączona/nazwana')."""
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    cfg = io_modbus.default_io()
    cfg.do["do0"].label = ""  # żadny kanał nie nosi etykiety "LG"
    cfg.do["do1"].label = ""  # żadny kanał nie nosi etykiety "LR"

    def run():
        _with_state(MachineState.ALARM, lambda: asyncio.run(main._apply_signal_lamps({"do": {}})))

    _with_io_cfg(cfg, run)

    assert calls == []


def test_apply_toleruje_blad_sprzetu(monkeypatch):
    monkeypatch.setattr(
        main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver([], raises=ModbusError("timeout"))
    )
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")
    result = {"do": {"do1": {"label": "LR", "value": False}}}

    def run():
        # nie rzuca — błąd sprzętu ma być po cichu spróbowany ponownie
        # przy następnym obiegu pętli, nie wywalać cały _io_modbus_poll_loop
        _with_state(MachineState.ALARM, lambda: asyncio.run(main._apply_signal_lamps(result)))

    _with_io_cfg(io_modbus.default_io(), run)
