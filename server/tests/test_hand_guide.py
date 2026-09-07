"""Testy prowadzenia za rękę (ekran /nauczanie) — funkcja czysta + symulator.

Trzecia wersja tego mechanizmu (2026-09-07, propozycja operatora po dwóch
odrzuconych podejściach — RELEASE i niski limit momentu, oba opisane w
docs/prowadzenie-za-reke.md): silnik zostaje na NORMALNYM limicie momentu
(nigdy nie dotykamy TrqGlobal, więc fault serwa z drugiej wersji jest
strukturalnie wykluczony). Wykrywamy małą zmianę odczytu momentu względem
wartości w spoczynku (histereza) — jedno wykryte naciśnięcie = jeden krok
JOG, potem trzeba puścić (siła wraca do spoczynku), zanim kolejne
naciśnięcie znów coś zrobi. Testy sprawdzają logikę decyzyjną (edge
detection) i to, że symulator poprawnie odmawia w złym stanie/na
zluzowanej osi — NIE testują „uczucia” prowadzenia, bo to wymaga
prawdziwej ręki na maszynie.
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


# --- hand_guide_step (czysta funkcja, wykrywanie zbocza) --------------------


def test_hand_guide_step_ponizej_progu_nic_nie_robi_gdy_uzbrojony():
    distance, armed = hand_guide_step(0.1, armed=True, threshold_pct=0.3)
    assert distance is None
    assert armed is True  # nadal uzbrojony, czeka na naciśnięcie


def test_hand_guide_step_powyzej_progu_rusza_i_rozbraja():
    distance, armed = hand_guide_step(0.5, armed=True, threshold_pct=0.3, step_mm=1.0)
    assert distance == 1.0
    assert armed is False  # zużyte - czeka na powrót do spoczynku


def test_hand_guide_step_kierunek_ze_znaku_delty():
    plus, _ = hand_guide_step(0.5, armed=True, threshold_pct=0.3, step_mm=1.0)
    minus, _ = hand_guide_step(-0.5, armed=True, threshold_pct=0.3, step_mm=1.0)
    assert plus == 1.0
    assert minus == -1.0


def test_hand_guide_step_nieuzbrojony_ignoruje_nawet_duza_delte():
    """Ciągły nacisk po zużyciu kroku nie generuje kolejnych kroków —
    trzeba wrócić do spoczynku, żeby uzbroić ponownie."""
    distance, armed = hand_guide_step(5.0, armed=False, threshold_pct=0.3)
    assert distance is None
    assert armed is False  # nadal poza progiem - nie uzbrojony


def test_hand_guide_step_powrot_do_spoczynku_uzbraja_ponownie():
    distance, armed = hand_guide_step(0.1, armed=False, threshold_pct=0.3)
    assert distance is None
    assert armed is True


def test_hand_guide_step_pelny_cykl_jedno_nacisniecie_jeden_krok():
    """Symuluje: spoczynek -> naciśnięcie -> krok -> przytrzymanie (nic) ->
    puszczenie -> ponowne naciśnięcie -> drugi krok."""
    armed = True
    # spoczynek
    d, armed = hand_guide_step(0.05, armed=armed, threshold_pct=0.3, step_mm=1.0)
    assert d is None and armed is True
    # naciśnięcie -> krok
    d, armed = hand_guide_step(0.5, armed=armed, threshold_pct=0.3, step_mm=1.0)
    assert d == 1.0 and armed is False
    # nadal trzyma -> nic (nieuzbrojony)
    d, armed = hand_guide_step(0.5, armed=armed, threshold_pct=0.3, step_mm=1.0)
    assert d is None and armed is False
    # puścił -> powrót do spoczynku, uzbraja
    d, armed = hand_guide_step(0.02, armed=armed, threshold_pct=0.3, step_mm=1.0)
    assert d is None and armed is True
    # nowe naciśnięcie -> drugi krok
    d, armed = hand_guide_step(-0.4, armed=armed, threshold_pct=0.3, step_mm=1.0)
    assert d == -1.0 and armed is False


def test_hand_guide_step_odrzuca_nieskonczonosc():
    distance, armed = hand_guide_step(float("nan"), armed=True)
    assert distance is None
    assert armed is True  # stan bez zmian przy złych danych


# --- Machine.hand_guide_* (symulator) ---------------------------------------


def _ready_machine():
    m = SimulatedMachine()
    m.status.state = MachineState.READY
    return m


def test_start_wymaga_stanu_ready():
    m = SimulatedMachine()
    m.status.state = MachineState.NOT_HOMED
    with pytest.raises(MachineError, match="READY"):
        asyncio.run(m.hand_guide_start("x"))


def test_start_odrzuca_zluzowana_os():
    m = _ready_machine()
    asyncio.run(m.set_released(["x"], True))
    with pytest.raises(MachineError, match="zluzowan"):
        asyncio.run(m.hand_guide_start("x"))


def test_start_odrzuca_prog_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="próg"):
        asyncio.run(m.hand_guide_start("x", threshold_pct=0.001))
    with pytest.raises(MachineError, match="próg"):
        asyncio.run(m.hand_guide_start("x", threshold_pct=50.0))


def test_start_odrzuca_posuw_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="posuw"):
        asyncio.run(m.hand_guide_start("x", feed=1.0))


def test_start_odrzuca_krok_poza_zakresem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="krok"):
        asyncio.run(m.hand_guide_start("x", step_mm=50.0))


def test_tick_bez_startu_jest_bledem():
    m = _ready_machine()
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_tick_bez_nacisku_nie_rusza_osi():
    """Zaraz po starcie moment = spoczynek (delta=0) — spokój."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x"))
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    assert result["axis"] == "x"
    assert result["armed"] is True


def test_tick_z_wystarczajaca_zmiana_momentu_wykonuje_krok():
    """Symulator ma niezerowy moment spoczynkowy domyślnie (np. tarcie) —
    liczy się ZMIANA względem wartości zapamiętanej przy starcie, nie
    wartość bezwzględna."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = baseline + 0.5
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is True
    assert result["armed"] is False


def test_tick_nie_powtarza_kroku_bez_powrotu_do_spoczynku():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = baseline + 0.5
    first = asyncio.run(m.hand_guide_tick())
    assert first["moving"] is True
    # moment nadal podniesiony, bez powrotu do spoczynku - drugi tick nic nie robi
    second = asyncio.run(m.hand_guide_tick())
    assert second["moving"] is False


def test_stop_konczy_prowadzenie():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x"))
    asyncio.run(m.hand_guide_stop())
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_stop_bez_startu_nie_jest_bledem():
    m = _ready_machine()
    asyncio.run(m.hand_guide_stop())  # nie rzuca
