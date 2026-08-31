"""Role i logowanie: hasła, sesje, dostęp do ekranów i API, dziennik zmian.

Testy budują własną instancję aplikacji z podstawionym plikiem kont —
`app.main` jest importowane raz na cały przebieg testów, a reszta plików
zakłada wyłączone logowanie.
"""

import importlib
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["MACHINE_MODE"] = "sim"
os.environ.setdefault(
    "PROGRAMS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "programs")
)

from app import audit, users  # noqa: E402

# Hasła w testach liczymy małą liczbą iteracji — 600 000 iteracji PBKDF2 razy
# kilkadziesiąt logowań to kilkadziesiąt sekund na nic.
TEST_ITERATIONS = 1000
HASLO = "haslo-testowe-123"

KONTA = [
    ("zbyszek", "Zbigniew", users.ROLE_ADMIN),
    ("ania", "Ania", users.ROLE_TECHNOLOG),
    ("operator1", "Operator", users.ROLE_OPERATOR),
]


# --- hasła ----------------------------------------------------------------


def test_haslo_nie_jest_zapisane_jawnie():
    stored = users.hash_password(HASLO, iterations=TEST_ITERATIONS)
    assert HASLO not in stored
    assert stored.startswith("pbkdf2_sha256$")


def test_weryfikacja_hasla():
    stored = users.hash_password(HASLO, iterations=TEST_ITERATIONS)
    assert users.verify_password(HASLO, stored)
    assert not users.verify_password(HASLO + "x", stored)


def test_dwa_te_same_hasla_maja_rozne_skroty():
    """Losowa sól — inaczej po skrótach widać, kto ma takie samo hasło."""
    a = users.hash_password(HASLO, iterations=TEST_ITERATIONS)
    b = users.hash_password(HASLO, iterations=TEST_ITERATIONS)
    assert a != b


def test_krotkie_haslo_odrzucone():
    with pytest.raises(users.UserError, match="znaków"):
        users.hash_password("krotkie")


def test_uszkodzony_skrot_to_odmowa_a_nie_wyjatek():
    assert users.verify_password(HASLO, "bzdura") is False


# --- role -----------------------------------------------------------------


@pytest.mark.parametrize(
    "rola,wymagana,oczekiwane",
    [
        ("admin", "operator", True),
        ("admin", "admin", True),
        ("technolog", "operator", True),
        ("technolog", "admin", False),
        ("operator", "operator", True),
        ("operator", "technolog", False),
        ("nieznana", "operator", False),
    ],
)
def test_role_sa_narastajace(rola, wymagana, oczekiwane):
    assert users.role_allows(rola, wymagana) is oczekiwane


# --- plik kont ------------------------------------------------------------


def _konto(login, rola=users.ROLE_ADMIN):
    return {
        "login": login,
        "name": login,
        "role": rola,
        "password_hash": users.hash_password(HASLO, iterations=TEST_ITERATIONS),
    }


def test_plik_bez_admina_jest_odrzucany():
    """Bez admina nikt nie wejdzie do konfiguracji — to zawsze pomyłka."""
    with pytest.raises(users.UserError, match="administrator"):
        users.parse_users([_konto("ktos", users.ROLE_OPERATOR)])


def test_haslo_jawne_w_pliku_jest_odrzucane():
    bad = {"login": "szef", "role": "admin", "password_hash": "tajne123"}
    with pytest.raises(users.UserError, match="PBKDF2"):
        users.parse_users([bad])


def test_zly_login_jest_odrzucany():
    with pytest.raises(users.UserError, match="login"):
        users.parse_users([_konto("Duże Litery")])


def test_zapis_pliku_kont_ma_prawa_tylko_dla_wlasciciela(tmp_path):
    path = tmp_path / "users.json"
    users.save(path, {"szef": users.User.from_dict(_konto("szef"))})
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_brak_pliku_to_wylaczone_logowanie(tmp_path):
    assert users.load(tmp_path / "nie-ma.json") == {}


def test_bledny_plik_zatrzymuje_zamiast_wylaczyc_logowanie(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{ to nie jest json", encoding="utf-8")
    with pytest.raises(users.UserError):
        users.load(path)


# --- sesje ----------------------------------------------------------------


def test_sesja_wygasa():
    s = users.Sessions(ttl_seconds=10)
    token = s.create("zbyszek", now=100.0)
    assert s.login_for(token, now=105.0) == "zbyszek"
    assert s.login_for(token, now=200.0) is None


def test_sesja_jest_przesuwna():
    """Panel stoi otwarty całą zmianę — liczymy od ostatniego użycia."""
    s = users.Sessions(ttl_seconds=10)
    token = s.create("zbyszek", now=100.0)
    assert s.login_for(token, now=109.0) == "zbyszek"
    assert s.login_for(token, now=117.0) == "zbyszek"


def test_nieznany_token_to_brak_sesji():
    assert users.Sessions(10).login_for("cokolwiek") is None


def test_blokada_po_nieudanych_probach():
    s = users.Sessions(10)
    for _ in range(users.MAX_FAILED):
        s.note_failure("zbyszek", now=100.0)
    assert s.locked_for("zbyszek", now=100.0) > 0
    assert s.locked_for("zbyszek", now=100.0 + users.LOCKOUT_SECONDS + 1) == 0
    assert s.locked_for("ktos-inny", now=100.0) == 0


def test_udane_logowanie_kasuje_licznik_prob():
    s = users.Sessions(10)
    for _ in range(users.MAX_FAILED - 1):
        s.note_failure("zbyszek", now=100.0)
    s.note_success("zbyszek")
    s.note_failure("zbyszek", now=100.0)
    assert s.locked_for("zbyszek", now=100.0) == 0


def test_wylogowanie_wszystkich_sesji_konta():
    s = users.Sessions(100)
    a, b = s.create("zbyszek"), s.create("zbyszek")
    c = s.create("ania")
    s.drop_user("zbyszek")
    assert s.login_for(a) is None and s.login_for(b) is None
    assert s.login_for(c) == "ania"


# --- dziennik zmian -------------------------------------------------------


def test_dziennik_zapisuje_kto_co_zmienil(tmp_path):
    path = tmp_path / "dziennik.jsonl"
    audit.record(path, login="zbyszek", role="admin", action="zapis profili", detail="10%")
    entries = audit.tail(path)
    assert entries[0]["login"] == "zbyszek"
    assert entries[0]["akcja"] == "zapis profili"


def test_dziennik_zwraca_od_najnowszego(tmp_path):
    path = tmp_path / "dziennik.jsonl"
    for i in range(3):
        audit.record(path, login="a", role="admin", action=f"akcja {i}")
    assert [e["akcja"] for e in audit.tail(path)] == ["akcja 2", "akcja 1", "akcja 0"]


def test_uszkodzona_linia_nie_psuje_dziennika(tmp_path):
    path = tmp_path / "dziennik.jsonl"
    audit.record(path, login="a", role="admin", action="dobra")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ucięty wpis\n")
    audit.record(path, login="b", role="admin", action="druga dobra")
    assert [e["akcja"] for e in audit.tail(path)] == ["druga dobra", "dobra"]


def test_blad_zapisu_dziennika_nie_wywraca_operacji(tmp_path):
    """Brak miejsca na dysku nie może zatrzymać maszyny przez dziennik."""
    audit.record(tmp_path / "plik" / "jako" / "katalog", login="a", role="admin",
                 action="x")  # katalog nadrzędny to plik — zapis się nie uda
    # brak wyjątku = test przeszedł


# --- aplikacja z włączonym logowaniem -------------------------------------


@pytest.fixture(scope="module")
def app_z_kontami(tmp_path_factory):
    """Osobna instancja aplikacji z plikiem kont i własnymi plikami konfiguracji."""
    tmp = tmp_path_factory.mktemp("auth")
    accounts = {
        login: users.User.from_dict(
            {
                "login": login,
                "name": name,
                "role": rola,
                "password_hash": users.hash_password(HASLO, iterations=TEST_ITERATIONS),
            }
        )
        for login, name, rola in KONTA
    }
    users_file = tmp / "users.json"
    users.save(users_file, accounts)

    stare = {k: os.environ.get(k) for k in
             ("USERS_CONFIG", "AUDIT_LOG", "AXES_CONFIG", "PROFILES_CONFIG",
              "CYCLE_CONFIG", "SPINDLE_CONFIG")}
    os.environ["USERS_CONFIG"] = str(users_file)
    os.environ["AUDIT_LOG"] = str(tmp / "dziennik.jsonl")
    for key, name in [("AXES_CONFIG", "axes.json"), ("PROFILES_CONFIG", "profiles.json"),
                      ("CYCLE_CONFIG", "cycle.json"), ("SPINDLE_CONFIG", "spindle.json")]:
        os.environ[key] = str(tmp / name)

    from app import config as config_mod
    from app import main as main_mod

    importlib.reload(config_mod)
    module = importlib.reload(main_mod)
    yield module, tmp

    for key, value in stare.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    importlib.reload(config_mod)
    importlib.reload(main_mod)


@pytest.fixture
def klient(app_z_kontami):
    module, _ = app_z_kontami
    with TestClient(module.app) as c:
        yield c


def zaloguj(klient, login):
    res = klient.post("/api/auth/login", json={"login": login, "password": HASLO})
    assert res.status_code == 200, res.text
    return res


def test_logowanie_i_kim_jestem(klient):
    assert klient.get("/api/auth/me").json()["user"] is None
    zaloguj(klient, "zbyszek")
    me = klient.get("/api/auth/me").json()
    assert me["auth_enabled"] is True
    assert me["user"]["role"] == "admin"
    assert "password_hash" not in me["user"]


def test_zle_haslo_daje_ten_sam_komunikat_co_nieznany_login(klient):
    a = klient.post("/api/auth/login", json={"login": "zbyszek", "password": "zle"})
    b = klient.post("/api/auth/login", json={"login": "nie-ma-takiego", "password": "zle"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_wylogowanie_uniewaznia_sesje(klient):
    zaloguj(klient, "zbyszek")
    klient.post("/api/auth/logout")
    assert klient.get("/api/auth/me").json()["user"] is None


def test_operator_nie_wejdzie_do_konfiguracji_osi(klient):
    zaloguj(klient, "operator1")
    res = klient.put("/api/axes", json={"axes": {}})
    assert res.status_code == 403
    assert "uprawnień" in res.json()["detail"]


def test_technolog_zapisze_program_ale_nie_profile(klient):
    zaloguj(klient, "ania")
    assert klient.get("/api/programs").status_code == 200
    res = klient.post("/api/profiles/active", json={"active": "globalny"})
    assert res.status_code == 403


def test_operator_nie_widzi_listy_programow(klient):
    zaloguj(klient, "operator1")
    assert klient.get("/api/programs").status_code == 403


def test_niezalogowany_dostaje_401(klient):
    assert klient.post("/api/machine/home").status_code == 401


def test_stop_dziala_bez_logowania(klient):
    """Świadomie: wygasła sesja nie może odebrać możliwości zatrzymania maszyny."""
    assert klient.post("/api/machine/stop").status_code == 200


def test_status_jest_publiczny(klient):
    assert klient.get("/api/status").status_code == 200


def test_ekran_bez_logowania_przekierowuje_na_login(klient):
    res = klient.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login?cel=/"


def test_ekran_ponad_role_daje_403_a_nie_przekierowanie(klient):
    zaloguj(klient, "operator1")
    res = klient.get("/axes", follow_redirects=False)
    assert res.status_code == 403


def test_admin_wchodzi_na_ekran_diagnostyczny(klient):
    zaloguj(klient, "zbyszek")
    assert klient.get("/diagnostics").status_code == 200
    dane = klient.get("/api/diagnostics").json()
    assert dane["auth"]["enabled"] is True
    assert len(dane["auth"]["users"]) == len(KONTA)
    assert dane["safety"]["brak"], "ekran ma wymieniać, czego nie ma"


def test_technolog_nie_wejdzie_na_diagnostyke(klient):
    zaloguj(klient, "ania")
    assert klient.get("/api/diagnostics").status_code == 403


def test_zmiana_konfiguracji_trafia_do_dziennika(klient, app_z_kontami):
    _, tmp = app_z_kontami
    zaloguj(klient, "zbyszek")
    assert klient.put("/api/spindle", json={"default_rpm": 8888}).status_code == 200
    wpisy = audit.tail(tmp / "dziennik.jsonl")
    zapis = next(e for e in wpisy if e["akcja"] == "zapis ustawień wrzeciona")
    assert zapis["login"] == "zbyszek"
    assert zapis["rola"] == "admin"
    assert "8888" in zapis["szczegoly"]


def test_nieudane_logowanie_trafia_do_dziennika(klient, app_z_kontami):
    _, tmp = app_z_kontami
    klient.post("/api/auth/login", json={"login": "ania", "password": "zle"})
    wpisy = audit.tail(tmp / "dziennik.jsonl")
    assert any(e["akcja"] == "nieudane logowanie" for e in wpisy)


def test_ekran_logowania_jest_publiczny(klient):
    assert klient.get("/login").status_code == 200


# --- aplikacja bez kont (dzisiejsze wdrożenia) ----------------------------


@pytest.fixture
def klient_bez_kont(tmp_path):
    """Aplikacja wczytana ze wskazaniem na nieistniejący plik kont."""
    stare = os.environ.get("USERS_CONFIG")
    os.environ["USERS_CONFIG"] = str(tmp_path / "nie-ma-kont.json")
    from app import config as config_mod
    from app import main as main_mod

    importlib.reload(config_mod)
    module = importlib.reload(main_mod)
    with TestClient(module.app) as c:
        yield c
    if stare is None:
        os.environ.pop("USERS_CONFIG", None)
    else:
        os.environ["USERS_CONFIG"] = stare
    importlib.reload(config_mod)
    importlib.reload(main_mod)


def test_bez_pliku_kont_wszystko_dziala_bez_logowania(klient_bez_kont):
    """Aktualizacja serwera nie może zablokować maszyny, na której nie ma kont."""
    c = klient_bez_kont
    assert c.get("/api/auth/me").json()["auth_enabled"] is False
    assert c.get("/", follow_redirects=False).status_code == 200
    assert c.get("/api/status").status_code == 200
    assert c.put("/api/spindle", json={"default_rpm": 12000}).status_code == 200
    res = c.post("/api/auth/login", json={"login": "ktos", "password": "haslo1234"})
    assert res.status_code == 409  # nie ma się do czego logować


def test_bez_kont_dziennik_notuje_ze_nie_wiadomo_kto(klient_bez_kont, tmp_path):
    """Zmiana bez logowania musi zostawić ślad, że nie da się jej przypisać."""
    from app import config as config_mod

    klient_bez_kont.put("/api/spindle", json={"default_rpm": 11000})
    wpisy = audit.tail(config_mod.AUDIT_FILE)
    assert any(e["login"] == "(bez logowania)" for e in wpisy)
