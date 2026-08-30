# Cykl maszyny na prawdziwym sterowniku (ClearCoreMachine)

Znalezisko z pracy nad tematem F: `ClearCoreMachine` nie miał w ogóle
`start_cycle` — `/cycle` (jeden przebieg i tryb automatyczny) na prawdziwym
sterowniku zwracał niezłapany błąd. Nie była to regresja tamtej zmiany —
`/cycle` nie działał na sprzęcie już od etapu 4 tematu B, po prostu nikt
wcześniej tego nie sprawdził ani nie zapisał (`docs/zmiany/tryby-pracy.md`).

## Co zrobione

Dopisane `start_cycle`/`_run_cycle`/`_execute_cycle_step`/
`_run_cycle_step_body` w `ClearCoreMachine`, analogicznie do już działającej
implementacji w `SimulatedMachine`:

- **RUCH** → `MOVEZ` + `MOVEXY` komendami mostka, z tą samą walidacją osi
  (tylko X/Y/Z) i limitów programowych co ruch ręczny.
- **PROGRAM** → wywołuje `_run_program_operations()` — dokładnie tę samą
  sekwencję komend, która obsługuje bezpośrednie uruchomienie programu
  (`start()`/`_run_program`) i była sprawdzona na sprzęcie w sesji
  2026-08-14. Wydzielona z `_run_program` bez zmiany treści ani kolejności
  komend — czysta refaktoryzacja.
- **PAUZA** → `SPINDLE 0`, czeka na wznowienie przyciskiem START.
- **WYJSCIE** → tylko `self.status.outputs` — **mostek nie ma jeszcze
  komendy ustawienia wyjścia** (to samo ograniczenie co w symulatorze,
  etap 2b/3 tematu B), więc nic fizycznie się nie przełącza.
- Tryb automatyczny (`loop=True`, temat F) i snapshot/restore profilu
  wokół kroku — ta sama logika co w symulatorze.

## Pliki

- `server/app/machine.py` — `ClearCoreMachine._run_program_operations`
  (wydzielone z `_run_program`), `start_cycle`, `_run_cycle`,
  `_execute_cycle_step`, `_run_cycle_step_body`.
- `server/tests/test_clearcore.py` — **nowy plik**, pierwsze testy
  automatyczne dla `ClearCoreMachine` w ogóle (wcześniej klasa nie miała
  żadnych — jedyną weryfikacją był prawdziwy sprzęt). `_command` jest
  podstawiane (bez TCP), więc testy sprawdzają wyłącznie tłumaczenie
  `Operation`/`CycleStep` na tekst komend, nie protokół sieciowy.

## Uwagi — to jest ważne

**Ten kod NIE BYŁ uruchomiony na fizycznym sterowniku.** Testy podstawiają
`_command`, więc potwierdzają, że logika tłumaczenia jest poprawna i się
nie wywala — nie zastępują realnego uruchomienia. Sekwencja komend dla
ścieżki PROGRAM jest identyczna z już sprawdzoną na sprzęcie (czysta
refaktoryzacja, bez zmiany treści), ale ścieżki RUCH/WYJSCIE/PAUZA
w kroku cyklu i tryb automatyczny na ClearCoreMachine — **do zweryfikowania
przy najbliższym uruchomieniu sprzętowym** (temat H). W szczególności do
sprawdzenia w praniu:

- czy mostek poprawnie obsłuży serię `MOVEZ`/`MOVEXY` z kroków RUCH
  następujących bezpośrednio po sobie (bez operacji programu pomiędzy),
- czy tryb automatyczny (pętla bez końca) nie odsłania jakiegoś problemu
  z połączeniem TCP przy bardzo długim, ciągłym działaniu.
