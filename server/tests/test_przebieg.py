"""Testy nagrywania przebiegu momentu/pozycji (ekran /sila) — GET /api/przebieg.

Zgłoszone przy maszynie 2026-09-01: moment i prędkość zmieniają się za
szybko, żeby obserwować je na żywo (zwłaszcza przy operacji SMART) — trzeba
dać się to przeanalizować po fakcie, osobno dla każdej operacji programu.
"""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app.machine import MachineState, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_poll_status_bazowy_nic_nie_robi():
    """Bez domyślnego poll_status w klasie bazowej _poll_loop wywalałby się
    AttributeError w trybie symulacji, zanim doszedłby do _record_sample()."""
    m = SimulatedMachine()
    asyncio.run(m.poll_status())


def test_nie_nagrywa_w_spoczynku():
    m = SimulatedMachine()
    m.status.state = MachineState.READY
    m._record_sample()
    m._record_sample()
    assert m.recording == []


def test_nagrywa_probki_w_running():
    m = SimulatedMachine()
    m.status.state = MachineState.RUNNING
    m.status.current_op = 1
    m.status.torque = {"x": 5.0, "y": 0.0, "z": 0.0}
    m._record_sample()
    m._record_sample()

    assert len(m.recording) == 2
    assert m.recording[0]["op"] == 1
    assert m.recording[0]["torque"]["x"] == 5.0
    assert "t" in m.recording[0]


def test_nagrywa_tez_w_paused():
    m = SimulatedMachine()
    m.status.state = MachineState.PAUSED
    m._record_sample()
    assert len(m.recording) == 1


def test_nowe_uruchomienie_zaczyna_nagranie_od_zera():
    m = SimulatedMachine()
    m.status.state = MachineState.RUNNING
    m._record_sample()
    m._record_sample()
    assert len(m.recording) == 2

    m.status.state = MachineState.READY
    m._record_sample()
    assert len(m.recording) == 2, "nagranie zostaje widoczne po zakończeniu ruchu"

    m.status.state = MachineState.RUNNING
    m._record_sample()
    assert len(m.recording) == 1, "nowe uruchomienie czyści poprzednie nagranie"


def test_nagranie_ograniczone_dlugoscia():
    m = SimulatedMachine()
    m.status.state = MachineState.RUNNING
    for _ in range(6005):
        m._record_sample()
    assert len(m.recording) == 6000


def test_api_przebieg_zwraca_nagranie(client):
    from app import main

    main.machine.recording = [{"t": 0.0, "op": 1, "torque": {"x": 1.0}}]
    res = client.get("/api/przebieg")
    assert res.status_code == 200
    assert res.json()["samples"] == [{"t": 0.0, "op": 1, "torque": {"x": 1.0}}]
    main.machine.recording = []
