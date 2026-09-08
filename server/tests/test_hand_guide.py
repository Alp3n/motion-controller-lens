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
zrobi. Rejestr spoczynku dryfuje do aktualnego odczytu TYLKO gdy jesteśmy
w spoczynku (nigdy podczas wykrytego nacisku — druga poprawka 2026-09-08,
patrz `test_tick_nie_aktualizuje_spoczynku_w_trakcie_wykrytego_nacisku`).
Testy sprawdzają logikę decyzyjną (edge detection + debounce + dryf
rejestru) i to, że symulator poprawnie odmawia w złym stanie/na
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
    HAND_GUIDE_SETTLE_TICKS,
    MachineError,
    MachineState,
    SimulatedMachine,
    hand_guide_step,
)


# --- hand_guide_step (czysta funkcja, wykrywanie zbocza + debounce) --------


def test_hand_guide_step_ponizej_progu_zwieksza_licznik_i_zglasza_spoczynek():
    distance, settle, at_rest = hand_guide_step(0.1, settle_count=0, threshold_pct=0.3)
    assert distance is None
    assert settle == 1
    assert at_rest is True


def test_hand_guide_step_licznik_spoczynku_nasyca_na_settle_ticks():
    distance, settle, at_rest = hand_guide_step(
        0.1, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3
    )
    assert distance is None
    assert settle == HAND_GUIDE_SETTLE_TICKS  # nie rośnie w nieskończoność
    assert at_rest is True


def test_hand_guide_step_rusza_dopiero_po_pelnym_uspokojeniu():
    """Poniżej progu uspokojenia (settle_ticks) przekroczenie progu NIE
    rusza osią — to jest dokładnie naprawiony błąd z 2026-09-08: pojedynczy
    przejściowy skok tuż po ruchu nie może sam wywołać kolejnego kroku."""
    distance, settle, at_rest = hand_guide_step(
        0.5, settle_count=HAND_GUIDE_SETTLE_TICKS - 1, threshold_pct=0.3, step_mm=1.0
    )
    assert distance is None
    assert settle == 0  # przerwane uspokajanie, trzeba zacząć liczyć od nowa
    assert at_rest is False  # nie w spoczynku - rejestr NIE wolno aktualizować


def test_hand_guide_step_rusza_i_zeruje_licznik_po_pelnym_uspokojeniu():
    distance, settle, at_rest = hand_guide_step(
        0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0
    )
    assert distance == -1.0  # znak odwrócony względem delty, patrz docstring
    assert settle == 0
    assert at_rest is False


def test_hand_guide_step_kierunek_odwrocony_wzgledem_znaku_delty():
    """Zgłoszone i potwierdzone przy maszynie 2026-09-08: naciśnięcie
    ruszało oś w przeciwną stronę — znak momentu w SDK jest przeciwny do
    kierunku pchnięcia (serwo opiera się naciskowi)."""
    plus, _, _ = hand_guide_step(0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0)
    minus, _, _ = hand_guide_step(-0.5, settle_count=HAND_GUIDE_SETTLE_TICKS, threshold_pct=0.3, step_mm=1.0)
    assert plus == -1.0
    assert minus == 1.0


def test_hand_guide_step_przejsciowy_sygnal_tuz_po_ruchu_nie_wywoluje_kroku():
    """Odtwarza dokładnie zgłoszony scenariusz: krok, potem PRZED pełnym
    uspokojeniem chwilowy skok w przeciwną stronę (np. hamowanie JOG-a) —
    nie może sam wywołać kroku wstecz."""
    settle = HAND_GUIDE_SETTLE_TICKS
    # naciśnięcie -> krok, licznik wyzerowany
    d, settle, at_rest = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == -1.0 and settle == 0 and at_rest is False
    # przejściowy skok w przeciwną stronę TUŻ po ruchu (np. hamowanie) - IGNOROWANY
    d, settle, at_rest = hand_guide_step(-0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == 0 and at_rest is False


def test_hand_guide_step_pelny_cykl_jedno_nacisniecie_jeden_krok():
    """Symuluje: spoczynek -> naciśnięcie -> krok -> pełne uspokojenie ->
    ponowne naciśnięcie -> drugi krok."""
    settle = HAND_GUIDE_SETTLE_TICKS  # start "uspokojony"
    # spoczynek
    d, settle, at_rest = hand_guide_step(0.05, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == HAND_GUIDE_SETTLE_TICKS and at_rest is True
    # naciśnięcie -> krok (znak odwrócony względem delty)
    d, settle, at_rest = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == -1.0 and settle == 0 and at_rest is False
    # nadal trzyma -> nic, licznik zerowany za każdym razem
    d, settle, at_rest = hand_guide_step(0.5, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d is None and settle == 0 and at_rest is False
    # puścił -> kilka odczytów w spoczynku z rzędu, aż uzbroi ponownie
    for _ in range(HAND_GUIDE_SETTLE_TICKS):
        d, settle, at_rest = hand_guide_step(0.02, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
        assert d is None and at_rest is True
    assert settle == HAND_GUIDE_SETTLE_TICKS
    # nowe naciśnięcie -> drugi krok
    d, settle, at_rest = hand_guide_step(-0.4, settle_count=settle, threshold_pct=0.3, step_mm=1.0)
    assert d == 1.0 and settle == 0 and at_rest is False


def test_hand_guide_step_odrzuca_nieskonczonosc():
    distance, settle, at_rest = hand_guide_step(float("nan"), settle_count=2)
    assert distance is None
    assert settle == 2  # stan bez zmian przy złych danych
    assert at_rest is False


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


def test_start_odrzuca_gdy_inna_sesja_juz_aktywna():
    """Zgłoszenie 2026-09-08 ("działa parę razy, potem błąd"): dwie karty
    ekranu /nauczanie potrafiły cicho nadpisać sobie nawzajem sesję, bo
    self._hand_guide to jeden, wspólny słownik. Druga próba startu ma być
    jawnie odrzucona, nie cicho nadpisywać pierwszej."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x"))
    with pytest.raises(MachineError, match="już aktywne"):
        asyncio.run(m.hand_guide_start("y"))


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


def test_tick_nie_aktualizuje_spoczynku_w_trakcie_wykrytego_nacisku():
    """Naprawiony błąd 2026-09-08 (druga iteracja): pierwsza próba
    przeładowywała rejestr zaraz PO ruchu, nawet jeśli operator nadal
    naciskał w chwili odczytu — rejestr zapamiętywał wtedy WARTOŚĆ
    NACISKU jako nowy "spoczynek", więc serwo "długo czekało na
    puszczenie" (normalny powrót do zera wyglądał jak nowe naciśnięcie).
    Rejestr ma się aktualizować TYLKO gdy odczyt jest w granicach progu
    (czyli naprawdę w spoczynku), nigdy podczas wykrytego nacisku."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    original_baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = original_baseline + 0.5
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is True
    # rejestr NIE mógł zostać zanieczyszczony wartością nacisku
    assert m._hand_guide["baseline"] == original_baseline


def test_tick_dryfuje_rejestr_w_oknie_uspokojenia_po_ruchu():
    """Zaraz PO kroku (settle_count wyzerowany) rejestr ma prawo dryfować
    do aktualnego, genuinie spokojnego odczytu — to jest mechanizm, który
    ma rozwiązać "długie czekanie po ruchu" (patrz nagłówek modułu)."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    baseline = m._hand_guide["baseline"]
    m.status.torque["x"] = baseline + 0.5
    first = asyncio.run(m.hand_guide_tick())
    assert first["moving"] is True
    post_move_baseline = m._hand_guide["baseline"]
    # nowy, genuinie spokojny odczyt w nowej pozycji (w granicach progu
    # względem rejestru sprzed ruchu) - to wciąż okno uzbrajania
    m.status.torque["x"] = post_move_baseline + 0.1
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    assert m._hand_guide["baseline"] == pytest.approx(post_move_baseline + 0.1)


def test_tick_nie_dryfuje_rejestru_gdy_juz_uzbrojony():
    """Naprawiony błąd 2026-09-08 (trzecia poprawka): dryf BEZ ograniczenia
    do okna uzbrajania aktualizował rejestr na każdym spokojnym ticku,
    również gdy oś stała nieruszana od dawna (już w pełni uzbrojona) —
    powolne, narastające pchnięcie ręką (typowe - nie skokowe) nigdy nie
    zdążyło przekroczyć progu względem rejestru, bo rejestr gonił każdy
    kolejny odczyt co 150 ms. Efekt na sprzęcie: żaden ruch nie startował
    NIGDY, niezależnie od siły nacisku ("jest cały czas nie tak"). Rejestr
    ma się zamrozić, gdy tylko oś raz w pełni się uzbroi."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x", threshold_pct=0.3))
    original_baseline = m._hand_guide["baseline"]
    assert m._hand_guide["settle_count"] == HAND_GUIDE_SETTLE_TICKS  # start "uzbrojony"
    # mały odczyt w granicach progu - PRZED naprawą to i tak przesuwało rejestr
    m.status.torque["x"] = original_baseline + 0.1
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    assert m._hand_guide["baseline"] == original_baseline
    # powolne, narastające pchnięcie: seria drobnych przyrostów, każdy
    # osobno poniżej progu względem POPRZEDNIEGO odczytu, ale suma
    # względem ZAMROŻONEGO rejestru w końcu przekracza próg
    m.status.torque["x"] += 0.15  # suma delt: 0.25 - wciąż poniżej progu
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is False
    m.status.torque["x"] += 0.15  # suma delt: 0.40 - przekracza próg 0.3
    result = asyncio.run(m.hand_guide_tick())
    assert result["moving"] is True


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


def test_tick_nie_wywala_sie_gdy_stop_wywolany_w_trakcie_poll_status():
    """Odtwarza dokładnie zgłoszony błąd 2026-09-08: 500 Internal Server
    Error / TypeError: 'NoneType' object is not subscriptable, gdy inny
    klient (druga karta przeglądarki) wywołał hand_guide_stop() W TRAKCIE
    oczekiwania na poll_status() tej korutyny. hand_guide_tick() ma
    dokończyć się bezpiecznie, korzystając z wcześniej zapamiętanej sesji,
    nie wywalić się na `self._hand_guide["..."]` po tym, jak ktoś inny
    zdążył ustawić `self._hand_guide = None`."""
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x"))
    original_poll = m.poll_status

    async def poll_then_concurrent_stop():
        await original_poll()
        m._hand_guide = None  # symuluje stop() z innej karty w trakcie await

    m.poll_status = poll_then_concurrent_stop

    result = asyncio.run(m.hand_guide_tick())  # nie może rzucić

    assert result["axis"] == "x"
    assert m._hand_guide is None  # stan po konkurencyjnym stop() zostaje


def test_stop_konczy_prowadzenie():
    m = _ready_machine()
    asyncio.run(m.hand_guide_start("x"))
    asyncio.run(m.hand_guide_stop())
    with pytest.raises(MachineError, match="nie jest aktywne"):
        asyncio.run(m.hand_guide_tick())


def test_stop_bez_startu_nie_jest_bledem():
    m = _ready_machine()
    asyncio.run(m.hand_guide_stop())  # nie rzuca
