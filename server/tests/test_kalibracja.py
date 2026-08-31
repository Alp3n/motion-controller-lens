"""Testy kalibracji moment->siła (etap 2 tematu K) — model, plik i API."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import kalibracja  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_kalibracja(client):
    """Przywraca stan sprzed testu — testy API zapisują na stałe."""
    before = client.get("/api/kalibracja").json()["kalibracja"]
    yield before
    client.put("/api/kalibracja", json={"kalibracja": before})


# --- model: PunktKalibracji -------------------------------------------------


def test_punkt_z_poprawnymi_danymi():
    p = kalibracja.PunktKalibracji.from_dict(
        {"moment_pct": 15, "sila_n": 42.5, "kierunek": "plus", "uwagi": "test"}
    )
    assert p.moment_pct == 15
    assert p.sila_n == 42.5
    assert p.data  # uzupełnione automatycznie


def test_punkt_odrzuca_moment_poza_zakresem():
    with pytest.raises(kalibracja.KalibracjaError, match="moment_pct"):
        kalibracja.PunktKalibracji.from_dict({"moment_pct": 0, "sila_n": 1})
    with pytest.raises(kalibracja.KalibracjaError, match="moment_pct"):
        kalibracja.PunktKalibracji.from_dict({"moment_pct": 101, "sila_n": 1})


def test_punkt_odrzuca_ujemna_sile():
    with pytest.raises(kalibracja.KalibracjaError, match="sila_n"):
        kalibracja.PunktKalibracji.from_dict({"moment_pct": 10, "sila_n": -1})


def test_punkt_odrzuca_srednik_w_uwagach():
    with pytest.raises(kalibracja.KalibracjaError, match="uwagi"):
        kalibracja.PunktKalibracji.from_dict(
            {"moment_pct": 10, "sila_n": 1, "uwagi": "a; b"}
        )


def test_punkt_akceptuje_przecinek_dziesietny():
    p = kalibracja.PunktKalibracji.from_dict({"moment_pct": "12,5", "sila_n": "3,2"})
    assert p.moment_pct == 12.5
    assert p.sila_n == 3.2


# --- parse_kalibracja / default -------------------------------------------


def test_parse_bez_wszystkich_osi_dziala():
    """W przeciwieństwie do axes.py brak osi nie jest błędem."""
    cfg = kalibracja.parse_kalibracja({"x": {"punkty": [{"moment_pct": 5, "sila_n": 1}]}})
    assert len(cfg["x"].punkty) == 1
    assert cfg["y"].punkty == []
    assert cfg["z"].punkty == []


def test_parse_odrzuca_nieznana_os():
    with pytest.raises(kalibracja.KalibracjaError, match="nieznana oś"):
        kalibracja.parse_kalibracja({"q": {"punkty": []}})


# --- plik: load/save ---------------------------------------------------------


def test_save_i_load_roundtrip(tmp_path):
    path = tmp_path / "kalibracja.json"
    cfg = kalibracja.parse_kalibracja(
        {"x": {"punkty": [{"moment_pct": 20, "sila_n": 55, "kierunek": "minus"}]}}
    )
    kalibracja.save(path, cfg)
    loaded = kalibracja.load(path)
    assert loaded["x"].punkty[0].sila_n == 55
    assert loaded["x"].punkty[0].kierunek == "minus"
    assert loaded["y"].punkty == []


def test_load_bez_pliku_zwraca_puste():
    cfg = kalibracja.load(Path("/nie/ma/takiego/pliku.json"))
    assert all(cfg[a].punkty == [] for a in kalibracja.AXES)


def test_load_z_uszkodzonym_plikiem_nie_wywala_startu(tmp_path):
    path = tmp_path / "zle.json"
    path.write_text("{ to nie jest json", encoding="utf-8")
    cfg = kalibracja.load(path)
    assert all(cfg[a].punkty == [] for a in kalibracja.AXES)


# --- API ---------------------------------------------------------------------


def test_api_get_zwraca_domyslnie_puste(client):
    res = client.get("/api/kalibracja")
    assert res.status_code == 200
    data = res.json()["kalibracja"]
    assert all(data[a]["punkty"] == [] for a in ("x", "y", "z"))


def test_api_put_i_get_roundtrip(client, restore_kalibracja):
    payload = {
        "kalibracja": {
            "x": {"punkty": [{"moment_pct": 20, "sila_n": 48.3, "kierunek": "plus"}]},
        }
    }
    res = client.put("/api/kalibracja", json=payload)
    assert res.status_code == 200
    assert res.json()["kalibracja"]["x"]["punkty"][0]["sila_n"] == 48.3

    res = client.get("/api/kalibracja")
    assert res.json()["kalibracja"]["x"]["punkty"][0]["sila_n"] == 48.3


def test_api_put_odrzuca_zly_moment(client, restore_kalibracja):
    payload = {"kalibracja": {"x": {"punkty": [{"moment_pct": 500, "sila_n": 1}]}}}
    res = client.put("/api/kalibracja", json=payload)
    assert res.status_code == 422
