"""Dziennik zmian konfiguracji: kto, kiedy i co zmienił.

Powód istnienia: przy wyborze osobnych kont zamiast wspólnych PIN-ów (temat E)
chodziło właśnie o to, żeby dało się ustalić, kto zmienił parametry siły
i prędkości. Samo konto tego nie daje — daje to dopiero zapis zmian.

Format: JSON Lines (jeden wpis na linię), dopisywany na końcu pliku. Prosty do
przejrzenia zwykłym `tail`, odporny na przerwany zapis (psuje się najwyżej
ostatnia linia, nie cały plik).

**Czego ten dziennik nie jest:** dowodem odpornym na manipulację. Plik leży na
tym samym komputerze, a kto ma do niego dostęp na poziomie systemu, może go
zmienić. To zapis roboczy „kto ostatnio ruszał parametry", nie rejestr
audytowy w sensie formalnym.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ile ostatnich wpisów czytamy na ekran diagnostyczny — plik może urosnąć,
# a i tak interesuje nas ogon
DEFAULT_TAIL = 200


def record(path: Path, *, login: str, role: str, action: str, detail: str = "") -> None:
    """Dopisuje jeden wpis. Błąd zapisu nie może wywrócić operacji maszyny.

    Świadomy kompromis: gdyby brak miejsca na dysku blokował zapis konfiguracji,
    maszyna stawałaby przez dziennik. Zamiast tego wpis ginie — dlatego ekran
    diagnostyczny pokazuje też, czy plik w ogóle istnieje.
    """
    entry = {
        "czas": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "login": login,
        "rola": role,
        "akcja": action,
        "szczegoly": detail,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def tail(path: Path, limit: int = DEFAULT_TAIL) -> list[dict]:
    """Ostatnie wpisy, od najnowszego. Uszkodzone linie są pomijane."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
        if len(entries) >= limit:
            break
    return entries
