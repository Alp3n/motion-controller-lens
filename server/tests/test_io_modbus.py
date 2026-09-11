"""Konfiguracja nazwanych kanałów I/O Modbus (temat L) — model, plik."""

from __future__ import annotations

import pytest

from app import io_modbus as io


def test_default_io_ma_zgloszone_nazwy():
    cfg = io.default_io()
    assert cfg.do["do0"].label == "LG"
    assert cfg.do["do1"].label == "LR"
    assert cfg.do["do2"].label == "LY"
    assert cfg.di["di0"].label == "osłona_1"
    assert cfg.di["di4"].label == "drzwi_impulsy"
    assert cfg.ai["ai0"].label == "temperatura_wrzeciona"
    assert cfg.ai["ai1"].label == "prąd_wrzeciona"


def test_default_io_watchdog_domyslnie_wylaczony():
    cfg = io.default_io()
    assert cfg.watchdog.enabled is False
    assert cfg.watchdog.pulse_channel == "di4"
    assert cfg.watchdog.guard_channel == "di0"


def test_default_io_ma_wszystkie_kanaly_nawet_puste():
    cfg = io.default_io()
    assert len(cfg.do) == io.DO_COUNT
    assert len(cfg.di) == io.DI_COUNT
    assert len(cfg.ai) == io.AI_COUNT
    assert cfg.do["do7"].label == ""


def test_to_dict_from_dict_roundtrip():
    cfg = io.default_io()
    restored = io.IoConfig.from_dict(cfg.to_dict())
    assert restored == cfg


def test_from_dict_nieznany_kanal_odrzucony():
    data = io.default_io().to_dict()
    data["do"]["do99"] = {"label": "cos"}
    with pytest.raises(io.IoConfigError, match="do99"):
        io.IoConfig.from_dict(data)


def test_from_dict_brak_pol_uzupelnia_puste():
    restored = io.IoConfig.from_dict({})
    assert len(restored.do) == io.DO_COUNT
    assert all(c.label == "" for c in restored.do.values())
    assert restored.watchdog.enabled is False


def test_channel_by_label():
    cfg = io.default_io()
    assert cfg.channel_by_label(cfg.do, "LG") == "do0"
    assert cfg.channel_by_label(cfg.di, "Stop") == "di3"
    assert cfg.channel_by_label(cfg.ai, "nieistniejące") is None


def test_watchdog_from_dict_czesciowe_pola():
    wd = io.WatchdogConfig.from_dict({"enabled": True})
    assert wd.enabled is True
    assert wd.pulse_channel == "di4"  # domyślne zostaje


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "io_modbus.json"
    cfg = io.default_io()
    cfg.do["do6"].label = "test_extra"
    io.save(path, cfg)
    loaded = io.load(path)
    assert loaded == cfg


def test_load_bez_pliku_zwraca_domyslne(tmp_path):
    assert io.load(tmp_path / "brak.json") == io.default_io()


def test_load_uszkodzony_plik_rzuca(tmp_path):
    path = tmp_path / "zle.json"
    path.write_text("{zle", encoding="utf-8")
    with pytest.raises(io.IoConfigError):
        io.load(path)
