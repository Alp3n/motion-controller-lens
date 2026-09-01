# RESET nie czyścił wewnętrznego znacznika „oś załączona" w mostku

Zgłoszone przy maszynie 2026-09-01: cykl automatyczny/ręczny **w 100%
powtarzalnie** kończył się na tym samym kroku (krok cyklu „PROGRAM",
operacja LP 1, ruch osi Z) komunikatem:

```
błąd sFoundation: Node @ 0 error. Reported by function:
virtual size_t sFnd::CPMmotion::MovePosnStart(int32_t, bool, bool, bool, bool).
Error: Node Reject: Move blocked by drive shutdown/disable/limit.
```

`Node @ 0` = oś Z. Wielokrotne `RESET` + ponowne bazowanie **nie pomagały**
— błąd wracał identyczny za każdym razem.

## Przyczyna

`bridge/sc4hub_bridge.cpp` trzyma lokalny znacznik `axisEnabled[3]` — czy
serwer *już wysłał* `EnableReq(true)` dla danej osi, żeby nie robić tego
przy każdym ruchu z osobna (`enableAxes()` pomija oś, dla której znacznik
jest `true`). Problem: jeśli serwo **samo się wyłączy** (alert/fault na
węźle) bez udziału mostka, `axisEnabled[]` **zostaje błędnie `true`** —
mostek myśli, że oś jest załączona, więc `enableAxes()` nigdy nie wysyła
ponownego `EnableReq`. `RESET` czyścił tylko alert na samym serwie
(`AlertsClear()`, `NodeStopClear()`), **nie ten znacznik** — więc kolejny
ruch od razu trafiał w ten sam mur: serwo naprawdę wyłączone, mostek
przekonany że włączone, żadnej komendy włączającej nigdy nie wysłanej.
To tłumaczy 100% powtarzalność niezależnie od liczby RESET-ów i bazowań.

## Naprawa

`RESET` zeruje teraz `axisEnabled[0..2]` dla wszystkich osi — wymusza to
pełny cykl `EnableReq(true)` + oczekiwanie na `IsReady()` przy najbliższym
ruchu każdej osi, zamiast zakładać, że stan sprzed alarmu wciąż jest
aktualny.

```cpp
axisEnabled[0] = axisEnabled[1] = axisEnabled[2] = false;
```

## Pliki

- `bridge/sc4hub_bridge.cpp` — `RESET` zeruje `axisEnabled[]`.

## Uwagi

- **Nie ustalono, co dokładnie wywołało pierwotne wyłączenie się węzła Z**
  (shutdown/disable/limit — trzy możliwości z komunikatu SDK). Ta poprawka
  usuwa efekt (mostek już nie "zapomina" włączyć osi od nowa po RESET-cie),
  ale nie diagnozuje przyczyny źródłowej. Jeśli błąd się powtórzy **mimo tej
  poprawki**, to znak, że przyczyna leży głębiej (np. realny Group Shutdown
  utrzymujący się dłużej, albo faktyczny limit fizyczny) — wtedy potrzebna
  fizyczna inspekcja (dioda LED węzła, ClearView).
- Ten sam mechanizm (lokalny znacznik software'owy rozjeżdżający się z
  realnym stanem serwa po niezależnym fault/alert) mógł też być powiązany
  z wcześniejszym incydentem „Node @ 1 error" na osi X
  (`zmiany/stop-nie-lapal-bledu.md`) — nie potwierdzone wprost, ale ten sam
  wzorzec: błąd SDK na węźle, potem RESET, potem błąd się nie powtórzył
  przy tamtej okazji tylko dlatego, że pomógł **restart mostka** (który i
  tak zeruje `axisEnabled[]` przy starcie), a nie sam RESET.
- **Nie zweryfikowane jeszcze fizycznie** — wdrożone od razu po
  zdiagnozowaniu, żeby nie blokować dalszej pracy, ale kolejny cykl na tym
  samym programie powinien to potwierdzić albo obalić.

## Aktualizacja (2026-09-01, po wdrożeniu): błąd wystąpił ponownie

Po naprawie i restarcie mostka użytkownik uruchomił cykl automatyczny
ponownie — **ten sam komunikat wystąpił znowu**, ale tym razem maszyna
zaszła dalej: `z=-1.038` (bliżej celu -1.5, poprzednio zatrzymywało się
bliżej z=0). To ważna nowa poszlaka:

- Poprawka `axisEnabled[]` **nie rozwiązuje problemu w całości** — albo nie
  jest jego jedyną przyczyną, albo naprawia tylko odzyskiwanie *między*
  uruchomieniami (przez RESET), a nie zapobiega **ponownemu** wystąpieniu
  w trakcie **tego samego, nieprzerwanego przebiegu** (jeśli oś zawiedzie
  w połowie operacji 1, kolejna komenda MOVEZ w tym samym przebiegu i tak
  zobaczy `axisEnabled[2]==true` sprzed chwili, bo RESET jeszcze się nie
  odbył).
- To, że maszyna zaszła głębiej (bliżej rzeczywistej głębokości cięcia
  w materiale), pasuje do hipotezy **limitu momentu podczas cięcia**:
  użytkownik testował bardzo niskie limity (5–8%) na profilach. Wejście
  freza w materiał (PMMA) mogło przekroczyć taki limit i wywołać na serwie
  twardy fault/wyłączenie (nie tylko łagodne zatrzymanie ruchu opisane w
  `zmiany/limit-momentu-sprzet.md`) — kolejna próba ruchu (druga głębokość
  przejścia, `PRZEJSCIA=2`) trafiałaby wtedy w węzeł już wyłączony.
- **Nierozstrzygnięte, wymaga fizycznej obecności:** czy podniesienie
  limitu momentu profilu „program"/„cykl" (dziś testowane na 5–8%) do
  wyższej, ale wciąż bezpiecznej wartości usuwa problem. Do sprawdzenia
  przy maszynie, nie zdalnie — zmiana limitu wpływa na rzeczywistą siłę
  cięcia.
