"""ModbusDriver (temat L) — logika wysoko-poziomowa, bez prawdziwego portu."""

from __future__ import annotations

import pytest

from app import modbus_protocol as mp
from app.modbus_driver import ModbusDriver


def _driver_with_fake(responses):
    d = ModbusDriver("/dev/null", baud=9600)
    calls = []
    it = iter(responses)

    def fake_exchange(packet, settle=0.05):
        calls.append(packet)
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    d._exchange = fake_exchange
    d.calls = calls
    return d


def _framed(slave_id: int, function: int, data: bytes) -> bytes:
    body = bytes([slave_id, function]) + data
    return body + mp.crc16(body)


def test_read_analog_channels_uzywa_potwierdzonego_polecenia():
    values = [100, 200, 300, 400, 500, 600, 700, 800]
    payload = bytes([16]) + b"".join(v.to_bytes(2, "big") for v in values)
    d = _driver_with_fake([_framed(1, mp.FUNC_READ_INPUT_REGISTERS, payload)])

    result = d.read_analog_channels(1)

    assert result == values
    assert d.calls[0] == bytes.fromhex("01 04 00 00 00 08 F1 CC")


def test_read_holding_registers():
    payload = bytes([2, 0x00, 0x2A])
    d = _driver_with_fake([_framed(1, mp.FUNC_READ_HOLDING_REGISTERS, payload)])
    assert d.read_holding_registers(1, 0x1000, 1) == [42]


def test_read_coils():
    payload = bytes([1, 0b00000011])
    d = _driver_with_fake([_framed(1, mp.FUNC_READ_COILS, payload)])
    assert d.read_coils(1, 0, 8) == [True, True, False, False, False, False, False, False]


def test_read_discrete_inputs():
    payload = bytes([1, 0b00000001])
    d = _driver_with_fake([_framed(1, mp.FUNC_READ_DISCRETE_INPUTS, payload)])
    assert d.read_discrete_inputs(1, 0, 1) == [True]


def test_write_single_coil_buduje_poprawna_ramke():
    d = _driver_with_fake([_framed(1, mp.FUNC_WRITE_SINGLE_COIL, bytes.fromhex("00 00 FF 00"))])
    d.write_single_coil(1, 0, True)
    assert d.calls[0][2:6] == bytes.fromhex("00 00 FF 00")


def test_write_single_register():
    d = _driver_with_fake([_framed(1, mp.FUNC_WRITE_SINGLE_REGISTER, bytes.fromhex("40 00 00 02"))])
    d.write_single_register(1, mp.ADDR_DEVICE_ADDRESS, 2)
    assert d.calls[0][2:6] == bytes.fromhex("40 00 00 02")


def test_brak_odpowiedzi_rzuca_modbuserror():
    d = _driver_with_fake([mp.ModbusError("brak odpowiedzi (timeout)")])
    with pytest.raises(mp.ModbusError):
        d.read_analog_channels(1)


def test_context_manager_otwiera_i_zamyka(monkeypatch):
    opened = []
    closed = []
    monkeypatch.setattr(ModbusDriver, "open", lambda self: opened.append(True))
    monkeypatch.setattr(ModbusDriver, "close", lambda self: closed.append(True))
    with ModbusDriver("/dev/null") as d:
        assert isinstance(d, ModbusDriver)
    assert opened == [True]
    assert closed == [True]
