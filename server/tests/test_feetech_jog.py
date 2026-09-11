"""JOG dla osi FEETECH (temat L, etap 2) — POST /api/machine/jog-feetech.

Bez prawdziwego portu — `main._feetech_jog` podstawiony fake'iem (jak
`_exchange` w testach `FeetekDriver`), sprawdzamy tylko routing,
walidację i znak kroku (cw/ccw)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import axes as axes_mod  # noqa: E402
from app import main  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def feetech_axis(monkeypatch):
    """Dodaje testową oś 'testos' (driver=feetech, id=42) do konfiguracji
    osi w pamięci — bez dotykania prawdziwego pliku/API `/api/axes`."""
    cfg = axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=-9, soft_max=-1, mm_per_rev=1.0,
        driver=axes_mod.DRIVER_FEETECH, feetech_id=42,
    )
    original = dict(main.machine.axes)
    main.machine.axes = {**original, "testos": cfg}
    monkeypatch.setattr(main.config, "FEETECH_PORT", "/dev/ttyUSB0")
    yield
    main.machine.axes = original


def test_jog_nieznana_os_zwraca_404(client):
    res = client.post("/api/machine/jog-feetech", json={"axis": "nieistniejaca", "kierunek": "cw"})
    assert res.status_code == 404


def test_jog_bez_portu_zwraca_409(client, feetech_axis, monkeypatch):
    monkeypatch.setattr(main.config, "FEETECH_PORT", None)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 409
    assert "FEETECH_PORT" in res.json()["detail"]


def test_jog_cw_wysyla_dodatni_krok(client, feetech_axis, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, counts: calls.append((servo_id, counts)) or 100)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 200
    assert res.json() == {"ok": True, "position": 100}
    assert calls == [(42, main.config.FEETECH_JOG_STEP)]


def test_jog_ccw_wysyla_ujemny_krok(client, feetech_axis, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, counts: calls.append((servo_id, counts)) or -50)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "ccw"})
    assert res.status_code == 200
    assert calls == [(42, -main.config.FEETECH_JOG_STEP)]


def test_jog_bledny_kierunek_jest_odrzucony(client, feetech_axis):
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "gora"})
    assert res.status_code == 422


def test_jog_blad_sprzetu_zwraca_409(client, feetech_axis, monkeypatch):
    from app.feetech_driver import FeetekError

    def boom(servo_id, counts):
        raise FeetekError("brak odpowiedzi z serwa (timeout)")

    monkeypatch.setattr(main, "_feetech_jog", boom)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 409
