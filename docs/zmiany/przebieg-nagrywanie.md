# Nagrywanie przebiegu momentu i prędkości (ekran /sila)

Zgłoszone przy maszynie 2026-09-01: moment i prędkość zmieniają się za
szybko, żeby ocenić je z samych liczb na żywo — zwłaszcza przy operacji
SMART, gdzie cały krok bywa krótszy niż czas potrzebny, żeby spojrzeć na
panel. Rozwiązanie: **nagrywanie przebiegu podczas uruchomienia**, które
zostaje widoczne na ekranie po zakończeniu ruchu, żeby dało się je
przejrzeć spokojnie — z podziałem na osobne operacje/kroki.

## Mechanizm

- `Machine._record_sample()` — wywoływane co 200 ms z `_poll_loop`
  (`main.py`), niezależnie od tego, czy `poll_status()` akurat się powiódł.
  Nagrywa próbkę `{t, op, cycle_step, x, y, z, torque}` **tylko** gdy stan
  to `RUNNING` albo `PAUSED`. Przejście w `RUNNING` z innego stanu czyści
  poprzednie nagranie i zaczyna liczyć czas od zera; po zakończeniu ruchu
  (stan wraca do READY/ALARM) nagranie **zostaje**, niezmienione, do
  następnego uruchomienia — to jest właśnie mechanizm „obejrzyj po fakcie".
  Ograniczone do 6000 próbek (~20 minut) — dłuższe uruchomienie i tak nie
  zmieściłoby się sensownie na jednym wykresie.
- `GET /api/przebieg` — zwraca surowe próbki (`{"samples": [...]}`). Bez
  żadnego przetwarzania po stronie serwera — segmentacja na operacje i
  liczenie prędkości z pozycji dzieje się w przeglądarce.
- Ekran `/sila`, sekcja „Przebieg ostatniego uruchomienia": dwa wykresy na
  `<canvas>` (moment % i prędkość mm/min) rysowane ręcznie — ten sam wzorzec
  co podgląd pozycji XY na panelu operatora (`app.js: drawView`), bez
  żadnej biblioteki wykresów. Prędkość liczona w JS z odległości między
  kolejnymi próbkami pozycji (serwer nagrywa x/y/z, nie gotową prędkość).
  Pionowe przerywane linie z etykietą LP/kroku znaczą granice operacji na
  obu wykresach naraz. Pod wykresami tabela: dla każdej operacji średni i
  maksymalny moment na każdej osi oraz czas trwania.
- Odświeża się co sekundę (`setInterval`) — działa jako podgląd na żywo
  **w trakcie** ruchu i zostaje statycznym zapisem **po** jego zakończeniu,
  bez żadnej zmiany w kodzie between tymi dwoma trybami.

## Poprawka przy okazji: `poll_status()` w klasie bazowej

`_poll_loop()` wywołuje `machine.poll_status()` bezwarunkowo, ale metoda ta
była zdefiniowana **tylko** w `SC4HubMachine` — w trybie symulacji
`SimulatedMachine.poll_status()` nie istniało, więc wywołanie kończyło się
`AttributeError` (nie `MachineError`, więc `contextlib.suppress(MachineError)`
tego nie łapał) i **cała pętla odpytywania status. wywalała się przy
pierwszej iteracji w trybie `sim`**. Nie wpływało to na produkcję (tryb
sprzętowy ma `poll_status()`), ale bez naprawy `_record_sample()` (wołane
w tej samej pętli, zaraz po `poll_status()`) nigdy by się nie wykonało w
symulatorze — nagrywanie nie działałoby w testach ani na checkoutach
deweloperskich. Naprawione: `Machine.poll_status()` w klasie bazowej jako
no-op.

## Pliki

- `server/app/machine.py` — `Machine.__init__`: `recording`,
  `_recording_t0`, `_recording_was_running`; `Machine.poll_status()` (nowy
  no-op w klasie bazowej); `Machine._record_sample()`.
- `server/app/main.py` — `_poll_loop()` woła `machine._record_sample()` po
  każdej próbie `poll_status()`; nowy `GET /api/przebieg`.
- `server/app/static/sila.html` — sekcja „Przebieg ostatniego uruchomienia":
  dwa `<canvas>` i tabela podsumowania.
- `server/app/static/sila.js` — rysowanie wykresów, liczenie prędkości,
  tabela per-operacja, odświeżanie co sekundę.
- `server/tests/test_przebieg.py` — 7 nowych testów: no-op `poll_status`
  w klasie bazowej, brak nagrywania w spoczynku, nagrywanie w
  RUNNING/PAUSED, reset przy nowym uruchomieniu, limit długości, API.

## Poprawka (2026-09-01, po pierwszym użyciu)

Skala wykresu momentu była na sztywno 0–100% — przy realnych wartościach
rzędu kilku procent (typowe na tej maszynie) linie spłaszczały się przy
samym dnie wykresu, praktycznie niewidoczne. Poprawione: skala dopasowuje
się teraz do rzeczywistego maksimum w nagraniu (jak już miał wykres
prędkości), z etykietami osi pokazującymi realne wartości, nie stałe
0/50/100%. Dopisana też liczba próbek (`N=...`) wprost na obu wykresach —
łatwo sprawdzić, czy przebieg w ogóle coś nagrał.

## Uwagi

- **Rozdzielczość to 200 ms** — tyle, co reszta odpytywania statusu.
  Krótka operacja SMART może mieć tylko kilka próbek; to nie jest
  precyzyjny rejestrator, tylko narzędzie do orientacyjnej analizy. Ekran
  mówi to wprost.
- **Nagranie żyje tylko w pamięci procesu** — restart `motion-controller-
  lens.service` je kasuje, tak jak resztę stanu w pamięci (np. sesje
  logowania). Świadomie: to narzędzie do bieżącej analizy, nie archiwum;
  zapis trwały to osobny temat, do rozważenia dopiero jeśli się okaże
  potrzebny.
- **Nie nagrywa JOG-a ani bazowania** — tylko `RUNNING`/`PAUSED`, czyli
  program technologa i cykl maszyny przez `start()`/`start_cycle()`.
  Świadomie: to są operacje planowane z operacjami/krokami do analizy,
  JOG nie ma takiej struktury.
- Nie zweryfikowane jeszcze fizycznie na prawdziwym programie z operacją
  SMART na sprzęcie — do zrobienia przy najbliższym uruchomieniu.
