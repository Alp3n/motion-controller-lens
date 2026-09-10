"""`FeetekDriver` — sterownik jednej magistrali serw FEETECH (temat L).

Owija `feetech_protocol.py` (budowanie/parsowanie ramek) prawdziwym portem
szeregowym przez `termios` — bez zewnętrznych bibliotek, tym samym stylem
co `tools/test_feetech_servo.py` (skąd przeniesiona jest logika portu).
Jedna instancja obsługuje CAŁĄ magistralę (wiele serw po ID), tak jak
jeden `SC4HubMachine` obsługuje X/Y/Z przez jedno połączenie z mostkiem —
to jest odpowiednik `TeknicSC4HubDriver` z
`docs/architektura-wielu-drajwerow-osi.md`.

**Świadomie NIEZINTEGROWANE jeszcze z `Machine`.** Otwarte pytania z tego
dokumentu (czy oś jest pełnoprawna w cyklu, konwersja mm↔kroki enkodera,
kierunek dodatni vs ujemny per oś) nie są tu rozstrzygane — ten moduł daje
tylko czyste operacje na magistrali (ping/status/ruch), które integracja
będzie mogła wykorzystać, gdy te pytania zostaną rozstrzygnięte.

Prędkość/przyspieszenie w jednostkach rejestru (nie mm/min!) — patrz
`zbyszek/FTServo_Python-main.zip` (`sms_sts/write.py`, komentarz): prędkość
≈ 0,732 obr/min na jednostkę, przyspieszenie ≈ 8,79°/s² na jednostkę
(zgadza się z `zbyszek/Tabela pamięci...xlsx`, pole „加速度" 8,7890625).
**Do przeliczenia na mm/min dopiero przy integracji z `Machine`** — tu
zostają surowe jednostki rejestru, żeby nie zgadywać przeliczenia przed
fizyczną kalibracją per oś (`mm_per_rev` z `config/axes.json`).
"""

from __future__ import annotations

import os
import struct
import termios
import time

from . import feetech_protocol as fp

BAUD_CONST = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}
if hasattr(termios, "B1000000"):
    BAUD_CONST[1000000] = termios.B1000000


class FeetekError(Exception):
    """Brak odpowiedzi, zła ramka, albo serwo zgłosiło błąd (bajt error != 0)."""


# Kierunek fizyczny vs znak rejestru pozycji — zmierzone empirycznie na
# sprzęcie 2026-09-10 (`tools/feetech_jog.py`, obserwacja operatora przy
# maszynie), NIE z dokumentacji (karta katalogowa mówi "Clockwise(0→4096)"
# dla WSZYSTKICH serw — u nas serwo 1 zachowuje się odwrotnie; prawdopodobnie
# kwestia strony, z której patrzy operator, nie błąd pomiaru, ale liczy się
# zmierzony wynik, nie założenie). Pierwszy odczyt dla serwa 2 (przy szybkich
# testach pod rząd) był błędny ("w lewo" dla rosnącej pozycji) — poprawiony
# po spokojnym, pojedynczym teście na "w prawo". Klucz: ID serwa PRZY
# DZISIEJSZYM OKABLOWANIU (1=docisk, 2=podajnik) — jeśli fizyczne
# podłączenie/ID się zmieni, ten słownik trzeba zweryfikować ponownie.
#
#   serwo 1 (docisk):   malejąca pozycja rejestru = zgodnie z zegarem (CW)
#   serwo 2 (podajnik): rosnąca pozycja rejestru  = zgodnie z zegarem (CW)
DIRECTION_SIGN_CW = {1: -1, 2: 1}


class FeetekDriver:
    """Jedna magistrala RS485, wiele serw po ID. `open()`/`close()` albo
    użycie jako context manager (`with FeetekDriver(...) as d:`)."""

    def __init__(self, port: str, baud: int = 115200, timeout_s: float = 0.3) -> None:
        self.port = port
        self.baud = baud
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def __enter__(self) -> "FeetekDriver":
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
        cflag &= ~termios.PARENB
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
            raise FeetekError("port niezotwarty — wywołaj open() albo użyj 'with'")
        os.write(self._fd, packet)
        time.sleep(settle)
        try:
            response = os.read(self._fd, 64)
        except OSError:
            response = b""
        if not response:
            raise FeetekError("brak odpowiedzi z serwa (timeout)")
        return response

    def ping(self, servo_id: int) -> int:
        """Zwraca numer modelu. Rzuca `FeetekError`, jeśli serwo nie odpowie."""
        _, error, data = fp.parse_response(self._exchange(fp.build_ping(servo_id)))
        if error != 0:
            raise FeetekError(f"serwo {servo_id} zgłosiło błąd: {error:#04x}")
        return 0 if not data else fp.decode_u16(data)

    def read_raw(self, servo_id: int, address: int, count: int) -> bytes:
        _, error, data = fp.parse_response(self._exchange(fp.build_read(servo_id, address, count)))
        if error != 0:
            raise FeetekError(f"serwo {servo_id} zgłosiło błąd przy odczycie {address}: {error:#04x}")
        return data

    def write_raw(self, servo_id: int, address: int, data: bytes) -> None:
        _, error, _ = fp.parse_response(self._exchange(fp.build_write(servo_id, address, data)))
        if error != 0:
            raise FeetekError(f"serwo {servo_id} zgłosiło błąd przy zapisie {address}: {error:#04x}")

    def read_position(self, servo_id: int) -> int:
        return fp.decode_signed16(self.read_raw(servo_id, fp.ADDR_PRESENT_POSITION_L, 2))

    def read_status(self, servo_id: int) -> dict[str, int]:
        return {
            "position": fp.decode_signed16(self.read_raw(servo_id, fp.ADDR_PRESENT_POSITION_L, 2)),
            "speed": fp.decode_signed16(self.read_raw(servo_id, fp.ADDR_PRESENT_SPEED_L, 2)),
            "load": fp.decode_signed16(self.read_raw(servo_id, fp.ADDR_PRESENT_LOAD_L, 2)),
            "voltage_x0_1v": self.read_raw(servo_id, fp.ADDR_PRESENT_VOLTAGE, 1)[0],
            "temperature_c": self.read_raw(servo_id, fp.ADDR_PRESENT_TEMPERATURE, 1)[0],
        }

    def move_to(self, servo_id: int, position: int, speed: int = 100, acc: int = 20) -> None:
        """Ruch pozycyjny — jednostki REJESTRU (kroki enkodera 0-4095 na
        obrót, prędkość/przyspieszenie jak w docstring modułu), NIE mm.

        Odpowiednik `WritePosEx` z SDK producenta: jeden zapis 7 bajtów od
        adresu ACC (41) — ACC, GOAL_POSITION_L/H (znak-magnituda, bit 15),
        GOAL_TIME_L/H (zawsze 0, nieużywane tutaj), GOAL_SPEED_L/H.
        """
        payload = (
            bytes([acc & 0xFF])
            + fp.encode_signed16(position)
            + struct.pack("<H", 0)
            + struct.pack("<H", speed)
        )
        self.write_raw(servo_id, fp.ADDR_ACC, payload)

    def move_relative_cw(self, servo_id: int, counts_cw: int, speed: int = 100, acc: int = 20) -> int:
        """Jak `move_to`, ale kierunek zawsze "zgodnie z zegarem = dodatnie",
        niezależnie od tego, czy dla tego konkretnego ID rejestr rośnie czy
        maleje przy CW (patrz `DIRECTION_SIGN_CW`, zmierzone empirycznie).
        Zwraca docelową pozycję W JEDNOSTKACH REJESTRU (do odczytu/logowania).

        Rzuca `KeyError`, jeśli `servo_id` nie ma jeszcze zmierzonego
        kierunku w `DIRECTION_SIGN_CW` — celowo, żeby nie zgadywać znaku dla
        nieprzetestowanego serwa.
        """
        sign = DIRECTION_SIGN_CW[servo_id]
        current = self.read_position(servo_id)
        target = current + sign * counts_cw
        self.move_to(servo_id, target, speed=speed, acc=acc)
        return target
