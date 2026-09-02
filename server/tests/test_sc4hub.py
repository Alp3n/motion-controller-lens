"""Testy SC4HubMachine — tłumaczenie programu i cyklu na komendy mostka.

SC4HubMachine nie miał wcześniej żadnych testów automatycznych — jedyną
weryfikacją było uruchomienie na prawdziwym sprzęcie (sesja 2026-08-14,
`docs/zmiany/mostek-sc4hub.md`). Tu podstawiamy `_command` (bez TCP), więc
testy sprawdzają WYŁĄCZNIE logikę tłumaczenia Operation/CycleStep na tekst
komend — nie protokół sieciowy ani samo połączenie. Cykl maszyny na
SC4HubMachine (`start_cycle`/`_run_cycle`) jest nowy w tej sesji i **nie
był uruchomiony na fizycznym sterowniku** — patrz `docs/zmiany/cykl-na-sprzecie.md`.
"""

import asyncio
import os

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

import pytest  # noqa: E402

from app import axes as axes_mod  # noqa: E402
from app import cycle  # noqa: E402
from app.machine import SC4HubMachine, MachineError, MachineState  # noqa: E402
from app.profiles import default_profiles  # noqa: E402
from app.program import Program  # noqa: E402


def _machine(axes_cfg=None):
    m = SC4HubMachine("127.0.0.1", 8500)
    calls = []

    async def fake_command(command: str) -> str:
        calls.append(command)
        return "OK"

    m._command = fake_command  # patrz docstring modułu — bez TCP
    m.calls = calls
    if axes_cfg is not None:
        m.apply_axis_config(axes_cfg)
    return m


def _program():
    from app.program import Operation

    return Program(
        number="583912004711",
        name="test",
        spindle_rpm=12000,
        feed_work=300,
        feed_travel=3000,
        z_safe=10,
        operations=[Operation(lp=1, op_type="PUNKT", x=5, y=5, z=-1)],
    )


# --- _run_program (refaktoryzacja _run_program_operations) ----------------


def test_run_program_sends_expected_command_sequence():
    """Regresja refaktoryzacji: dokładnie ta sama sekwencja, co przed
    wydzieleniem `_run_program_operations` z `_run_program`."""
    m = _machine()
    m._program = _program()
    m.status.state = MachineState.READY

    asyncio.run(m.start())
    asyncio.run(_wait_done(m))

    assert m.calls == [
        "SPINDLE 1 12000",
        "MOVEZ 10.000 3000",
        "MOVEXY 5.000 5.000 3000",
        "MOVEZ -1.000 300",
        "MOVEZ 10.000 3000",
        "MOVEXY 0 0 3000",
        "SPINDLE 0",
    ]
    assert m.status.state == MachineState.READY


async def _wait_done(m, timeout=2.0):
    for _ in range(int(timeout / 0.01)):
        if m._run_task is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("zadanie się nie zakończyło")


def test_run_program_error_sets_alarm_and_still_stops_spindle():
    m = _machine()
    m._program = _program()
    m.status.state = MachineState.READY

    async def failing_command(command: str) -> str:
        if command.startswith("MOVEXY 5"):
            raise MachineError("sterownik odrzucił komendę: ERR limit")
        m.calls.append(command)
        return "OK"

    m._command = failing_command
    m.calls = []

    asyncio.run(m.start())
    asyncio.run(_wait_done(m))

    assert m.status.state == MachineState.ALARM
    assert "ERR limit" in m.status.alarm_message
    assert m.calls[-1] == "SPINDLE 0"  # finally wysyła mimo błędu


# --- cykl maszyny — RUCH ----------------------------------------------


def _cycle_machine(steps, axes_cfg=None):
    m = _machine(axes_cfg)
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")
    m.apply_cycle(cycle.parse_cycle({"steps": steps}))
    m.status.state = MachineState.READY
    return m


def test_cycle_move_step_sends_movez_then_movexy():
    m = _cycle_machine([{"lp": 1, "kind": "RUCH", "targets": {"x": 5, "y": 2}, "feed": 1500}])
    asyncio.run(_drive(m))
    # ostatnie "SPINDLE 0" wysyła bezwarunkowo finally _run_cycle — jak przy
    # bezpośrednim uruchomieniu programu, niezależnie od rodzaju kroków
    assert m.calls == ["MOVEZ 0.000 1500", "MOVEXY 5.000 2.000 1500", "SPINDLE 0"]
    assert m.status.state == MachineState.READY


async def _drive(m):
    await m.start_cycle()
    for _ in range(400):
        if m._run_task is None:
            break
        await asyncio.sleep(0.01)


def test_cycle_move_step_only_moves_named_axes_and_uses_default_feed():
    m = _cycle_machine([{"lp": 1, "kind": "RUCH", "targets": {"z": -2}}])
    asyncio.run(_drive(m))
    # domyślny posuw 1000, bez podanego X/Y w komendzie MOVEZ/MOVEXY zostają zerowe pozycje
    assert m.calls == ["MOVEZ -2.000 1000", "MOVEXY 0.000 0.000 1000", "SPINDLE 0"]


def test_cycle_move_step_rejects_axis_outside_xyz():
    m = _cycle_machine([{"lp": 1, "kind": "RUCH", "targets": {"podajnik": 5}}])
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.ALARM
    assert "nie jest obsługiwana przez mostek" in m.status.alarm_message


def test_cycle_move_step_respects_soft_limits():
    axes_cfg = axes_mod.parse_axes(
        {
            a: {
                "length": 100, "home": "srodek",
                "soft_min": -50, "soft_max": 50, "mm_per_rev": 5,
            }
            for a in ("x", "y", "z")
        }
    )
    m = _cycle_machine([{"lp": 1, "kind": "RUCH", "targets": {"x": 999}}], axes_cfg)
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.ALARM
    assert "limitem programowym" in m.status.alarm_message
    # walidacja zatrzymuje krok, zanim cokolwiek pojedzie — jedyna komenda to
    # bezwarunkowe "SPINDLE 0" z finally _run_cycle
    assert m.calls == ["SPINDLE 0"]


# --- cykl maszyny — WYJSCIE, PAUZA, PROGRAM --------------------------------


def test_cycle_output_step_sends_bridge_command():
    """WYJSCIE przełącza fizyczne wyjście huba (komenda OUTPUT mostka).

    Wcześniej ten test pilnował odwrotnego stanu rzeczy — że mostek takiej
    komendy nie ma i krok zmienia tylko status. Komenda została dopisana,
    patrz docs/zmiany/wyjscia-fizyczne.md.
    """
    m = _cycle_machine(
        [{"lp": 1, "kind": "WYJSCIE", "output": "wyjscie_0", "output_on": True}]
    )
    asyncio.run(_drive(m))
    assert m.status.outputs["wyjscie_0"] is True
    # "SPINDLE 0" jest bezwarunkowe z finally _run_cycle; wyjście nie gaśnie,
    # bo domyślna konfiguracja nie ma go oznaczonego do gaszenia przy STOP
    assert m.calls == ["OUTPUT 0 1", "SPINDLE 0"]


def test_cycle_pause_step_sends_spindle_off_and_waits_for_resume():
    m = _cycle_machine([{"lp": 1, "kind": "PAUZA"}])

    async def run_and_resume():
        await m.start_cycle()
        await asyncio.sleep(0.05)
        assert m.status.state == MachineState.PAUSED
        assert m.calls == ["SPINDLE 0"]
        m.resume()
        await _wait_done(m)

    asyncio.run(run_and_resume())
    assert m.status.state == MachineState.READY


def test_cycle_program_step_runs_program_operations():
    m = _cycle_machine([{"lp": 1, "kind": "PROGRAM"}])
    m._program = _program()
    asyncio.run(_drive(m))
    assert m.calls[0] == "SPINDLE 1 12000"
    assert "MOVEXY 5.000 5.000 3000" in m.calls
    assert m.status.state == MachineState.READY


def test_cycle_program_step_without_loaded_program_is_an_error():
    m = _cycle_machine([{"lp": 1, "kind": "PROGRAM"}])
    with pytest.raises(MachineError) as exc:
        asyncio.run(m.start_cycle())
    assert "program detalu" in str(exc.value)


# --- profil kroku: snapshot/restore ----------------------------------------


def test_cycle_step_profile_restored_after_step():
    m = _cycle_machine(
        [{"lp": 1, "kind": "RUCH", "targets": {"x": 1}, "profile": "program"}]
    )
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.READY
    assert m.active_profile == "globalny"


def test_cycle_step_profile_restored_after_error():
    axes_cfg = axes_mod.parse_axes(
        {
            a: {"length": 100, "home": "srodek", "soft_min": -50, "soft_max": 50, "mm_per_rev": 5}
            for a in ("x", "y", "z")
        }
    )
    m = _cycle_machine(
        [{"lp": 1, "kind": "RUCH", "targets": {"x": 999}, "profile": "program"}], axes_cfg
    )
    asyncio.run(_drive(m))
    assert m.status.state == MachineState.ALARM
    assert m.active_profile == "globalny"


# --- tryb automatyczny (temat F) -------------------------------------------


def test_cycle_loop_repeats_until_stopped():
    m = _cycle_machine([{"lp": 1, "kind": "RUCH", "targets": {"x": 1}}])

    async def drive_loop():
        await m.start_cycle(loop=True)
        assert m.status.cycle_loop is True
        for _ in range(500):
            if len(m.calls) >= 6:  # 2 komendy na przebieg (MOVEZ+MOVEXY) x 3
                break
            await asyncio.sleep(0.01)
        assert len(m.calls) >= 6, "cykl nie powtórzył się mimo loop=True"
        if m._run_task:
            m._run_task.cancel()
            m._run_task = None

    asyncio.run(asyncio.wait_for(drive_loop(), timeout=5))


# --- JEDŹ DO ZERA (dojazd do zera po bazowaniu, bez ponownego bazowania) --


def _axes_with_home_order(orders):
    return axes_mod.parse_axes(
        {
            a: {
                "length": 200, "home": "srodek",
                "soft_min": -100, "soft_max": 100, "mm_per_rev": 5,
                "home_order": orders[a],
            }
            for a in ("x", "y", "z")
        }
    )


def test_go_to_zero_wymaga_stanu_ready():
    m = _machine()
    m.status.state = MachineState.NOT_HOMED
    with pytest.raises(MachineError, match="READY"):
        asyncio.run(m.go_to_zero())


def test_go_to_zero_z_first_wysyla_movez_przed_movexy():
    axes_cfg = _axes_with_home_order({"z": 1, "x": 2, "y": 3})
    m = _machine(axes_cfg)
    m.status.state = MachineState.READY

    asyncio.run(m.go_to_zero())

    assert m.calls == ["MOVEZ 0.000 1000", "MOVEXY 0.000 0.000 1000"]


def test_go_to_zero_xy_first_wysyla_jedna_komende_movexy():
    """Konfiguracja produkcyjna tej maszyny: X=1, Y=2, Z=3. X i Y jadą razem
    jedną komendą MOVEXY (mostek nie umie ruszyć nimi osobno), potem Z."""
    axes_cfg = _axes_with_home_order({"x": 1, "y": 2, "z": 3})
    m = _machine(axes_cfg)
    m.status.state = MachineState.READY

    asyncio.run(m.go_to_zero())

    assert m.calls == ["MOVEXY 0.000 0.000 1000", "MOVEZ 0.000 1000"]


def test_go_to_zero_z_pustej_kolejnosci_jest_odrzucony():
    axes_cfg = _axes_with_home_order({"x": 0, "y": 0, "z": 0})
    m = _machine(axes_cfg)
    m.status.state = MachineState.READY

    with pytest.raises(MachineError, match="kolejności bazowania"):
        asyncio.run(m.go_to_zero())
    assert m.calls == []


# --- limit momentu do sprzętu (etap 2b tematu B) ---------------------------
#
# `_machine()` podstawia _command w całości (fake_command), więc pomija
# logikę _axes_pending/_profile_pending — testy niżej zamiast tego podstawiają
# tylko _exchange (niższy poziom, bez sieci), żeby przetestować REALNY
# `_command` z jego mechanizmem "wypchnij, gdy coś się zmieniło".


class _FakeWriter:
    def is_closing(self) -> bool:
        return False


def _connected_machine(axes_cfg=None):
    m = SC4HubMachine("127.0.0.1", 8500)
    m._writer = _FakeWriter()
    m._reader = object()
    calls = []

    async def fake_exchange(command: str) -> str:
        calls.append(command)
        return "OK"

    m._exchange = fake_exchange
    m.calls = calls
    if axes_cfg is not None:
        m.apply_axis_config(axes_cfg)
    return m


def test_trqlimit_wyslany_przed_pierwsza_komenda():
    m = _connected_machine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")

    asyncio.run(m._command("STATUS"))

    assert m.calls == ["TRQLIMIT X 20.00", "TRQLIMIT Y 20.00", "TRQLIMIT Z 20.00", "STATUS"]


def test_trqlimit_nie_wysylany_ponownie_bez_zmiany():
    m = _connected_machine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")

    asyncio.run(m._command("STATUS"))
    asyncio.run(m._command("STATUS"))

    assert m.calls.count("STATUS") == 2
    assert sum(1 for c in m.calls if c.startswith("TRQLIMIT")) == 3


def test_trqlimit_wyslany_ponownie_po_zmianie_profilu():
    m = _connected_machine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")
    asyncio.run(m._command("STATUS"))

    m.set_active_profile("program")
    asyncio.run(m._command("STATUS"))

    assert m.calls[-4:] == [
        "TRQLIMIT X 10.00",
        "TRQLIMIT Y 10.00",
        "TRQLIMIT Z 10.00",
        "STATUS",
    ]


def test_trqlimit_pomija_os_bez_wpisu_w_profilu():
    m = _connected_machine()
    m.apply_profiles(default_profiles(["x", "y"]), "globalny")  # brak Z

    asyncio.run(m._command("STATUS"))

    assert "TRQLIMIT X 20.00" in m.calls
    assert "TRQLIMIT Y 20.00" in m.calls
    assert not any(c.startswith("TRQLIMIT Z") for c in m.calls)


# --- STOP musi trafić na gniazdo natychmiast, nie za kolejką pushy --------
#
# Zgłoszone przy maszynie 2026-09-02: przy dłuższym ruchu STOP zatrzymywał
# osie dopiero po kilku sekundach. Przyczyna: zwykłe `_command()` przed
# wysłaniem STOP próbowałoby najpierw wypchnąć TRQLIMIT/AXCFG, jeśli
# `_profile_pending`/`_axes_pending` akurat było True (np. bo `finally:` w
# `_execute_cycle_step` przywraca profil po przerwanym kroku) - a mostek w
# trakcie ruchu ignoruje wszystko poza STOP/STATUS, więc taki push nigdy nie
# dostałby odpowiedzi i blokowałby STOP aż do naturalnego końca ruchu.


def test_stop_pomija_push_profilu_mimo_pending():
    m = _connected_machine()
    m.apply_profiles(default_profiles(["x", "y", "z"]), "globalny")
    m._profile_pending = True

    asyncio.run(m.stop())

    assert m.calls == ["STOP"]


def test_stop_pomija_push_osi_mimo_pending():
    m = _connected_machine(axes_cfg=None)
    m._axes_pending = True

    asyncio.run(m.stop())

    assert m.calls == ["STOP"]


def test_stop_anuluje_run_task():
    m = _connected_machine()

    async def never_ends():
        await asyncio.sleep(100)

    async def run():
        m._run_task = asyncio.create_task(never_ends())
        await asyncio.sleep(0)
        await m.stop()

    asyncio.run(run())

    assert m.calls == ["STOP"]
    assert m._run_task is None


# --- RESUMED=1 w STATUS (wznowienie po alarmie bez ponownego bazowania) ----


def test_poll_status_czyta_resumed_flag():
    m = _machine()
    m.status.state = MachineState.NOT_HOMED

    async def fake_command(command: str) -> str:
        if command == "STATUS":
            return "OK STATE=READY EN=1 X=0.000 Y=0.000 Z=0.000 SP=0 REL=- OUT=00 RESUMED=1"
        return "OK"

    m._command = fake_command

    asyncio.run(m.poll_status())

    assert m.status.resumed_without_homing is True
    assert m.status.state == MachineState.READY


def test_poll_status_bez_pola_resumed_zostaje_false():
    """Starszy mostek (bez tej zmiany) nie wysyła RESUMED — brak pola to
    False, nie błąd parsowania."""
    m = _machine()

    async def fake_command(command: str) -> str:
        if command == "STATUS":
            return "OK STATE=READY EN=1 X=0.000 Y=0.000 Z=0.000 SP=0 REL=- OUT=00"
        return "OK"

    m._command = fake_command

    asyncio.run(m.poll_status())

    assert m.status.resumed_without_homing is False


def test_go_to_zero_respects_soft_limits():
    axes_cfg = axes_mod.parse_axes(
        {
            a: {"length": 100, "home": "srodek", "soft_min": 5, "soft_max": 50, "mm_per_rev": 5}
            for a in ("x", "y", "z")
        }
    )
    m = _machine(axes_cfg)
    m.status.state = MachineState.READY

    with pytest.raises(MachineError, match="limitem programowym"):
        asyncio.run(m.go_to_zero())
    assert m.calls == []
