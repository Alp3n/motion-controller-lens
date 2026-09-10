"""Zbieranie zużycia osi: szczegóły z bieżącej doby + trwały trend.

Ustalone z użytkownikiem 2026-09-10 (temat M, `docs/analiza-zuzycia-osi.md`):
bez dużych baz danych. Szczegółowe wpisy (jeden na zakończony przebieg —
cykl maszyny albo pojedynczy program) trzymane tylko w pliku BIEŻĄCEGO dnia
(`zuzycie/YYYY-MM-DD.jsonl`); przy pierwszym zapisie po zmianie dnia
poprzedni plik dnia jest sprowadzany do jednej linii PER OŚ (liczba
przebiegów, suma dystansu, średni/maks. moment) dopisywanej trwale do
`zuzycie/trend.jsonl`, po czym kasowany. Trend rośnie wolno (najwyżej kilka
linii dziennie na oś) — bezpiecznie bez limitu, to jest dane pod
długoterminową predykcję maintenance.

Format JSON Lines, jak `app/audit.py` — łatwy do przejrzenia `tail`em,
odporny na przerwany zapis (psuje się najwyżej ostatnia linia).

Moment liczony tylko, gdy przekazano `torque_measured=True` (realny odczyt
sprzętowy, `status.torque_source == "sterownik"`) — w symulatorze/bez
odczytu pole zostaje `None`, żeby nie mylić zmyślonych wartości z pomiarem
(patrz zastrzeżenia w `docs/funkcje-smart.md`).

**Świadomie poza zakresem tej pierwszej wersji** (patrz `analiza-zuzycia-osi.md`):
ekran podglądu, definicje alarmów, powiadomienia — to tylko zbieranie i
trwałe przechowywanie danych, krok 1-2 z proponowanej kolejności.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

TREND_FILENAME = "trend.jsonl"
_DAY_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")
AXES = ("x", "y", "z")  # recording (_record_sample) zna tylko te trzy


def summarize_recording(recording: list[dict], torque_measured: bool) -> dict[str, dict]:
    """Dystans i moment (śr./maks.) per oś z próbek jednego przebiegu.

    `recording` to `Machine.recording` (patrz `_record_sample` w
    `machine.py`): próbki co ~200 ms z polami x/y/z/torque. Dystans to suma
    odległości między kolejnymi próbkami — przybliżenie z dokładnością do
    kroku próbkowania, nie dokładny tor.
    """
    result: dict[str, dict] = {}
    for axis in AXES:
        distance = 0.0
        prev: float | None = None
        torque_values: list[float] = []
        for sample in recording:
            pos = sample.get(axis)
            if pos is not None:
                if prev is not None:
                    distance += abs(pos - prev)
                prev = pos
            torque = sample.get("torque", {}).get(axis)
            if torque is not None:
                torque_values.append(torque)
        avg = max_abs = None
        if torque_measured and torque_values:
            avg = round(sum(torque_values) / len(torque_values), 2)
            max_abs = max(torque_values, key=abs)
        result[axis] = {
            "dystans_mm": round(distance, 3),
            "moment_srednia_pct": avg,
            "moment_max_pct": max_abs,
        }
    return result


def _day_file(dir_path: Path, day: date) -> Path:
    return dir_path / f"{day.isoformat()}.jsonl"


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def _combine_max(current: float | None, candidate: float | None) -> float | None:
    if candidate is None:
        return current
    if current is None or abs(candidate) > abs(current):
        return candidate
    return current


def _aggregate_entries(entries: list[dict]) -> dict[str, dict]:
    """Sprowadza listę wpisów dnia (jeden per przebieg) do jednego
    podsumowania per oś — wspólne dla rollupu do trendu i dla podglądu
    „dzisiaj" na ekranie (`summarize_today`)."""
    per_axis: dict[str, dict] = {}
    for entry in entries:
        for axis, values in entry.get("osie", {}).items():
            acc = per_axis.setdefault(
                axis,
                {"n": 0, "dystans": 0.0, "moment_sum": 0.0, "moment_n": 0, "moment_max": None},
            )
            acc["n"] += 1
            acc["dystans"] += values.get("dystans_mm") or 0.0
            srednia = values.get("moment_srednia_pct")
            if srednia is not None:
                acc["moment_sum"] += srednia
                acc["moment_n"] += 1
            acc["moment_max"] = _combine_max(acc["moment_max"], values.get("moment_max_pct"))
    result = {}
    for axis, acc in per_axis.items():
        result[axis] = {
            "liczba_przebiegow": acc["n"],
            "dystans_mm_suma": round(acc["dystans"], 1),
            "moment_srednia_pct": (
                round(acc["moment_sum"] / acc["moment_n"], 2) if acc["moment_n"] else None
            ),
            "moment_max_pct": acc["moment_max"],
        }
    return result


def _rollup_day_file(day_path: Path, trend_path: Path) -> None:
    """Sprowadza jeden plik dnia do wpisów trendu (jeden per oś) i kasuje go."""
    entries = _read_jsonl(day_path)
    day = day_path.stem  # "YYYY-MM-DD"
    for axis, summary in _aggregate_entries(entries).items():
        _append_jsonl(trend_path, {"data": day, "os": axis, **summary})
    day_path.unlink(missing_ok=True)


def summarize_today(dir_path: Path, now: datetime | None = None) -> dict[str, dict]:
    """Podsumowanie bieżącej doby per oś (do ekranu `/zuzycie`) — te same
    pola co wpis trendu (`liczba_przebiegow`, `dystans_mm_suma`,
    `moment_srednia_pct`, `moment_max_pct`), liczone na żywo z pliku dnia,
    bez zapisu/rollupu."""
    return _aggregate_entries(read_today(dir_path, now))


def record_run(
    dir_path: Path,
    recording: list[dict],
    torque_measured: bool,
    now: datetime | None = None,
) -> None:
    """Wywoływane po zakończeniu przebiegu (patrz `main.py::_poll_loop`).

    Nigdy nie rzuca — błąd zapisu zużycia nie może wywrócić zatrzymania
    maszyny ani zamrozić pollera statusu (ten sam powód co w `audit.record`).
    """
    if not recording:
        return
    try:
        moment = now or datetime.now().astimezone()
        today = moment.date()
        dir_path.mkdir(parents=True, exist_ok=True)
        trend_path = dir_path / TREND_FILENAME
        for existing in sorted(dir_path.glob("*.jsonl")):
            if existing.name == TREND_FILENAME or not _DAY_FILE_RE.match(existing.name):
                continue
            if existing.stem != today.isoformat():
                _rollup_day_file(existing, trend_path)
        summary = summarize_recording(recording, torque_measured)
        _append_jsonl(
            _day_file(dir_path, today),
            {"czas": moment.isoformat(timespec="seconds"), "osie": summary},
        )
    except OSError:
        pass


def read_trend(dir_path: Path, limit: int = 1000) -> list[dict]:
    """Ostatnie wpisy trendu, od najnowszego — pod przyszły ekran (etap 3)."""
    entries = _read_jsonl(dir_path / TREND_FILENAME)
    return list(reversed(entries))[:limit]


def read_today(dir_path: Path, now: datetime | None = None) -> list[dict]:
    """Szczegółowe wpisy bieżącego dnia — pod przyszły ekran (etap 3)."""
    today = (now or datetime.now().astimezone()).date()
    return _read_jsonl(_day_file(dir_path, today))
