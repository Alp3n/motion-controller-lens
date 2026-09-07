"""Testy prowadzenia za rękę (ekran /nauczanie) — funkcja czysta + symulator.

Trzecia wersja tego mechanizmu (2026-09-07/08, po dwóch odrzuconych
podejściach — RELEASE i niski limit momentu, oba opisane w
docs/prowadzenie-za-reke.md): silnik zostaje na NORMALNYM limicie momentu
(nigdy nie dotykamy TrqGlobal). Wykrywamy małą zmianę odczytu momentu
względem wartości w spoczynku (histereza) — jedno wykryte naciśnięcie =
jeden krok JOG, potem trzeba KILKA kolejnych odczytów w spoczynku z rzędu
(nie tylko jednego — pierwszy test na sprzęcie 2026-09-08 pokazał, że
pojedynczy przejściowy skok momentu tuż po ruchu bywa mylnie odczytany
jako nowe, przeciwne naciśnięcie), zanim kolejne naciśnięcie znów coś
zrobi. Testy sprawdzają logikę decyzyjną (edge detection + debounce) i to,
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
    HAND_GUIDE_SETTLE_TICKS,
    MachineError,
    MachineState,
    SimulatedMachine,
    hand_guide_step,
)


# --- hand_guide_step (czysta funkcja, wykrywanie zbocza + debounce) --------


def test_hand_guide_step_ponizej_progu_zwieksza_licznik_spoczynku():
    distance, settle = hand_guide_step(0.1, settle_count=0, threshold_pct=0.3)
    assert distance is None
    assert settle == 1


def test_hand_guide_step_licznik_spoczynku_nasyca_na_settle_ticks():
    distance, settle = hand_guide_step(
        0.1, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3
    )
    assert distance is None
    assert settle == HAND_GUIDE_SETTLE_TICKS  # nie rośnie w nieskończoność


def test_hand_guide_step_rusza_dopiero_po_pelnym_uspokojeniu():
    """Poniżej progu uspokojenia (settle_ticks) przekroczenie progu NIE
    rusza osią — to jest dokładnie naprawiony błąd z 2026-09-08: pojedynczy
    przejściowy skok tuż po ruchu nie może sam wywołać kolejnego kroku."""
    distance, settle = hand_guide_step(
        0.5, settle_count=HAND_GUIDE_SETTLE_TICKS - 1, threshold_pct=0.3, step_mm=1.0
    )
    assert distance is None
    assert settle == 0  # przerwane uspokajanie, trzeba zacząć liczyć od nowa


def test_hand_guide_step_rusza_i_zeruje_licznik_po_pelnym_uspokojeniu():
    distance, settle = hand_guide_step(
        0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0
    )
    assert distance == 1.0
    assert settle == 0


def test_hand_guide_step_kierunek_ze_znaku_delty():
    plus, _ = hand_guide_step(0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0)
    minus, _ = hand_guide_step(-0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0)
    assert plus == 1.0
    assert minus == -1.0


def test_hand_guide_step_przejsciowy_sygnal_tuz_po_ruchu_nie_wywoluje_kroku():
    """Odtwarza dokładnie zgłoszony scenariusz: krok, potem PRZED pełnym
    uspokojeniem chwilowy skok w przeciwną stronę (np. hamowanie JOG-a) —
    nie może sam wywołać kroku wstecz."""
    settle = HAND_GUIDE_SETTLE_TICKS
    # naciśnięcie -> krok, licznik wyzerowany
    d, settle = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == 1.0 and settle == 0
    # przejściowy skok w przeciwną stronę TUŻ po ruchu (np. hamowanie) - IGNOROWANY
    d, settle = hand_guide_step(-0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == 0


def test_hand_guide_step_pelny_cykl_jedno_nacisniecie_jeden_krok():
    """Symuluje: spoczynek -> naciśnięcie -> krok -> pełne uspokojenie ->
    ponowne naciśnięcie -> drugi krok."""
    settle = HAND_GUIDE_SETTLE_TICKS  # start "uspokojony"
    # spoczynek
    d, settle = hand_guide_step(0.05, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == HAND_GUIDE_SETTLE_TICKS
    # naciśnięcie -> krok
    d, settle = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == 1.0 and settle == 0
    # nadal trzyma -> nic, licznik zerowany za każdym razem
    d, settle = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == 0
    # puścił -> kilka odczytów w spoczynku z rzędu, aż uzbroi ponownie
    for _ in range(HAND_GUIDE_SETTLE_TICKS):
        d, settle = hand_guide_step(0.02, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
        assert d is None
    assert settle == HAND_GUIDE_SETTLE_TICKS
    # nowe naciśnięcie -> drugi krok
    d, settle = hand_guide_step(-0.4, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == -1.0 and settle == 0


def test_hand_guide_step_odrzuca_nieskonczonosc():
    distance, settle = hand_guide_step(float("nan"), settle_count=2)
    assert distance is None
    assert settle == 2  # stan bez zmian przy złych danych


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
    """Zaraz po starcie moment = spoczynek (delta=0) — spokój, uzbrojony."""
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


def test_tick_nie_powtarza_kroku_bez_pelnego_uspokojenia():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = baseline + 0.5
    first = asyncio.run(m.hand_guide_tick())
    assert first["moving"] is True
    # moment nadal podniesiony, bez powrotu do spoczynku - drugi tick nic nie robi
    second = asyncio.run(m.hand_guide_tick())
    assert second["moving"] is False


def test_tick_przejsciowy_skok_tuz_po_ruchu_nie_odwraca_kroku():
    """Odtwarza zgłoszenie 2026-09-08: krok w jedną stronę, zaraz potem
    przejściowy skok w przeciwną (np. hamowanie ruchu) - nie może sam
    wywołać kroku wstecz, bo oś jeszcze się nie uspokoiła."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = baseline + 0.5
    first = asyncio.run(m.hand_guide_tick())
    assert first["moving"] is True
    # zaraz po ruchu: przejściowy skok w PRZECIWNĄ stronę
    m.status.torque["x"] = baseline - 0.5
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
