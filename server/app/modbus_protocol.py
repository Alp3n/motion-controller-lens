"""Protokół Modbus RTU — dla modułów I/O Waveshare na magistrali serw (temat L).

W przeciwieństwie do serw FEETECH (`feetech_protocol.py`, protokół własny
producenta), moduły I/O **są** prawdziwym Modbus RTU — potwierdzone
2026-09-11 dla dwóch konkretnych modeli:

    SKU 26244 — Modbus RTU IO 8CH (cyfrowy, 8DI/8DO)
    SKU 25821 — Modbus RTU Analog Input 8CH (analogowy, 12-bit)

Oba: adres 1-255, domyślnie adres 1, domyślny baudrate 9600 (N,8,1) —
INNY niż serwa (115200), stąd osobne połączenie (`ModbusDriver`, osobny
port/baud niż `FeetekDriver`), mimo współdzielonej magistrali fizycznej.

Ramka: ``<adres> <funkcja> <dane...> <CRC16 (low, high)>``. To ODWROTNA
kolejność bajtów CRC niż w ramce FEETECH (tu low byte CRC pierwszy) —
standardowy Modbus RTU.

**Zweryfikowane u źródła 2026-09-11** (nie z pamięci): mapa rejestrów
modułu analogowego (SKU 25821) z instrukcji producenta — patrz
`ADDR_ANALOG_*` niżej — a konkretnie polecenie odczytu `01 04 00 00 00 08
F1 CC` potwierdzone przeliczeniem CRC16 niezależnie (zgadza się co do
bajtu).

**Mapa rejestrów modułu cyfrowego (SKU 26244) POTWIERDZONA FIZYCZNIE
2026-09-11** — nie tylko brakiem błędu Modbus przy sondowaniu, ale
zapisem coil 0 → ON i obserwacją diody DO0 na module. Coils 0-7 = DO0-DO7
(zapis+odczyt), discrete inputs 0-7 = DI0-DI7 (tylko odczyt, z definicji
Modbus). Moduł dzieli układ rejestrów konfiguracyjnych z modułem
analogowym — `read_holding_registers(0x4000, 1)` zwrócił wartość zgodną
z rzeczywistym adresem urządzenia, niezależne potwierdzenie tego samego
wzorca.
"""

from __future__ import annotations

import struct

# --- funkcje Modbus używane tutaj ---
FUNC_READ_COILS = 0x01
FUNC_READ_DISCRETE_INPUTS = 0x02
FUNC_READ_HOLDING_REGISTERS = 0x03
FUNC_READ_INPUT_REGISTERS = 0x04
FUNC_WRITE_SINGLE_COIL = 0x05
FUNC_WRITE_SINGLE_REGISTER = 0x06
FUNC_WRITE_MULTIPLE_REGISTERS = 0x10
ERROR_BIT = 0x80

# --- moduł analogowy SKU 25821 — POTWIERDZONE z instrukcji producenta ---
# Odczyt 8 kanałów: funkcja 0x04 (Read Input Registers), adresy 0x0000-0x0007.
ADDR_ANALOG_CHANNELS = 0x0000
ANALOG_CHANNEL_COUNT = 8
# Typ/zakres danych per kanał (read/write, funkcja 0x03/0x06/0x10):
ADDR_ANALOG_DATA_TYPE = 0x1000
ANALOG_RANGE_0_5V = 0x0000
ANALOG_RANGE_1_5V = 0x0001
ANALOG_RANGE_0_20MA = 0x0002
ANALOG_RANGE_4_20MA = 0x0003
ANALOG_RANGE_RAW = 0x0004  # 0-4096, wymaga przeliczenia liniowego samemu

# --- moduł cyfrowy SKU 26244 — POTWIERDZONE fizycznie 2026-09-11 ---
# DO0-DO7: coils (funkcja 0x01 odczyt, 0x05 zapis), adresy 0x0000-0x0007.
# DI0-DI7: discrete inputs (funkcja 0x02, tylko odczyt), te same adresy.
ADDR_DIGITAL_CHANNELS = 0x0000
DIGITAL_CHANNEL_COUNT = 8

# Konfiguracja wspólna dla obu modułów (potwierdzone dla obu — adres
# urządzenia zweryfikowany fizycznie też na module cyfrowym):
ADDR_UART_PARAMS = 0x2000
ADDR_DEVICE_ADDRESS = 0x4000
ADDR_SOFTWARE_VERSION = 0x8000

DEFAULT_ADDRESS = 1
DEFAULT_BAUD = 9600


class ModbusError(Exception):
    """Zła ramka, zła suma CRC, albo urządzenie zgłosiło wyjątek Modbus."""


def crc16(data: bytes) -> bytes:
    """CRC16 Modbus — low byte, high byte (kolejność ODWROTNA niż w ramce
    FEETECH). Zweryfikowane niezależnie względem przykładu z instrukcji
    producenta modułu analogowego: `crc16(b'\\x01\\x04\\x00\\x00\\x00\\x08')
    == b'\\xf1\\xcc'`."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack("<H", crc)


def build_request(slave_id: int, function: int, payload: bytes = b"") -> bytes:
    body = bytes([slave_id, function]) + payload
    return body + crc16(body)


def build_read(function: int, slave_id: int, address: int, count: int) -> bytes:
    return build_request(slave_id, function, struct.pack(">HH", address, count))


def build_read_input_registers(slave_id: int, address: int, count: int) -> bytes:
    return build_read(FUNC_READ_INPUT_REGISTERS, slave_id, address, count)


def build_read_holding_registers(slave_id: int, address: int, count: int) -> bytes:
    return build_read(FUNC_READ_HOLDING_REGISTERS, slave_id, address, count)


def build_read_coils(slave_id: int, address: int, count: int) -> bytes:
    return build_read(FUNC_READ_COILS, slave_id, address, count)


def build_read_discrete_inputs(slave_id: int, address: int, count: int) -> bytes:
    return build_read(FUNC_READ_DISCRETE_INPUTS, slave_id, address, count)


def build_write_single_register(slave_id: int, address: int, value: int) -> bytes:
    return build_request(slave_id, FUNC_WRITE_SINGLE_REGISTER, struct.pack(">HH", address, value))


def build_write_single_coil(slave_id: int, address: int, on: bool) -> bytes:
    value = 0xFF00 if on else 0x0000
    return build_request(slave_id, FUNC_WRITE_SINGLE_COIL, struct.pack(">HH", address, value))


def parse_response(request_function: int, response: bytes) -> bytes:
    """Sprawdza CRC i nagłówek, zwraca DANE (bez adresu/funkcji/CRC).

    Dla funkcji odczytu (0x01-0x04) dane to `[liczba_bajtów, bajty...]` —
    licznik zostaje w zwróconych bajtach, wywołujący go pomija świadomie
    (spójne z tym, jak `feetech_protocol.parse_response` zostawia surowe
    dane do interpretacji przez wywołującego).
    """
    if len(response) < 5:
        raise ModbusError(f"odpowiedź za krótka: {response.hex(' ')}")
    body, received_crc = response[:-2], response[-2:]
    if crc16(body) != received_crc:
        raise ModbusError(
            f"zła suma CRC: {received_crc.hex(' ')} != {crc16(body).hex(' ')}"
        )
    slave_id, function = body[0], body[1]
    if function & ERROR_BIT:
        exc_code = body[2] if len(body) > 2 else None
        raise ModbusError(
            f"urządzenie {slave_id} zgłosiło wyjątek Modbus dla funkcji "
            f"{request_function:#04x}: kod {exc_code}"
        )
    if function != request_function:
        raise ModbusError(
            f"nieoczekiwana funkcja w odpowiedzi: {function:#04x} != {request_function:#04x}"
        )
    return body[2:]


def decode_registers(data: bytes) -> list[int]:
    """`data` to `[liczba_bajtów, rejestr0_hi, rejestr0_lo, ...]` — zwraca
    listę wartości 16-bit (big-endian, standard Modbus), bez licznika."""
    byte_count = data[0]
    values = data[1:1 + byte_count]
    return [struct.unpack(">H", values[i:i + 2])[0] for i in range(0, len(values), 2)]


def decode_bits(data: bytes, count: int) -> list[bool]:
    """`data` to `[liczba_bajtów, bity...]` (Modbus pakuje bity do bajtów,
    LSB pierwszy) — zwraca listę `count` wartości bool."""
    byte_count = data[0]
    packed = data[1:1 + byte_count]
    bits = []
    for byte in packed:
        for i in range(8):
            bits.append(bool(byte & (1 << i)))
    return bits[:count]
