"""Testy definicji SMART — model, rejestr procedur, plik i API."""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import smart  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def restore_smart(client):
    """Przywraca definicje — testy API zapisują je na stałe."""
    before = client.get("/api/smart").json()["definitions"]
    yield before
    payload = {
        name: {"procedure": d["procedure"], "params": d["params"], "note": d["note"]}
        for name, d in before.items()
    }
    client.put("/api/smart", json={"definitions": payload})


def _definition(**overrides):
    params = {p.name: p.default for p in smart.PROCEDURES["ciecie_adaptacyjne"].params}
    params.update(overrides)
    return {"procedure": "ciecie_adaptacyjne", "params": params, "note": ""}


# --- model ----------------------------------------------------------------


def test_default_definition_matches_source_material():
    """Wartości startowe są te z zbyszek/kontrola-sily.md (30% / 5 mm / 1 mm)."""
    defs = smart.default_definitions()
    d = defs[smart.DEFAULT_DEFINITION]
    assert d.params["sila_pct"] == 30.0
    assert d.params["dojazd_mm"] == 5.0
    assert d.params["cofniecie_mm"] == 1.0
    assert d.params["os"] == "z"


def test_definition_name_allows_hyphen_and_capitals():
    """Nazwa „SMART-sila" musi przechodzić — tak ją nazwaliśmy."""
    d = smart.SmartDefinition.from_dict("SMART-sila", _definition())
    assert d.name == "SMART-sila"


@pytest.mark.parametrize("bad", ["SMART sila", "1sila", "sila;x", "", "-sila"])
def test_invalid_definition_names_rejected(bad):
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict(bad, _definition())
    assert "nazwa definicji" in str(exc.value)


def test_unknown_procedure_rejected():
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict("x", {"procedure": "nie_ma_takiej"})
    assert "nieznana procedura" in str(exc.value)


def test_unknown_parameter_rejected_not_silently_dropped():
    """Literówka w nazwie parametru musi być błędem, nie cichym pominięciem."""
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict(
            "x", {"procedure": "ciecie_adaptacyjne", "params": {"sila_pcnt": 30}}
        )
    assert "nie ma parametrów" in str(exc.value)


def test_missing_parameters_filled_from_defaults():
    """Stara definicja bez nowego parametru ma dalej działać, nie blokować startu."""
    d = smart.SmartDefinition.from_dict(
        "x", {"procedure": "ciecie_adaptacyjne", "params": {"sila_pct": 12}}
    )
    assert d.params["sila_pct"] == 12
    assert d.params["dojazd_mm"] == 5.0  # z rejestru


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"sila_pct": 0}, "Próg siły"),
        ({"sila_pct": 101}, "Próg siły"),
        ({"dojazd_mm": 0}, "Dojazd"),
        ({"probkowanie_ms": 0}, "Okres próbkowania"),
        ({"os": "q"}, "Oś ruchu"),
    ],
)
def test_parameter_ranges_enforced(overrides, fragment):
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict("x", _definition(**overrides))
    assert fragment in str(exc.value)


def test_zero_force_rejected_not_treated_as_safest():
    """0% momentu nie znaczy „bezpieczniej" — oś by nie ruszyła i nie powiedziała czemu."""
    with pytest.raises(smart.SmartError):
        smart.SmartDefinition.from_dict("x", _definition(sila_pct=0))


def test_speed_thresholds_must_not_overlap():
    """Próg przyspieszenia >= progu zwolnienia to przełączanie prędkości w kółko."""
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict(
            "x", _definition(prog_zwolnienia=0.5, prog_przyspieszenia=0.6)
        )
    assert "próg przyspieszenia" in str(exc.value)


def test_slow_speed_cannot_exceed_fast():
    with pytest.raises(smart.SmartError) as exc:
        smart.SmartDefinition.from_dict("x", _definition(v_szybka=100, v_wolna=500))
    assert "prędkość wolna" in str(exc.value)


def test_comma_decimal_accepted():
    """Pliki i formularze z polskimi ustawieniami używają przecinka."""
    d = smart.SmartDefinition.from_dict("x", _definition(sila_pct="12,5"))
    assert d.params["sila_pct"] == 12.5


# --- rejestr procedur -----------------------------------------------------


def test_registry_exposes_parameter_schema():
    """Ekran rysuje pola z tego, co zwraca rejestr — musi mieć komplet opisu."""
    procs = smart.procedures_to_dict()
    assert [p["name"] for p in procs] == ["ciecie_adaptacyjne"]
    params = {p["name"]: p for p in procs[0]["params"]}
    assert params["sila_pct"]["unit"] == "%"
    assert params["sila_pct"]["maximum"] == 100.0
    assert params["os"]["choices"] == ["x", "y", "z"]
    assert all(p["label"] for p in procs[0]["params"])


# --- plik -----------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "smart.json"
    original = smart.default_definitions()
    smart.save(path, original)
    loaded = smart.load(path)
    assert smart.to_dict(loaded) == smart.to_dict(original)


def test_load_without_file_gives_starting_definition(tmp_path):
    loaded = smart.load(tmp_path / "nie-ma.json")
    assert smart.DEFAULT_DEFINITION in loaded


def test_broken_file_is_an_error_not_a_silent_default(tmp_path):
    path = tmp_path / "smart.json"
    path.write_text("{to nie jest json", encoding="utf-8")
    with pytest.raises(smart.SmartError):
        smart.load(path)

    path.write_text(
        json.dumps({"definitions": {"x": {"procedure": "brak"}}}), encoding="utf-8"
    )
    with pytest.raises(smart.SmartError):
        smart.load(path)


# --- ostrzeżenia ----------------------------------------------------------


def test_warning_says_procedure_is_not_in_bridge_yet():
    """Technolog musi wiedzieć, że progu siły nic jeszcze nie pilnuje."""
    out = smart.warnings(smart.default_definitions(), "sim")
    assert any("nie ma jeszcze w mostku" in w for w in out)


def test_hardware_mode_warns_about_missing_command():
    out = smart.warnings(smart.default_definitions(), "clearcore")
    assert any("błędem sterownika" in w for w in out)


# --- API ------------------------------------------------------------------


def test_get_smart_returns_definitions_and_registry(client):
    data = client.get("/api/smart").json()
    assert smart.DEFAULT_DEFINITION in data["definitions"]
    assert data["procedures"][0]["name"] == "ciecie_adaptacyjne"
    assert data["warnings"]


def test_put_smart_saves(client, restore_smart):
    new = {"SMART-sila": _definition(sila_pct=18), "wlewek-gruby": _definition(sila_pct=45)}
    res = client.put("/api/smart", json={"definitions": new})
    assert res.status_code == 200, res.text

    data = client.get("/api/smart").json()["definitions"]
    assert data["SMART-sila"]["params"]["sila_pct"] == 18
    assert data["wlewek-gruby"]["params"]["sila_pct"] == 45

    from app import config as app_config

    on_disk = json.loads(app_config.SMART_FILE.read_text(encoding="utf-8"))
    assert on_disk["definitions"]["wlewek-gruby"]["params"]["sila_pct"] == 45


def test_put_smart_rejects_bad_range(client, restore_smart):
    res = client.put("/api/smart", json={"definitions": {"x": _definition(sila_pct=500)}})
    assert res.status_code == 422
    assert "Próg siły" in res.json()["detail"]


def test_smart_page_is_served(client):
    res = client.get("/smart")
    assert res.status_code == 200
    assert "Funkcje SMART" in res.text
    assert "/static/smart.js" in res.text
