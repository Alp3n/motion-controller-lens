"""main._read_feetech_status (temat L, etap 2 kalibracji mm) — bez
prawdziwego portu, FeetekDriver podstawiony fake'iem (jak w
test_feetech_jog.py)."""

from __future__ import annotations

import os

import pytest

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import axes as axes_mod  # noqa: E402
from app import main  # noqa: E402
from app.feetech_driver import FeetekError  # noqa: E402


class _FakeDriver:
    def __init__(self, readings):
        self._readings = readings

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read_position_and_load(self, servo_id):
        result = self._readings[servo_id]
        if isinstance(result, Exception):
            raise result
        return result


def _axis(mm_per_rev):
    return axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=-9, soft_max=-1,
        mm_per_rev=mm_per_rev, driver=axes_mod.DRIVER_FEETECH, feetech_id=1,
    )


def test_dolicza_position_mm_dla_skonfigurowanej_osi(monkeypatch):
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver({1: (4096, 0)}))
    result = main._read_feetech_status({"docisk": 1}, {"docisk": _axis(mm_per_rev=1.0)})
    assert result["docisk"]["position"] == 4096
    assert result["docisk"]["position_mm"] == pytest.approx(1.0)


def test_bez_konfiguracji_osi_pomija_position_mm(monkeypatch):
    monkeypatch.setattr(main, "FeetekDriver", lambda *a, **k: _FakeDriver({1: (100, 0)}))
    result = main._read_feetech_status({"nieznana": 1}, {})
    assert result["nieznana"]["position"] == 100
    assert "position_mm" not in result["nieznana"]


def test_blad_serwa_nie_ma_position_mm(monkeypatch):
    monkeypatch.setattr(
        main, "FeetekDriver", lambda *a, **k: _FakeDriver({1: FeetekError("brak odpowiedzi (timeout)")})
    )
    result = main._read_feetech_status({"docisk": 1}, {"docisk": _axis(mm_per_rev=1.0)})
    assert "error" in result["docisk"]
    assert "position_mm" not in result["docisk"]
