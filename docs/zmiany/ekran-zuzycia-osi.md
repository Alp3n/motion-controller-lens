# Ekran zużycia osi (temat M, krok 3-4)

Ekran `/zuzycie` — podgląd danych zebranych przez `zuzycie.record_run()`
(temat M, krok 1-2): podsumowanie bieżącej doby per oś, wykresy trendu
długoterminowego, i (krok 4) definicje alarmów zużycia + ich bieżąca
ocena. **Bez wysyłki powiadomień** — to robi wMES (decyzja 2026-09-10),
sposób udostępnienia mu tych danych to osobny, jeszcze nieustalony krok 5.

## Pliki

- `server/app/zuzycie.py` — wydzielona `_aggregate_entries()` (wspólna
  logika sumowania/uśredniania, używana teraz zarówno przez rollup do
  trendu, jak i przez nową `summarize_today()`); `summarize_today()` liczy
  podsumowanie bieżącej doby na żywo, bez zapisu/kasowania pliku.
- `server/app/main.py` — `GET /api/zuzycie` (`require_technolog`): zwraca
  `{"dzisiaj": {...}, "trend": [...], "alarmy": [...]}` (trzecie pole:
  ocena z ostatniego przebiegu, krok 4). `GET/PUT /api/zuzycie/alarmy`
  (odczyt `require_technolog`, zapis `require_admin`, wzorem `/api/smart`).
  Strona `/zuzycie` — **`require_admin`, nie `TECHNOLOG` jak w kroku 3** —
  podniesione, bo doszedł CRUD definicji (spójne z `/smart`: podgląd niżej,
  edycja wyżej, całą stronę gates się na poziomie edycji).
- `server/app/zuzycie_alarmy.py` — nowy moduł, wzorem `app/smart.py`, ale
  prostszy (jedna logika oceny, nie rejestr wielu procedur):
  `AlarmDefinition` (oś, metryka, okres, próg, aktywny, note), `evaluate()`
  (ocena względem `dzisiaj`/`trend` z `zuzycie.py`), plik
  `config/zuzycie_alarmy.json`. Metryki: `dystans_mm_suma` (suma),
  `moment_max_pct` (największa wartość bezwzględna, nie suma — sumowanie
  procentów momentu nie ma sensu). Okresy: `dzien` (dzisiejsze
  podsumowanie), `tydzien` (ostatnie 7 dni trendu + dzisiaj).
- `server/app/main.py::_poll_loop` — ocena alarmów DOKŁADNIE po
  `zuzycie.record_run()` (ten sam punkt w kodzie, „po cyklu, na
  spokojnie"), wynik w module-owym `_zuzycie_alarm_status` (w pamięci,
  nieprzechowywany trwale — to tylko bieżący stan, nie historia alarmów).
- `server/app/static/zuzycie.html`, `zuzycie.js` — tabela „dzisiaj" +
  wykresy słupkowe trendu, jeden per oś (małe wielokrotności — osie mają
  różne skale dystansu, wspólna oś Y by je spłaszczyła) + tabela stanu
  alarmów (kolor czerwony/zielony) + CRUD definicji (dodaj/usuń, wzorem
  kalibracji w `sila.js`: stan lokalny, PUT całego obiektu). Rysowanie
  wykresów ręczne na `<canvas>`, bez biblioteki — ten sam wzorzec co
  `/sila`. Linki nawigacyjne dopisane w `index.html` i `sila.html`.
- `server/tests/test_zuzycie.py` — 3 nowe testy `summarize_today()`.
- `server/tests/test_zuzycie_alarmy.py` — 23 testy: walidacja definicji,
  `evaluate()` (dzień/tydzień, wartość bezwzględna względem progu, pomija
  nieaktywne), zapis/odczyt pliku, 4 testy API (GET/PUT roundtrip,
  odrzucenie błędnej definicji, obecność `alarmy` w `/api/zuzycie`).

## Uwagi

- **Dziś obejmuje wyłącznie X/Y/Z** — osie FEETECH (`docisk`, `podajnik`)
  jeszcze nie są wliczane do zużycia; `zuzycie.summarize_recording()` zna
  tylko `AXES = ("x", "y", "z")`. Rozszerzenie o osie FEETECH to osobna
  praca (przecięcie tematów L i M), niezrobiona teraz — ekran jawnie o tym
  informuje operatora.
- `GET/PUT /api/zuzycie` (bez `/alarmy`) nie ma osobnego testu na poziomie
  HTTP (wzorem innych cienkich endpointów w `main.py`, np.
  `_read_feetech_status`) — zweryfikowany ręcznie (izolowany `ZUZYCIE_DIR`,
  `TestClient`); `/api/zuzycie/alarmy` MA testy API (CRUD to więcej niż
  cienka warstwa, wzorem `test_smart.py`).
- **Stan alarmów żyje tylko w pamięci procesu** (`_zuzycie_alarm_status`)
  — restart usługi go zeruje do następnego zakończonego przebiegu. To
  świadomie proste rozwiązanie na krok 4; historia alarmów (kto/kiedy był
  przekroczony) nie jest jeszcze zapisywana — do rozważenia przy kroku 5,
  jeśli wMES miałby tego potrzebować.
- Zweryfikowane end-to-end na produkcji po restarcie usługi: `/zuzycie`
  (200), `GET/PUT /api/zuzycie/alarmy` (pełny cykl zapis→odczyt→sprzątanie
  wykonany ręcznie przez `curl`).
