# Przebudowa edytora technologa

Pola operacji zależą teraz od jej rodzaju, walidacja działa na bieżąco,
doszedł podgląd toru oraz wstawianie i przestawianie wierszy.

## Pliki

- `server/app/static/editor.js` — `OP_SCHEMA` jako jedno źródło prawdy o polach
  operacji, walidacja obszaru roboczego, podgląd toru na canvasie, akcje
  wiersza (↑ ↓ + ✕).
- `server/app/static/editor.html` — kolumny formatu 2, kontener przewijany
  poziomo, pasek walidacji, sekcja „Podgląd toru".
- `server/app/static/style.css` — szerokości pól w tabeli operacji, znaczniki
  błędów, wygaszone pola nieużywane, `min-width: 0` na elementach siatki.

## Co doszło

- **Pola zależne od rodzaju operacji.** `PUNKT` nie pokazuje już X2/Y2,
  `PAUZA` nie pokazuje niczego. Zmiana rodzaju czyści pola, których nowy
  rodzaj nie używa — inaczej zostawałyby wartości odrzucane przez parser.
- **Walidacja na bieżąco.** Obszar roboczy z `/api/config`, pola wymagane,
  wykluczanie `PRZEJSCIA`/`PRZYROST`, wartości dodatnie. Błędne pole dostaje
  czerwoną ramkę, nad przyciskami jest podsumowanie. Serwer i tak waliduje
  przy zapisie — to tylko wcześniejsza informacja dla technologa.
- **Podgląd toru** rysujący zawartość tabeli, także przed zapisem: operacje
  z numerami LP, odcinki `LINIA`, przejazdy między operacjami linią
  przerywaną, kreskowany obrys obszaru roboczego.
- **Wstawianie i przestawianie wierszy** — `↑`, `↓`, `+` (wstaw poniżej),
  `✕`. LP przelicza się automatycznie, więc wymóg ciągłej numeracji nie
  przeszkadza przy edycji.

## Poprawione problemy z układem

Wyszły dopiero na zrzucie ekranu z przeglądarki:

- Pola liczbowe były tak wąskie, że strzałki spinnera zajmowały całą
  szerokość i **nie było widać wartości** — strzałki usunięte, szerokość
  ustalona.
- Lista rodzajów operacji ucinała nazwy (`PUNK1`, `PAUZ/`).
- Tabela rozjeżdżała stronę w poziomie zamiast się przewijać — elementy
  siatki mają domyślnie `min-width: auto`; dodane `min-width: 0` sprawia,
  że przewija się kontener tabeli, a nie cała strona.
- Kadr podglądu psuła jedna literówka (`X=999` rozciągało widok do 1147 mm)
  — kadr jest teraz przycinany do obszaru roboczego.

## Weryfikacja

Sprawdzone w prawdziwej przeglądarce (Firefox headless przez Selenium),
nie na atrapie DOM: inicjalizacja skryptu, wczytanie programu (4 operacje,
„bez błędów"), wyłączanie pól per rodzaj, rysowanie na canvasie, przenoszenie
wierszy w górę i w dół, wstawianie i usuwanie, zmiana rodzaju odblokowująca
X2/Y2 wraz z natychmiastowym zgłoszeniem braków, oznaczenie wartości poza
obszarem roboczym, przewijalność tabeli.

Testy serwera: 34/34.

## Uwagi

- Podgląd pokazuje tylko płaszczyznę XY. Głębokości i przejścia widać
  wyłącznie jako liczby w tabeli.
- WebDriver Firefoksa nie widzi deklaracji `const`/`let` z zakresu
  globalnego — testy sprawdzają funkcje i skutki w DOM, nie zmienne modułu.
