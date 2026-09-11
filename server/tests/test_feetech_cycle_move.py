"""main._feetech_cycle_move / _feetech_move_to_and_wait (temat L, etap 4 —
osie FEETECH pełnoprawne w cyklu maszyny; limit obciążenia dopisany
2026-09-12) — bez prawdziwego portu, FeetekDriver podstawiony fake'iem
(jak test_feetech_status.py)."""

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
    """`moving_then_stop`: ile razy `is_moving()` ma zwrócić True przed
    False (domyślnie 1 — jeden odczyt w ruchu, potem zatrzymane). `load`:
    stała wartość zwracana przez `read_position_and_load()`."""

    def __init__(self, calls, moving_then_stop=1, load=0, never_stops=False):
        self.calls = calls
        self.moving_then_stop = moving_then_stop
        self.load = load
        self.never_stops = never_stops

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def move_to(self, servo_id, position, speed=100, acc=20):
        self.calls.append(("move_to", servo_id, position, speed, acc))

    def read_position_and_load(self, servo_id):
        self.calls.append(("read", servo_id))
        return (0, self.load)

    def is_moving(self, servo_id):
        if self.never_stops:
            return True
        if self.moving_then_stop > 0:
            self.moving_then_stop -= 1
            return True
        return False

    def stop_position_move(self, servo_id, speed=100, acc=20):
        self.calls.append(("stop_position_move", servo_id, speed, acc))


def _axis(mm_per_rev=1.0, feetech_id=1, speed=100, acc=20, load_limit=None):
    return axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=-9, soft_max=-1,
        mm_per_rev=mm_per_rev, driver=axes_mod.DRIVER_FEETECH, feetech_id=feetech_id,
        feetech_speed=speed, feetech_acc=acc, feetech_load_limit=load_limit,
    )


def _with_axis(cfg, fn):
    original = dict(main.machine.axes)
    main.machine.axes = {**original, "docisk": cfg}
    try:
        fn()
    finally:
        main.machine.axes = original


def test_cycle_move_przelicza_mm_na_rejestr_i_czeka_na_koniec(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, moving_then_stop=0))
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._feetech_cycle_move("docisk", -1.0))

    _with_axis(_axis(mm_per_rev=1.0, speed=333, acc=77), run)

    assert calls[0] == ("move_to", 1, -main.COUNTS_PER_REV, 333, 77)
    assert ("read", 1) in calls


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


def test_move_to_and_wait_timeout_rzuca_feetekerror(monkeypatch):
    """Timeout testowany bezpośrednio na `_feetech_move_to_and_wait` (nie
    przez `_feetech_cycle_move`) z krótkim `timeout_s`/`poll_interval_s` —
    inaczej test czekałby realne 10s (domyślny timeout produkcyjny)."""
    from app.feetech_driver import FeetekError

    calls = []
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, never_stops=True))
    with pytest.raises(FeetekError, match="czas oczekiwania"):
        main._feetech_move_to_and_wait(
            1, 0, 100, 20, None, timeout_s=0.05, poll_interval_s=0.01
        )


# --- limit obciążenia (zabezpieczenie awaryjne, decyzja 2026-09-12) --------


def test_cycle_move_bez_limitu_ignoruje_wysokie_obciazenie(monkeypatch):
    """load_limit=None (domyślne) — RUCH ma normalnie dojechać, nawet przy
    dużym obciążeniu."""
    calls = []
    monkeypatch.setattr(
        main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, moving_then_stop=0, load=9000)
    )
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._feetech_cycle_move("docisk", 0.0))  # nie rzuca

    _with_axis(_axis(load_limit=None), run)


def test_cycle_move_z_limitem_przerywa_ruch_przy_przeciazeniu(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, moving_then_stop=5, load=1500)
    )
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        with pytest.raises(MachineError, match="przeciążenie"):
            asyncio.run(main._feetech_cycle_move("docisk", 0.0))

    _with_axis(_axis(speed=333, acc=77, load_limit=1000), run)

    assert ("stop_position_move", 1, 333, 77) in calls


def test_cycle_move_z_limitem_ponizej_progu_dojezdza_normalnie(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main, "FeetekDriver", lambda *a, **k: _FakeDriver(calls, moving_then_stop=0, load=500)
    )
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")

    def run():
        asyncio.run(main._feetech_cycle_move("docisk", 0.0))  # nie rzuca

    _with_axis(_axis(load_limit=1000), run)

    assert not any(c[0] == "stop_position_move" for c in calls)
