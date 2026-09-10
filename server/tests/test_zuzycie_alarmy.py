"""Definicje alarmów zużycia (temat M, krok 4) — model, walidacja, ocena."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import zuzycie_alarmy as za  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_alarmy(client):
    """Przywraca definicje — testy API zapisują je na stałe (jak restore_smart)."""
    before = client.get("/api/zuzycie/alarmy").json()["alarmy"]
    yield before
    client.put("/api/zuzycie/alarmy", json={"alarmy": before})


def _def(**overrides):
    params = dict(os="x", metryka=za.METRYKA_DYSTANS, okres=za.OKRES_DZIEN, prog=100.0)
    params.update(overrides)
    return za.AlarmDefinition.from_dict("test-alarm", params)


# --- walidacja ---------------------------------------------------------------


def test_poprawna_definicja():
    d = _def()
    assert d.os == "x"
    assert d.prog == 100.0
    assert d.aktywny is True


def test_nieznana_metryka_odrzucona():
    with pytest.raises(za.AlarmError, match="metryka"):
        _def(metryka="cos_innego")


def test_nieznany_okres_odrzucony():
    with pytest.raises(za.AlarmError, match="okres"):
        _def(okres="miesiac")


def test_prog_musi_byc_dodatni():
    with pytest.raises(za.AlarmError, match="dodatni"):
        _def(prog=0)
    with pytest.raises(za.AlarmError, match="dodatni"):
        _def(prog=-5)


def test_prog_nieliczbowy_odrzucony():
    with pytest.raises(za.AlarmError, match="liczbą"):
        _def(prog="dużo")


def test_nieprawidlowa_nazwa_odrzucona():
    with pytest.raises(za.AlarmError, match="nazwa"):
        za.AlarmDefinition.from_dict(
            "1zle", {"os": "x", "metryka": za.METRYKA_DYSTANS, "okres": za.OKRES_DZIEN, "prog": 1}
        )


def test_domyslnie_aktywny_i_bez_notatki():
    d = za.AlarmDefinition.from_dict(
        "x", {"os": "x", "metryka": za.METRYKA_DYSTANS, "okres": za.OKRES_DZIEN, "prog": 1}
    )
    assert d.aktywny is True
    assert d.note == ""


def test_mozna_wylaczyc():
    d = _def(aktywny=False)
    assert d.aktywny is False


# --- to_dict / from_dict roundtrip -------------------------------------------


def test_roundtrip():
    d = _def(note="uwaga testowa", prog=42.5)
    restored = za.AlarmDefinition.from_dict("test-alarm", d.to_dict())
    assert restored == d


# --- ocena (evaluate) ---------------------------------------------------------


def test_evaluate_dzien_przekroczony():
    defs = {"a": _def(os="x", metryka=za.METRYKA_DYSTANS, okres=za.OKRES_DZIEN, prog=10.0)}
    dzisiaj = {"x": {"dystans_mm_suma": 15.0}}
    statuses = za.evaluate(defs, dzisiaj, [])
    assert len(statuses) == 1
    assert statuses[0].przekroczony is True
    assert statuses[0].wartosc == 15.0


def test_evaluate_dzien_nieprzekroczony():
    defs = {"a": _def(os="x", metryka=za.METRYKA_DYSTANS, okres=za.OKRES_DZIEN, prog=10.0)}
    dzisiaj = {"x": {"dystans_mm_suma": 5.0}}
    statuses = za.evaluate(defs, dzisiaj, [])
    assert statuses[0].przekroczony is False


def test_evaluate_brak_danych_dla_osi_nie_jest_przekroczony():
    defs = {"a": _def(os="y", metryka=za.METRYKA_DYSTANS, okres=za.OKRES_DZIEN, prog=10.0)}
    statuses = za.evaluate(defs, {"x": {"dystans_mm_suma": 999.0}}, [])
    assert statuses[0].wartosc is None
    assert statuses[0].przekroczony is False


def test_evaluate_pomija_nieaktywne():
    defs = {"a": _def(aktywny=False, prog=1.0)}
    dzisiaj = {"x": {"dystans_mm_suma": 999.0}}
    assert za.evaluate(defs, dzisiaj, []) == []


def test_evaluate_tydzien_sumuje_dystans():
    defs = {"a": _def(os="x", metryka=za.METRYKA_DYSTANS, okres=za.OKRES_TYDZIEN, prog=30.0)}
    trend = [
        {"data": "2026-09-09", "os": "x", "dystans_mm_suma": 20.0, "moment_max_pct": 5.0},
        {"data": "2026-09-08", "os": "x", "dystans_mm_suma": 10.0, "moment_max_pct": -3.0},
        {"data": "2026-09-08", "os": "y", "dystans_mm_suma": 999.0, "moment_max_pct": 999.0},
    ]
    dzisiaj = {"x": {"dystans_mm_suma": 5.0}}
    statuses = za.evaluate(defs, dzisiaj, trend)
    assert statuses[0].wartosc == pytest.approx(20.0 + 10.0 + 5.0)
    assert statuses[0].przekroczony is True


def test_evaluate_tydzien_moment_max_bierze_szczyt_nie_sume():
    defs = {"a": _def(os="x", metryka=za.METRYKA_MOMENT_MAX, okres=za.OKRES_TYDZIEN, prog=8.0)}
    trend = [
        {"data": "2026-09-09", "os": "x", "dystans_mm_suma": 1.0, "moment_max_pct": -9.0},
        {"data": "2026-09-08", "os": "x", "dystans_mm_suma": 1.0, "moment_max_pct": 3.0},
    ]
    dzisiaj = {"x": {"moment_max_pct": 2.0}}
    statuses = za.evaluate(defs, dzisiaj, trend)
    assert statuses[0].wartosc == -9.0  # największa wartość bezwzględna, ze znakiem
    assert statuses[0].przekroczony is True


def test_evaluate_uzywa_wartosci_bezwzglednej_do_porownania_z_progiem():
    """Moment ujemny (-15%) i tak przekracza próg 10%, mimo że -15 < 10
    jako liczba — liczy się siła nacisku, nie znak/kierunek."""
    defs = {"a": _def(os="x", metryka=za.METRYKA_MOMENT_MAX, okres=za.OKRES_DZIEN, prog=10.0)}
    dzisiaj = {"x": {"moment_max_pct": -15.0}}
    statuses = za.evaluate(defs, dzisiaj, [])
    assert statuses[0].przekroczony is True


# --- plik ----------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "alarmy.json"
    d = za.AlarmDefinition.from_dict(
        "a", {"os": "x", "metryka": za.METRYKA_DYSTANS, "okres": za.OKRES_DZIEN,
              "prog": 12.5, "note": "test"},
    )
    defs = {"a": d}
    za.save(path, defs)
    loaded = za.load(path)
    assert loaded == defs


def test_load_bez_pliku_zwraca_pusty_slownik(tmp_path):
    assert za.load(tmp_path / "brak.json") == {}


def test_load_uszkodzony_plik_rzuca(tmp_path):
    path = tmp_path / "zle.json"
    path.write_text("{niepoprawny json", encoding="utf-8")
    with pytest.raises(za.AlarmError):
        za.load(path)


# --- API --------------------------------------------------------------------


def test_api_get_zwraca_metryki_i_okresy(client):
    res = client.get("/api/zuzycie/alarmy")
    assert res.status_code == 200
    body = res.json()
    assert set(body["metryki"]) == set(za.METRYKI)
    assert set(body["okresy"]) == set(za.OKRESY)
    assert "alarmy" in body


def test_api_put_i_get_roundtrip(client, restore_alarmy):
    payload = {
        "alarmy": {
            "test-put": {
                "os": "x", "metryka": za.METRYKA_DYSTANS, "okres": za.OKRES_DZIEN,
                "prog": 250.0, "aktywny": True, "note": "test API",
            }
        }
    }
    res = client.put("/api/zuzycie/alarmy", json=payload)
    assert res.status_code == 200
    assert res.json()["alarmy"]["test-put"]["prog"] == 250.0

    res = client.get("/api/zuzycie/alarmy")
    assert res.json()["alarmy"]["test-put"]["os"] == "x"


def test_api_put_odrzuca_bledna_definicje(client, restore_alarmy):
    payload = {"alarmy": {"zly": {"os": "x", "metryka": "cos", "okres": za.OKRES_DZIEN, "prog": 1}}}
    res = client.put("/api/zuzycie/alarmy", json=payload)
    assert res.status_code == 422


def test_api_zuzycie_zawiera_alarmy(client):
    """GET /api/zuzycie łączy dane z oceną alarmów (krok 3 + krok 4)."""
    res = client.get("/api/zuzycie")
    assert res.status_code == 200
    body = res.json()
    assert "dzisiaj" in body
    assert "trend" in body
    assert "alarmy" in body
