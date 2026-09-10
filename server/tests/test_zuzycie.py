"""Zużycie osi (temat M): podsumowanie przebiegu, plik dnia, rollup do trendu."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app import zuzycie


def _sample(x=0.0, y=0.0, z=0.0, torque=None):
    return {"t": 0.0, "op": None, "cycle_step": None, "x": x, "y": y, "z": z,
            "torque": torque or {}}


# --- summarize_recording ----------------------------------------------------


def test_summarize_recording_liczy_dystans_i_moment():
    recording = [
        _sample(x=0.0, torque={"x": 1.0}),
        _sample(x=5.0, torque={"x": 3.0}),
        _sample(x=2.0, torque={"x": -9.0}),
    ]
    result = zuzycie.summarize_recording(recording, torque_measured=True)
    assert result["x"]["dystans_mm"] == pytest.approx(5.0 + 3.0)
    assert result["x"]["moment_srednia_pct"] == pytest.approx((1.0 + 3.0 - 9.0) / 3, abs=0.01)
    assert result["x"]["moment_max_pct"] == -9.0  # największa wartość bezwzględna, ze znakiem
    assert result["y"]["dystans_mm"] == 0.0


def test_summarize_recording_bez_pomiaru_momentu_zwraca_none():
    recording = [_sample(x=0.0, torque={"x": 1.0}), _sample(x=5.0, torque={"x": 3.0})]
    result = zuzycie.summarize_recording(recording, torque_measured=False)
    assert result["x"]["dystans_mm"] == 5.0
    assert result["x"]["moment_srednia_pct"] is None
    assert result["x"]["moment_max_pct"] is None


def test_summarize_recording_pusta_lista():
    result = zuzycie.summarize_recording([], torque_measured=True)
    assert result["x"]["dystans_mm"] == 0.0
    assert result["x"]["moment_srednia_pct"] is None


# --- record_run: plik bieżącego dnia ----------------------------------------


def test_record_run_dopisuje_do_pliku_dnia(tmp_path: Path):
    recording = [_sample(x=0.0, torque={"x": 1.0}), _sample(x=4.0, torque={"x": 5.0})]
    now = datetime(2026, 9, 10, 14, 30, 0)

    zuzycie.record_run(tmp_path, recording, torque_measured=True, now=now)

    day_file = tmp_path / "2026-09-10.jsonl"
    assert day_file.exists()
    lines = day_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["osie"]["x"]["dystans_mm"] == 4.0
    assert entry["czas"].startswith("2026-09-10T14:30:00")


def test_record_run_pusta_lista_nie_zapisuje_niczego(tmp_path: Path):
    zuzycie.record_run(tmp_path, [], torque_measured=True, now=datetime(2026, 9, 10))
    assert not (tmp_path / "2026-09-10.jsonl").exists()


def test_record_run_dwa_przebiegi_tego_samego_dnia_dopisuja_sie(tmp_path: Path):
    now = datetime(2026, 9, 10, 8, 0, 0)
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False, now=now)
    zuzycie.record_run(tmp_path, [_sample(x=2.0)], torque_measured=False, now=now)
    lines = (tmp_path / "2026-09-10.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_record_run_blad_zapisu_nie_rzuca(tmp_path: Path):
    """dir_path, którego nie da się utworzyć (rodzic to plik) — błąd ginie po cichu."""
    blocker = tmp_path / "blocker"
    blocker.write_text("nie katalog")
    bad_dir = blocker / "zuzycie"

    zuzycie.record_run(bad_dir, [_sample(x=1.0)], torque_measured=True)  # nie rzuca


# --- rollup do trendu przy zmianie dnia -------------------------------------


def test_rollup_przy_zmianie_dnia_agreguje_i_kasuje_plik(tmp_path: Path):
    wczoraj = datetime(2026, 9, 9, 10, 0, 0)
    dzis = datetime(2026, 9, 10, 8, 0, 0)

    zuzycie.record_run(
        tmp_path, [_sample(x=0.0, torque={"x": 2.0}), _sample(x=3.0, torque={"x": 4.0})],
        torque_measured=True, now=wczoraj,
    )
    zuzycie.record_run(
        tmp_path, [_sample(x=0.0, torque={"x": -10.0}), _sample(x=1.0, torque={"x": -1.0})],
        torque_measured=True, now=wczoraj.replace(hour=15),
    )
    assert (tmp_path / "2026-09-09.jsonl").exists()

    # Pierwszy zapis następnego dnia wyzwala rollup poprzedniego.
    zuzycie.record_run(tmp_path, [_sample(x=0.0)], torque_measured=False, now=dzis)

    assert not (tmp_path / "2026-09-09.jsonl").exists()
    trend = zuzycie.read_trend(tmp_path)
    x_entry = next(e for e in trend if e["os"] == "x" and e["data"] == "2026-09-09")
    assert x_entry["liczba_przebiegow"] == 2
    assert x_entry["dystans_mm_suma"] == pytest.approx(3.0 + 1.0)
    assert x_entry["moment_max_pct"] == -10.0  # największa wartość bezwzględna z obu przebiegów
    # dzisiejszy plik zostaje osobno, nie trafia do trendu
    assert (tmp_path / "2026-09-10.jsonl").exists()


def test_rollup_pomija_dni_ktore_juz_sa_dzisiejszym_plikiem(tmp_path: Path):
    now = datetime(2026, 9, 10, 9, 0, 0)
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False, now=now)
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False, now=now.replace(hour=10))

    assert (tmp_path / "2026-09-10.jsonl").exists()
    assert not (tmp_path / zuzycie.TREND_FILENAME).exists()


# --- odczyt ------------------------------------------------------------------


def test_read_trend_od_najnowszych(tmp_path: Path):
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False,
                        now=datetime(2026, 9, 8, 10, 0, 0))
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False,
                        now=datetime(2026, 9, 9, 10, 0, 0))
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False,
                        now=datetime(2026, 9, 10, 10, 0, 0))  # wyzwala rollup 08 i 09

    trend = zuzycie.read_trend(tmp_path)
    dates = [e["data"] for e in trend if e["os"] == "x"]
    assert dates == sorted(dates, reverse=True)


def test_read_today_zwraca_tylko_dzisiejsze_wpisy(tmp_path: Path):
    now = datetime(2026, 9, 10, 9, 0, 0)
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False, now=now)
    entries = zuzycie.read_today(tmp_path, now=now)
    assert len(entries) == 1


# --- summarize_today ---------------------------------------------------------


def test_summarize_today_agreguje_biezaca_dobe(tmp_path: Path):
    now = datetime(2026, 9, 10, 9, 0, 0)
    zuzycie.record_run(
        tmp_path, [_sample(x=0.0, torque={"x": 2.0}), _sample(x=3.0, torque={"x": 4.0})],
        torque_measured=True, now=now,
    )
    zuzycie.record_run(
        tmp_path, [_sample(x=0.0, torque={"x": -10.0}), _sample(x=1.0, torque={"x": -1.0})],
        torque_measured=True, now=now.replace(hour=11),
    )
    summary = zuzycie.summarize_today(tmp_path, now=now)
    assert summary["x"]["liczba_przebiegow"] == 2
    assert summary["x"]["dystans_mm_suma"] == pytest.approx(3.0 + 1.0)
    assert summary["x"]["moment_max_pct"] == -10.0


def test_summarize_today_puste_gdy_brak_danych(tmp_path: Path):
    assert zuzycie.summarize_today(tmp_path, now=datetime(2026, 9, 10)) == {}


def test_summarize_today_nie_dotyka_pliku_ani_trendu(tmp_path: Path):
    """W przeciwieństwie do rollupu - samo podsumowanie nie kasuje pliku
    dnia ani nic nie dopisuje do trendu (to nadal aktywna, dzisiejsza doba)."""
    now = datetime(2026, 9, 10, 9, 0, 0)
    zuzycie.record_run(tmp_path, [_sample(x=1.0)], torque_measured=False, now=now)
    zuzycie.summarize_today(tmp_path, now=now)
    assert (tmp_path / "2026-09-10.jsonl").exists()
    assert not (tmp_path / zuzycie.TREND_FILENAME).exists()
