"""JOG dla osi FEETECH — tryb koła (POST /api/machine/jog-feetech,
POST /api/machine/jog-feetech/stop) — poprawka "ruch skokami" 2026-09-11,
patrz docs/zmiany/jog-feetech-tryb-kolo.md.

Bez prawdziwego portu — `main._feetech_jog`/`_feetech_jog_stop` podstawione
fake'ami (jak `_exchange` w testach `FeetekDriver`), sprawdzamy routing,
walidację, znak prędkości (cw/ccw) i strażnika (`_feetech_wheel_deadline`,
`_feetech_wheel_stop_reason`)."""

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
    main._feetech_wheel_deadline.clear()
    yield
    main.machine.axes = original
    main._feetech_wheel_deadline.clear()


# --- POST /api/machine/jog-feetech (heartbeat, start/przytrzymanie) --------


def test_jog_nieznana_os_zwraca_404(client):
    res = client.post("/api/machine/jog-feetech", json={"axis": "nieistniejaca", "kierunek": "cw"})
    assert res.status_code == 404


def test_jog_bez_portu_zwraca_409(client, feetech_axis, monkeypatch):
    monkeypatch.setattr(main.config, "FEETECH_PORT", None)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 409
    assert "FEETECH_PORT" in res.json()["detail"]


def test_jog_cw_wysyla_dodatnia_predkosc(client, feetech_axis, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, speed_cw: calls.append((servo_id, speed_cw)))
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert calls == [(42, 100)]  # domyślne feetech_speed


def test_jog_ccw_wysyla_ujemna_predkosc(client, feetech_axis, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, speed_cw: calls.append((servo_id, speed_cw)))
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "ccw"})
    assert res.status_code == 200
    assert calls == [(42, -100)]  # domyślne feetech_speed


def test_jog_uzywa_predkosci_z_konfiguracji_osi(client, feetech_axis, monkeypatch):
    cfg = axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=-9, soft_max=-1, mm_per_rev=1.0,
        driver=axes_mod.DRIVER_FEETECH, feetech_id=42, feetech_speed=333, feetech_acc=77,
    )
    main.machine.axes = {**main.machine.axes, "testos": cfg}
    calls = []
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, speed_cw: calls.append((servo_id, speed_cw)))
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 200
    assert calls == [(42, 333)]


def test_jog_ustawia_termin_straznika(client, feetech_axis, monkeypatch):
    monkeypatch.setattr(main, "_feetech_jog", lambda servo_id, speed_cw: None)
    assert "testos" not in main._feetech_wheel_deadline
    client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert "testos" in main._feetech_wheel_deadline


def test_jog_bledny_kierunek_jest_odrzucony(client, feetech_axis):
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "gora"})
    assert res.status_code == 422


def test_jog_blad_sprzetu_zwraca_409(client, feetech_axis, monkeypatch):
    from app.feetech_driver import FeetekError

    def boom(servo_id, speed_cw):
        raise FeetekError("brak odpowiedzi z serwa (timeout)")

    monkeypatch.setattr(main, "_feetech_jog", boom)
    res = client.post("/api/machine/jog-feetech", json={"axis": "testos", "kierunek": "cw"})
    assert res.status_code == 409


# --- POST /api/machine/jog-feetech/stop (puszczenie przycisku) ------------


def test_stop_nieznana_os_zwraca_404(client):
    res = client.post("/api/machine/jog-feetech/stop", json={"axis": "nieistniejaca"})
    assert res.status_code == 404


def test_stop_woła_wheel_stop_i_czysci_straznika(client, feetech_axis, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_feetech_jog_stop", lambda servo_id: calls.append(servo_id))
    main._feetech_wheel_deadline["testos"] = 999999.0
    res = client.post("/api/machine/jog-feetech/stop", json={"axis": "testos"})
    assert res.status_code == 200
    assert calls == [42]
    assert "testos" not in main._feetech_wheel_deadline


def test_stop_bez_portu_nie_rzuca(client, feetech_axis, monkeypatch):
    monkeypatch.setattr(main.config, "FEETECH_PORT", None)
    res = client.post("/api/machine/jog-feetech/stop", json={"axis": "testos"})
    assert res.status_code == 200


def test_stop_blad_sprzetu_zwraca_409(client, feetech_axis, monkeypatch):
    from app.feetech_driver import FeetekError

    def boom(servo_id):
        raise FeetekError("brak odpowiedzi z serwa (timeout)")

    monkeypatch.setattr(main, "_feetech_jog_stop", boom)
    res = client.post("/api/machine/jog-feetech/stop", json={"axis": "testos"})
    assert res.status_code == 409


# --- _feetech_wheel_stop_reason (strażnik, czysta funkcja) -----------------


def _axis(soft_min=-9.0, soft_max=-1.0):
    return axes_mod.AxisConfig(
        length=10, home=axes_mod.HOME_PLUS, soft_min=soft_min, soft_max=soft_max, mm_per_rev=1.0,
    )


def test_wheel_stop_reason_brak_powodu_gdy_w_zakresie_i_przed_terminem():
    assert main._feetech_wheel_stop_reason(_axis(), -5.0, deadline=100.0, now=50.0) is None


def test_wheel_stop_reason_watchdog_po_terminie():
    assert main._feetech_wheel_stop_reason(_axis(), -5.0, deadline=100.0, now=101.0) == "watchdog"


def test_wheel_stop_reason_limit_poza_zakresem():
    assert main._feetech_wheel_stop_reason(_axis(), 5.0, deadline=100.0, now=50.0) == "limit"


def test_wheel_stop_reason_brak_pozycji_lub_konfiguracji_nie_rzuca():
    assert main._feetech_wheel_stop_reason(None, None, deadline=100.0, now=50.0) is None
    assert main._feetech_wheel_stop_reason(_axis(), None, deadline=100.0, now=50.0) is None
