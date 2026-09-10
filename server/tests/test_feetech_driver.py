"""FeetekDriver (temat L) — logika wysoko-poziomowa, bez prawdziwego portu.

`_exchange` jest podmieniane na fake'a (jak `_command`/`_exchange` w
`test_sc4hub.py`) — testujemy budowanie żądań i parsowanie odpowiedzi,
nie prawdziwy termios."""

from __future__ import annotations

import pytest

from app import feetech_protocol as fp
from app.feetech_driver import FeetekDriver, FeetekError


def _driver_with_fake(responses):
    """`responses`: lista bajtów (albo wyjątków) zwracanych po kolei."""
    d = FeetekDriver("/dev/null", baud=115200)
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


def _ok_response(servo_id: int, data: bytes = b"") -> bytes:
    body = bytes([servo_id, len(data) + 2, 0]) + data
    return b"\xff\xff" + body + bytes([fp.checksum(body)])


def test_ping_zwraca_numer_modelu():
    d = _driver_with_fake([_ok_response(1, bytes([0x08, 0x2A]))])
    assert d.ping(1) == 0x2A08


def test_ping_bez_odpowiedzi_rzuca_feetekerror():
    d = _driver_with_fake([FeetekError("brak odpowiedzi z serwa (timeout)")])
    with pytest.raises(FeetekError):
        d.ping(1)


def test_read_position_dekoduje_signed16():
    d = _driver_with_fake([_ok_response(1, fp.encode_signed16(-123))])
    assert d.read_position(1) == -123


def test_read_status_zwraca_wszystkie_pola():
    responses = [
        _ok_response(2, fp.encode_signed16(100)),   # position
        _ok_response(2, fp.encode_signed16(-5)),    # speed
        _ok_response(2, fp.encode_signed16(0)),     # load
        _ok_response(2, bytes([231])),               # voltage
        _ok_response(2, bytes([27])),                 # temperature
    ]
    d = _driver_with_fake(responses)
    status = d.read_status(2)
    assert status == {
        "position": 100,
        "speed": -5,
        "load": 0,
        "voltage_x0_1v": 231,
        "temperature_c": 27,
    }


def test_write_raw_z_bledem_serwa_rzuca():
    body = bytes([1, 2, 32])  # bit 32 = przeciążenie (ERRBIT_OVERLOAD w SDK)
    packet = b"\xff\xff" + body + bytes([fp.checksum(body)])
    d = _driver_with_fake([packet])
    with pytest.raises(FeetekError, match="błąd"):
        d.write_raw(1, fp.ADDR_TORQUE_ENABLE, bytes([1]))


def test_move_to_wysyla_poprawna_ramke_z_acc_pozycja_speed():
    d = _driver_with_fake([_ok_response(1)])
    d.move_to(1, position=-200, speed=100, acc=20)

    packet = d.calls[0]
    servo_id, length, instruction = packet[2], packet[3], packet[4]
    assert servo_id == 1
    assert instruction == fp.INST_WRITE
    body_params = packet[5:5 + length - 2]
    address = body_params[0]
    data = body_params[1:]
    assert address == fp.ADDR_ACC
    assert data[0] == 20  # acc
    assert fp.decode_signed16(data[1:3]) == -200  # goal position
    goal_time = fp.decode_u16(data[3:5])
    assert goal_time == 0
    assert fp.decode_u16(data[5:7]) == 100  # speed


def test_context_manager_otwiera_i_zamyka(monkeypatch):
    opened = []
    closed = []
    monkeypatch.setattr(FeetekDriver, "open", lambda self: opened.append(True))
    monkeypatch.setattr(FeetekDriver, "close", lambda self: closed.append(True))
    with FeetekDriver("/dev/null") as d:
        assert isinstance(d, FeetekDriver)
    assert opened == [True]
    assert closed == [True]
