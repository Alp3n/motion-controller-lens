"""FeetekDriver (temat L) — logika wysoko-poziomowa, bez prawdziwego portu.

`_exchange` jest podmieniane na fake'a (jak `_command`/`_exchange` w
`test_sc4hub.py`) — testujemy budowanie żądań i parsowanie odpowiedzi,
nie prawdziwy termios."""

from __future__ import annotations

import pytest

from app import feetech_protocol as fp
from app.feetech_driver import (
    COUNTS_PER_REV,
    DIRECTION_SIGN_CW,
    FeetekDriver,
    FeetekError,
    position_to_mm,
)


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


def test_read_position_and_load_jednym_odczytem():
    data = fp.encode_signed16(100) + fp.encode_signed16(-5) + fp.encode_signed16(-30)
    d = _driver_with_fake([_ok_response(1, data)])
    position, load = d.read_position_and_load(1)
    assert position == 100
    assert load == -30
    assert len(d.calls) == 1  # jeden odczyt, nie trzy


def test_write_raw_z_bledem_serwa_rzuca():
    body = bytes([1, 2, 32])  # bit 32 = przeciążenie (ERRBIT_OVERLOAD w SDK)
    packet = b"\xff\xff" + body + bytes([fp.checksum(body)])
    d = _driver_with_fake([packet])
    with pytest.raises(FeetekError, match="błąd"):
        d.write_raw(1, fp.ADDR_TORQUE_ENABLE, bytes([1]))


def _write_frame(packet):
    """Rozbiera ramkę WRITE na (adres, dane) — pomija nagłówek/id/sumę."""
    length, instruction = packet[3], packet[4]
    assert instruction == fp.INST_WRITE
    body_params = packet[5:5 + length - 2]
    return body_params[0], body_params[1:]


def test_move_to_ustawia_tryb_pozycyjny_przed_ruchem():
    """move_to() obronnie przywraca MODE_POSITION PRZED zapisem celu — na
    wypadek, gdyby serwo zostało w trybie koła po JOG (patrz docstring)."""
    d = _driver_with_fake([_ok_response(1), _ok_response(1)])
    d.move_to(1, position=-200, speed=100, acc=20)

    assert len(d.calls) == 2
    mode_addr, mode_data = _write_frame(d.calls[0])
    assert mode_addr == fp.ADDR_MODE
    assert mode_data == bytes([fp.MODE_POSITION])

    addr, data = _write_frame(d.calls[1])
    assert addr == fp.ADDR_ACC
    assert data[0] == 20  # acc
    assert fp.decode_signed16(data[1:3]) == -200  # goal position
    assert fp.decode_u16(data[3:5]) == 0  # goal time, nieużywane
    assert fp.decode_u16(data[5:7]) == 100  # speed


def test_move_relative_cw_servo1_odejmuje_od_pozycji():
    # serwo 1 (docisk): CW = malejąca pozycja rejestru (zmierzone 2026-09-10)
    assert DIRECTION_SIGN_CW[1] == -1
    d = _driver_with_fake([
        _ok_response(1, fp.encode_signed16(500)),  # read_position (current)
        _ok_response(1),                            # move_to: set_mode ack
        _ok_response(1),                            # move_to: ACC/pozycja ack
    ])
    target = d.move_relative_cw(1, counts_cw=100, speed=50, acc=10)
    assert target == 400  # 500 - 100


def test_move_relative_cw_servo2_dodaje_do_pozycji():
    # serwo 2 (podajnik): CW = rosnąca pozycja rejestru (zmierzone 2026-09-10)
    assert DIRECTION_SIGN_CW[2] == 1
    d = _driver_with_fake([
        _ok_response(2, fp.encode_signed16(200)),
        _ok_response(2),
        _ok_response(2),
    ])
    target = d.move_relative_cw(2, counts_cw=100, speed=50, acc=10)
    assert target == 300  # 200 + 100


# --- tryb "koło" (stała prędkość) — płynny JOG -----------------------------


def test_set_mode_zapisuje_adres_mode():
    d = _driver_with_fake([_ok_response(1)])
    d.set_mode(1, fp.MODE_WHEEL)
    addr, data = _write_frame(d.calls[0])
    assert addr == fp.ADDR_MODE
    assert data == bytes([fp.MODE_WHEEL])


def test_wheel_speed_cw_ustawia_tryb_i_predkosc_ze_znakiem():
    # serwo 1: CW = malejąca pozycja -> dodatnie speed_cw pisze UJEMNĄ
    # wartość do rejestru (ten sam sens co move_relative_cw)
    d = _driver_with_fake([_ok_response(1), _ok_response(1)])
    d.wheel_speed_cw(1, 300)
    mode_addr, mode_data = _write_frame(d.calls[0])
    assert mode_addr == fp.ADDR_MODE
    assert mode_data == bytes([fp.MODE_WHEEL])
    speed_addr, speed_data = _write_frame(d.calls[1])
    assert speed_addr == fp.ADDR_GOAL_SPEED_L
    assert fp.decode_signed16(speed_data) == -300


def test_wheel_speed_cw_servo2_dodatnie_speed_daje_dodatni_rejestr():
    d = _driver_with_fake([_ok_response(2), _ok_response(2)])
    d.wheel_speed_cw(2, 300)
    _, speed_data = _write_frame(d.calls[1])
    assert fp.decode_signed16(speed_data) == 300


def test_wheel_speed_cw_nieznane_id_rzuca_keyerror():
    d = _driver_with_fake([])
    with pytest.raises(KeyError):
        d.wheel_speed_cw(99, 100)


def test_wheel_stop_zeruje_predkosc_i_przywraca_tryb_pozycyjny():
    d = _driver_with_fake([_ok_response(1), _ok_response(1)])
    d.wheel_stop(1)
    speed_addr, speed_data = _write_frame(d.calls[0])
    assert speed_addr == fp.ADDR_GOAL_SPEED_L
    assert fp.decode_signed16(speed_data) == 0
    mode_addr, mode_data = _write_frame(d.calls[1])
    assert mode_addr == fp.ADDR_MODE
    assert mode_data == bytes([fp.MODE_POSITION])


def test_wait_until_stopped_konczy_gdy_moving_spada_do_zera():
    d = _driver_with_fake([
        _ok_response(1, bytes([1])),  # jeszcze w ruchu
        _ok_response(1, bytes([1])),  # jeszcze w ruchu
        _ok_response(1, bytes([0])),  # zatrzymane
    ])
    assert d.wait_until_stopped(1, timeout_s=5.0, poll_interval_s=0) is True


def test_wait_until_stopped_zwraca_false_po_timeout():
    d = _driver_with_fake([_ok_response(1, bytes([1]))] * 50)
    assert d.wait_until_stopped(1, timeout_s=0.05, poll_interval_s=0.02) is False


def test_move_relative_cw_nieznane_id_rzuca_keyerror():
    d = _driver_with_fake([])
    with pytest.raises(KeyError):
        d.move_relative_cw(99, counts_cw=100)


def test_context_manager_otwiera_i_zamyka(monkeypatch):
    opened = []
    closed = []
    monkeypatch.setattr(FeetekDriver, "open", lambda self: opened.append(True))
    monkeypatch.setattr(FeetekDriver, "close", lambda self: closed.append(True))
    with FeetekDriver("/dev/null") as d:
        assert isinstance(d, FeetekDriver)
    assert opened == [True]
    assert closed == [True]


# --- position_to_mm (temat L, etap 2 kalibracji) ---------------------------


def test_position_to_mm_jeden_pelny_obrot():
    # docisk: skok śruby 1.0 mm/obr (config/axes.json) — pełny obrót
    # (COUNTS_PER_REV jednostek rejestru) to dokładnie jeden skok
    assert position_to_mm(COUNTS_PER_REV, mm_per_rev=1.0) == pytest.approx(1.0)


def test_position_to_mm_skaluje_przez_mm_per_rev():
    # podajnik: skok śruby 8.0 mm/obr — pół obrotu to połowa skoku
    assert position_to_mm(COUNTS_PER_REV // 2, mm_per_rev=8.0) == pytest.approx(4.0)


def test_position_to_mm_zero_to_zero():
    assert position_to_mm(0, mm_per_rev=8.0) == 0.0


def test_position_to_mm_zachowuje_znak_rejestru():
    # celowo bez odwracania znaku względem DIRECTION_SIGN_CW — patrz
    # docstring position_to_mm(): bazowanie/kierunek to osobny, niezrobiony
    # jeszcze krok (etap 3)
    assert position_to_mm(-COUNTS_PER_REV, mm_per_rev=1.0) == pytest.approx(-1.0)
