"""Testy nazwanych punktów PTP (ekrany /nauczanie i /punkty) — model, plik i API."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import punkty  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_punkty(client):
    """Przywraca stan sprzed testu — testy API zapisują na stałe."""
    before = client.get("/api/punkty").json()["points"]
    yield before
    client.put("/api/punkty", json={"points": before})


# --- model: NamedPoint -------------------------------------------------------


def test_punkt_z_poprawnymi_danymi():
    p = punkty.NamedPoint.from_dict("wlewek-1", {"x": 12.5, "y": -30, "z": -1.5, "note": "test"})
    assert p.x == 12.5
    assert p.y == -30
    assert p.z == -1.5
    assert p.note == "test"


def test_punkt_odrzuca_zla_nazwe():
    with pytest.raises(punkty.PunktyError, match="nazwa"):
        punkty.NamedPoint.from_dict("1zly-start", {"x": 0, "y": 0, "z": 0})
    with pytest.raises(punkty.PunktyError, match="nazwa"):
        punkty.NamedPoint.from_dict("ze spacja", {"x": 0, "y": 0, "z": 0})
    with pytest.raises(punkty.PunktyError, match="nazwa"):
        punkty.NamedPoint.from_dict("ze;srednikiem", {"x": 0, "y": 0, "z": 0})


def test_punkt_akceptuje_przecinek_dziesietny():
    p = punkty.NamedPoint.from_dict("p1", {"x": "12,5", "y": "-3,2", "z": "0"})
    assert p.x == 12.5
    assert p.y == -3.2


def test_punkt_odrzuca_nieliczbowe_wspolrzedne():
    with pytest.raises(punkty.PunktyError, match="X"):
        punkty.NamedPoint.from_dict("p1", {"x": "abc", "y": 0, "z": 0})


# --- parse_points ------------------------------------------------------------


def test_parse_points_pusty_slownik():
    assert punkty.parse_points({"points": {}}) == {}


def test_parse_points_odrzuca_zla_nazwe_wewnatrz():
    with pytest.raises(punkty.PunktyError):
        punkty.parse_points({"points": {"zla nazwa": {"x": 0, "y": 0, "z": 0}}})


# --- plik: load/save ----------------------------------------------------------


def test_save_i_load_roundtrip(tmp_path):
    path = tmp_path / "punkty.json"
    pts = punkty.parse_points(
        {"points": {"wlewek-gorny": {"x": 12.5, "y": 30, "z": -1.5, "note": "np. lewa"}}}
    )
    punkty.save(path, pts)
    loaded = punkty.load(path)
    assert loaded["wlewek-gorny"].x == 12.5
    assert loaded["wlewek-gorny"].note == "np. lewa"


def test_load_bez_pliku_zwraca_puste():
    assert punkty.load(Path("/nie/ma/takiego/pliku.json")) == {}


def test_load_z_uszkodzonym_plikiem_nie_wywala_startu(tmp_path):
    path = tmp_path / "zle.json"
    path.write_text("{ to nie jest json", encoding="utf-8")
    assert punkty.load(path) == {}


# --- API -----------------------------------------------------------------------


def test_api_get_zwraca_domyslnie_puste(client):
    res = client.get("/api/punkty")
    assert res.status_code == 200
    assert res.json()["points"] == {}


def test_api_put_i_get_roundtrip(client, restore_punkty):
    payload = {"points": {"wlewek-gorny": {"x": 12.5, "y": 30, "z": -1.5, "note": ""}}}
    res = client.put("/api/punkty", json=payload)
    assert res.status_code == 200
    assert res.json()["points"]["wlewek-gorny"]["x"] == 12.5

    res = client.get("/api/punkty")
    assert res.json()["points"]["wlewek-gorny"]["x"] == 12.5


def test_api_put_usuwa_pominiety_punkt(client, restore_punkty):
    client.put("/api/punkty", json={"points": {"a": {"x": 1, "y": 1, "z": 1}}})
    res = client.put("/api/punkty", json={"points": {}})
    assert res.status_code == 200
    assert client.get("/api/punkty").json()["points"] == {}


def test_api_put_odrzuca_zla_nazwe(client, restore_punkty):
    payload = {"points": {"zla nazwa": {"x": 0, "y": 0, "z": 0}}}
    res = client.put("/api/punkty", json=payload)
    assert res.status_code == 422
