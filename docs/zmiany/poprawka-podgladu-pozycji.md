# Poprawka: martwy podgląd pozycji na panelu operatora

Panel operatora nie pokazywał pozycji osi ani rysunku podglądu — wartości
stały na `0.000`, a płótno było puste. Przyczyną był błąd JavaScriptu
zatrzymujący cały skrypt panelu przy starcie.

## Przyczyna

W `app.js` wywołania startowe `initView()` i `connectWs()` stały **przed**
deklaracją `const view = {...}`, z której korzysta `initView()`.

Deklaracje `function` są w JavaScripcie podnoszone (hoisting), więc samo
wywołanie funkcji zdefiniowanej niżej jest poprawne — ale `const` **nie
jest**. Wejście do `initView()` przed linią z `const view` kończyło się
wyjątkiem `Cannot access 'view' before initialization`.

Skutek był większy, niż sugeruje nazwa błędu: skrypt przerywał się na tej
linii, więc **`connectWs()` nigdy się nie wykonywało**. Panel nie otwierał
WebSocketu, nie odbierał statusu i wszystkie pola — pozycja, stan, wrzeciono,
podświetlenie operacji — zostawały na wartościach z HTML-a.

Błąd był w repozytorium od pierwszego commitu `app.js` („z laptopa") i nie
został wprowadzony żadną z późniejszych zmian.

## Pliki

- `server/app/static/app.js` — `initView()`/`connectWs()` przeniesione na
  koniec pliku, za wszystkie deklaracje; przy `const view` komentarz
  wyjaśniający, dlaczego kolejność ma znaczenie.

## Uwagi

- Sprawdzone w przeglądarce (Playwright/Chromium): po poprawce płótno się
  rysuje, `view-info` pokazuje współrzędne, JOG w osi X zmienia odczyt na
  żywo (`X 1.000`), a bazowanie przełącza stan na `HOMING` — czyli
  WebSocket działa.
- **Luka w testach:** cała warstwa przeglądarki nie ma pokrycia. Zestaw
  `pytest` sprawdza API i logikę Pythona, więc błąd tego rodzaju przechodzi
  przez testy niezauważony — tu wyszedł dopiero przy ręcznym klikaniu.
  Do rozważenia: lekki test przeglądarkowy w CI (dokłada zależność
  Playwright + przeglądarkę).
- Zastane, nienaprawione: wszystkie ekrany zgłaszają w konsoli 404 na
  `/favicon.ico` — w `static/` nie ma ikony. Sam w sobie nieszkodliwy, ale
  zaśmieca konsolę i utrudnia wypatrzenie prawdziwych błędów.
