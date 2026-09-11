"""main._feetech_cycle_move / _feetech_move_to_and_wait (temat L, etap 4 —
osie FEETECH pełnoprawne w cyklu maszyny, zamówienie 2026-09-11) — bez
prawdziwego portu, FeetekDriver podstawiony fake'iem (jak test_feetech_status.py)."""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import axes as axes_mod  # noqa: E402
from app import main  # noqa: E402
from app.machine import MachineError  # noqa: E402


class _FakeDriver:
    def __init__(self, calls, stops=True):
        self.calls = calls
        self.stops = stops

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def move_to(self, servo_id, position, speed=100, acc=20):
        self.calls.append(("move_to", servo_id, position, speed, acc))

    def wait_until_stopped(self, servo_id, timeout_s=10.0, poll_interval_s=0.1):
        self.calls.append(("wait", servo_id))
        return self.stops


def _axis(mm_per_rev=1.0, feetech_id=1, speed=100, acc=20):
    return axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=-9, soft_max=-1,
        mm_per_rev=mm_per_rev, driver=axes_mod.DRIVER_FEETECH, feetech_id=feetech_id,
        feetech_speed=speed, feetech_acc=acc,
    )


def _with_axis(cfg, fn):
    original = dict(main.machine.axes)
    main.machine.axes = {**original, "docisk": cfg}
    try:
        fn()
    finally:
        main.machine.axes = original


def test_cycle_move_przelicza_mm_na_rejestr_i_czeka(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls))
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._feetech_cycle_move("docisk", -1.0))

    _with_axis(_axis(mm_per_rev=1.0, speed=333, acc=77), run)

    assert calls == [
        ("move_to", 1, -main.COUNTS_PER_REV, 333, 77),
        ("wait", 1),
    ]


def test_cycle_move_nieznana_os_rzuca_machineerror(monkeypatch):
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")
    with pytest.raises(MachineError, match="FEETECH"):
        asyncio.run(main._feetech_cycle_move("nieistniejaca", 0.0))


def test_cycle_move_bez_portu_rzuca_machineerror(monkeypatch):
    monkeypatch.setattr(main.config, "FEETECH_PORT", None)

    def run():
        with pytest.raises(MachineError, match="FEETECH_PORT"):
            asyncio.run(main._feetech_cycle_move("docisk", 0.0))

    _with_axis(_axis(), run)


def test_cycle_move_timeout_rzuca_machineerror(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, stops=False))
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        with pytest.raises(MachineError, match="czas oczekiwania"):
            asyncio.run(main._feetech_cycle_move("docisk", 0.0))

    _with_axis(_axis(), run)
