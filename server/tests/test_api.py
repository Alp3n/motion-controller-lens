"""Testy API (tryb symulacji) — MES, programy, sterowanie."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault("PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs"))

from app.machine import MachineError  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_status_endpoint(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] in ("NOT_HOMED", "READY", "INIT")
    assert "position" in data


def test_list_programs(client):
    res = client.get("/api/programs")
    assert res.status_code == 200
    numbers = [p["number"] for p in res.json()["programs"]]
    assert "583912004711" in numbers


def test_mes_select_order_loads_program(client):
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-2026-001", "program_number": "583912004711"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["program"]["number"] == "583912004711"
    # nie liczba dokładna — to prawdziwy plik przykładowy, edytowany też
    # ręcznie przez operatora; test sprawdza, że MES faktycznie coś wczytał
    assert len(data["program"]["operations"]) >= 1

    status = client.get("/api/status").json()
    assert status["order_id"] == "ZL-2026-001"
    assert status["program_number"] == "583912004711"


def test_mes_select_order_unknown_program(client):
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-1", "program_number": "999999999999"},
    )
    assert res.status_code == 404


def test_mes_select_order_bad_number(client):
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-1", "program_number": "abc"},
    )
    assert res.status_code == 400


def test_mes_select_order_bez_tokenu_gdy_nieustawiony(client):
    """Domyślnie (MES_TOKEN nieustawiony) endpoint zostaje otwarty — świadoma
    kompatybilność wsteczna, nie przeoczenie (patrz zmiany/token-mes.md)."""
    from app import config

    assert config.MES_TOKEN is None
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-TOK-1", "program_number": "583912004711"},
    )
    assert res.status_code == 200


def test_mes_select_order_wymaga_tokenu_gdy_ustawiony(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MES_TOKEN", "sekret-mes")
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-TOK-2", "program_number": "583912004711"},
    )
    assert res.status_code == 401


def test_mes_select_order_odrzuca_zly_token(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MES_TOKEN", "sekret-mes")
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-TOK-3", "program_number": "583912004711"},
        headers={"X-MES-Token": "zly"},
    )
    assert res.status_code == 401


def test_mes_select_order_akceptuje_poprawny_token(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MES_TOKEN", "sekret-mes")
    res = client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-TOK-4", "program_number": "583912004711"},
        headers={"X-MES-Token": "sekret-mes"},
    )
    assert res.status_code == 200


def test_start_requires_ready_state(client):
    """Bez bazowania (NOT_HOMED) start musi być odrzucony."""
    client.post("/api/machine/reset")
    client.post(
        "/api/mes/select-order",
        json={"order_id": "ZL-1", "program_number": "583912004711"},
    )
    res = client.post("/api/machine/start")
    assert res.status_code == 409
    assert "READY" in res.json()["detail"]


def test_save_program_validates(client, tmp_path):
    bad = "[NAGLOWEK]\nFORMAT;1\n"
    res = client.put("/api/programs/111111111111", json={"content": bad})
    assert res.status_code == 422


def test_save_and_get_program(client, tmp_path, monkeypatch):
    from app import config, main

    monkeypatch.setattr(config, "PROGRAMS_DIR", tmp_path)
    content = (
        "[NAGLOWEK]\nFORMAT;1\nPROGRAM;222222222222\nNAZWA;Test\n"
        "OBROTY_FREZU;10000\nPOSUW_ROBOCZY;300\nPOSUW_DOJAZDU;3000\nZ_BEZPIECZNE;10\n"
        "\n[OPERACJE]\nLP;OPERACJA;X;Y;Z;X2;Y2;UWAGI\n1;PUNKT;1;2;-1;;;test\n"
    )
    res = client.put("/api/programs/222222222222", json={"content": content})
    assert res.status_code == 200, res.text
    res = client.get("/api/programs/222222222222")
    assert res.status_code == 200
    assert res.json()["parsed"]["name"] == "Test"


# --- luzowanie osi --------------------------------------------------------


def test_release_single_axis(client):
    res = client.post("/api/machine/release", json={"axis": "z", "released": True})
    assert res.status_code == 200
    assert res.json()["released_axes"] == ["z"]
    assert client.get("/api/status").json()["released_axes"] == ["z"]

    res = client.post("/api/machine/release", json={"axis": "z", "released": False})
    assert res.json()["released_axes"] == []


def test_release_all_axes(client):
    res = client.post("/api/machine/release", json={"axis": "all", "released": True})
    assert res.json()["released_axes"] == ["x", "y", "z"]
    client.post("/api/machine/release", json={"axis": "all", "released": False})


def test_jog_refused_on_released_axis(client):
    client.post("/api/machine/release", json={"axis": "x", "released": True})
    res = client.post("/api/machine/jog", json={"axis": "x", "distance": 1})
    assert res.status_code == 409
    assert "zluzowane" in res.json()["detail"]
    # inna oś nadal działa
    assert client.post("/api/machine/jog", json={"axis": "y", "distance": 1}).status_code == 200
    client.post("/api/machine/release", json={"axis": "x", "released": False})


def test_home_refused_on_released_axis(client):
    client.post("/api/machine/release", json={"axis": "y", "released": True})
    res = client.post("/api/machine/home")
    assert res.status_code == 409
    client.post("/api/machine/release", json={"axis": "y", "released": False})


def test_go_to_zero_requires_ready_state(client):
    """Maszyna w tym pliku testów nie jest zbazowana — dojazd do zera musi
    to odrzucić, tak samo jak start programu (patrz `test_home_refused_on_released_axis`
    obok — inny powód odrzucenia, ten sam brak gotowości maszyny)."""
    res = client.post("/api/machine/go-to-zero")
    assert res.status_code == 409
    assert "READY" in res.json()["detail"]


def test_stop_zwraca_409_nie_500_gdy_mostek_odrzuci_komende(client, monkeypatch):
    """Regresja: STOP był jedynym endpointem sterowania bez obsługi
    MachineError - błąd komunikacji z mostkiem (np. odrzucona komenda SDK)
    wywalał nieobsłużony wyjątek (500) zamiast czytelnego komunikatu.
    Znalezione przy maszynie 2026-09-01 ("Node @ 1 error" przy próbie STOP)."""
    from app import main

    async def failing_stop():
        raise MachineError("mostek SC4-Hub odrzucił komendę: ERR Node @ 1 error")

    monkeypatch.setattr(main.machine, "stop", failing_stop)

    res = client.post("/api/machine/stop")

    assert res.status_code == 409
    assert "Node @ 1" in res.json()["detail"]


def test_reset_zwraca_409_nie_500_gdy_mostek_odrzuci_komende(client, monkeypatch):
    """Ten sam brakujący wzorzec co przy STOP (zobacz test wyżej) - RESET
    był jedynym pozostałym endpointem sterowania bez obsługi MachineError.
    Znalezione przy maszynie 2026-09-02, gdy "Kasuj alarm" nic nie robił
    ("Node @ 1 error" ponownie, tym razem przy próbie RESET)."""
    from app import main

    async def failing_reset():
        raise MachineError("mostek SC4-Hub odrzucił komendę: ERR Node @ 1 error")

    monkeypatch.setattr(main.machine, "reset", failing_reset)

    res = client.post("/api/machine/reset")

    assert res.status_code == 409
    assert "Node @ 1" in res.json()["detail"]


def test_release_rejects_unknown_axis(client):
    assert client.post("/api/machine/release", json={"axis": "q", "released": True}).status_code == 422
