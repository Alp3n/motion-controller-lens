"""Testy cyklu maszyny — model, plik, API oraz snapshot/restore profilu."""

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import cycle  # noqa: E402
from app.machine import MachineError, MachineState, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402
from app.profiles import default_profiles  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_cycle(client):
    """Przywraca cykl i zostawia maszynę bezczynną.

    Testy współdzielą jedną instancję maszyny z `app.main`, więc cykl
    zostawiony w ruchu blokowałby kolejne moduły („nie można ... w trakcie
    ruchu maszyny"). Sprzątanie jest tu, a nie w każdym teście z osobna.
    """
    before = client.get("/api/cycle").json()["cycle"]
    yield before
    client.post("/api/machine/stop")
    client.post("/api/machine/reset")
    client.put("/api/cycle", json={"name": before["name"], "steps": before["steps"]})


def _move(lp, **targets):
    return {"lp": lp, "kind": "RUCH", "targets": targets}


# --- model ----------------------------------------------------------------


def test_parse_minimal_cycle():
    c = cycle.parse_cycle(
        {
            "name": "test",
            "steps": [
                _move(1, x=10),
                {"lp": 2, "kind": "PROGRAM", "profile": "program"},
                {"lp": 3, "kind": "WYJSCIE", "output": "wyjscie_1", "output_on": True},
                {"lp": 4, "kind": "PAUZA"},
            ],
        }
    )
    assert len(c.steps) == 4
    assert c.uses_program() is True
    assert c.steps[0].targets == {"x": 10.0}


def test_cycle_without_program_step():
    c = cycle.parse_cycle({"steps": [_move(1, z=5)]})
    assert c.uses_program() is False


@pytest.mark.parametrize(
    "step, fragment",
    [
        ({"lp": 1, "kind": "NIEZNANY"}, "nieznany rodzaj kroku"),
        ({"lp": 1, "kind": "RUCH"}, "wymaga co najmniej jednej osi"),
        ({"lp": 1, "kind": "RUCH", "targets": {"x": 1}, "feed": 0}, "posuw"),
        ({"lp": 1, "kind": "PAUZA", "targets": {"x": 1}}, "nie przyjmuje pozycji"),
        ({"lp": 1, "kind": "WYJSCIE", "output_on": True}, "nieznane wyjście"),
        ({"lp": 1, "kind": "WYJSCIE", "output": "wyjscie_0"}, "wymaga stanu"),
        (
            {"lp": 1, "kind": "PAUZA", "output": "wyjscie_0", "output_on": True},
            "nie steruje wyjściem",
        ),
    ],
)
def test_invalid_step_rejected(step, fragment):
    with pytest.raises(cycle.CycleError) as exc:
        cycle.parse_cycle({"steps": [step]})
    assert fragment in str(exc.value)


def test_lp_must_be_continuous():
    with pytest.raises(cycle.CycleError) as exc:
        cycle.parse_cycle({"steps": [_move(1, x=1), _move(3, x=2)]})
    assert "numeracja LP" in str(exc.value)


def test_error_carries_step_number():
    with pytest.raises(cycle.CycleError) as exc:
        cycle.parse_cycle({"steps": [_move(1, x=1), {"lp": 2, "kind": "RUCH"}]})
    assert "krok 2" in str(exc.value)


def test_warnings_flag_unknown_profile_and_axis():
    c = cycle.parse_cycle(
        {"steps": [{"lp": 1, "kind": "RUCH", "targets": {"w": 1}, "profile": "nie_ma"}]}
    )
    out = cycle.warnings(c, ["globalny"], ["x", "y", "z"])
    assert any("nie istnieje" in w for w in out)
    assert any("nieskonfigurowane" in w for w in out)


# --- plik -----------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "cycle.json"
    original = cycle.parse_cycle({"name": "c", "steps": [_move(1, x=5), {"lp": 2, "kind": "PAUZA"}]})
    cycle.save(path, original)
    assert cycle.load(path).to_dict() == original.to_dict()


def test_load_without_file_gives_empty_cycle(tmp_path):
    assert cycle.load(tmp_path / "nie-ma.json").steps == []


def test_broken_file_is_an_error_not_a_silent_default(tmp_path):
    path = tmp_path / "cycle.json"
    path.write_text("{to nie jest json", encoding="utf-8")
    with pytest.raises(cycle.CycleError):
        cycle.load(path)


# --- snapshot/restore profilu ---------------------------------------------


def _machine_with_cycle(steps, active="globalny"):
    m = SimulatedMachine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), active)
    m.apply_cycle(cycle.parse_cycle({"steps": steps}))
    m.status.state = MachineState.READY
    return m


def test_step_profile_applies_only_during_the_step():
    """Profil kroku obowiązuje w kroku i znika po nim."""
    seen = []
    m = _machine_with_cycle([_move(1, x=1), _move(2, x=2)])
    m.cycle.steps[0].profile = "program"

    original_move = m._move_to

    async def spy(x, y, z, feed):
        seen.append(m.active_profile)
        await original_move(x, y, z, feed)

    m._move_to = spy
    asyncio.run(_drive(m))
    assert seen == ["program", "globalny"]
    assert m.active_profile == "globalny"


def test_profile_restored_after_error_in_step():
    """Błąd w trakcie kroku nie zostawia maszyny na profilu tego kroku."""
    from app import axes as axes_mod

    m = _machine_with_cycle([_move(1, x=999)])  # poza limitem -> błąd w kroku
    m.cycle.steps[0].profile = "program"
    m.apply_axis_config(
        axes_mod.parse_axes(
            {
                a: {
                    "length": 100,
                    "home": "srodek",
                    "soft_min": -50,
                    "soft_max": 50,
                    "mm_per_rev": 5,
                }
                for a in ("x", "y", "z")
            }
        )
    )
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.ALARM
    assert m.active_profile == "globalny"


def test_profile_restored_after_cancellation():
    """STOP w trakcie kroku też przywraca profil — to jest sedno wymogu.

    Bez `finally` przerwany program detalu zostawiłby maszynę na swoich
    parametrach (np. 10% momentu) i kolejne ruchy poszłyby z nimi po cichu.
    """
    m = _machine_with_cycle([_move(1, x=50)])
    m.cycle.steps[0].profile = "program"
    m.cycle.steps[0].feed = 60  # wolno, żeby zdążyć przerwać

    async def run_and_cancel():
        await m.start_cycle()
        await asyncio.sleep(0.1)
        assert m.active_profile == "program"  # w trakcie kroku
        await m.stop()
        await asyncio.sleep(0.05)

    asyncio.run(run_and_cancel())
    assert m.active_profile == "globalny"


async def _drive(m):
    await m.start_cycle()
    for _ in range(400):
        if m._run_task is None:
            break
        await asyncio.sleep(0.01)


# --- wykonanie kroków -----------------------------------------------------


def test_output_step_sets_output():
    m = _machine_with_cycle(
        [{"lp": 1, "kind": "WYJSCIE", "output": "wyjscie_1", "output_on": True}]
    )
    asyncio.run(_drive(m))
    assert m.status.outputs["wyjscie_1"] is True
    assert m.status.state == MachineState.READY


def test_program_step_nie_wraca_do_zera():
    """Regresja 2026-09-05: krok PROGRAM cyklu wracał do (0,0) po każdym
    uruchomieniu programu detalu, mimo że zaraz potem jedzie kolejny krok
    cyklu - zbędny nawrót przez zero marnował czas. Powrót do zera ma sens
    tylko przy samodzielnym uruchomieniu programu (`_run_program`)."""
    from app.program import Operation, Program

    program = Program(
        number="1", name="test", spindle_rpm=12000,
        feed_work=300, feed_travel=3000, z_safe=10,
        operations=[Operation(lp=1, op_type="PUNKT", x=5, y=5, z=-1)],
    )
    m = _machine_with_cycle([{"lp": 1, "kind": "PROGRAM"}])
    m._program = program
    asyncio.run(_drive(m))
    assert (round(m.status.x, 3), round(m.status.y, 3)) == (5.0, 5.0)


def test_move_step_moves_only_named_axes():
    m = _machine_with_cycle([_move(1, x=5)])
    m.status.y = 3.0
    asyncio.run(_drive(m))
    assert round(m.status.x, 3) == 5.0
    assert round(m.status.y, 3) == 3.0  # oś pominięta zostaje na miejscu


def test_move_step_respects_soft_limits():
    from app import axes as axes_mod

    m = _machine_with_cycle([_move(1, x=999)])
    m.apply_axis_config(
        axes_mod.parse_axes(
            {
                a: {
                    "length": 100,
                    "home": "srodek",
                    "soft_min": -50,
                    "soft_max": 50,
                    "mm_per_rev": 5,
                }
                for a in ("x", "y", "z")
            }
        )
    )
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.ALARM
    assert "limitem programowym" in m.status.alarm_message


# --- tryb automatyczny (temat F) -------------------------------------------


def test_start_cycle_loop_repeats_until_stopped():
    """`loop=True` musi realnie powtarzać cykl, nie tylko ustawiać flagę.

    Krok celowo wraca za każdym razem do tego samego punktu (x=1) — od
    drugiego przebiegu to ruch o zerowym dystansie. `asyncio.wait_for`
    to twardy limit czasu: bez punktu zawieszenia na taki krok (patrz test
    `test_start_cycle_loop_yields_even_without_real_movement` niżej) ten test
    zawiesiłby cały przebieg testów zamiast po prostu nie przejść.
    """
    m = _machine_with_cycle([_move(1, x=1)])
    m.cycle.steps[0].feed = 6000  # szybko — kilka przebiegów w rozsądnym czasie

    calls = []
    original_move = m._move_to

    async def spy(x, y, z, feed):
        calls.append(1)
        await original_move(x, y, z, feed)

    m._move_to = spy

    async def drive_loop():
        await m.start_cycle(loop=True)
        assert m.status.cycle_loop is True
        for _ in range(500):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.01)
        assert len(calls) >= 3, "cykl nie powtórzył się mimo loop=True"
        await m.stop()
        count_after_stop = len(calls)
        await asyncio.sleep(0.05)
        assert len(calls) == count_after_stop, "STOP nie przerwał pętli"

    asyncio.run(asyncio.wait_for(drive_loop(), timeout=5))
    assert m.status.state == MachineState.ALARM
    assert m.status.cycle_loop is False


def test_start_cycle_loop_yields_even_without_real_movement():
    """Krok bez żadnego realnego ruchu (WYJSCIE) nie może zawiesić event
    loopa — bez punktu zawieszenia w pętli automatycznej taki krok mrozi
    cały serwer (żadne inne żądanie HTTP ani WebSocket nie dostają
    sterowania), bo Python nigdy nie oddaje kontroli dobrowolnie.
    Znalezione i naprawione przy pisaniu tego etapu (`asyncio.sleep(0)` po
    każdym kroku w `_run_cycle`).
    """
    m = _machine_with_cycle(
        [{"lp": 1, "kind": "WYJSCIE", "output": "wyjscie_0", "output_on": True}]
    )
    calls = []
    original = m._execute_cycle_step

    async def spy(step):
        calls.append(1)
        await original(step)

    m._execute_cycle_step = spy

    async def drive_loop():
        await m.start_cycle(loop=True)
        for _ in range(500):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.01)
        assert len(calls) >= 3, "pętla nie wykonała kilku przebiegów"
        await m.stop()

    asyncio.run(asyncio.wait_for(drive_loop(), timeout=5))
    assert m.status.state == MachineState.ALARM


def test_start_cycle_without_loop_runs_once():
    """Domyślne zachowanie (bez `loop`) nie mogło się zmienić."""
    m = _machine_with_cycle([_move(1, x=1)])
    calls = []
    original_move = m._move_to

    async def spy(x, y, z, feed):
        calls.append(1)
        await original_move(x, y, z, feed)

    m._move_to = spy
    asyncio.run(_drive(m))
    assert len(calls) == 1
    assert m.status.state == MachineState.READY
    assert m.status.cycle_loop is False


# --- API ------------------------------------------------------------------


def test_get_cycle_empty_by_default(client):
    data = client.get("/api/cycle").json()
    assert data["cycle"]["steps"] == []
    assert "RUCH" in data["step_kinds"]


def test_put_and_get_cycle(client, restore_cycle):
    steps = [_move(1, x=1), {"lp": 2, "kind": "PAUZA"}]
    res = client.put("/api/cycle", json={"name": "prod", "steps": steps})
    assert res.status_code == 200, res.text
    assert client.get("/api/cycle").json()["cycle"]["name"] == "prod"


def test_put_cycle_rejects_invalid_step(client, restore_cycle):
    res = client.put("/api/cycle", json={"name": "x", "steps": [{"lp": 1, "kind": "RUCH"}]})
    assert res.status_code == 422
    assert "wymaga co najmniej jednej osi" in res.json()["detail"]


def _home(client):
    """Cykl wymaga stanu READY — bazowanie jest warunkiem wstępnym."""
    assert client.post("/api/machine/home").status_code == 200
    for _ in range(200):
        if client.get("/api/status").json()["state"] == "READY":
            return
        time.sleep(0.05)
    raise AssertionError("bazowanie symulatora nie zakończyło się")


def test_start_cycle_without_definition_is_rejected(client, restore_cycle):
    client.put("/api/cycle", json={"name": "", "steps": []})
    _home(client)
    res = client.post("/api/machine/cycle/start")
    assert res.status_code == 409
    assert "nie jest zdefiniowany" in res.json()["detail"]


def test_start_cycle_needs_program_when_it_calls_one():
    """Cykl z krokiem PROGRAM nie wystartuje bez załadowanego programu.

    Na własnej instancji, nie przez API: maszyna w `app.main` jest wspólna
    dla wszystkich testów i może mieć program załadowany przez inny moduł.
    """
    m = _machine_with_cycle([{"lp": 1, "kind": "PROGRAM"}])
    with pytest.raises(MachineError) as exc:
        asyncio.run(m.start_cycle())
    assert "program detalu" in str(exc.value)


def test_start_cycle_endpoint_accepts_loop_flag(client, restore_cycle):
    steps = [{"lp": 1, "kind": "RUCH", "targets": {"x": 1}, "feed": 6000}]
    assert client.put("/api/cycle", json={"name": "", "steps": steps}).status_code == 200
    _home(client)

    res = client.post("/api/machine/cycle/start", json={"loop": True})
    assert res.status_code == 200, res.text
    time.sleep(0.05)
    assert client.get("/api/status").json()["cycle_loop"] is True

    assert client.post("/api/machine/stop").status_code == 200
    assert client.get("/api/status").json()["cycle_loop"] is False


def test_cycle_page_is_served(client):
    res = client.get("/cycle")
    assert res.status_code == 200
    assert "Cykl maszyny" in res.text
    assert "/static/cycle.js" in res.text
