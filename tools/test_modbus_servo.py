#!/usr/bin/env python3
"""Test łączności Modbus RTU z serwem po RS485 (np. FEETECH SM45BL, oś 4).

Bez zewnętrznych bibliotek (jak reszta tools/) — sam port szeregowy przez
termios, sam Modbus RTU (funkcja 0x03 "Read Holding Registers" + CRC16).
Nie zakłada znajomości mapy rejestrów serwa (jeszcze jej nie mamy, patrz
docs/architektura-wielu-drajwerow-osi.md) — to tylko test, czy COKOLWIEK
odpowiada na danym porcie/baudrate/adresie, zanim zabierzemy się za
właściwy protokół.

Użycie:
    tools/test_modbus_servo.py                      # skanuje /dev/ttyUSB*
    tools/test_modbus_servo.py /dev/ttyUSB0          # jeden port
    tools/test_modbus_servo.py /dev/ttyUSB0 --id 1   # jeden adres węzła
    tools/test_modbus_servo.py --baud 115200 --id 1 --reg 0 --count 1

Domyślnie próbuje typowych baudrate'ów Modbus RTU (9600, 19200, 38400,
57600, 115200) i adresu węzła 1 (fabryczny domyślny dla wielu serw —
DO POTWIERDZENIA w dokumentacji SM45BL, nie zakładam na pewno).

Przed uruchomieniem:
    - serwo musi mieć podłączone ZASILANIE (osobne od sygnału RS485)
    - okablowanie A/B (nie pomylić z przeciwną parą — jeśli brak
      odpowiedzi, pierwsza rzecz do sprawdzenia to zamiana A/B)
    - użytkownik uruchamiający musi być w grupie `dialout` (jak przy
      SC4-Hub) albo uruchomić przez sudo
"""

from __future__ import annotations

import argparse
import glob
import os
import struct
import sys
import termios
import time

BAUD_CONST = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}
DEFAULT_BAUDS = [9600, 19200, 38400, 57600, 115200]


def modbus_crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return struct.pack("<H", crc)


def build_read_holding_registers(slave_id: int, reg_addr: int, count: int) -> bytes:
    body = struct.pack(">BBHH", slave_id, 0x03, reg_addr, count)
    return body + modbus_crc16(body)


def open_serial(path: str, baud: int, timeout_s: float = 0.5) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    attrs = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
    baud_const = BAUD_CONST[baud]
    cflag = (cflag & ~termios.CSIZE) | termios.CS8
    cflag |= termios.CLOCAL | termios.CREAD
    cflag &= ~termios.PARENB  # 8N1 — bez parzystości (do zmiany, gdy protokół to sprecyzuje)
    cflag &= ~termios.CSTOPB  # 1 bit stopu
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


def try_once(path: str, baud: int, slave_id: int, reg: int, count: int) -> bytes | None:
    fd = open_serial(path, baud)
    try:
        request = build_read_holding_registers(slave_id, reg, count)
        os.write(fd, request)
        time.sleep(0.2)
        try:
            response = os.read(fd, 256)
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
    parser.add_argument("--baud", type=int, help="jeden baudrate zamiast domyślnej listy")
    parser.add_argument("--id", type=int, default=1, help="adres węzła Modbus (domyślnie 1)")
    parser.add_argument("--reg", type=int, default=0, help="adres rejestru do odczytu (domyślnie 0)")
    parser.add_argument("--count", type=int, default=1, help="liczba rejestrów do odczytu (domyślnie 1)")
    args = parser.parse_args()

    ports = [args.port] if args.port else discover_ports()
    if not ports:
        print("Brak /dev/ttyUSB*/ttyACM* — podłącz konwerter USB-RS485 i uruchom ponownie.")
        return 1

    bauds = [args.baud] if args.baud else DEFAULT_BAUDS

    print(f"Porty: {ports}")
    print(f"Baudrate'y: {bauds}")
    print(f"Adres węzła: {args.id}, rejestr: {args.reg}, liczba: {args.count}")
    print("Szukam odpowiedzi (Ctrl+C żeby przerwać)...\n")

    for path in ports:
        for baud in bauds:
            label = f"{path} @ {baud} id={args.id}"
            try:
                response = try_once(path, baud, args.id, args.reg, args.count)
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
        "serwa, zamianę A/B, czy adres węzła 1 to faktycznie fabryczny domyślny "
        "dla SM45BL (do potwierdzenia w dokumentacji), czy port w ogóle działa "
        "(np. echo testowe na spięte razem TX/RX, jeśli to możliwe na konwerterze)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
