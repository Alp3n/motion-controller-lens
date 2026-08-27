# Ekran cyklu maszyny — etap 4

Ekran `/cycle` do definiowania kroków cyklu (poziom admina), analogiczny do
edytora technologa: tabela kroków, walidacja na bieżąco, przestawianie
wierszy, zapis do pliku. Do tego uruchomienie cyklu i podgląd na żywo —
który krok się wykonuje, na jakim profilu, w jakim stanie są wyjścia.

Ostatni z czterech etapów tematu B — model w
[`../model-cyklu-maszyny.md`](../model-cyklu-maszyny.md), backend w
[`cykl-maszyny-etap3.md`](cykl-maszyny-etap3.md).

## Pliki

- `server/app/static/cycle.html` — nowy ekran: tabela kroków, panel
  uruchamiania, opis rodzajów kroków i tego, czego jeszcze nie ma.
- `server/app/static/cycle.js` — nowy: `STEP_SCHEMA` (lustro
  `CycleStep.validate()` z `app/cycle.py`), budowa wierszy, walidacja na
  bieżąco, zapis, polling statusu z podświetlaniem wykonywanego kroku.
- `server/app/static/style.css` — style tabeli kroków, wygaszanie pól
  nieużywanych przez dany rodzaj kroku, podświetlenie kroku w trakcie.
- `server/app/main.py` — trasa `GET /cycle`.
- `server/app/static/{index,axes,editor}.html` — linki nawigacyjne do
  nowego ekranu.
- `server/tests/test_cycle.py` — test serwowania strony.

## Uwagi

- **`STEP_SCHEMA` w JS musi odpowiadać `CycleStep.validate()` w Pythonie.**
  Rozjazd oznaczałby, że ekran pozwala zapisać coś, co serwer odrzuci —
  albo odwrotnie, blokuje coś dozwolonego. Walidacja jest celowo powtórzona
  (jak w edytorze technologa i ekranie osi): serwer decyduje, przeglądarka
  tylko pokazuje błąd wcześniej.
- Pola nieużywane przez dany rodzaj kroku są **wygaszane i czyszczone**, nie
  ukrywane — kolumny nie skaczą przy zmianie rodzaju kroku.
- **Krok PROGRAM to „skok do podprogramu technologa"** z
  `NOTATKI_FUNKCJONALNE.md` §3. Nie potrzebuje osobnej składni skoku:
  program detalu jest listą operacji bez własnych pętli, więc krok kończy
  się razem z nim.
- Ekran sprawdza pozycje kroków `RUCH` względem limitów programowych osi
  (pobiera je z `/api/axes`), tak jak edytor technologa sprawdza obszar
  roboczy.
- **Ruch tylko w osiach X/Y/Z** — tabela pokazuje te trzy, bo tylko one
  dziś jeżdżą. Osie dodatkowe z konfiguracji (podajnik, docisk) czekają na
  rozszerzenie protokołu mostka; ekran o tym mówi wprost zamiast kusić
  polem, które nic nie zrobi.
- Sprawdzone w przeglądarce (Playwright, Chromium): dodawanie kroków,
  walidacja pustego `RUCH` i niekompletnego `WYJSCIE`, wygaszanie pól przy
  zmianie rodzaju, zapis, trwałość po przeładowaniu, uruchomienie cyklu
  z podglądem przełączania profili `cykl` → `program` → `globalny`
  i stanu wyjść. Bez błędów JavaScriptu.
- Drobiazg zastany, nie wprowadzony tą zmianą: wszystkie ekrany zgłaszają
  w konsoli 404 na `/favicon.ico` — w `static/` nie ma ikony.
