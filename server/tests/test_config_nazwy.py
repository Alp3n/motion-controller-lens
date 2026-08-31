"""Nazewnictwo trybu i adresu mostka: nowe nazwy + zgodność wsteczna.

Po przemianowaniu ClearCore -> SC4-Hub (temat A planu rozwoju) hosty
produkcyjne mają w `machine.env` i w usłudze systemd stare nazwy. Te testy
pilnują, żeby aktualizacja serwera nie przełączyła po cichu prawdziwej
maszyny w tryb symulacji.
"""

import importlib
import os

import pytest

from app import config as config_mod
from app.machine import SC4HubMachine, SimulatedMachine, create_machine


@pytest.fixture
def reload_config(monkeypatch):
    """Przeładowuje app.config z podstawionym środowiskiem i sprząta po sobie."""

    def _reload(**env):
        for key in (
            "MACHINE_MODE",
            "BRIDGE_HOST",
            "BRIDGE_PORT",
            "CLEARCORE_HOST",
            "CLEARCORE_PORT",
        ):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(config_mod)

    yield _reload
    # inne testy importują app.main, które trzyma referencje do tego modułu —
    # przywracamy stan sprzed podmiany środowiska
    monkeypatch.undo()
    importlib.reload(config_mod)


def test_tryb_sc4hub(reload_config):
    assert reload_config(MACHINE_MODE="sc4hub").MACHINE_MODE == "sc4hub"


def test_dawna_nazwa_trybu_dalej_oznacza_sprzet(reload_config):
    """`MACHINE_MODE=clearcore` z hosta produkcyjnego -> tryb sprzętowy."""
    assert reload_config(MACHINE_MODE="clearcore").MACHINE_MODE == "sc4hub"


def test_tryb_jest_odporny_na_wielkosc_liter_i_spacje(reload_config):
    assert reload_config(MACHINE_MODE=" SC4Hub ").MACHINE_MODE == "sc4hub"


def test_nieznany_tryb_zostaje_bez_zmian(reload_config):
    """Literówka nie może udawać sprzętu — ma zostać sobą i dać symulator."""
    cfg = reload_config(MACHINE_MODE="sc4hubb")
    assert cfg.MACHINE_MODE == "sc4hubb"
    assert isinstance(create_machine(cfg.MACHINE_MODE, "127.0.0.1", 8500), SimulatedMachine)


def test_adres_mostka_z_nowych_nazw(reload_config):
    cfg = reload_config(BRIDGE_HOST="10.0.0.7", BRIDGE_PORT="9000")
    assert (cfg.BRIDGE_HOST, cfg.BRIDGE_PORT) == ("10.0.0.7", 9000)


def test_adres_mostka_z_dawnych_nazw(reload_config):
    cfg = reload_config(CLEARCORE_HOST="10.0.0.8", CLEARCORE_PORT="9100")
    assert (cfg.BRIDGE_HOST, cfg.BRIDGE_PORT) == ("10.0.0.8", 9100)


def test_nowe_nazwy_maja_pierwszenstwo(reload_config):
    cfg = reload_config(
        BRIDGE_HOST="10.0.0.7",
        BRIDGE_PORT="9000",
        CLEARCORE_HOST="10.0.0.8",
        CLEARCORE_PORT="9100",
    )
    assert (cfg.BRIDGE_HOST, cfg.BRIDGE_PORT) == ("10.0.0.7", 9000)


def test_domyslny_adres_to_lokalny_mostek(reload_config):
    """Mostek działa na tym samym komputerze — dawne 192.168.0.50 było z ClearCore."""
    cfg = reload_config()
    assert (cfg.BRIDGE_HOST, cfg.BRIDGE_PORT) == ("127.0.0.1", 8500)


@pytest.mark.parametrize("mode", ["sc4hub", "clearcore"])
def test_create_machine_daje_sprzet_dla_obu_nazw(mode):
    assert isinstance(create_machine(mode, "127.0.0.1", 8500), SC4HubMachine)


def test_create_machine_domyslnie_symulator():
    assert isinstance(create_machine("sim", "127.0.0.1", 8500), SimulatedMachine)
