#!/usr/bin/env python3
"""Mały, kontrolowany ruch serwa FEETECH — do sprawdzenia kierunku (temat L).

**Realnie rusza fizycznym serwem.** Domyślny krok jest mały (200 kroków
enkodera ≈ 17,6°) i wolny (niska prędkość/przyspieszenie), ale to i tak
prawdziwy ruch — uruchamiaj tylko, gdy jesteś przy maszynie i obserwujesz,
co się dzieje.

Użycie:
    tools/feetech_jog.py /dev/ttyUSB0 --id 1 --delta 200      # ruch +200
    tools/feetech_jog.py /dev/ttyUSB0 --id 1 --delta -200     # powrót

Wypisuje pozycję PRZED i PO ruchu (w krokach enkodera, 0-4095 na obrót —
NIE mm; przeliczenie na mm przez `mm_per_rev` z `config/axes.json` zostaje
na później, przy integracji `FeetekDriver` z `Machine`). Czeka na
zakończenie ruchu odpytując rejestr MOVING (nie zgaduje czasu z prędkości).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from app import feetech_protocol as fp  # noqa: E402
from app.feetech_driver import FeetekDriver, FeetekError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port", help="np. /dev/ttyUSB0")
    parser.add_argument("--id", type=int, required=True, help="ID serwa")
    parser.add_argument("--delta", type=int, required=True,
                         help="zmiana pozycji w krokach enkodera (może być ujemna)")
    parser.add_argument("--speed", type=int, default=80, help="prędkość rejestru (domyślnie 80, wolno)")
    parser.add_argument("--acc", type=int, default=15, help="przyspieszenie rejestru (domyślnie 15, łagodnie)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=10.0, help="max czas czekania na koniec ruchu [s]")
    args = parser.parse_args()

    try:
        with FeetekDriver(args.port, baud=args.baud) as driver:
            before = driver.read_position(args.id)
            target = before + args.delta
            print(f"Serwo {args.id}: pozycja przed ruchem = {before}")
            print(f"Cel: {target} (delta {args.delta:+d}), prędkość={args.speed}, przyspieszenie={args.acc}")
            driver.move_to(args.id, target, speed=args.speed, acc=args.acc)

            t0 = time.monotonic()
            while time.monotonic() - t0 < args.timeout:
                moving = driver.read_raw(args.id, fp.ADDR_MOVING, 1)[0]
                if not moving:
                    break
                time.sleep(0.1)
            else:
                print("UWAGA: przekroczono limit czasu czekania na koniec ruchu (--timeout) — sprawdzam pozycję mimo to.")

            after = driver.read_position(args.id)
            print(f"Pozycja po ruchu = {after} (zmiana rzeczywista: {after - before:+d})")
    except FeetekError as exc:
        print(f"Błąd: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
