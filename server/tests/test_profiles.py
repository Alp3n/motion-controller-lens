"""Testy profili parametrów ruchu — model, plik, API i wpływ na ruch."""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import profiles  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_profiles(client):
    """Przywraca profile — testy API zapisują je na stałe."""
    before = client.get("/api/profiles").json()
    yield before
    client.put(
        "/api/profiles",
        json={"profiles": before["profiles"], "active": before["active"]},
    )


def _params(**overrides):
    payload = dict(vel_max=3000, accel=500, decel=500, torque_pct=20)
    payload.update(overrides)
    return payload


def _profile(axes=("x", "y", "z"), **overrides):
    return {"axes": {axis: _params(**overrides) for axis in axes}}


# --- model ----------------------------------------------------------------


def test_default_profiles_use_documented_torque_levels():
    """Wartości z NOTATKI_FUNKCJONALNE §2: 20% / 15% / 10%."""
    made = profiles.default_profiles(["x", "y", "z"])
    assert set(made) == {"globalny", "cykl", "program"}
    assert made["globalny"].axes["x"].torque_pct == 20.0
    assert made["cykl"].axes["x"].torque_pct == 15.0
    assert made["program"].axes["x"].torque_pct == 10.0


def test_default_profiles_cover_extra_axes():
    made = profiles.default_profiles(["x", "y", "z", "podajnik"])
    assert set(made["cykl"].axes) == {"x", "y", "z", "podajnik"}


@pytest.mark.parametrize(
    "kwargs, fragment",
    [
        (dict(vel_max=0), "prędkość maksymalna"),
        (dict(accel=0), "przyspieszenie"),
        (dict(decel=-1), "hamowanie"),
        (dict(torque_pct=0), "limit momentu"),
        (dict(torque_pct=101), "limit momentu"),
    ],
)
def test_invalid_params_rejected(kwargs, fragment):
    with pytest.raises(profiles.ProfileError) as exc:
        profiles.AxisParams(**_params(**kwargs)).validate("cykl", "x")
    assert fragment in str(exc.value)


def test_zero_torque_is_rejected_not_treated_as_safest():
    """0% momentu nie jest 'najbezpieczniej' — to maszyna, która nie rusza."""
    with pytest.raises(profiles.ProfileError):
        profiles.AxisParams(**_params(torque_pct=0)).validate("cykl", "x")


def test_invalid_profile_name_rejected():
    with pytest.raises(profiles.ProfileError) as exc:
        profiles.ParameterProfile.from_dict("Zły Profil", _profile())
    assert "nieprawidłowa nazwa profilu" in str(exc.value)


def test_active_profile_must_exist():
    with pytest.raises(profiles.ProfileError) as exc:
        profiles.parse_profiles({"profiles": {"cykl": _profile()}, "active": "nie_ma"})
    assert "nie istnieje" in str(exc.value)


def test_missing_axes_reported_not_silently_ignored():
    parsed, _ = profiles.parse_profiles(
        {"profiles": {"cykl": _profile(axes=("x", "y"))}, "active": "cykl"}
    )
    gaps = profiles.missing_axes(parsed, ["x", "y", "z"])
    assert gaps == {"cykl": ["z"]}


# --- plik -----------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "profiles.json"
    original = profiles.default_profiles(["x", "y", "z"])
    profiles.save(path, original, "cykl")
    loaded, active = profiles.load(path, ["x", "y", "z"])
    assert active == "cykl"
    assert profiles.to_dict(loaded) == profiles.to_dict(original)


def test_load_without_file_uses_defaults(tmp_path):
    loaded, active = profiles.load(tmp_path / "nie-ma.json", ["x", "y", "z"])
    assert active == profiles.PROFILE_GLOBAL
    assert loaded["program"].axes["z"].torque_pct == 10.0


def test_broken_file_is_an_error_not_a_silent_default(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{to nie jest json", encoding="utf-8")
    with pytest.raises(profiles.ProfileError):
        profiles.load(path, ["x"])

    path.write_text(json.dumps({"profiles": {}}), encoding="utf-8")
    with pytest.raises(profiles.ProfileError):
        profiles.load(path, ["x"])


# --- API ------------------------------------------------------------------


def test_get_profiles(client):
    data = client.get("/api/profiles").json()
    assert set(data["profiles"]) == {"globalny", "cykl", "program"}
    assert data["active"] == "globalny"
    assert data["profiles"]["program"]["axes"]["x"]["torque_pct"] == 10.0


def test_put_profiles_saves_and_applies(client, restore_profiles):
    new = {name: _profile(torque_pct=33) for name in ("globalny", "cykl", "program")}
    res = client.put("/api/profiles", json={"profiles": new, "active": "cykl"})
    assert res.status_code == 200, res.text
    assert res.json()["active"] == "cykl"

    data = client.get("/api/profiles").json()
    assert data["active"] == "cykl"
    assert data["profiles"]["cykl"]["axes"]["y"]["torque_pct"] == 33.0


def test_put_profiles_rejects_invalid_torque(client, restore_profiles):
    new = {name: _profile(torque_pct=150) for name in ("globalny", "cykl", "program")}
    res = client.put("/api/profiles", json={"profiles": new, "active": "globalny"})
    assert res.status_code == 422
    assert "limit momentu" in res.json()["detail"]


def test_switch_active_profile(client, restore_profiles):
    res = client.post("/api/profiles/active", json={"active": "program"})
    assert res.status_code == 200, res.text
    assert client.get("/api/profiles").json()["active"] == "program"


def test_switch_to_unknown_profile_is_rejected(client, restore_profiles):
    res = client.post("/api/profiles/active", json={"active": "nie_ma_takiego"})
    assert res.status_code == 409
    assert "nieznany profil" in res.json()["detail"]


def test_missing_axis_surfaces_as_warning(client, restore_profiles):
    """Profil bez którejś osi jest dozwolony, ale operator ma to zobaczyć."""
    new = {
        name: _profile(axes=("x", "y")) for name in ("globalny", "cykl", "program")
    }
    res = client.put("/api/profiles", json={"profiles": new, "active": "globalny"})
    assert res.status_code == 200, res.text
    assert any("nie opisuje osi Z" in w for w in res.json()["warnings"])


# --- wpływ na ruch --------------------------------------------------------


def test_profile_caps_jog_speed(client, restore_profiles):
    """Profil realnie ogranicza ruch, a nie jest samą strukturą danych."""
    import time

    slow = {name: _profile(vel_max=60) for name in ("globalny", "cykl", "program")}
    assert client.put(
        "/api/profiles", json={"profiles": slow, "active": "globalny"}
    ).status_code == 200

    # JOG 1 mm przy limicie 60 mm/min = 1 mm/s -> ruch musi zająć ok. sekundy,
    # mimo że żądany posuw jest dużo wyższy
    start = time.monotonic()
    res = client.post("/api/machine/jog", json={"axis": "x", "distance": 1, "feed": 3000})
    assert res.status_code == 200, res.text
    assert time.monotonic() - start > 0.5
