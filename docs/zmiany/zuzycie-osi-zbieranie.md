# Zużycie osi — zbieranie i trwały zapis (temat M, krok 1-2)

Dopisuje krok 1 i 2 z proponowanej kolejności w `analiza-zuzycia-osi.md`:
zbieranie danych zużycia osi po każdym zakończonym przebiegu (cykl maszyny
albo pojedynczy program), bez dużych baz danych — szczegóły tylko z
bieżącej doby, trwały trend jako jedna linia per oś per dzień aktywności.
Bez alarmów, bez e-maila/MES, bez ekranu — to świadomie osobne kroki.

## Pliki

- `server/app/zuzycie.py` — nowy moduł: `summarize_recording()` liczy
  dystans i moment (śr./maks.) per oś z próbek jednego przebiegu;
  `record_run()` dopisuje wpis do pliku bieżącego dnia i przy okazji
  rozlicza (rollup) stare pliki dni do `trend.jsonl`, po czym je kasuje;
  `read_trend()`/`read_today()` do przyszłego ekranu (krok 3).
- `server/app/config.py` — `ZUZYCIE_DIR` (domyślnie `config/zuzycie`).
- `server/app/main.py` — `_poll_loop()` wywołuje `zuzycie.record_run()`
  dokładnie przy przejściu stanu RUNNING/PAUSED → cokolwiek innego (koniec
  przebiegu), na `machine.recording` z tego przebiegu (żyje aż do startu
  następnego, patrz `_record_sample` w `machine.py`).
- `server/tests/test_zuzycie.py` — 11 testów (podsumowanie próbek, zapis
  dnia, rollup przy zmianie dnia, odczyt, odporność na błąd zapisu).

## Uwagi

- **Moment liczony tylko na sprzęcie** (`torque_source == "sterownik"`) —
  w symulatorze pola momentu zostają `None`, żeby nie mylić zmyślonych
  wartości z pomiarem (ta sama zasada co w `funkcje-smart.md`).
- Dystans to suma odległości między kolejnymi próbkami co ~200 ms —
  przybliżenie z dokładnością do kroku próbkowania, nie dokładny tor.
- Rollup jest **leniwy** (przy pierwszym zapisie po zmianie dnia), nie
  cron — brak infrastruktury do zadań w tle w tym projekcie. Jeśli
  maszyna stoi kilka dni bez przebiegu, plik poprzedniego dnia aktywności
  zostaje rozliczony dopiero przy pierwszym kolejnym przebiegu — nie ma to
  znaczenia dla samych danych (rollup i tak liczy z timestampu pliku, nie
  z „teraz"), tylko dla tego, kiedy trafiają do `trend.jsonl`.
- Błąd zapisu (dysk pełny, brak uprawnień) nigdy nie rzuca — ginie po
  cichu, tak jak `audit.record()`. Świadomy kompromis: dane zużycia nie
  mogą zamrozić pollera statusu ani zatrzymać maszyny.
- **Nie zweryfikowane na fizycznym sterowniku** — moment z symulatora
  zawsze daje `None`, więc pola momentu w praktyce dostaną realne wartości
  dopiero na sprzęcie.
