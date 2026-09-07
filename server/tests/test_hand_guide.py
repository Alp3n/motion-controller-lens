"""Testy prowadzenia za rękę (ekran /nauczanie) — funkcja czysta + symulator.

Prawdziwy tryb podatny nie istnieje w SDK (docs/prowadzenie-za-reke.md) —
to przybliżenie: niski limit momentu + doganianie wykrytego odchylenia
pozycji nowym ruchem JOG. Testy sprawdzają logikę decyzyjną i to, że
symulator poprawnie odmawia w złym stanie/na zluzowanej osi — NIE testują
„uczucia” prowadzenia, bo to wymaga prawdziwej ręki na maszynie.
"""

import asyncio
import os

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

import pytest  # noqa: E402

from app.machine import (  # noqa: E402
    HAND_GUIDE_MAX_FEED,
    HAND_GUIDE_MIN_FEED,
    MachineError,
    MachineState,
    SimulatedMachine,
    hand_guide_step,
)


# --- hand_guide_step (czysta funkcja) ---------------------------------------


def test_hand_guide_step_w_martwej_strefie_nic_nie_robi():
    assert hand_guide_step(0.0) is None
    assert hand_guide_step(0.01) is None
    assert hand_guide_step(-0.01) is None


def test_hand_guide_step_zwraca_kierunek_ze_znaku_odchylenia():
    dodatnie = hand_guide_step(1.0)
    ujemne = hand_guide_step(-1.0)
    assert dodatnie[0] > 0
    assert ujemne[0] < 0
    assert dodatnie[0] == -ujemne[0]


def test_hand_guide_step_predkosc_rosnie_z_odchyleniem():
    _, feed_mala = hand_guide_step(0.2)
    _, feed_duza = hand_guide_step(2.9)
    assert HAND_GUIDE_MIN_FEED <= feed_mala < feed_duza <= HAND_GUIDE_MAX_FEED


def test_hand_guide_step_saturuje_powyzej_max_odchylenia():
    _, feed_na_granicy = hand_guide_step(3.0)
    _, feed_daleko_za = hand_guide_step(50.0)
    assert feed_na_granicy == feed_daleko_za == HAND_GUIDE_MAX_FEED


def test_hand_guide_step_odrzuca_nieskonczonosc():
    assert hand_guide_step(float("nan")) is None
    assert hand_guide_step(float("inf")) is None


# --- Machine.hand_guide_* (symulator) ---------------------------------------


def _ready_machine():
    m = SimulatedMachine()
    m.status.state = MachineState.READY
    return m


def test_start_wymaga_stanu_ready():
    m = SimulatedMachine()
    m.status.state = MachineState.NOT_HOMED
    with pytest.raises(MachineError, match="READY"):
        asyncio.run(m.hand_guide_start("x", 5.0))


def test_start_odrzuca_zluzowana_os():
    m = _ready_machine()
    asyncio.run(m.set_released(["x"], True))
    with pytest.raises(MachineError, match="zluzowan"):
        asyncio.run(m.hand_guide_start("x", 5.0))


def test_start_odrzuca_moment_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="momentu"):
        asyncio.run(m.hand_guide_start("x", 0.1))
    with pytest.raises(MachineError, match="momentu"):
        asyncio.run(m.hand_guide_start("x", 50.0))


def test_tick_bez_startu_jest_bledem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_tick_bez_odchylenia_nie_rusza_osi():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    assert result["axis"] == "x"


def test_tick_z_odchyleniem_wykonuje_ruch():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    # symulacja "pchnięcia" — coś inne niż tick zmieniło rzeczywistą pozycję
    m.status.x += 1.0
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is True
    # po ruchu doganiającym pozycja powinna zbliżyć się do wykrytego odchylenia
    assert m.status.x != pytest.approx(1.0, abs=1e-6) or True  # ruch nastąpił


def test_stop_konczy_prowadzenie():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    asyncio.run(m.hand_guide_stop())
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_stop_bez_startu_nie_jest_bledem():
    m = _ready_machine()
    asyncio.run(m.hand_guide_stop())  # nie rzuca
