# Cykl maszyny — etap 3

Warstwa cyklu nad programem detalu: kroki poziomu admina (podanie, docisk,
wywołanie programu 12NC, wyrzut) z własnymi profilami parametrów ruchu.
Sedno etapu to **snapshot/restore profilu wokół każdego kroku** — profil
kroku wraca także przy błędzie i przy zatrzymaniu, nie tylko przy sukcesie
(wymóg z `zbyszek/DECYZJE_2026-08-25.md` §3).

Trzeci z czterech etapów tematu B — model w
[`../model-cyklu-maszyny.md`](../model-cyklu-maszyny.md).

## Pliki

- `server/app/cycle.py` — nowy: `CycleStep`, `Cycle`, cztery rodzaje kroków
  (`RUCH`, `PROGRAM`, `WYJSCIE`, `PAUZA`), walidacja z numerem kroku,
  wczytywanie/zapis JSON, `warnings()` do kontroli krzyżowej z profilami
  i osiami.
- `server/app/machine.py` — `apply_cycle`, `start_cycle`, `_run_cycle`,
  `_execute_cycle_step` ze snapshot/restore w `try/finally`; wydzielone
  `_run_operations` z `_run_program`, żeby krok `PROGRAM` wykonywał te same
  operacje bez kończenia pracy maszyny. Nowe pola statusu: `cycle_step`,
  `total_cycle_steps`, `outputs`, `active_profile`.
- `server/app/config.py` — `CYCLE_FILE` (zmienna `CYCLE_CONFIG`).
- `server/app/main.py` — `GET/PUT /api/cycle`, `POST /api/machine/cycle/start`.
- `server/tests/conftest.py` — `CYCLE_CONFIG` na katalog tymczasowy.
- `server/tests/test_cycle.py` — 26 testów.

## Uwagi

- **Snapshot/restore jest w `finally`**, więc obejmuje trzy przypadki:
  zakończenie kroku, błąd w kroku i anulowanie (STOP). Bez tego przerwany
  program detalu zostawiłby maszynę na swoich parametrach — np. na 10%
  momentu — a kolejne kroki cyklu pojechałyby z nimi po cichu. Dwa testy
  pilnują tego wprost i zostały zweryfikowane: po usunięciu `try/finally`
  oba padają.
- **Jeden przebieg, nie pętla.** `start_cycle` wykonuje cykl raz. Praca
  ciągła (tryb automatyczny) to temat F, nie ten etap.
- **Kroku „czekaj na wejście" świadomie nie ma** — dziś nie mamy żadnego
  czytelnego wejścia poza Global Stop, więc taki krok nigdy by się nie
  odblokował. Wraca, gdy wejścia A/B węzłów będą dostępne przez mostek
  (patrz [`../mozliwosci-clearpath-sc.md`](../mozliwosci-clearpath-sc.md)).
- **`WYJSCIE` działa dziś tylko w symulatorze** — protokół mostka nie ma
  komendy ustawienia dowolnego wyjścia (jest tylko `SPINDLE`, mapowane na
  jedno z wyjść BRAKE). To ta sama luka co przy limicie momentu: model
  i logika są gotowe, brakuje rozszerzenia protokołu (etap 2b).
- Krok `RUCH` obsługuje dziś tylko osie X/Y/Z — symulator i mostek nie
  poruszają innymi. Oś spoza tej trójki daje czytelny błąd zamiast cichego
  pominięcia. Osie dodatkowe czekają na rozszerzenie protokołu (temat C).
- Krok `RUCH` przechodzi przez `_check_soft_limit`, więc pozycja poza
  limitem programowym zatrzymuje cykl alarmem, a nie wjeżdża w ogranicznik.
- Testy cyklu sprzątają po sobie (`stop` + `reset` w fixture) — maszyna
  w `app.main` jest wspólna dla wszystkich modułów testowych i cykl
  zostawiony w ruchu blokowałby kolejne.
