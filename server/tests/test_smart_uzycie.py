"""Użycie funkcji SMART: operacja w `.prg`, krok cyklu, wykonanie, moment.

Etapy 3 i 4 tematu K (`docs/funkcje-smart.md`). Pilnują dwóch rzeczy naraz:
że definicja SMART działa tak samo w programie technologa i w cyklu maszyny,
oraz że nigdzie nie udajemy kontroli siły tam, gdzie jej nie ma.
"""

import asyncio
import os

import pytest

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import cycle, smart  # noqa: E402
from app.machine import (  # noqa: E402
    ClearCoreMachine,
    MachineError,
    MachineState,
    SimulatedMachine,
)
from app.profiles import default_profiles  # noqa: E402
from app.program import (  # noqa: E402
    ProgramError,
    parse_program,
    serialize_program,
    smart_warnings,
)

HEADER = """[NAGLOWEK]
FORMAT;5
PROGRAM;000000000001
NAZWA;test
OBROTY_FREZU;12000
POSUW_ROBOCZY;300
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;10

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;MOMENT;PRZEJSCIA;PRZYROST;SMART;UWAGI
"""


def _prg(*rows: str) -> str:
    return HEADER + "\n".join(rows) + "\n"


# --- operacja SMART w programie technologa (etap 3) ------------------------


def test_smart_operation_parses():
    p = parse_program(_prg("1;PUNKT;10;20;-1;;;;;;;;;", "2;SMART;;;;;;;;;;;SMART-sila;po punkcie"))
    assert p.operations[1].op_type == "SMART"
    assert p.operations[1].smart == "SMART-sila"
    assert p.operations[1].note == "po punkcie"


def test_smart_operation_requires_definition_name():
    with pytest.raises(ProgramError) as exc:
        parse_program(_prg("1;SMART;;;;;;;;;;;;"))
    assert "wymaga wypełnionej kolumny SMART" in str(exc.value)


@pytest.mark.parametrize(
    "row, fragment",
    [
        ("1;SMART;10;;;;;;;;;;SMART-sila;", "nie przyjmuje współrzędnych"),
        ("1;SMART;;;;;;500;;;;;SMART-sila;", "nie przyjmuje POSUW"),
        ("1;SMART;;;;;;;;40;;;SMART-sila;", "nie przyjmuje MOMENT"),
        ("1;PUNKT;1;2;-1;;;;;;;;SMART-sila;", "dotyczy wyłącznie operacji SMART"),
    ],
)
def test_smart_operation_rejects_conflicting_columns(row, fragment):
    with pytest.raises(ProgramError) as exc:
        parse_program(_prg(row))
    assert fragment in str(exc.value)


def test_invalid_smart_name_rejected():
    with pytest.raises(ProgramError) as exc:
        parse_program(_prg("1;SMART;;;;;;;;;;;1sila;"))
    assert "nieprawidłowa nazwa definicji SMART" in str(exc.value)


def test_smart_operation_survives_roundtrip():
    text = _prg("1;SMART;;;;;;;;;;;SMART-sila;wlewek 1")
    again = parse_program(serialize_program(parse_program(text)))
    assert again.operations[0].smart == "SMART-sila"


def test_older_format_still_parses_without_smart_column():
    """Format 4 nie zna kolumny SMART — pliki technologa mają dalej działać."""
    text = _prg("1;PUNKT;1;2;-1;;;;;;;;;").replace(
        "FORMAT;5", "FORMAT;4"
    ).replace(";PRZYROST;SMART;UWAGI", ";PRZYROST;UWAGI").replace(
        "1;PUNKT;1;2;-1;;;;;;;;;", "1;PUNKT;1;2;-1;;;;;;;;"
    )
    p = parse_program(text)
    assert p.operations[0].smart == ""


def test_unknown_definition_is_a_warning_not_a_parse_error():
    """Plik `.prg` jest samodzielny — brak definicji ma dać się otworzyć."""
    p = parse_program(_prg("1;SMART;;;;;;;;;;;nie-ma-takiej;"))
    assert smart_warnings(p, ["SMART-sila"])
    assert smart_warnings(p, ["nie-ma-takiej"]) == []


# --- krok SMART w cyklu maszyny (etap 4) -----------------------------------


def test_cycle_smart_step_parses():
    c = cycle.parse_cycle({"steps": [{"lp": 1, "kind": "SMART", "smart": "SMART-sila"}]})
    assert c.steps[0].kind == cycle.STEP_SMART
    assert c.steps[0].smart == "SMART-sila"


@pytest.mark.parametrize(
    "step, fragment",
    [
        ({"lp": 1, "kind": "SMART"}, "wymaga wskazania definicji"),
        ({"lp": 1, "kind": "SMART", "smart": "zla nazwa"}, "nieprawidłowa nazwa"),
        ({"lp": 1, "kind": "SMART", "targets": {"x": 1}}, "nie przyjmuje pozycji"),
        ({"lp": 1, "kind": "PAUZA", "smart": "SMART-sila"}, "nie wywołuje funkcji SMART"),
    ],
)
def test_cycle_smart_step_validation(step, fragment):
    with pytest.raises(cycle.CycleError) as exc:
        cycle.parse_cycle({"steps": [step]})
    assert fragment in str(exc.value)


def test_cycle_warns_about_unknown_definition():
    c = cycle.parse_cycle({"steps": [{"lp": 1, "kind": "SMART", "smart": "nie-ma"}]})
    assert cycle.warnings(c, [], ["x", "y", "z"], ["SMART-sila"])
    assert cycle.warnings(c, [], ["x", "y", "z"], ["nie-ma"]) == []


# --- wykonanie w symulatorze ----------------------------------------------


def _definition(name="SMART-test", **params):
    body = {p.name: p.default for p in smart.PROCEDURES["ciecie_adaptacyjne"].params}
    body.update(params)
    return smart.SmartDefinition.from_dict(
        name, {"procedure": "ciecie_adaptacyjne", "params": body}
    )


def _machine(definitions=None):
    m = SimulatedMachine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")
    m.apply_smart({d.name: d for d in (definitions or [_definition()])})
    m.status.state = MachineState.READY
    return m


def test_smart_travels_full_distance_when_load_stays_low():
    m = _machine([_definition(dojazd_mm=-5.0, sila_pct=90.0, v_szybka=1000.0)])
    asyncio.run(m._run_smart("SMART-test"))
    assert round(m.status.z, 2) == -5.0


def test_smart_stops_and_retracts_when_load_reaches_threshold():
    """Sedno procedury: dojechać, zatrzymać się na progu, cofnąć narzędzie."""
    m = _machine(
        [
            _definition(
                dojazd_mm=-5.0, sila_pct=45.0, cofniecie_mm=1.0,
                v_szybka=1000.0, v_wolna=600.0,
            )
        ]
    )
    m.status.spindle_on = True  # symulowane obciążenie skrawaniem rośnie z głębokością
    asyncio.run(m._run_smart("SMART-test"))
    # zatrzymanie przed pełnym dojazdem i cofnięcie o 1 mm w górę
    assert -5.0 < m.status.z < 0.0
    assert m.status.z > -5.0 + 1.0


def test_smart_unknown_definition_is_a_clear_error():
    m = _machine()
    with pytest.raises(MachineError) as exc:
        asyncio.run(m._run_smart("nie-ma-takiej"))
    assert "nie ma definicji SMART" in str(exc.value)


def test_smart_step_in_cycle_runs_the_same_procedure():
    m = _machine([_definition(dojazd_mm=-2.0, sila_pct=90.0, v_szybka=1000.0)])
    m.apply_cycle(
        cycle.parse_cycle({"steps": [{"lp": 1, "kind": "SMART", "smart": "SMART-test"}]})
    )

    async def drive():
        await m.start_cycle()
        for _ in range(400):
            if m._run_task is None:
                return
            await asyncio.sleep(0.01)

    asyncio.run(drive())
    assert m.status.state == MachineState.READY
    assert round(m.status.z, 2) == -2.0


def test_smart_operation_in_program_runs_the_same_procedure():
    """Ta sama definicja użyta w programie technologa daje ten sam ruch."""
    m = _machine([_definition(dojazd_mm=-2.0, sila_pct=90.0, v_szybka=1000.0)])
    program = parse_program(_prg("1;SMART;;;;;;;;;;;SMART-test;"))
    asyncio.run(m._execute_operation(program, program.operations[0]))
    assert round(m.status.z, 2) == -2.0


# --- moment: symulacja kontra pomiar --------------------------------------


def test_simulated_torque_is_labelled_as_simulation():
    """Zmyślonych liczb nie wolno podać jako pomiaru — panel czyta to pole."""
    m = _machine()
    st = m.status.to_dict()
    assert st["torque_source"] == "symulacja"
    assert set(st["torque"]) == {"x", "y", "z"}


def test_simulated_z_torque_is_higher_going_up_than_down():
    """Asymetria grawitacyjna — inaczej ekran /sila nie miałby czego pokazać."""
    m = _machine()
    up = m._sim_torque("z", delta=1.0, feed=1000.0)
    down = m._sim_torque("z", delta=-1.0, feed=1000.0)
    assert up > down


def test_torque_from_bridge_is_labelled_as_measurement():
    """Gdy mostek zacznie wysyłać TRQ*, serwer ma to rozpoznać bez zmian."""
    m = ClearCoreMachine("127.0.0.1", 8500)

    async def fake_command(command):
        return "OK STATE=READY EN=1 X=0 Y=0 Z=0 SP=0 REL=- TRQX=1.5 TRQY=2 TRQZ=12.5"

    m._command = fake_command
    asyncio.run(m.poll_status())
    assert m.status.torque_source == "sterownik"
    assert m.status.torque["z"] == 12.5


def test_torque_absent_from_status_is_not_faked_as_zero():
    m = ClearCoreMachine("127.0.0.1", 8500)

    async def fake_command(command):
        return "OK STATE=READY EN=1 X=0 Y=0 Z=0 SP=0 REL=-"

    m._command = fake_command
    asyncio.run(m.poll_status())
    assert m.status.torque_source == "brak"


# --- sprzęt: SMART nie może przejść jako zwykły ruch -----------------------


def test_bridge_refuses_smart_step_instead_of_moving_blindly():
    """Cichy ruch bez kontroli siły byłby gorszy niż błąd — nóż w materiale."""
    m = ClearCoreMachine("127.0.0.1", 8500)
    step = cycle.CycleStep(lp=1, kind=cycle.STEP_SMART, smart="SMART-sila")
    with pytest.raises(MachineError) as exc:
        asyncio.run(m._run_cycle_step_body(step))
    assert "nie zna jeszcze komendy SMART" in str(exc.value)


def test_bridge_refuses_smart_operation_in_program():
    m = ClearCoreMachine("127.0.0.1", 8500)
    sent = []

    async def fake_command(command):
        sent.append(command)
        return "OK"

    m._command = fake_command
    program = parse_program(_prg("1;SMART;;;;;;;;;;;SMART-sila;"))
    with pytest.raises(MachineError):
        asyncio.run(m._run_program_operations(program))
    assert not any(c.startswith("MOVE") for c in sent)
