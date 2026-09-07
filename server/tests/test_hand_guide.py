"""Testy prowadzenia za rękę (ekran /nauczanie) — funkcja czysta + symulator.

Prawdziwy tryb podatny nie istnieje w SDK (docs/prowadzenie-za-reke.md) —
to przybliżenie doprecyzowane przez operatora po pierwszym teście na
sprzęcie (2026-09-07): niski limit momentu + ruch dopiero, gdy zmierzony
moment sięgnie tego limitu (to jest sygnał „ktoś naciska”), z kierunkiem
ustalanym z przesunięcia pozycji. Testy sprawdzają logikę decyzyjną i to,
że symulator poprawnie odmawia w złym stanie/na zluzowanej osi — NIE
testują „uczucia” prowadzenia, bo to wymaga prawdziwej ręki na maszynie.
"""

import asyncio
import os

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

import pytest  # noqa: E402

from app.machine import (  # noqa: E402
    MachineError,
    MachineState,
    SimulatedMachine,
    hand_guide_step,
)


# --- hand_guide_step (czysta funkcja) ---------------------------------------


def test_hand_guide_step_wymaga_obu_warunkow():
    """Sam moment na limicie bez przesunięcia (kierunek nieznany) — nic.
    Samo przesunięcie bez momentu na limicie (nikt nie naciska) — nic."""
    assert hand_guide_step(0.0, torque_measured_pct=5.0, torque_limit_pct=5.0) is None
    assert hand_guide_step(1.0, torque_measured_pct=0.0, torque_limit_pct=5.0) is None


def test_hand_guide_step_rusza_gdy_oba_warunki_spelnione():
    step = hand_guide_step(1.0, torque_measured_pct=4.5, torque_limit_pct=5.0)
    assert step is not None
    distance, feed = step
    assert distance > 0
    assert feed > 0


def test_hand_guide_step_ponizej_progu_momentu_nic_nie_robi():
    """Moment poniżej progu (domyślnie 80% limitu) mimo przesunięcia — nic
    (odchylenie mogło powstać z innego powodu, nie z realnego nacisku)."""
    step = hand_guide_step(1.0, torque_measured_pct=1.0, torque_limit_pct=5.0)
    assert step is None


def test_hand_guide_step_kierunek_ze_znaku_odchylenia():
    dodatnie = hand_guide_step(1.0, torque_measured_pct=5.0, torque_limit_pct=5.0)
    ujemne = hand_guide_step(-1.0, torque_measured_pct=5.0, torque_limit_pct=5.0)
    assert dodatnie[0] > 0
    assert ujemne[0] < 0
    assert dodatnie[0] == -ujemne[0]


def test_hand_guide_step_moment_ujemny_liczy_sie_z_wartosci_bezwzglednej():
    """Znak odczytu momentu (kierunek nacisku serwa) nie ma znaczenia dla
    progu — liczy się, jak mocno serwo się wysila, nie w którą stronę."""
    step = hand_guide_step(1.0, torque_measured_pct=-4.9, torque_limit_pct=5.0)
    assert step is not None


def test_hand_guide_step_stale_dystans_i_posuw():
    step = hand_guide_step(
        1.0, torque_measured_pct=5.0, torque_limit_pct=5.0, step_mm=2.0, feed=300.0
    )
    assert step == (2.0, 300.0)


def test_hand_guide_step_odrzuca_nieskonczonosc():
    assert hand_guide_step(float("nan"), 5.0, 5.0) is None
    assert hand_guide_step(float("inf"), 5.0, 5.0) is None
    assert hand_guide_step(1.0, float("nan"), 5.0) is None


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


def test_start_odrzuca_posuw_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="posuw"):
        asyncio.run(m.hand_guide_start("x", 5.0, feed=1.0))


def test_start_odrzuca_krok_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="krok"):
        asyncio.run(m.hand_guide_start("x", 5.0, step_mm=50.0))


def test_tick_bez_startu_jest_bledem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_tick_bez_nacisku_nie_rusza_osi():
    """Brak przesunięcia i brak momentu (domyślnie 0 w symulatorze) — spokój."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    assert result["axis"] == "x"


def test_tick_samo_przesuniecie_bez_momentu_nie_rusza():
    """Symulator nie generuje realnego momentu z zewnętrznej siły — sam
    przesunięty encoder, bez momentu na limicie, ma zostać zignorowany.
    To jest właśnie naprawiony błąd zgłoszony 2026-09-07 (oś Z nie
    reagowała mimo przesunięcia, bo brakowało wysokiego momentu)."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    m.status.x += 1.0
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False


def test_tick_z_momentem_i_przesunieciem_wykonuje_ruch():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    m.status.x += 1.0
    m.status.torque["x"] = 4.8  # >= 80% z limitu 5.0
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is True


def test_stop_konczy_prowadzenie():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", 5.0))
    asyncio.run(m.hand_guide_stop())
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_stop_bez_startu_nie_jest_bledem():
    m = _ready_machine()
    asyncio.run(m.hand_guide_stop())  # nie rzuca
