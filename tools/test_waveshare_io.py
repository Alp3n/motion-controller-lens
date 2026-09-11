#!/usr/bin/env python3
"""Test łączności z modułami I/O Waveshare Modbus RTU (temat L).

Dwa konkretne moduły potwierdzone 2026-09-11:
    SKU 26244 — Modbus RTU IO 8CH (cyfrowy, 8DI/8DO)
    SKU 25821 — Modbus RTU Analog Input 8CH (analogowy, 12-bit)

Oba domyślnie: adres 1, baudrate 9600 (N,8,1) — INNY niż serwa FEETECH
(115200), więc to OSOBNE połączenie na tym samym porcie/magistrali.

**Uwaga — kolizja adresów jak przy serwach wczoraj:** oba moduły
fabrycznie mają prawdopodobnie ten sam adres (1). Jeśli podłączysz OBA
naraz przed zmianą adresu jednego z nich, żaden nie odpowie poprawnie
(kolizja na magistrali). Podłącz JEDEN na raz, ustal adres, dopiero potem
podłącz drugi.

Odczyt modułu analogowego jest POTWIERDZONY u źródła (instrukcja
producenta, zweryfikowane niezależnie przeliczeniem CRC16) — `--analog`.
Mapa rejestrów modułu cyfrowego NIE jest potwierdzona — `--digital-probe`
próbuje typowych adresów/funkcji (read coils, read discrete inputs) i
pokazuje surowe wyniki do interpretacji ręcznej.

Użycie:
    tools/test_waveshare_io.py --analog                # odczyt 8 kanałów analogowych
    tools/test_waveshare_io.py --digital-probe          # sondowanie modułu cyfrowego
    tools/test_waveshare_io.py /dev/ttyUSB0 --id 1 --analog
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from app import modbus_protocol as mp  # noqa: E402
from app.modbus_driver import ModbusDriver  # noqa: E402


def discover_ports() -> list[str]:
    return sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))


def run_analog(port: str, baud: int, slave_id: int) -> None:
    print(f"\n--- Moduł analogowy (SKU 25821), {port} @ {baud}, adres {slave_id} ---")
    try:
        with ModbusDriver(port, baud=baud) as driver:
            values = driver.read_analog_channels(slave_id)
        for i, v in enumerate(values):
            print(f"  kanał {i + 1}: {v} (surowa wartość rejestru — jednostka zależy od "
                  f"skonfigurowanego zakresu na module, domyślnie 0-20mA -> µA)")
    except mp.ModbusError as exc:
        print(f"  błąd: {exc}")


def run_digital_probe(port: str, baud: int, slave_id: int) -> None:
    print(f"\n--- Moduł cyfrowy (SKU 26244), {port} @ {baud}, adres {slave_id} — SONDOWANIE ---")
    print("  (mapa rejestrów NIEPOTWIERDZONA — to są próby, nie pewniki)")
    attempts = [
        ("read_coils(addr=0, count=8) — typowe DO", lambda d: d.read_coils(slave_id, 0, 8)),
        ("read_discrete_inputs(addr=0, count=8) — typowe DI", lambda d: d.read_discrete_inputs(slave_id, 0, 8)),
        ("read_holding_registers(addr=0x1000, count=1) — wg wzorca modułu analogowego", lambda d: d.read_holding_registers(slave_id, 0x1000, 1)),
        ("read_holding_registers(addr=0x4000, count=1) — adres urządzenia, wg wzorca analogowego", lambda d: d.read_holding_registers(slave_id, 0x4000, 1)),
    ]
    with ModbusDriver(port, baud=baud) as driver:
        for label, fn in attempts:
            try:
                result = fn(driver)
                print(f"  {label}: ODPOWIEDŹ {result}")
            except mp.ModbusError as exc:
                print(f"  {label}: błąd — {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", nargs="?", help="np. /dev/ttyUSB0 (domyślnie: skanuj wszystkie)")
    parser.add_argument("--baud", type=int, default=mp.DEFAULT_BAUD, help=f"domyślnie {mp.DEFAULT_BAUD}")
    parser.add_argument("--id", type=int, default=mp.DEFAULT_ADDRESS, help=f"domyślnie {mp.DEFAULT_ADDRESS}")
    parser.add_argument("--analog", action="store_true", help="odczytaj moduł analogowy (SKU 25821)")
    parser.add_argument("--digital-probe", action="store_true", help="sonduj moduł cyfrowy (SKU 26244)")
    parser.add_argument("--write-coil", type=int, metavar="ADRES",
                         help="zapisz coil pod danym adresem (do testu mapowania DO — patrz --state)")
    parser.add_argument("--set-address", type=int, metavar="NOWY_ADRES",
                         help="zmień adres urządzenia (rejestr 0x4000) — TYLKO gdy na magistrali "
                              "jest fizycznie podłączony JEDEN moduł (oba domyślnie mają adres 1)")
    parser.add_argument("--state", choices=["on", "off"], default="on",
                         help="stan dla --write-coil (domyślnie on)")
    args = parser.parse_args()

    if not args.analog and not args.digital_probe and args.write_coil is None and args.set_address is None:
        parser.error("podaj --analog i/lub --digital-probe i/lub --write-coil i/lub --set-address")
    if args.write_coil is not None and not args.port:
        parser.error("--write-coil wymaga podania konkretnego portu (nie skanowania)")
    if args.set_address is not None and not args.port:
        parser.error("--set-address wymaga podania konkretnego portu (nie skanowania)")

    ports = [args.port] if args.port else discover_ports()
    if not ports:
        print("Brak /dev/ttyUSB*/ttyACM* — podłącz konwerter i uruchom ponownie.")
        return 1

    for port in ports:
        if args.analog:
            run_analog(port, args.baud, args.id)
        if args.digital_probe:
            run_digital_probe(port, args.baud, args.id)

    if args.write_coil is not None:
        on = args.state == "on"
        print(f"\n--- Zapis coil {args.write_coil} = {args.state} na {ports[0]} @ {args.baud}, adres {args.id} ---")
        try:
            with ModbusDriver(ports[0], baud=args.baud) as driver:
                driver.write_single_coil(args.id, args.write_coil, on)
                readback = driver.read_coils(args.id, args.write_coil, 1)
            print(f"  zapisano, odczyt potwierdzający: coil {args.write_coil} = {readback[0]}")
        except mp.ModbusError as exc:
            print(f"  błąd: {exc}")

    if args.set_address is not None:
        print(f"\n--- Zmiana adresu {args.id} -> {args.set_address} na {ports[0]} @ {args.baud} ---")
        try:
            with ModbusDriver(ports[0], baud=args.baud) as driver:
                driver.write_single_register(args.id, mp.ADDR_DEVICE_ADDRESS, args.set_address)
                readback = driver.read_holding_registers(args.set_address, mp.ADDR_DEVICE_ADDRESS, 1)
            print(f"  zapisano, odczyt pod NOWYM adresem {args.set_address}: {readback[0]}")
        except mp.ModbusError as exc:
            print(f"  błąd: {exc}")

    print(
        "\nBrak odpowiedzi? Sprawdź: zasilanie modułu OSOBNE od RS485 (7-36V DC), "
        "zamianę A/B, czy oba moduły nie mają przypadkiem tego samego adresu "
        "fabrycznego (podłącz jeden na raz przy pierwszym teście)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
