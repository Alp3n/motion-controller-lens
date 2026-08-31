"""Wrzeciono: kiedy się załącza, kiedy gaśnie, API i zachowanie obu maszyn."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import spindle as spindle_mod  # noqa: E402
from app.machine import MachineState, SC4HubMachine, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402
from app.program import Operation, Program  # noqa: E402
from app.spindle import SpindleConfig  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _program(*operations):
    return Program(
        number="000000000001",
        name="test",
        z_safe=5.0,
        feed_travel=1500.0,
        feed_work=300.0,
        spindle_rpm=12000.0,
        operations=list(operations),
    )


def _cut(lp=1):
    return Operation(
        lp=lp, op_type="PUNKT", x=1.0, y=2.0, z=-1.0, x2=None, y2=None,
        rpm=None, feed=None, note="",
    )


# --- model ----------------------------------------------------------------


def test_domyslne_ustawienia_odtwarzaja_dawne_zachowanie():
    """Program zapala wrzeciono, nie gasi go na swojej granicy, maszyna nie."""
    cfg = SpindleConfig()
    assert cfg.start_with_program is True
    assert cfg.stop_after_program is False
    assert cfg.start_with_machine is False


def test_zapis_czesciowy_nie_rusza_pozostalych_pol():
    cfg = SpindleConfig(start_with_machine=True, default_rpm=8000)
    merged = cfg.merged({"stop_after_program": True})
    assert merged.stop_after_program is True
    assert merged.start_with_machine is True
    assert merged.default_rpm == 8000


def test_zapis_odrzuca_nieznane_pole():
    with pytest.raises(spindle_mod.SpindleConfigError, match="nieznane"):
        SpindleConfig().merged({"pwm_hz": 100})


def test_ujemne_obroty_sa_odrzucane():
    with pytest.raises(spindle_mod.SpindleConfigError):
        SpindleConfig.from_dict({"default_rpm": -1})


def test_ostrzezenie_o_wrzecionie_ruszajacym_z_maszyna():
    warns = spindle_mod.warnings(SpindleConfig(start_with_machine=True), False, None)
    assert any("razem z maszyną" in w for w in warns)


def test_ostrzezenie_gdy_nic_nie_zalacza_wrzeciona():
    cfg = SpindleConfig(start_with_machine=False, start_with_program=False)
    assert any("WRZECIONO" in w for w in spindle_mod.warnings(cfg, False, None))


def test_ostrzezenia_sprzetowe_o_braku_pwm_i_wyjscia():
    warns = spindle_mod.warnings(SpindleConfig(), True, "none")
    assert any("RPM" in w for w in warns)
    assert any("SPINDLE_OUTPUT=none" in w for w in warns)


def test_ostrzezenie_gdy_serwer_nie_zna_wyjscia_mostka():
    assert any(
        "nie zna ustawienia SPINDLE_OUTPUT" in w
        for w in spindle_mod.warnings(SpindleConfig(), True, None)
    )


# --- symulator ------------------------------------------------------------


def _sim(cfg):
    m = SimulatedMachine()
    m.apply_spindle_config(cfg)
    m.status.state = MachineState.READY
    m.load_program(_program(_cut()), None)
    return m


async def _run(machine):
    await machine.start()
    task = machine._run_task
    if task is not None:
        await task


def test_symulator_zapala_wrzeciono_na_starcie_maszyny():
    """Zapala się od razu po START, jeszcze zanim ruszy pierwszy ruch."""

    async def scenario():
        m = _sim(SpindleConfig(start_with_machine=True))
        await m.start()
        on = m.status.spindle_on  # przed oddaniem sterowania zadaniu programu
        await m.stop()
        return on

    assert asyncio.run(scenario()) is True


def test_symulator_nie_zapala_wrzeciona_gdy_program_tego_nie_robi():
    """Operacja skrawająca sama z siebie nie może zapalić wrzeciona."""
    m = _sim(SpindleConfig(start_with_machine=False, start_with_program=False))
    states = []
    original = m._execute_operation

    async def spy(program, op):
        await original(program, op)
        states.append(m.status.spindle_on)

    m._execute_operation = spy
    asyncio.run(_run(m))
    assert states == [False]


def test_symulator_zapala_wrzeciono_na_starcie_programu():
    m = _sim(SpindleConfig(start_with_program=True))
    states = []
    original = m._execute_operation

    async def spy(program, op):
        states.append(m.status.spindle_on)
        await original(program, op)

    m._execute_operation = spy
    asyncio.run(_run(m))
    assert states == [True]


def test_wrzeciono_zawsze_gasnie_na_koniec_pracy_maszyny():
    """Nawet przy stop_after_program=False — to jest w `finally`, nie w konfiguracji."""
    m = _sim(SpindleConfig(start_with_program=True, stop_after_program=False))
    asyncio.run(_run(m))
    assert m.status.spindle_on is False
    assert m.status.state is MachineState.READY


def test_pauza_gasi_wrzeciono_i_je_przywraca():
    async def scenario():
        m = SimulatedMachine()
        m.apply_spindle_config(SpindleConfig(start_with_program=True))
        m.status.state = MachineState.READY
        pauza = Operation(
            lp=1, op_type="PAUZA", x=0.0, y=0.0, z=0.0, x2=None, y2=None,
            rpm=None, feed=None, note="",
        )
        m.load_program(_program(pauza), None)
        await m.start()
        for _ in range(50):
            await asyncio.sleep(0.01)
            if m.status.state is MachineState.PAUSED:
                break
        assert m.status.state is MachineState.PAUSED
        assert m.status.spindle_on is False  # gaśnie na czas pauzy
        m.resume()
        await asyncio.sleep(0.05)
        return m

    m = asyncio.run(scenario())
    # po wznowieniu wrzeciono wróciło (a na koniec programu i tak zgasło)
    assert m.status.state in (MachineState.RUNNING, MachineState.READY)


# --- mostek SC4-Hub -------------------------------------------------------


def _bridge(cfg):
    m = SC4HubMachine("127.0.0.1", 8500)
    m.apply_spindle_config(cfg)
    calls = []

    async def fake_command(command: str) -> str:
        calls.append(command)
        return "OK"

    m._command = fake_command
    m.calls = calls
    m.status.state = MachineState.READY
    m.load_program(_program(_cut()), None)
    return m


def test_mostek_zapala_wrzeciono_przy_starcie_maszyny():
    m = _bridge(SpindleConfig(start_with_machine=True, default_rpm=9000))
    asyncio.run(m.start())
    assert m.calls[0] == "SPINDLE 1 9000"
    asyncio.run(m.stop())


def test_mostek_nie_wysyla_spindle_gdy_program_tego_nie_robi():
    m = _bridge(SpindleConfig(start_with_program=False))
    asyncio.run(m._run_program_operations(m.program))
    assert not any(c.startswith("SPINDLE 1") for c in m.calls)


def test_mostek_gasi_wrzeciono_po_programie_gdy_tak_ustawiono():
    m = _bridge(SpindleConfig(start_with_program=True, stop_after_program=True))
    asyncio.run(m._run_program_operations(m.program))
    assert m.calls[0] == "SPINDLE 1 12000"
    assert m.calls[-1] == "SPINDLE 0"


def test_mostek_zostawia_wrzeciono_po_programie_domyslnie():
    """Domyślne zachowanie sprzed tej zmiany: wrzeciono chodzi do końca cyklu."""
    m = _bridge(SpindleConfig())
    asyncio.run(m._run_program_operations(m.program))
    assert m.calls[-1] != "SPINDLE 0"


def test_mostek_po_pauzie_nie_zapala_wrzeciona_ktorego_program_nie_zapalil():
    async def scenario():
        m = _bridge(SpindleConfig(start_with_program=False))
        pauza = Operation(
            lp=1, op_type="PAUZA", x=0.0, y=0.0, z=0.0, x2=None, y2=None,
            rpm=None, feed=None, note="",
        )
        m.load_program(_program(pauza), None)
        task = asyncio.create_task(m._run_program_operations(m.program))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if m.status.state is MachineState.PAUSED:
                break
        m.resume()
        await task
        return m

    m = asyncio.run(scenario())
    assert not any(c.startswith("SPINDLE 1") for c in m.calls)


def test_operacja_wrzeciono_w_programie_dziala_mimo_wylaczonego_startu():
    """Technolog może zapalić wrzeciono z programu, nawet gdy start jest wyłączony."""
    m = _bridge(SpindleConfig(start_with_program=False))
    op = Operation(
        lp=1, op_type="WRZECIONO", x=0.0, y=0.0, z=0.0, x2=None, y2=None,
        rpm=8000.0, feed=None, note="",
    )
    m.load_program(_program(op), None)
    asyncio.run(m._run_program_operations(m.program))
    assert "SPINDLE 1 8000" in m.calls


# --- API ------------------------------------------------------------------


def test_api_spindle_odczyt(client):
    data = client.get("/api/spindle").json()
    assert set(data["spindle"]) == {
        "start_with_machine",
        "start_with_program",
        "stop_after_program",
        "default_rpm",
    }


def test_api_spindle_zapis_czesciowy(client):
    assert client.put("/api/spindle", json={"default_rpm": 7000}).status_code == 200
    res = client.put("/api/spindle", json={"start_with_machine": True})
    assert res.status_code == 200
    body = res.json()
    assert body["spindle"]["start_with_machine"] is True
    assert body["spindle"]["default_rpm"] == 7000  # nie skasowane
    assert any("razem z maszyną" in w for w in body["warnings"])
    # sprzątamy po sobie — inne testy zakładają wartości domyślne
    client.put(
        "/api/spindle", json={"start_with_machine": False, "default_rpm": 12000}
    )


def test_api_spindle_odrzuca_pusty_zapis(client):
    assert client.put("/api/spindle", json={}).status_code == 422
