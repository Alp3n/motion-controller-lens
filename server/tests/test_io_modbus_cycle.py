"""main._cycle_output_names() / _io_modbus_cycle_write() — krok WYJSCIE
cyklu na kanale I/O Modbus (zamówienie 2026-09-12: "dodać nowe I/O do
wykorzystania w cyklu maszyny, zostaw dwa istniejące"). Bez prawdziwego
portu, ModbusDriver podstawiony fake'iem."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import io_modbus  # noqa: E402
from app import main  # noqa: E402
from app.machine import MachineError  # noqa: E402
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


def test_cycle_output_names_laczy_teknic_i_modbus():
    cfg = io_modbus.default_io()
    names = main._cycle_output_names()
    assert {"wyjscie_0", "wyjscie_1"} <= names
    assert "do0" in names
    assert "LG" in names  # etykieta domyślna kanału do0, patrz default_io()


def test_resolve_io_modbus_channel_po_nazwie_i_etykiecie():
    cfg = io_modbus.default_io()

    def run():
        assert main._resolve_io_modbus_channel("do0") == "do0"
        assert main._resolve_io_modbus_channel("LG") == "do0"
        with pytest.raises(KeyError):
            main._resolve_io_modbus_channel("nieistniejace")

    _with_io_cfg(cfg, run)


def test_cycle_write_po_nazwie_kanalu(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._io_modbus_cycle_write("do3", True))

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == [(io_modbus.DIGITAL_MODULE_ADDRESS, 3, True)]


def test_cycle_write_po_etykiecie(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls))
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._io_modbus_cycle_write("LG", True))  # etykieta do0

    _with_io_cfg(io_modbus.default_io(), run)

    assert calls == [(io_modbus.DIGITAL_MODULE_ADDRESS, 0, True)]


def test_cycle_write_nieznany_kanal_rzuca_machineerror(monkeypatch):
    def run():
        with pytest.raises(MachineError, match="nieznany kanał"):
            asyncio.run(main._io_modbus_cycle_write("nieistniejace", True))

    _with_io_cfg(io_modbus.default_io(), run)


def test_cycle_write_bez_portu_rzuca_machineerror(monkeypatch):
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", None)

    def run():
        with pytest.raises(MachineError, match="MODBUS_IO_PORT"):
            asyncio.run(main._io_modbus_cycle_write("do3", True))

    _with_io_cfg(io_modbus.default_io(), run)


def test_cycle_write_blad_sprzetu_rzuca_machineerror(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main, "ModbusDriver", lambda *a, **k: _FakeModbusDriver(calls, raises=ModbusError("timeout"))
    )
    monkeypatch.setattr(main.config, "MODBUS_IO_PORT", "/dev/ttyUSB0")

    def run():
        with pytest.raises(MachineError, match="timeout"):
            asyncio.run(main._io_modbus_cycle_write("do3", True))

    _with_io_cfg(io_modbus.default_io(), run)
