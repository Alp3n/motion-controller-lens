# Przykłady beta SDK Teknica — co z nich wynika dla naszego mostka

Analiza `zbyszek/ClearPath_SC_Beta_Examples.zip` (dodany na GitHub
2026-09-02) — oficjalne przykłady C++ Teknica do sFoundation/ClearView
(„beta-cpp-examples-windows"). Pisane pod Windows/Visual Studio, ale API
sFoundation jest to samo, co używa `bridge/sc4hub_bridge.cpp` na Linuksie —
kod się nie kompiluje wprost (inny projekt, inne nagłówki systemowe), ale
**wzorce użycia API i konkretne wywołania są bezpośrednio przenośne**.
Każde poniższe ustalenie zweryfikowane też w naszych faktycznie
zainstalowanych nagłówkach (`vendor/teknic/Linux_Software/sFoundation/
inc/inc-pub/`), nie tylko w przykładzie — jeśli metoda w przykładzie nie
istnieje u nas, jest to wprost zaznaczone.

## 1. Diagnoza alertów węzła — bezpośrednio przydatne do otwartego problemu „Node @ 0/1 error"

`NodeAlerts-Status.cpp` pokazuje, czego **dziś nie robimy**, a czego
brakuje w diagnozie z `docs/zmiany/reset-nie-czyscil-axisenabled.md`:

```cpp
myNode.Status.Alerts.Refresh();
if (myNode.Status.Alerts.Value().isInAlert()) {
    char buf[500];
    myNode.Status.Alerts.Value().StateStr(buf, sizeof(buf));  // nazwy KONKRETNYCH alertów
    // EStopped jest wyjątkiem: NIE czyści go AlertsClear(), trzeba osobno:
    if (myNode.Status.Alerts.Value().cpm.Common.EStopped)
        myNode.Motion.NodeStopClear();
    myNode.Status.AlertsClear();
}
```

**Dziś nasz `handle()` w mostku łapie tylko tekst wyjątku `mnErr`
(„Move blocked by drive shutdown/disable/limit") — nie sprawdza, KTÓRY
konkretny alert jest ustawiony.** `alertReg::StateStr()` dałoby nazwę
wprost (np. `EStopped`, `TrackingShutdown`, `TorqueSaturation` — pełna
lista bitów w `pubCpmRegs.h`), zamiast zgadywania między trzema
możliwościami. To bezpośrednio adresuje niedomknięty problem z osią Z:
**dopisanie `Status.Alerts.Value().StateStr()` do komunikatu alarmu przy
odrzuceniu ruchu powiedziałoby wprost, który to przypadek**, zamiast
budować hipotezy z samego tekstu wyjątku SDK.

Potwierdzone w naszych nagłówkach: `IAlerts::isInAlert()`, `StateStr()`,
`AlertsClear()` — wszystkie istnieją (`pubSysCls.h`, klasa `IAlerts`).

## 2. Szybsze wykrycie faultu w trakcie ruchu, nie dopiero po timeoucie

`Homing.cpp` (pętla oczekiwania na `WasHomed()`) sprawdza **trzy** warunki
zamiast tylko czasu:

```cpp
myNode.Status.RT.Refresh();
if (myNode.Status.RT.Value().cpm.AlertPresent) { /* alert */ }
else if (myNode.Status.RT.Value().cpm.MoveCanceled) { /* ruch anulowany */ }
else if (timeout) { /* naprawdę czas */ }
```

**Nasz `waitMoves()` w `sc4hub_bridge.cpp` sprawdza tylko
`MoveIsDone()`, sygnał zezwolenia i czas** — nie sprawdza `AlertPresent`
w trakcie oczekiwania. Efekt: jeśli węzeł dostanie alert w trakcie ruchu
(np. torque saturation odcinający ruch), czekamy pełny
`szacowany_czas × 1.5 + 3000 ms`, zamiast wykryć to natychmiast i zgłosić
z nazwą alertu. To wyjaśnia też, dlaczego komunikat „przekroczono czas
ruchu" (nawet po poprawce z `HadTorqueSaturation()`) jest opóźniony —
mielibyśmy dokładną przyczynę od razu, sprawdzając `AlertPresent` przy
każdym obiegu pętli `waitMoves`, nie tylko na końcu.

**Do rozważenia jako kolejny krok** (nie zaimplementowane tutaj — zmiana
zachowania ruchu wymaga przetestowania na sprzęcie, nie zrobię tego bez
Ciebie): dopisać sprawdzenie `AlertPresent` do `waitMoves()`, przerywające
czekanie od razu z treścią alertu z `StateStr()`, zamiast czekać na
timeout.

## 3. Realny stan „włączona" z węzła, nie tylko nasza zmienna software'owa

`NodeAlerts-Status.cpp` czyta faktyczny stan włączenia bezpośrednio ze
sprzętu:

```cpp
myNode.Status.RT.Refresh();
bool enabled = myNode.Status.RT.Value().cpm.Enabled;
```

**To jest dokładnie to, czego brakowało w błędzie naprawionym w
`docs/zmiany/reset-nie-czyscil-axisenabled.md`.** Nasza poprawka (zerowanie
`axisEnabled[]` przy RESET) usuwa objaw, ale wciąż polega na **lokalnej
zmiennej C++, która może rozjechać się z rzeczywistością**. Bardziej
odporne rozwiązanie: `enableAxes()` mogłoby sprawdzać
`nodeOf(a).Status.RT.Value().cpm.Enabled` **zamiast** (albo obok) naszej
`axisEnabled[]`, więc nigdy nie ufałoby nieaktualnemu założeniu. Skoro błąd
Node@0 wrócił nawet po naszej poprawce (patrz aktualizacja w tym samym
pliku zmian), to wzmacnia argument za tym podejściem — warto rozważyć przy
następnej iteracji, przy maszynie.

## 4. Global Stop — nazwa metody w przykładzie NIE pasuje do naszego SDK (i to jest OK)

`SC4-IO.cpp` woła `myPort.GrpShutdown.GetGlobalStop()`. **Sprawdzone
wprost w naszych nagłówkach: tej metody nie ma.** Jest tylko
`GetGlobalStopInputState()` (`pubCpmCls.h:851,966`, `pubSysCls.h:3298`) —
dokładnie ta, której już używa nasz `safetyEnabled()`
(`bridge/sc4hub_bridge.cpp`). Przykład najwyraźniej pochodzi z innej wersji
SDK niż ta, którą mamy zainstalowaną. **Wniosek: nasz kod jest poprawny,
nie trzeba nic zmieniać** — odnotowuję to tylko, żeby nikt w przyszłości
nie „naprawiał" działającego kodu na podstawie tego przykładu.

Semantyka (potwierdzona w obu miejscach zgodnie): `true` = wejście **nie**
jest zaasertowane (stan bezpieczny).

## 5. Wejścia ogólnego przeznaczenia (InA/InB) — gotowy przepis pod sygnał drzwi (temat E)

`SC4-IO.cpp` pokazuje dokładnie, jak czytać wejścia węzła:

```cpp
if (theNode.Status.RT.Value().cpm.InA) { /* wejście A węzła zaasertowane */ }
if (theNode.Status.RT.Value().cpm.InB) { /* wejście B węzła zaasertowane */ }
```

To jest **konkretna odpowiedź na pytanie „jak w kodzie" dla otwartego
punktu z tematu E** (`kanban.md`: „Wejście sygnału drzwi (PWM/binarny)").
Każdy węzeł ma dwa takie wejścia (6 przy trzech serwach) — miejsce
podłączenia już potwierdzone w `mozliwosci-clearpath-sc.md`, teraz mamy też
dokładne wywołanie API do odczytu. **Nie zaimplementowane** — to nadal
wymaga decyzji, do którego węzła/wejścia podłączyć czujnik drzwi, i pracy
przy maszynie.

## 6. Grupy wyzwalania (TriggerGroup) — potwierdzone w naszym SDK, gotowy wzorzec pod „LINIA" i jednoczesny start XY

Nasz `kanban.md` (temat H) ma od dawna otwarty punkt: „spróbować grup
wyzwalania (`TriggerGroup` + `TriggerMovesInGroup`) — usuwają niejednoczesny
start osi". Metody **istnieją w naszym SDK**
(`pubSysCls.h:3341-3370`, z gotowym przykładem w komentarzu nagłówka):

```cpp
// Załaduj ruch wyzwalany (nie startuje od razu — trzeci argument true)
myNodeX.Motion.Adv.MovePosnStart(target, /*abs*/true, /*triggered*/true);
myNodeY.Motion.Adv.MovePosnStart(target, /*abs*/true, /*triggered*/true);

// Przypisz obie osie do tej samej grupy wyzwalania
myNodeX.Motion.Adv.TriggerGroup(1);
myNodeY.Motion.Adv.TriggerGroup(1);

// Wystrzel obie naraz
myPort.Adv.TriggerMovesInGroup(1);
```

Dziś nasz `moveXY()` w `sc4hub_bridge.cpp` uruchamia `MovePosnStart` na X i
Y **osobno, jedno po drugim** (widać to już w kodzie: `nx.Motion.
MovePosnStart(...)` potem `ny.Motion.MovePosnStart(...)`) — stąd niewielkie
opóźnienie startu między osiami, które ten mechanizm by usunął. To
bezpośrednio adresuje punkt „Weryfikacja pomiarowa toru `LINIA`" z
tematu H. **Nie zaimplementowane** — wymaga przejścia z `Motion.
MovePosnStart` na `Motion.Adv.MovePosnStart` (interfejs `IMotionAdv`,
inny niż używany dziś) i testu na sprzęcie.

## 7. Wczytywanie plików `.mtr` z Auto-Tune — potwierdza API pod jeszcze nieotwarty temat H

`LoadingConfigFile.cpp` demonstruje wczytanie pliku konfiguracji `.mtr`
(zapisanego z Auto-Tune w ClearView na Windows) z poziomu Linuksa — dokładnie
to, czego dotyczy otwarty punkt w `kanban.md`/`sterownik-sc4-hub.md`:
„Auto-Tune każdej osi pod obciążeniem — wymaga Windows z ClearView; zapisać
`.mtr` i wczytywać z Linuksa (`LoadingConfigFile`)". Przykład potwierdza, że
to jest gotowy, znany mechanizm SDK, nie coś do wymyślenia — gdy dojdzie do
tego punktu, ten plik jest gotowym punktem wyjścia (ścieżka w zipie:
`beta-cpp-examples-windows/LoadingConfigFile/LoadingConfigFile.cpp`).

## Pozostałe przykłady w paczce — krótko, bez głębokiej analizy

- `PositionMoves.cpp`, `MotionVelocity.cpp`, `MotionDualAxis.cpp` — warianty
  ruchu pozycyjnego/prędkościowego na jednej/dwóch osiach, w większości
  odpowiadają temu, co już robi nasz mostek (`MovePosnStart` przez
  `Motion`, nie `Motion.Adv`).
- `SingleThreaded(Polling)` i `MultiThreaded(Attentions)` (z klasami `Axis`,
  `Supervisor`) — dwa wzorce sterowania wieloma osiami. Nasz mostek jest
  bliżej modelu pollingowego (jeden wątek, blokujące komendy) niż
  wielowątkowego z callbackami na atencje (`Attentions`) — świadoma różnica
  architektoniczna, nie coś do „naprawienia" pod wpływem tego przykładu.
- `SCNetworkReport.cpp`, `ProjectTemplate.cpp` — narzędzie diagnostyczne
  sieci SC i szkielet nowego projektu, bez bezpośredniego zastosowania do
  naszego kodu.

## Źródło i zastrzeżenie

Paczka ma własny `README.txt`: *„These example projects have... NOT yet
gone through Teknic's full, exhaustive test plan. They are provided as
beta content"* — traktuję je jako materiał poglądowy potwierdzający istnienie
i sygnatury API (zweryfikowane niezależnie w naszych nagłówkach), nie jako
gotowy do wklejenia kod produkcyjny.
