# Ekran /cycle: kolumny dla osi dodatkowych w kroku RUCH

Zgłoszenie 2026-09-12: „ruch cyklu nie można zdefiniować dodatkowych osi"
— backend (etap 4 tematu L, [[feetech-w-cyklu-maszyny]]) od dawna
obsługiwał dowolną skonfigurowaną oś w `step.targets`, ale **ekran
`/cycle` renderował kolumny wyłącznie dla X/Y/Z** (`AXES` w `cycle.js`
było stałą `["x","y","z"]`) — nie dało się wpisać celu dla `docisk`/
`podajnik` z panelu, tylko przez ręczną edycję pliku/API.

Rozważona alternatywa (zaproponowana przez operatora): osobny ekran
„kroki dla osi dodatkowych" + nowy rodzaj kroku „skocz do niego i wróć"
(podprogram). **Niepotrzebne** — `Machine._resolve_move_targets()` już
dziś rusza (i czeka na koniec ruchu) oś FEETECH WEWNĄTRZ tego samego
kroku RUCH co X/Y/Z, więc jeden krok `{"x":5,"y":80,"docisk":-3}` już
robi dokładnie to, o co chodziło — brakowało tylko pól do jego wypełnienia
na ekranie.

## Zmiana

- `server/app/static/cycle.html` — `<thead>` dostaje `id="step-header-row"`,
  nagłówek „Posuw" dostaje `id="th-feed"` (kotwica do wstawiania kolumn),
  poprawiony nieaktualny opis „ruchu osi innych niż X/Y/Z [nie ma]" i
  rozszerzony opis kroku RUCH.
- `server/app/static/cycle.js` — `AXES`/`NUM_FIELDS` z `const` na `let`;
  nowa `updateAxesFromConfig()`: po wczytaniu `/api/axes` dopisuje do
  `AXES` wszystkie skonfigurowane osie poza X/Y/Z (posortowane), przelicza
  `NUM_FIELDS` i `STEP_SCHEMA.RUCH.uses`, oraz wstawia brakujące `<th>` do
  nagłówka tabeli (tytuł zaznacza `(FEETECH, RS485 — czeka na koniec
  ruchu)` dla osi z tym sterownikiem). Wywoływana raz, przed pierwszym
  `applyCycle()`. Reszta kodu (`addStepRow`, `readRows`, `validate`) była
  już generyczna względem `AXES`/`NUM_FIELDS` — nie wymagała zmian.

## Uwagi

- Walidacja limitów programowych dla osi dodatkowych działała już
  wcześniej (kod czytał `axesCfg[axis]` generycznie) — tylko nie było jak
  wpisać wartości, żeby ją wywołać.
- Kolumna „Posuw" **nie dotyczy** osi FEETECH — jadą własną skonfigurowaną
  prędkością (`feetech_speed`/`feetech_acc`, ekran `/axes`), zaznaczone w
  tooltipie nagłówka.
- Nowo dodana oś domyślnie ma sterownik `teknic` (patrz `zmiany/
  dodawanie-osi-ekran.md`) — dopóki ktoś ręcznie nie ustawi `driver:
  feetech` w pliku konfiguracji, jej kolumna w `/cycle` pojawi się, ale
  krok RUCH z celem na niej zakończy się błędem „oś nie jest obsługiwana"
  (bo nie ma zarejestrowanego sterownika ruchu) — zgodne z istniejącym
  zachowaniem dla czystych osi teknic-extra.
