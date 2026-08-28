"""Testy konfiguracji osi — model, plik, API i wpływ na ruch."""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import axes  # noqa: E402
from app.machine import MachineState, SimulatedMachine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_axes(client):
    """Przywraca konfigurację osi — testy API zapisują ją na stałe."""
    before = client.get("/api/axes").json()["axes"]
    yield before
    client.put("/api/axes", json={"axes": before})


# --- model ----------------------------------------------------------------


def test_physical_range_depends_on_home_point():
    def rng(home):
        cfg = axes.AxisConfig(
            length=300, home=home, soft_min=0, soft_max=0, mm_per_rev=5
        )
        return cfg.physical_range()

    assert rng(axes.HOME_MINUS) == (0, 300)
    assert rng(axes.HOME_PLUS) == (-300, 0)
    assert rng(axes.HOME_CENTER) == (-150, 150)


def test_soft_limits_may_touch_physical_range():
    cfg = axes.AxisConfig(
        length=300, home=axes.HOME_CENTER, soft_min=-150, soft_max=150, mm_per_rev=5
    )
    cfg.validate("x")  # granica zakresu jest dopuszczalna


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        (dict(length=0), "długość"),
        (dict(mm_per_rev=0), "przełożenie"),
        (dict(soft_min=50, soft_max=50), "MIN"),
        (dict(soft_min=-200), "poza zakres fizyczny"),
        (dict(soft_max=200), "poza zakres fizyczny"),
        (dict(home="lewo"), "punkt bazowania"),
        (dict(vel_jog=0), "prędkość JOG"),
        (dict(vel_home=0), "prędkość bazowania"),
    ],
)
def test_invalid_axis_rejected(kwargs, fragment):
    params = dict(
        length=300, home=axes.HOME_CENTER, soft_min=-100, soft_max=100, mm_per_rev=5
    )
    params.update(kwargs)
    with pytest.raises(axes.AxisConfigError) as exc:
        axes.AxisConfig(**params).validate("x")
    assert fragment in str(exc.value)


def test_defaults_keep_work_area_from_env():
    area = {
        "x_min": -100, "x_max": 100,
        "y_min": 0, "y_max": 250,
        "z_min": -20, "z_max": 50,
    }
    cfg = axes.default_axes(area)
    assert axes.work_area(cfg) == area
    assert cfg["x"].home == axes.HOME_CENTER and cfg["x"].length == 200
    assert cfg["y"].home == axes.HOME_MINUS and cfg["y"].length == 250
    # zakres nieosiągalny końcami osi: środek i długość do dalszego krańca
    assert cfg["z"].home == axes.HOME_CENTER and cfg["z"].length == 100


def test_missing_speed_fields_get_old_defaults():
    """Pliki sprzed pola JOG/bazowania nie mogą blokować startu serwera."""
    data = {
        axis: dict(length=300, home="srodek", soft_min=-100, soft_max=100, mm_per_rev=5)
        for axis in ("x", "y", "z")
    }
    parsed = axes.parse_axes(data)
    assert parsed["x"].vel_jog == axes.DEFAULT_VEL_JOG
    assert parsed["x"].vel_home == axes.DEFAULT_VEL_HOME


def test_speed_fields_round_trip_through_to_dict():
    cfg = axes.AxisConfig(
        length=300, home="srodek", soft_min=-100, soft_max=100, mm_per_rev=5,
        vel_jog=250, vel_home=800,
    )
    d = cfg.to_dict()
    assert d["vel_jog"] == 250 and d["vel_home"] == 800


# --- plik -----------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "axes.json"
    original = axes.default_axes(
        {"x_min": 0, "x_max": 300, "y_min": 0, "y_max": 300, "z_min": -80, "z_max": 0}
    )
    axes.save(path, original)
    loaded = axes.load(path, {})
    assert axes.to_dict(loaded) == axes.to_dict(original)
    assert loaded["z"].home == axes.HOME_PLUS


def test_load_without_file_uses_defaults(tmp_path):
    area = {"x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10, "z_min": -5, "z_max": 0}
    loaded = axes.load(tmp_path / "nie-ma.json", area)
    assert axes.work_area(loaded) == area


def test_broken_file_is_an_error_not_a_silent_default(tmp_path):
    path = tmp_path / "axes.json"
    path.write_text("{to nie jest json", encoding="utf-8")
    with pytest.raises(axes.AxisConfigError):
        axes.load(path, {})

    path.write_text(json.dumps({"axes": {"x": {}}}), encoding="utf-8")
    with pytest.raises(axes.AxisConfigError):
        axes.load(path, {})


# --- osie dodatkowe (ponad wymagane X/Y/Z) ---------------------------------


def _axis_payload(**overrides):
    payload = dict(length=300, home="srodek", soft_min=-100, soft_max=100, mm_per_rev=5)
    payload.update(overrides)
    return payload


def test_parse_axes_keeps_extra_axis_beyond_required(tmp_path):
    data = {axis: _axis_payload() for axis in ("x", "y", "z")}
    data["podajnik"] = _axis_payload(home="plus", soft_min=-100, soft_max=0)
    parsed = axes.parse_axes(data)
    assert set(parsed) == {"x", "y", "z", "podajnik"}
    assert parsed["podajnik"].home == "plus"


def test_save_and_to_dict_keep_extra_axis(tmp_path):
    data = {axis: _axis_payload() for axis in ("x", "y", "z")}
    data["docisk"] = _axis_payload()
    parsed = axes.parse_axes(data)

    assert set(axes.to_dict(parsed)) == {"x", "y", "z", "docisk"}

    path = tmp_path / "axes.json"
    axes.save(path, parsed)
    loaded = axes.load(path, {})
    assert set(loaded) == {"x", "y", "z", "docisk"}


def test_parse_axes_rejects_invalid_axis_name():
    data = {axis: _axis_payload() for axis in ("x", "y", "z")}
    data["Nieprawidlowa Nazwa"] = _axis_payload()
    with pytest.raises(axes.AxisConfigError) as exc:
        axes.parse_axes(data)
    assert "nieprawidłowa nazwa osi" in str(exc.value)


def test_work_area_ignores_extra_axes(tmp_path):
    data = {axis: _axis_payload() for axis in ("x", "y", "z")}
    data["podajnik"] = _axis_payload(soft_min=0, soft_max=500, length=500, home="minus")
    parsed = axes.parse_axes(data)
    area = axes.work_area(parsed)
    assert set(area) == {"x_min", "x_max", "y_min", "y_max", "z_min", "z_max"}


# --- API ------------------------------------------------------------------


def test_get_axes(client):
    data = client.get("/api/axes").json()
    assert set(data["axes"]) == {"x", "y", "z"}
    assert data["home_points"] == list(axes.HOME_POINTS)
    x = data["axes"]["x"]
    assert x["phys_min"] <= x["soft_min"] < x["soft_max"] <= x["phys_max"]


def test_put_axes_saves_and_changes_work_area(client, restore_axes):
    new = {
        axis: {
            "length": 300,
            "home": "srodek",
            "soft_min": -120,
            "soft_max": 120,
            "mm_per_rev": 4,
        }
        for axis in ("x", "y", "z")
    }
    res = client.put("/api/axes", json={"axes": new})
    assert res.status_code == 200, res.text
    assert res.json()["axes"]["x"]["phys_max"] == 150

    area = client.get("/api/config").json()["work_area"]
    assert area["x_min"] == -120 and area["z_max"] == 120

    # plik konfiguracji rzeczywiście powstał
    from app import config as app_config

    assert json.loads(app_config.AXES_FILE.read_text(encoding="utf-8"))["axes"]["y"][
        "mm_per_rev"
    ] == 4


def test_put_axes_rejects_limits_outside_physical_range(client, restore_axes):
    new = {axis: dict(restore_axes[axis]) for axis in ("x", "y", "z")}
    new["x"]["soft_max"] = new["x"]["phys_max"] + 10
    res = client.put("/api/axes", json={"axes": new})
    assert res.status_code == 422
    assert "poza zakres fizyczny" in res.json()["detail"]


def test_program_outside_new_limits_is_rejected(client, restore_axes):
    """Limity programowe są obszarem roboczym przy wczytywaniu programu."""
    new = {
        axis: {
            "length": 40,
            "home": "srodek",
            "soft_min": -20,
            "soft_max": 20,
            "mm_per_rev": 5,
        }
        for axis in ("x", "y", "z")
    }
    assert client.put("/api/axes", json={"axes": new}).status_code == 200

    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-1", "program_number": "583912004711"},
    )
    assert res.status_code == 422
    assert "obszarem roboczym" in res.json()["detail"]


def test_jog_beyond_soft_limit_is_rejected(client, restore_axes):
    new = {axis: dict(restore_axes[axis]) for axis in ("x", "y", "z")}
    # wąskie okno wokół zera: skok JOG wyjdzie poza limit
    new["x"].update({"soft_min": -1, "soft_max": 1})
    assert client.put("/api/axes", json={"axes": new}).status_code == 200

    res = client.post("/api/machine/jog", json={"axis": "x", "distance": 5})
    assert res.status_code == 409
    assert "limitem programowym" in res.json()["detail"]

    # ruch mieszczący się w limicie nadal działa
    assert client.post("/api/machine/jog", json={"axis": "x", "distance": 0.5}).status_code == 200


def test_jog_uses_configured_axis_speed_when_feed_omitted(client, restore_axes):
    """`vel_jog` musi realnie ograniczać ruch, nie być samą liczbą w pliku."""
    import time

    new = {axis: dict(restore_axes[axis]) for axis in ("x", "y", "z")}
    new["x"]["vel_jog"] = 60  # 60 mm/min = 1 mm/s
    assert client.put("/api/axes", json={"axes": new}).status_code == 200

    # feed pominięty w żądaniu -> serwer musi sam użyć skonfigurowanej prędkości
    start = time.monotonic()
    res = client.post("/api/machine/jog", json={"axis": "x", "distance": 1})
    assert res.status_code == 200, res.text
    assert time.monotonic() - start > 0.5


def test_home_uses_configured_axis_speed():
    """`vel_home` musi realnie ograniczać ruch bazowania w symulatorze.

    Instancja izolowana (nie współdzielony `client`) — bazowanie zmienia stan
    maszyny na czas ruchu i nie chcemy zakłócać innych testów modułu.
    """
    import asyncio
    import time

    area = {"x_min": -100, "x_max": 100, "y_min": -100, "y_max": 100, "z_min": -20, "z_max": 40}
    cfg = axes.default_axes(area)
    for axis_cfg in cfg.values():
        axis_cfg.vel_home = 60  # 60 mm/min = 1 mm/s

    m = SimulatedMachine()
    m.apply_axis_config(cfg)

    async def drive():
        await m.home()
        while m.status.state == MachineState.HOMING:
            await asyncio.sleep(0.02)

    start = time.monotonic()
    asyncio.run(drive())
    assert time.monotonic() - start > 0.5
    assert m.status.state == MachineState.READY
