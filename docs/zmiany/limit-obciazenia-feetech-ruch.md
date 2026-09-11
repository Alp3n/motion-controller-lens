# Limit obciążenia FEETECH w kroku RUCH (zabezpieczenie awaryjne)

Dopełnienie zamówienia z 2026-09-11 („w programie jedzie na pozycję z
zakresu długości osi i kontroluje siłę"). Decyzja operatora po doprecyzowaniu
2026-09-12: **RUCH ma NORMALNIE dojeżdżać do zadanej pozycji** — próg
obciążenia to wyłącznie zabezpieczenie awaryjne (np. zablokowany
mechanizm), nie zwykły sposób zatrzymania (w przeciwieństwie do procedur
SMART na X, które celowo zwalniają/zatrzymują się na progu siły).

## Zachowanie

- `AxisConfig.feetech_load_limit: int | None` — domyślnie `None`
  (wyłączony, bezpieczny start). Ustawiany per oś z ekranu `/axes`, tylko
  dla osi ze sterownikiem `feetech`.
- Gdy ustawiony: podczas kroku RUCH (`_feetech_move_to_and_wait`) serwer
  na bieżąco czyta `|PRESENT_LOAD|` (jeden odczyt `read_position_and_load`
  na iterację pętli oczekiwania na `MOVING`, bez dodatkowych rund RS485).
  Przekroczenie progu **przerywa ruch** (`FeetekDriver.stop_position_move`
  — komenda „jedź tam, gdzie już jesteś", bo tryb pozycyjny nie ma osobnej
  komendy STOP) i rzuca błąd → krok cyklu kończy się `MachineError` → cykl
  przechodzi w ALARM, jak przy każdym innym błędzie kroku.
- Bez przekroczenia progu (albo gdy limit wyłączony) — zero zmiany
  zachowania względem `zmiany/feetech-w-cyklu-maszyny.md`.
- **Nie dotyczy JOG** (tryb koła) — tylko RUCH cyklu.

## Pliki

- `server/app/axes.py` — `AxisConfig.feetech_load_limit`, walidacja
  (musi być `> 0`, jeśli podany), dopisane od razu do `OPTIONAL_FIELDS`
  (ten sam prewencyjny wzorzec co `feetech_speed`/`feetech_acc`).
- `server/app/feetech_driver.py` — `is_moving()` (wydzielone z
  `wait_until_stopped`, reużywane), `stop_position_move()` (przerwanie
  ruchu pozycyjnego przez komendę do bieżącej pozycji).
- `server/app/main.py` — `_feetech_move_to_and_wait()` przepisane: zamiast
  delegować do `driver.wait_until_stopped()`, pyta samo, w tej samej pętli
  sprawdzając `load_limit`; `_feetech_cycle_move()` przekazuje
  `axis_cfg.feetech_load_limit`.
- `server/app/static/axes.html`, `axes.js` — nowa kolumna „Limit
  obciążenia FEETECH" (tylko dla osi feetech), puste pole = wyłączony
  (nie 0 — 0 oznaczałoby zatrzymanie przy najmniejszym obciążeniu).
- `server/tests/test_axes.py` — 6 testów (domyślnie wyłączony, walidacja,
  round-trip, kompatybilność starych plików, regresja `with_current_values`).
- `server/tests/test_feetech_driver.py` — testy `is_moving`,
  `stop_position_move`.
- `server/tests/test_feetech_cycle_move.py` — przepisany pod nową pętlę
  (`read_position_and_load`/`is_moving` zamiast `wait_until_stopped`) +
  3 nowe testy limitu (bez limitu ignoruje wysokie obciążenie, z limitem
  przerywa przy przekroczeniu, z limitem dojeżdża normalnie poniżej progu).

## Uwagi

- **Dekodowanie `PRESENT_LOAD` nie jest w pełni potwierdzone** (patrz
  `zmiany/protokol-feetech.md`) — próg działa na wartości bezwzględnej
  (`abs(load)`), odpornie na niepewność znaku, ale sama SKALA (co
  numerycznie oznacza „duże obciążenie" dla tego serwa/mechanizmu) nie
  jest znana z dokumentacji. **Próg trzeba wyznaczyć empirycznie przy
  maszynie** — obserwując realne odczyty `load` w `/api/status`
  (`feetech_raw`) podczas normalnej pracy i przy celowym oporze, zanim
  ustawi się limit w konfiguracji.
- Nie testowane jeszcze fizycznie — do zweryfikowania przy najbliższej
  obecności przy maszynie, najpierw z bardzo wysokim progiem (żeby
  potwierdzić, że NIE przerywa normalnego ruchu), potem z niskim progiem
  celowo (żeby potwierdzić, że przerywa i cykl idzie w ALARM).
