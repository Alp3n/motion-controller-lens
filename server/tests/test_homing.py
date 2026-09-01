"""Bazowanie: kolejność osi, tryby, API /api/homing i sekwencja symulatora."""

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import axes as axes_mod  # noqa: E402
from app.machine import MachineError, MachineState, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _axes(**overrides):
    """Trzy osie z domyślnym bazowaniem; `overrides` nadpisuje pola per oś."""
    base = {
        axis: {
            "length": 200,
            "home": "srodek",
            "soft_min": -100,
            "soft_max": 100,
            "mm_per_rev": 5,
        }
        for axis in ("x", "y", "z")
    }
    for axis, fields in overrides.items():
        base.setdefault(axis, dict(base["x"])).update(fields)
    return axes_mod.parse_axes(base)


# --- model ----------------------------------------------------------------


def test_domyslna_kolejnosc_odtwarza_dawna_sekwencje():
    """Plik sprzed ekranu bazowania: najpierw X i Y, potem Z — jak wcześniej."""
    assert axes_mod.home_groups(_axes()) == [["x", "y"], ["z"]]


def test_kolejnosc_zero_wylacza_bazowanie_osi():
    cfg = _axes(y={"home_order": 0})
    assert axes_mod.home_groups(cfg) == [["x"], ["z"]]


def test_osie_z_ta_sama_kolejnoscia_baza_sie_razem():
    cfg = _axes(x={"home_order": 5}, y={"home_order": 5}, z={"home_order": 5})
    assert axes_mod.home_groups(cfg) == [["x", "y", "z"]]


def test_kolejnosc_nie_musi_byc_ciagla():
    cfg = _axes(z={"home_order": 1}, x={"home_order": 7}, y={"home_order": 90})
    assert axes_mod.home_groups(cfg) == [["z"], ["x"], ["y"]]


def test_os_dodatkowa_domyslnie_nie_jest_bazowana():
    cfg = _axes(podajnik={"length": 50, "soft_min": -25, "soft_max": 25})
    assert "podajnik" not in [a for group in axes_mod.home_groups(cfg) for a in group]


@pytest.mark.parametrize("bad", [{"home_order": -1}, {"home_mode": "krancowka"},
                                 {"home_torque": 0}, {"home_torque": 120}])
def test_bledne_parametry_bazowania_sa_odrzucane(bad):
    with pytest.raises(axes_mod.AxisConfigError):
        _axes(x=bad)


def test_tryb_hardstop_jest_dozwolony():
    cfg = _axes(z={"home_mode": "hardstop", "home_torque": 8, "home_offset": 2.5})
    assert cfg["z"].home_mode == axes_mod.HOME_MODE_HARDSTOP
    assert cfg["z"].home_torque == 8
    assert cfg["z"].home_offset == 2.5


# --- ostrzeżenia ----------------------------------------------------------


def test_ostrzezenie_gdy_zadna_os_nie_jest_bazowana():
    cfg = _axes(x={"home_order": 0}, y={"home_order": 0}, z={"home_order": 0})
    assert any("żadna oś" in w for w in axes_mod.homing_warnings(cfg, False))


def test_ostrzezenie_ze_parametry_hardstop_zyja_w_clearview():
    cfg = _axes(z={"home_mode": "hardstop"})
    assert any("ClearView" in w for w in axes_mod.homing_warnings(cfg, False))


def test_ostrzezenie_w_trybie_sprzetowym():
    """Na sprzęcie kolejność z ekranu nie działa — to musi być powiedziane."""
    assert any("tylko\nw symulatorze" in w.replace(" ", "\n") or "symulator" in w
               for w in axes_mod.homing_warnings(_axes(), True))


def test_ostrzezenie_o_osi_dodatkowej_ktora_nie_pojedzie():
    cfg = _axes(podajnik={"length": 50, "soft_min": -25, "soft_max": 25,
                          "home_order": 3})
    assert any("PODAJNIK" in w for w in axes_mod.homing_warnings(cfg, False))


# --- scalanie zapisu ------------------------------------------------------


def test_zapis_bazowania_nie_rusza_limitow():
    cfg = _axes()
    merged = axes_mod.merge_homing(cfg, {"z": {"home_order": 9, "home_mode": "hardstop"}})
    assert merged["z"].home_order == 9
    assert merged["z"].soft_min == cfg["z"].soft_min
    assert merged["z"].soft_max == cfg["z"].soft_max
    assert merged["x"] == cfg["x"]


def test_zapis_bazowania_odrzuca_nieznana_os():
    with pytest.raises(axes_mod.AxisConfigError):
        axes_mod.merge_homing(_axes(), {"podajnik": {"home_order": 1}})


def test_zapis_osi_nie_kasuje_ustawien_bazowania():
    """Ekran /axes nie wysyła pól bazowania — serwer bierze je z pliku."""
    cfg = _axes(z={"home_order": 4, "home_mode": "hardstop", "home_torque": 7,
                   "home_offset": 1.5, "vel_home": 250})
    z_only_geometry = {
        "z": {"length": 200, "home": "srodek", "soft_min": -100,
              "soft_max": 100, "mm_per_rev": 5}
    }
    filled = axes_mod.parse_axes(
        axes_mod.with_current_values({**axes_mod.to_dict(cfg), **z_only_geometry}, cfg)
    )
    assert filled["z"].home_order == 4
    assert filled["z"].home_mode == "hardstop"
    assert filled["z"].home_torque == 7
    assert filled["z"].home_offset == 1.5
    assert filled["z"].vel_home == 250


# --- sekwencja w symulatorze ----------------------------------------------


def _record_moves(machine):
    """Podmienia _move_to na zapis punktów docelowych — bez czekania w czasie."""
    moves = []

    async def fake_move(x, y, z, feed):
        moves.append((round(x, 3), round(y, 3), round(z, 3), round(feed)))
        machine.status.x, machine.status.y, machine.status.z = x, y, z

    machine._move_to = fake_move
    return moves


def test_symulator_bazuje_grupami_w_kolejnosci():
    m = SimulatedMachine()
    m.apply_axis_config(_axes(z={"home_order": 1, "vel_home": 300},
                              x={"home_order": 2}, y={"home_order": 3}))
    m.status.state = MachineState.READY
    m.status.x, m.status.y, m.status.z = 10.0, 20.0, 5.0
    moves = _record_moves(m)

    asyncio.run(_home_and_wait(m))

    # 1. odjazd w górę z bieżącego XY, 2. Z do zera, 3. X, 4. Y
    assert moves[0][:3] == (10.0, 20.0, 40.0)
    assert moves[1][:3] == (10.0, 20.0, 0.0)
    assert moves[2][:3] == (0.0, 20.0, 0.0)
    assert moves[3][:3] == (0.0, 0.0, 0.0)
    assert m.status.state is MachineState.READY


def test_symulator_pomija_os_z_kolejnoscia_zero():
    m = SimulatedMachine()
    m.apply_axis_config(_axes(y={"home_order": 0}))
    m.status.state = MachineState.READY
    m.status.x, m.status.y, m.status.z = 10.0, 20.0, 5.0
    moves = _record_moves(m)

    asyncio.run(_home_and_wait(m))

    assert m.status.y == 20.0  # Y nie było bazowane
    assert m.status.x == 0.0 and m.status.z == 0.0


def test_bazowanie_z_pustej_kolejnosci_jest_odrzucone():
    m = SimulatedMachine()
    m.apply_axis_config(_axes(x={"home_order": 0}, y={"home_order": 0},
                              z={"home_order": 0}))
    m.status.state = MachineState.READY
    with pytest.raises(MachineError, match="kolejności bazowania"):
        asyncio.run(m.home())


def test_bez_konfiguracji_osi_dziala_dawna_sekwencja():
    """Serwer bez pliku konfiguracji nie może stracić bazowania."""
    assert SimulatedMachine().home_groups() == [["x", "y"], ["z"]]


# --- JEDŹ DO ZERA (dojazd do zera po bazowaniu, bez ponownego bazowania) --


def test_jedz_do_zera_wymaga_stanu_ready():
    m = SimulatedMachine()
    m.apply_axis_config(_axes())
    m.status.state = MachineState.NOT_HOMED
    with pytest.raises(MachineError, match="READY"):
        asyncio.run(m.go_to_zero())


def test_jedz_do_zera_porusza_w_kolejnosci_bez_najpierw_z():
    """W przeciwieństwie do bazowania NIE ma odjazdu w górę na start —
    to zwykły dojazd do zera, nie procedura bazowania."""
    m = SimulatedMachine()
    m.apply_axis_config(_axes(z={"home_order": 1, "vel_home": 300},
                              x={"home_order": 2}, y={"home_order": 3}))
    m.status.state = MachineState.READY
    m.status.x, m.status.y, m.status.z = 10.0, 20.0, 5.0
    moves = _record_moves(m)

    asyncio.run(_go_to_zero_and_wait(m))

    assert [mv[:3] for mv in moves] == [
        (10.0, 20.0, 0.0),
        (0.0, 20.0, 0.0),
        (0.0, 0.0, 0.0),
    ]
    assert m.status.state is MachineState.READY


def test_jedz_do_zera_z_pustej_kolejnosci_jest_odrzucony():
    m = SimulatedMachine()
    m.apply_axis_config(_axes(x={"home_order": 0}, y={"home_order": 0},
                              z={"home_order": 0}))
    m.status.state = MachineState.READY
    with pytest.raises(MachineError, match="kolejności bazowania"):
        asyncio.run(m.go_to_zero())


async def _home_and_wait(machine):
    await machine.home()
    task = machine._run_task
    if task is not None:
        await task


async def _go_to_zero_and_wait(machine):
    await machine.go_to_zero()
    task = machine._run_task
    if task is not None:
        await task


# --- API ------------------------------------------------------------------


def test_api_homing_zwraca_pola_i_plan(client):
    data = client.get("/api/homing").json()
    assert set(data["axes"]["x"]) == set(axes_mod.HOMING_FIELDS)
    assert data["groups"] == [["x", "y"], ["z"]]
    assert data["modes"] == list(axes_mod.HOME_MODES)


def test_api_homing_zapis_i_odczyt(client):
    """Z pierwsze, potem X i Y razem — odwrotnie niż domyślnie."""
    res = client.put(
        "/api/homing",
        json={
            "axes": {
                "z": {"home_order": 1, "home_mode": "hardstop", "home_torque": 12},
                "x": {"home_order": 2},
                "y": {"home_order": 2},
            }
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["axes"]["z"]["home_order"] == 1
    assert body["groups"] == [["z"], ["x", "y"]]
    assert client.get("/api/homing").json()["axes"]["z"]["home_mode"] == "hardstop"
    # sprzątamy — pozostałe testy zakładają domyślną kolejność
    client.put(
        "/api/homing",
        json={
            "axes": {
                "z": {"home_order": 2, "home_mode": "programowe", "home_torque": 20},
                "x": {"home_order": 1},
                "y": {"home_order": 1},
            }
        },
    )


def test_api_homing_odrzuca_bledny_tryb(client):
    res = client.put("/api/homing", json={"axes": {"x": {"home_mode": "krancowka"}}})
    assert res.status_code == 422
    assert "tryb bazowania" in res.json()["detail"]


def test_ekran_bazowania_sie_serwuje(client):
    assert client.get("/homing").status_code == 200


# --- RESET po alarmie: wznowienie bez ponownego bazowania -----------------


def test_reset_po_bazowaniu_wraca_do_ready_z_ostrzezeniem():
    m = SimulatedMachine()
    m.apply_axis_config(_axes())
    asyncio.run(_home_and_wait(m))
    assert m.status.state is MachineState.READY

    m.status.state = MachineState.ALARM
    m.status.alarm_message = "zatrzymano przyciskiem STOP"
    asyncio.run(m.reset())

    assert m.status.state is MachineState.READY
    assert m.status.resumed_without_homing is True
    assert m.status.alarm_message == ""


def test_reset_bez_wczesniejszego_bazowania_wymusza_not_homed():
    m = SimulatedMachine()
    m.status.state = MachineState.ALARM
    asyncio.run(m.reset())

    assert m.status.state is MachineState.NOT_HOMED
    assert m.status.resumed_without_homing is False


def test_kolejne_bazowanie_gasi_ostrzezenie_wznowienia():
    m = SimulatedMachine()
    m.apply_axis_config(_axes())
    asyncio.run(_home_and_wait(m))
    m.status.state = MachineState.ALARM
    asyncio.run(m.reset())
    assert m.status.resumed_without_homing is True

    asyncio.run(_home_and_wait(m))

    assert m.status.resumed_without_homing is False
    assert m.status.state is MachineState.READY
