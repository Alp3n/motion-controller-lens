#!/usr/bin/env python3
"""Test łączności z serwem FEETECH SM45BL (protokół natywny SCS/SMS, nie Modbus RTU).

**Ustalone 2026-09-10 z oficjalnej dokumentacji Feetecha** (`zbyszek/`):
SM45BL należy do serii SMBL (brushless, RS485), która używa TEGO SAMEGO
protokołu co SMS/STS — cytat wprost: „The communication protocols of the
three series are identical and interworking" (`zbyszek/SM45BL start
tutorial201015_3.pdf`, str. 7, tabela serii SCS/STS/SMBL). To protokół
pakietowy w stylu Dynamixel Protocol 1.0, **nie standardowy Modbus RTU**
(inny nagłówek, inna suma kontrolna, inne kody instrukcji) — mimo że tak
było opisane w ogłoszeniu sprzedażowym. Potwierdzone w kodzie źródłowym
`zbyszek/FTServo_Python-main.zip` (`scservo_sdk/protocol_packet_handler.py`,
`scservo_sdk/scservo_def.py`).

Ten skrypt zastępuje `tools/test_modbus_servo.py` dla tego serwa — tamten
zostaje na wypadek, gdyby konkretny egzemplarz jednak miał przełączalny
tryb Modbus (do sprawdzenia eksperymentalnie, nie zakładane na pewno).

Format ramki:

    0xFF 0xFF <ID> <DŁUGOŚĆ> <INSTRUKCJA> [parametry...] <SUMA_KONTROLNA>

Suma kontrolna = ~(ID + DŁUGOŚĆ + INSTRUKCJA + parametry) & 0xFF (bez
nagłówka FF FF). PING (instrukcja 0x01) nie ma parametrów, DŁUGOŚĆ=2.

Bez zewnętrznych bibliotek (jak reszta `tools/`) — sam port przez termios.

Użycie:
    tools/test_feetech_servo.py                    # skanuje /dev/ttyUSB*
    tools/test_feetech_servo.py /dev/ttyUSB0
    tools/test_feetech_servo.py /dev/ttyUSB0 --id 1 --baud 115200

Domyślny baudrate serii SM to **115200** (potwierdzone w tutorialu, str. 2
i FAQ str. 9) — inny niż STS (1000000, też próbowany domyślnie). Domyślne
ID zwykle 1. **Zasilanie serwa jest OSOBNE od sygnału RS485** — 9-24V wg
karty katalogowej (`zbyszek/Feetech karta katalogowa SM45BL 001.pdf`),
bez niego PING nie dostanie odpowiedzi niezależnie od poprawności
okablowania sygnałowego.
"""

from __future__ import annotations

import argparse
import glob
import os
import termios
import time

BAUD_CONST = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}
if hasattr(termios, "B1000000"):
    BAUD_CONST[1000000] = termios.B1000000

DEFAULT_BAUDS = [b for b in (115200, 1000000) if b in BAUD_CONST]
INST_PING = 0x01


def checksum(payload: bytes) -> int:
    return (~sum(payload)) & 0xFF


def build_ping(servo_id: int) -> bytes:
    body = bytes([servo_id, 0x02, INST_PING])
    return b"\xff\xff" + body + bytes([checksum(body)])


def open_serial(path: str, baud: int, timeout_s: float = 0.3) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    attrs = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
    baud_const = BAUD_CONST[baud]
    cflag = (cflag & ~termios.CSIZE) | termios.CS8
    cflag |= termios.CLOCAL | termios.CREAD
    cflag &= ~termios.PARENB  # 8N1 — do zmiany, gdyby mapa pamięci mówiła inaczej
    cflag &= ~termios.CSTOPB
    iflag = 0
    oflag = 0
    lflag = 0
    cc = list(cc)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = int(timeout_s * 10)
    termios.tcsetattr(
        fd, termios.TCSANOW,
        [iflag, oflag, cflag, lflag, baud_const, baud_const, cc],
    )
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def try_ping(path: str, baud: int, servo_id: int) -> bytes | None:
    fd = open_serial(path, baud)
    try:
        os.write(fd, build_ping(servo_id))
        time.sleep(0.1)
        try:
            response = os.read(fd, 64)
        except OSError:
            response = b""
        return response or None
    finally:
        os.close(fd)


def discover_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", nargs="?", help="np. /dev/ttyUSB0 (domyślnie: skanuj wszystkie)")
    parser.add_argument("--baud", type=int, help="jeden baudrate zamiast domyślnej listy (115200, 1000000)")
    parser.add_argument("--id", type=int, default=1, help="ID serwa (domyślnie 1)")
    args = parser.parse_args()

    ports = [args.port] if args.port else discover_ports()
    if not ports:
        print("Brak /dev/ttyUSB*/ttyACM* — podłącz konwerter USB-RS485 i uruchom ponownie.")
        return 1

    bauds = [args.baud] if args.baud else DEFAULT_BAUDS
    print(f"Porty: {ports}")
    print(f"Baudrate'y: {bauds}")
    print(f"ID serwa: {args.id}")
    print("Wysyłam PING (protokół SCS/SMS, nie Modbus)...\n")

    for path in ports:
        for baud in bauds:
            label = f"{path} @ {baud} id={args.id}"
            try:
                response = try_ping(path, baud, args.id)
            except PermissionError:
                print(f"{label}: brak uprawnień — jesteś w grupie dialout? (sudo usermod -aG dialout $USER)")
                continue
            except OSError as exc:
                print(f"{label}: błąd portu — {exc}")
                continue
            if response:
                print(f"{label}: ODPOWIEDŹ {response.hex(' ')}")
            else:
                print(f"{label}: brak odpowiedzi")

    print(
        "\nBrak odpowiedzi na wszystkich kombinacjach? Sprawdź kolejno: zasilanie "
        "serwa (OSOBNE od RS485, 9-24V), zamianę A/B, czy ID to na pewno 1 (--id "
        "inny numer), a jeśli nic nie pomaga — spróbuj tools/test_modbus_servo.py "
        "na wypadek, gdyby ten konkretny egzemplarz jednak miał tryb Modbus RTU."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
