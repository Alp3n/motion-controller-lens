"""Protokół Modbus RTU dla modułów I/O Waveshare (temat L) — budowanie/parsowanie."""

from __future__ import annotations

import pytest

from app import modbus_protocol as mp


def test_crc16_zgadza_sie_z_przykladem_z_instrukcji_producenta():
    """`01 04 00 00 00 08 F1 CC` — polecenie odczytu 8 kanałów analogowych
    z instrukcji Waveshare Modbus RTU Analog Input 8CH (SKU 25821)."""
    assert mp.crc16(bytes.fromhex("01 04 00 00 00 08")) == bytes.fromhex("F1 CC")


def test_build_read_input_registers_zgadza_sie_z_przykladem():
    packet = mp.build_read_input_registers(1, mp.ADDR_ANALOG_CHANNELS, mp.ANALOG_CHANNEL_COUNT)
    assert packet == bytes.fromhex("01 04 00 00 00 08 F1 CC")


def test_build_read_holding_registers():
    packet = mp.build_read_holding_registers(1, 0x1000, 1)
    assert packet[:2] == bytes([1, mp.FUNC_READ_HOLDING_REGISTERS])
    assert packet[-2:] == mp.crc16(packet[:-2])


def test_build_write_single_register():
    packet = mp.build_write_single_register(1, mp.ADDR_DEVICE_ADDRESS, 2)
    assert packet[:2] == bytes([1, mp.FUNC_WRITE_SINGLE_REGISTER])
    assert packet[2:6] == bytes.fromhex("40 00 00 02")
    assert packet[-2:] == mp.crc16(packet[:-2])


def test_build_write_single_coil_on_off():
    on = mp.build_write_single_coil(1, 0, True)
    off = mp.build_write_single_coil(1, 0, False)
    assert on[2:6] == bytes.fromhex("00 00 FF 00")
    assert off[2:6] == bytes.fromhex("00 00 00 00")


def test_build_read_coils_and_discrete_inputs():
    coils = mp.build_read_coils(1, 0, 8)
    discrete = mp.build_read_discrete_inputs(1, 0, 8)
    assert coils[1] == mp.FUNC_READ_COILS
    assert discrete[1] == mp.FUNC_READ_DISCRETE_INPUTS


# --- parse_response ----------------------------------------------------------


def _framed(slave_id: int, function: int, data: bytes) -> bytes:
    body = bytes([slave_id, function]) + data
    return body + mp.crc16(body)


def test_parse_response_poprawna_ramka():
    response = _framed(1, mp.FUNC_READ_INPUT_REGISTERS, bytes([2, 0x01, 0x23]))
    data = mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, response)
    assert data == bytes([2, 0x01, 0x23])


def test_parse_response_zla_suma_crc():
    response = _framed(1, mp.FUNC_READ_INPUT_REGISTERS, bytes([2, 0, 0]))
    corrupted = response[:-1] + bytes([response[-1] ^ 0xFF])
    with pytest.raises(mp.ModbusError, match="CRC"):
        mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, corrupted)


def test_parse_response_za_krotka():
    with pytest.raises(mp.ModbusError):
        mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, bytes.fromhex("01 04"))


def test_parse_response_wyjatek_modbus():
    # bit błędu (0x80) ustawiony na funkcji + kod wyjątku
    response = _framed(1, mp.FUNC_READ_INPUT_REGISTERS | mp.ERROR_BIT, bytes([0x02]))
    with pytest.raises(mp.ModbusError, match="wyjątek Modbus"):
        mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, response)


def test_parse_response_niepasujaca_funkcja():
    response = _framed(1, mp.FUNC_READ_HOLDING_REGISTERS, bytes([2, 0, 0]))
    with pytest.raises(mp.ModbusError, match="funkcja"):
        mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, response)


# --- dekodowanie danych --------------------------------------------------


def test_decode_registers():
    data = bytes([4, 0x01, 0x23, 0x00, 0x0A])  # 2 rejestry: 0x0123, 0x000A
    assert mp.decode_registers(data) == [0x0123, 0x000A]


def test_decode_bits_lsb_pierwszy():
    # bajt 0b00000101 = bity 0 i 2 ustawione (LSB pierwszy)
    data = bytes([1, 0b00000101])
    assert mp.decode_bits(data, count=8) == [True, False, True, False, False, False, False, False]


def test_decode_bits_obcina_do_count():
    data = bytes([1, 0b11111111])
    assert mp.decode_bits(data, count=3) == [True, True, True]
