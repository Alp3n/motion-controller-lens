"""Protokół natywny serw FEETECH (temat L) — budowanie/parsowanie ramek."""

from __future__ import annotations

import pytest

from app import feetech_protocol as fp


def test_build_ping_zgadza_sie_z_reczna_kalkulacja():
    # FF FF 01 02 01 <suma>; suma = ~(1+2+1) & 0xFF = ~4 & 0xFF = 0xFB
    assert fp.build_ping(1) == bytes.fromhex("ff ff 01 02 01 fb")


def test_build_read_ramka():
    # odczyt 2 bajtów spod adresu 56 (present position), ID=1
    packet = fp.build_read(1, 56, 2)
    assert packet[:5] == bytes([0xFF, 0xFF, 1, 4, fp.INST_READ])
    assert packet[5:7] == bytes([56, 2])
    # suma kontrolna liczona bez nagłówka
    assert packet[-1] == fp.checksum(packet[2:-1])


def test_build_write_ramka():
    packet = fp.build_write(1, fp.ADDR_TORQUE_ENABLE, bytes([1]))
    assert packet[:5] == bytes([0xFF, 0xFF, 1, 4, fp.INST_WRITE])
    assert packet[5:7] == bytes([fp.ADDR_TORQUE_ENABLE, 1])


def test_parse_response_poprawna_ramka():
    # odpowiedź na ping: FF FF 01 02 00 <suma>
    body = bytes([1, 2, 0])
    packet = b"\xff\xff" + body + bytes([fp.checksum(body)])
    servo_id, error, data = fp.parse_response(packet)
    assert servo_id == 1
    assert error == 0
    assert data == b""


def test_parse_response_z_danymi():
    # odpowiedź na read 2 bajtów: id, len=4, error, data0, data1, suma
    body = bytes([1, 4, 0, 0x34, 0x12])
    packet = b"\xff\xff" + body + bytes([fp.checksum(body)])
    _, error, data = fp.parse_response(packet)
    assert error == 0
    assert data == bytes([0x34, 0x12])
    assert fp.decode_u16(data) == 0x1234


def test_parse_response_zla_suma_kontrolna():
    body = bytes([1, 2, 0])
    packet = b"\xff\xff" + body + bytes([0x00])  # zła suma
    with pytest.raises(fp.ProtocolError, match="suma kontrolna"):
        fp.parse_response(packet)


def test_parse_response_zly_naglowek():
    with pytest.raises(fp.ProtocolError, match="nagłówek"):
        fp.parse_response(bytes.fromhex("00 00 01 02 00 fd"))


def test_parse_response_za_krotki_pakiet():
    with pytest.raises(fp.ProtocolError):
        fp.parse_response(bytes.fromhex("ff ff 01"))


def test_decode_u16_low_byte_first():
    assert fp.decode_u16(bytes([0x34, 0x12])) == 0x1234


def test_decode_signed16_dodatni():
    assert fp.decode_signed16(bytes([0x64, 0x00])) == 100  # 0x0064, bit15=0


def test_decode_signed16_ujemny():
    # bit 15 ustawiony = znak ujemny, magnituda w pozostałych bitach
    raw = 100 | 0x8000
    data = bytes([raw & 0xFF, (raw >> 8) & 0xFF])
    assert fp.decode_signed16(data) == -100
