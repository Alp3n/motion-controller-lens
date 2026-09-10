"""Protokół natywny serw FEETECH serii SM/SMS/STS (temat L) — NIE Modbus RTU.

Ustalone 2026-09-10 (`docs/architektura-wielu-drajwerow-osi.md`): SM45BL
(seria SMBL, planowana oś 4) używa tego samego protokołu pakietowego co
SMS/STS — cytat z oficjalnego tutoriala producenta: „The communication
protocols of the three series are identical and interworking". Ramka w
stylu Dynamixel Protocol 1.0. Ten moduł to minimalny, przepisany od zera
podzbiór tego, co robi `scservo_sdk` z `zbyszek/FTServo_Python-main.zip`
(`protocol_packet_handler.py`, `scservo_def.py`, `sms_sts.py`) — PING i
READ, bez dodawania zależności do repo (styl reszty projektu: własny,
wąski kod zamiast biblioteki, jak `tools/docs-pdf.py`).

**Świadomie NIEZINTEGROWANE jeszcze z `Machine`/`SC4HubMachine`.** To
tylko warstwa protokołu (budowanie/parsowanie ramek), testowalna bez
fizycznego sprzętu przez podstawienie funkcji zapisu/odczytu. Integracja
z resztą aplikacji (właściwy `FeetekDriver`, architektura wielu drajwerów)
czeka na: (1) fizyczne potwierdzenie tego protokołu na sprzęcie
(`tools/test_feetech_servo.py`), (2) rozstrzygnięcie otwartych pytań w
`docs/architektura-wielu-drajwerow-osi.md` (m.in. czy oś 4 jest
pełnoprawna w cyklu/programie, czy pomocnicza).

Ramka: ``0xFF 0xFF <ID> <DŁUGOŚĆ> <INSTRUKCJA> [parametry...] <SUMA>``.
Suma kontrolna = ``~(ID + DŁUGOŚĆ + INSTRUKCJA + parametry) & 0xFF``.

Kolejność bajtów: **low byte first** dla serii SM (inaczej niż SCS, patrz
tutorial, pyt. 11: „SCS series high byte first, SMS low byte first").
"""

from __future__ import annotations

import struct

BROADCAST_ID = 0xFE

INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03

# Adresy rejestrów serii SMS (potwierdzone w scservo_sdk/sms_sts.py z SDK
# producenta) — dotyczą SM45BL, bo seria SMBL dzieli protokół/tabelę
# pamięci z SMS/STS (patrz docstring modułu).
ADDR_MODEL_L = 3
ADDR_MODEL_H = 4
ADDR_ID = 5
ADDR_BAUD_RATE = 6
ADDR_MODE = 33
ADDR_TORQUE_ENABLE = 40
ADDR_ACC = 41
ADDR_GOAL_POSITION_L = 42
ADDR_GOAL_POSITION_H = 43
ADDR_GOAL_TIME_L = 44
ADDR_GOAL_TIME_H = 45
ADDR_GOAL_SPEED_L = 46
ADDR_GOAL_SPEED_H = 47
ADDR_LOCK = 55  # 0=EPROM odblokowane do zapisu (ID, baudrate, ...), 1=zablokowane
ADDR_PRESENT_POSITION_L = 56
ADDR_PRESENT_SPEED_L = 58
ADDR_PRESENT_LOAD_L = 60
ADDR_PRESENT_VOLTAGE = 62
ADDR_PRESENT_TEMPERATURE = 63
ADDR_MOVING = 66
ADDR_PRESENT_CURRENT_L = 69


class ProtocolError(Exception):
    """Ramka odpowiedzi jest za krótka, ma zły nagłówek albo złą sumę kontrolną."""


def checksum(payload: bytes) -> int:
    return (~sum(payload)) & 0xFF


def build_packet(servo_id: int, instruction: int, params: bytes = b"") -> bytes:
    length = len(params) + 2
    body = bytes([servo_id, length, instruction]) + params
    return b"\xff\xff" + body + bytes([checksum(body)])


def build_ping(servo_id: int) -> bytes:
    return build_packet(servo_id, INST_PING)


def build_read(servo_id: int, address: int, count: int) -> bytes:
    return build_packet(servo_id, INST_READ, bytes([address, count]))


def build_write(servo_id: int, address: int, data: bytes) -> bytes:
    return build_packet(servo_id, INST_WRITE, bytes([address]) + bytes(data))


def parse_response(packet: bytes) -> tuple[int, int, bytes]:
    """Zwraca ``(id, błąd, dane)``. Rzuca `ProtocolError` przy złej ramce."""
    if len(packet) < 6 or packet[0] != 0xFF or packet[1] != 0xFF:
        raise ProtocolError(f"zły nagłówek: {packet.hex(' ')}")
    servo_id = packet[2]
    length = packet[3]
    total = 4 + length
    if len(packet) < total:
        raise ProtocolError(
            f"pakiet za krótki: oczekiwano {total} bajtów, jest {len(packet)}"
        )
    body = packet[2:total]
    expected = checksum(body[:-1])
    if body[-1] != expected:
        raise ProtocolError(f"zła suma kontrolna: {body[-1]:#x} != {expected:#x}")
    error = packet[4]
    data = packet[5:total - 1]
    return servo_id, error, bytes(data)


def decode_u16(data: bytes, offset: int = 0) -> int:
    """Little-endian (low byte first — patrz docstring modułu)."""
    return data[offset] | (data[offset + 1] << 8)


def decode_signed16(data: bytes, offset: int = 0) -> int:
    """Znak-magnituda, bit 15 (potwierdzone w SDK: `scs_tohost(value, 15)`
    używane przez `ReadPos`/`ReadSpeed`). **Nie potwierdzone dla
    PRESENT_LOAD** konkretnie — SDK producenta nie ma dla niego gotowej
    metody dekodującej; ten sam schemat jest typowy dla tej rodziny
    protokołu, ale przed użyciem do czegokolwiek więcej niż podgląd
    zweryfikuj na sprzęcie (dodatni/ujemny moment przy pchnięciu w obie
    strony)."""
    raw = decode_u16(data, offset)
    if raw & 0x8000:
        return -(raw & 0x7FFF)
    return raw


def encode_signed16(value: int) -> bytes:
    """Odwrotność `decode_signed16` — znak-magnituda, bit 15, low byte first.

    Odpowiednik `scs_toscs(value, 15)` w SDK producenta."""
    magnitude = abs(value) & 0x7FFF
    raw = magnitude | 0x8000 if value < 0 else magnitude
    return struct.pack("<H", raw)
