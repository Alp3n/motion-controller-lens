"""`ModbusDriver` — sterownik magistrali Modbus RTU dla modułów I/O Waveshare
(temat L). Osobne połączenie od `FeetekDriver` — inny baudrate (9600 vs
115200 serw), mimo współdzielonej magistrali fizycznej RS485.

Struktura identyczna z `feetech_driver.py` (port przez `termios`, context
manager) — patrz tamten plik po uzasadnienie stylu.
"""

from __future__ import annotations

import os
import termios
import time

from . import modbus_protocol as mp

BAUD_CONST = {
    4800: termios.B4800,
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


class ModbusDriver:
    """Jedna magistrala Modbus RTU, wiele urządzeń po adresie (1-255)."""

    def __init__(self, port: str, baud: int = mp.DEFAULT_BAUD, timeout_s: float = 0.3) -> None:
        self.port = port
        self.baud = baud
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def __enter__(self) -> "ModbusDriver":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def open(self) -> None:
        fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY)
        attrs = termios.tcgetattr(fd)
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
        baud_const = BAUD_CONST[self.baud]
        cflag = (cflag & ~termios.CSIZE) | termios.CS8
        cflag |= termios.CLOCAL | termios.CREAD
        cflag &= ~termios.PARENB  # 8N1 — zgodne z domyślnym "9600, N, 8, 1" obu modułów
        cflag &= ~termios.CSTOPB
        iflag = 0
        oflag = 0
        lflag = 0
        cc = list(cc)
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = int(self.timeout_s * 10)
        termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, baud_const, baud_const, cc])
        termios.tcflush(fd, termios.TCIOFLUSH)
        self._fd = fd

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _exchange(self, packet: bytes, settle: float = 0.05) -> bytes:
        if self._fd is None:
            raise mp.ModbusError("port niezotwarty — wywołaj open() albo użyj 'with'")
        os.write(self._fd, packet)
        time.sleep(settle)
        try:
            response = os.read(self._fd, 256)
        except OSError:
            response = b""
        if not response:
            raise mp.ModbusError("brak odpowiedzi (timeout)")
        return response

    # --- odczyty ogólne (do sondowania nieznanego jeszcze mapowania) -----

    def read_input_registers(self, slave_id: int, address: int, count: int) -> list[int]:
        response = self._exchange(mp.build_read_input_registers(slave_id, address, count))
        return mp.decode_registers(mp.parse_response(mp.FUNC_READ_INPUT_REGISTERS, response))

    def read_holding_registers(self, slave_id: int, address: int, count: int) -> list[int]:
        response = self._exchange(mp.build_read_holding_registers(slave_id, address, count))
        return mp.decode_registers(mp.parse_response(mp.FUNC_READ_HOLDING_REGISTERS, response))

    def read_coils(self, slave_id: int, address: int, count: int) -> list[bool]:
        response = self._exchange(mp.build_read_coils(slave_id, address, count))
        return mp.decode_bits(mp.parse_response(mp.FUNC_READ_COILS, response), count)

    def read_discrete_inputs(self, slave_id: int, address: int, count: int) -> list[bool]:
        response = self._exchange(mp.build_read_discrete_inputs(slave_id, address, count))
        return mp.decode_bits(mp.parse_response(mp.FUNC_READ_DISCRETE_INPUTS, response), count)

    def write_single_register(self, slave_id: int, address: int, value: int) -> None:
        response = self._exchange(mp.build_write_single_register(slave_id, address, value))
        mp.parse_response(mp.FUNC_WRITE_SINGLE_REGISTER, response)

    def write_single_coil(self, slave_id: int, address: int, on: bool) -> None:
        response = self._exchange(mp.build_write_single_coil(slave_id, address, on))
        mp.parse_response(mp.FUNC_WRITE_SINGLE_COIL, response)

    # --- moduł analogowy SKU 25821 — POTWIERDZONE z instrukcji producenta -

    def read_analog_channels(self, slave_id: int) -> list[int]:
        """8 kanałów, jednostki zależne od skonfigurowanego zakresu na module
        (domyślnie 0-20mA -> µA po stronie modułu, patrz `ADDR_ANALOG_DATA_TYPE`
        w `modbus_protocol.py`) — surowa wartość rejestru, bez przeliczenia
        tutaj (przeliczenie zależy od zakresu, który jest per-kanał
        konfigurowalny)."""
        return self.read_input_registers(slave_id, mp.ADDR_ANALOG_CHANNELS, mp.ANALOG_CHANNEL_COUNT)

    # --- moduł cyfrowy SKU 26244 — POTWIERDZONE fizycznie 2026-09-11 ------
    #
    # coils 0-7 = DO0-DO7, discrete inputs 0-7 = DI0-DI7 — potwierdzone
    # zapisem coil 0 -> ON i obserwacją diody DO0 na module (nie tylko
    # brakiem błędu Modbus, jak przy pierwszym sondowaniu). Adresy z tego
    # samego wzorca co moduł analogowy (0x4000=adres urządzenia,
    # zweryfikowane odczytem zgodnym z rzeczywistością).

    def read_digital_inputs(self, slave_id: int) -> list[bool]:
        """DI0-DI7, w kolejności."""
        return self.read_discrete_inputs(slave_id, mp.ADDR_DIGITAL_CHANNELS, mp.DIGITAL_CHANNEL_COUNT)

    def read_digital_outputs(self, slave_id: int) -> list[bool]:
        """DO0-DO7, w kolejności (stan aktualny, z odczytu coils)."""
        return self.read_coils(slave_id, mp.ADDR_DIGITAL_CHANNELS, mp.DIGITAL_CHANNEL_COUNT)

    def write_digital_output(self, slave_id: int, channel: int, on: bool) -> None:
        """Ustawia jedno wyjście, `channel` 0-7 (DO0-DO7)."""
        if not (0 <= channel < mp.DIGITAL_CHANNEL_COUNT):
            raise ValueError(f"channel musi być 0-{mp.DIGITAL_CHANNEL_COUNT - 1}, jest {channel}")
        self.write_single_coil(slave_id, mp.ADDR_DIGITAL_CHANNELS + channel, on)
