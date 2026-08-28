# Możliwości ClearPath-SC — czego jeszcze nie wykorzystujemy

Analiza dokumentacji producenta pod kątem funkcji serw i huba, których nasz
mostek dziś nie używa, a które odpowiadają na zaplanowane wymagania
(`plan-rozwoju.md`) albo na otwarte ryzyka z
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md).

Źródła (pobrane ze strony Teknica, w `zbyszek/`):

- `Clearpath-SC User Manual.pdf` — instrukcja silnika, rev. 1.45 z 2026-02-06,
  119 stron. Numery stron w nawiasach.
- `S-FoundationRef.chm` — referencja API biblioteki sFoundation 2.0
  (dokumentacja Doxygen wygenerowana z `pubSysCls.h`). Odwołania w formie
  nazw klas i metod.
- `Readme.txt` — tylko instrukcja odblokowania pliku `.chm` w Windows.

## Ustalenie kluczowe: mamy silniki **Advanced**

Numer katalogowy naszych serw to **`CPM-SCSK-2310S-RLNA`** (trzy sztuki,
patrz [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md)). Klucz numeru
katalogowego z instrukcji (str. 115) rozkłada go tak:

| Człon | Znaczenie |
|---|---|
| `CPM` | ClearPath Motor |
| `SCSK` | Software Control / „Stepper Killer" |
| `23` | NEMA 23 |
| `1` | długość korpusu 82 mm |
| `0` `S` | struktura magnetyczna, uzwojenie Series-Wye (większy moment, mniejsza prędkość) |
| `R` | **rozdzielczość 800 impulsów/obrót** |
| `L` | wał standardowy (3/8" dla NEMA 23) |
| `N` | standardowe uszczelnienie |
| `A` | **zestaw funkcji: Advanced** |

Weryfikacja krzyżowa: człon `R` = 800 imp/obr zgadza się dokładnie z tym, co
mostek odczytał ze sprzętu (`Info.PositioningResolution`, patrz
[`zmiany/mostek-sc4hub.md`](zmiany/mostek-sc4hub.md)). To potwierdza odczyt
całego klucza, a więc i ostatniego członu.

**Konsekwencja:** dostępny jest pełen zestaw Advanced (str. 115), z którego
dziś **nie używamy niczego**:

| Funkcje Basic (używamy części) | Funkcje Advanced (nie używamy wcale) |
|---|---|
| ruchy prędkościowe | RAS™ i g-Stop™ (ograniczanie zrywu, tłumienie drgań) |
| globalny limit momentu | dodatnie i ujemne limitowanie momentu |
| **foldback przy bazowaniu do oporu (HardStop)** | ruchy wyzwalane (na wejście lub komendę, **z grupami ruchu**) |
| ruchy trapezowe | ruchy head-tail |
| node stop / e-stop | ruchy asymetryczne |
| odczyt i modyfikacja pozycji | zdarzenia A-after-start |
| RAS™ (ograniczanie zrywu) | zdarzenia B-before-end |
| rejestr statusu | **warunkowe limitowanie momentu** |
| system ostrzeżeń i alertów | **generowanie „attentions" (zdarzeń)** |
| pamięć parametrów | |
| wyłączenia bezpieczeństwa | |
| **limity programowe (soft limits)** | |
| dane użytkownika | |
| automatyczne sterowanie hamulcem | |
| wyłączenia grupowe | |

## Co mostek robi dziś

Z całego API sFoundation `bridge/sc4hub_bridge.cpp` używa:

`Motion.MovePosnStart`, `MoveIsDone`, `MoveWentDone`,
`MovePosnDurationMsec`, `VelLimit`, `AccLimit`, `NodeStop(STOP_TYPE_ABRUPT)`,
`NodeStopClear`, `AddToPosition`, `PosnMeasured`, `Homing.Initiate`,
`Homing.WasHomed`, `Homing.HomingValid`, `Info.SerialNumber`,
`Info.PositioningResolution`, `Status.AlertsClear`,
`BrakeControl.BrakeSetting`, `GrpShutdown.GetGlobalStopInputState`,
`EnableReq`.

Czyli: ruch trapezowy, prędkość, przyspieszenie, zatrzymanie, odczyt pozycji.
**Zero z warstwy momentu, zdarzeń, ruchów zaawansowanych i limitów.**

## Odpowiedzi na pytania, które były otwarte

### 1. Siła/moment konfigurowalny z programu — **tak, jest API**

`NOTATKI_FUNKCJONALNE.md` §2 zostawiał to jako „sprawdzić w bibliotece
Teknic dostępne funkcje pod to zastosowanie". Odpowiedź: klasa
`sFnd::ILimits` daje `TrqGlobal` — **globalny limit momentu ustawialny
w czasie pracy**, w procentach maksimum:

```cpp
myNode.TrqUnit(myNode.PCT_MAX);
myNode.Limits.TrqGlobal = 100;      // limit 100%
```

To jest wprost mechanizm pod trzypoziomową konfigurację siły, którą
zaplanowałeś (globalna 20% / cykl 15% / program technologa 10%) oraz pod
siłę per operacja. Dokumentacja zaznacza, że „zwykle ustawia się to przez
ClearView i nie zmienia w trakcie aplikacji" — ale **nie zabrania** zmiany
z API; to kwestia świadomego użycia, nie ograniczenie.

Druga, mocniejsza warstwa to **warunkowe limitowanie momentu** (torque
foldback, tylko Advanced — mamy). Konfigurowane w ClearView, działa w samym
serwie, kilka warunków naraz (przy każdym takcie wygrywa najniższy limit):

| Warunek | Do czego |
|---|---|
| **Move Done** | zmniejszenie momentu trzymania po zakończeniu ruchu — ogranicza ciągłe obciążenie na mechanice nieodwracalnej |
| **A After Start / B Before End** | limit w oknie odległości od początku/końca ruchu (`AfterStartDistance`, `BeforeEndDistance` — ustawialne z API) |
| **Absolute Position** | **limit momentu zależny od pozycji bezwzględnej** — wymaga bazowania |
| **Node Input A/B** | inny limit momentu wyzwalany wejściem węzła |

Warunek „Absolute Position" to dokładnie Twój zapis z notatek: *„siła
i prędkość konfigurowalne na każdym kroku programu, zależnie od pozycji
(np. oś X, pozycja 100, ACC, DCC, prędkość, siła 10%)"*. Z zastrzeżeniem:
to jest **konfiguracja silnika w ClearView**, nie parametr wysyłany per ruch.
Wersję „per operacja" realizuje się przez `TrqGlobal` z API.

Dochodzi jeszcze `TrqGlobal` jako limit ciągły oraz wbudowany podgląd
**RMS Torque Limit** — pokazuje, jak blisko jesteśmy ciągłego limitu silnika.

### 2. Bazowanie do oporu — **jest, i to w wersji Basic**

`HardStop foldback (homing)` jest na liście funkcji **Basic**, czyli byłoby
dostępne nawet bez Advanced. Konfiguracja (ClearView → Setup → Homing Setup):

- kierunek obrotu przy bazowaniu,
- prędkość i przyspieszenie bazowania,
- **cel: „Change of Input" albo „HardStop"**,
- **Homing Torque Limit** — maksymalna siła użyta do wykrycia oporu,
- **Offset Move** — ruch wykonywany automatycznie po znalezieniu bazy;
  po nim pozycja jest zerowana.

`Offset Move` odwzorowuje nasz model „punktu bazowania" z
[`konfiguracja-osi.md`](konfiguracja-osi.md) — zero osi nie musi leżeć na
zderzaku.

**Ważne ograniczenie API:** klasa `sFnd::IHoming` pozwala tylko
`Initiate()`, `IsHoming()`, `WasHomed()`, `HomingValid()`,
`SignalComplete()`, `SignalInvalid()`. **Parametrów bazowania nie da się
ustawić z kodu** — wyłącznie w ClearView (Windows). To potwierdza zadanie,
które już mamy na liście, i domyka pytanie „czy da się to obejść z Linuksa":
nie da się, poza wczytaniem gotowego pliku konfiguracyjnego.

### 3. Limity programowe w samym silniku — **są, ale wymagają bazowania**

Poza naszymi limitami (serwer + `AXCFG` w mostku) silnik ma **własne soft
limits**: zakres w pozycjach enkodera, bez czujników. Silnik **odmówi
wykonania ruchu naruszającego limit**.

Haczyk, wprost z dokumentacji: *„Homing is required to use soft limits"* —
limity są ignorowane, dopóki oś nie jest zbazowana. Ponieważ nasze bazowanie
to dziś atrapa (`AddToPosition`, patrz
[`zmiany/mostek-sc4hub.md`](zmiany/mostek-sc4hub.md)), **ta warstwa ochrony
jest u nas nieaktywna**. Cała ochrona przed wyjazdem poza zakres opiera się
dziś wyłącznie na naszym kodzie.

Jest obejście dla aplikacji, które nie bazują: `IHoming::SignalComplete()`
oznacza przestrzeń pozycji jako ważną. To **nie zastępuje bazowania**, ale
pozwoliłoby włączyć limity w silniku również w obecnym stanie — do
rozważenia jako warstwa dodatkowa, nie zamiennik.

### 4. Interpolacja XY — **jest kandydat na rozwiązanie: grupy wyzwalania**

To było otwarte ryzyko w [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md):
osie startują sekwencyjnie, bo każda komenda idzie osobno po łączu.

Funkcja **Triggered Moves** (Advanced) rozwiązuje właśnie ten problem:
ruch jest **wysyłany do silnika i czeka** na zdarzenie wyzwalające.
Wszystkie osie w tej samej **grupie wyzwalania** ruszają jedną komendą:

```cpp
node.Motion.Adv.TriggerGroup(1);                    // przypisz oś do grupy
node.Motion.Adv.MovePosnStart(target, true, true);  // isTriggered = true
// ...to samo dla drugiej osi...
port.Adv.TriggerMovesInGroup(1);                    // obie ruszają razem
```

Cytat z dokumentacji: *„This feature can reduce the latency and increase
synchronization of motion between multiple nodes […] by masking the motion
command download with the execution initiation."*

**To nie jest interpolacja** — każda oś nadal jedzie własnym profilem, więc
odchyłka od prostej na rampach zostaje. Ale usuwa jedną z dwóch przyczyn
błędu: niejednoczesny start. Wymaga weryfikacji pomiarowej razem z zadaniem
„zweryfikować pomiarowo tor operacji `LINIA`", które już mamy.

### 5. Obciążalność wyjść BRAKE — **500 mA, 24 VDC**

Zadanie „obciążalność wyjść `BRAKE_0`/`BRAKE_1` pod stycznik wrzeciona"
jest odpowiedziane (str. 47):

> *„The Brake Control circuit was designed for use with 24VDC »power-off«
> type brakes that draw 500mA or less."*

Do tego API ma bity wykrywania przeciążenia (`GPO_OVERLOAD_BIT`,
`BRAKE_OVERLOAD_BIT`), więc mostek może rozpoznać zwarcie lub przeciążenie
obwodu, zamiast po cichu nie załączyć wrzeciona.

500 mA wystarcza na cewkę **małego przekaźnika pośredniczącego** (typowo
20–50 mA). Cewki większych styczników potrafią przekroczyć ten limit —
dlatego wrzeciono należy załączać **przez przekaźnik pośredniczący**, a nie
bezpośrednio stycznikiem.

## Ryzyka — nie do zmiękczenia

### A. System operacyjny może **przypadkowo załączyć** wyjście BRAKE

To jest najważniejsze znalezisko w całym materiale i **zmienia warunki
decyzji o wrzecionie na wyjściu BRAKE** (temat J w `plan-rozwoju.md`).
Cytat wprost (str. 48):

> *„when your ClearPath-SC application code does not have control of the
> host's communication port (USB or serial), it is possible for the operating
> system to inadvertently release the brake. This can happen, for example, if
> the operating system scans its connected hardware (like during a port
> »auto-discover« function)."*

Przełożone na naszą maszynę: jeśli `BRAKE_1` załącza regulator wrzeciona, to
**wrzeciono może ruszyć bez udziału naszej aplikacji** — gdy mostek nie
działa, a system skanuje porty USB.

To nie jest hipoteza. Wiemy już z
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md), że **`cdc_acm` przejmuje hub
przy każdej ponownej enumeracji** — czyli scenariusz „system operacyjny
dobiera się do portu" u nas realnie występuje, przy każdym włączeniu 24 V
albo przewtyknięciu kabla.

Zalecenie producenta jest jednoznaczne i **musi zostać wpięte w projekt
elektryczny**, a nie tylko odnotowane:

> *„the brake outputs should be wired in series with an interlock switch
> circuit to all guard mechanisms […] any safety circuit of this type must go
> open circuit when unsafe access is attempted."*

Czyli: sygnał z `BRAKE_x` do regulatora wrzeciona **przechodzi przez styk
obwodu bezpieczeństwa** (osłony/kurtyny), tak żeby przy otwartej osłonie
obwód był fizycznie rozwarty niezależnie od stanu softu. Decyzja o wrzecionie
na wyjściu BRAKE zostaje w mocy — ale **wyłącznie z tym szeregowym
zabezpieczeniem**.

### B. Przerwanie komunikacji rozłącza wyjścia BRAKE

> *„Brakes automatically engage (disallow motion) if communication with the
> Application PC is interrupted."*

Dla wrzeciona to zachowanie **pożądane** (utrata łączności → wrzeciono
gaśnie). Warto to jednak wiedzieć wprost i przetestować, bo oznacza, że
wyjście nie utrzyma stanu przy chwilowej utracie USB — a to zmienia sposób,
w jaki mostek powinien raportować taki stan operatorowi (nie „wrzeciono
wyłączone przez program", tylko „utracono łączność").

### C. Nota zgodnościowa producenta

Instrukcja przy sekcji hamulców zawiera własne zastrzeżenie (str. 47):

> *„Engineer's Safety/Compliance Note: Depending on your machine application
> and safety compliance requirements (i.e. ISO 13849) external safety controls
> may be required when using this feature."*

Czyli sam producent kieruje do zewnętrznych układów bezpieczeństwa. To
spójne z tym, co już zapisaliśmy o Global Stop: **funkcja sterowania, nie
funkcja bezpieczeństwa**. Nic w tym materiale tego nie zmienia.

### D. Watchdog sieciowy — do świadomego skonfigurowania

Dokumentacja NodeStop wymienia jako jedną z przyczyn zatrzymania:
*„If the Network Watchdog has expired due to lack of host traffic."*

To bezpośrednio dotyczy otwartego ryzyka „realtime i utrata łączności"
z [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md): przy zawieszeniu mostka
albo procesu Pythona **silniki same się zatrzymają**. Trzeba jednak
sprawdzić, jaki jest domyślny czas watchdoga i czy jest w ogóle włączony —
dokumentacja API tego nie podaje, a od tego zależy, czy możemy się na tym
oprzeć. **Do zweryfikowania pomiarowo**, nie do założenia.

## Pozostałe funkcje warte uwagi

### Zdarzenia zamiast odpytywania („Attentions")

Advanced ClearPath-SC potrafi **sam wysłać powiadomienie** do hosta, gdy
zmieni się wybrany bit statusu — zamiast czekać, aż host o to zapyta.
Konfiguracja: `IAttnPort::Enable`, maska bitów w `IAttnNode::Mask`, potem
albo `WaitForAttn` (wątek na oś), albo jedna funkcja zwrotna
`IAttnPort::AttnHandler` dla całego portu.

To jest sprzętowy odpowiednik przerwań, których wzorzec opisałem przy
MIC488 ([`inspiracje-mic488.md`](inspiracje-mic488.md), punkt 3) — z tą
różnicą, że tu **zdarzenie generuje sam silnik**, a nie sterownik nadrzędny.
Nasz mostek dziś odpytuje status w pętli co 20 ms; przy rozbudowie o kolejne
osie i tryb automatyczny to jest naturalna droga wyjścia.

### Ruchy head-tail — pod zagłębianie frezu

Ruch head-tail ma **osobną, niższą prędkość na początku i/lub końcu**,
zdefiniowaną odległością od krańca ruchu (`HeadDistance`, `TailDistance`,
`HeadTailVelLimit` — wszystkie ustawialne z API). Dokumentacja opisuje to
jako *„high speed »get it close« section with a more gentler »until the axis
touches the part« section"*.

Dla nas: **zagłębianie w Z** — szybki zjazd nad materiał, delikatne wejście
w plastik, w jednej komendzie zamiast dwóch ruchów z zatrzymaniem pośrednim.
Dziś realizujemy to dwoma osobnymi `MOVEZ`, co daje przestój między nimi.

### Ruchy asymetryczne

Osobne przyspieszenie i hamowanie (`DecelLimit`). Przy osi Z z frezem
przydatne: szybkie podnoszenie, łagodne opuszczanie.

### RAS i g-Stop — tłumienie drgań

Advanced daje `g-Stop™` (tłumienie drgań) obok `RAS™` (ograniczanie zrywu).
Przy frezowaniu plastiku drgania przekładają się wprost na jakość
powierzchni. Konfigurowane w ClearView, więc wchodzi w ten sam pakiet co
Auto-Tune. Instrukcja zaznacza, że **g-Stop nie jest dostępny we wszystkich
konfiguracjach** (str. 2164 tekstu) — do sprawdzenia przy strojeniu.

### Rodzaje zatrzymania (`NodeStop`)

Mostek używa wyłącznie `STOP_TYPE_ABRUPT`. Dostępne są trzy style
(abrupt, rampa po `DecelLimit`, rampa po aktywnym decel) w trzech wariantach
(zwykły, `ESTOP_*` blokujący ruch do `NodeStopClear`, `DISABLE_*` wyłączający
węzeł po zatrzymaniu) — dziewięć kombinacji.

Dla nas istotne: `STOP_TYPE_ABRUPT` przy frezie zagłębionym w materiale to
zatrzymanie bez rampy, z pełnym momentem. Przy trybie półautomatycznym
i automatycznym (temat F) warto rozważyć wariant z rampą dla zatrzymania
„miękkiego" (przycisk STOP operatora), zostawiając abrupt dla zdarzeń
bezpieczeństwa.

### Global Stop jest okablowany fail-safe

> *„A normally closed switch is attached to the global stop Input […] If this
> switch is opened or the wire to the input is removed, a group shutdown will
> be generated. This provides a level of fail safe should the wire to the
> switch become disconnected."*

Zerwany przewód wywołuje zatrzymanie, nie ciszę. To dobra własność — ale
nadal **nie czyni z tego funkcji bezpieczeństwa w sensie certyfikacji**
(patrz ryzyko C).

### Wejścia A/B każdego węzła robią więcej, niż zakładaliśmy

Każdy węzeł ma dwa wejścia ogólnego przeznaczenia, konfigurowalne
w ClearView (okno „Input Actions") do:

- automatycznego zatrzymania węzła przy zaniku sygnału,
- **blokowania ruchu w zadanym kierunku (jak krańcówka)**,
- **limitowania momentu przy zadanym stanie wejścia**,
- wyzwalania ruchu (Advanced),
- **przechwytywania bieżącej pozycji** (Advanced).

Przy trzech serwach daje to 6 wejść. Dla tematu E (sygnał drzwi) i tematu C
(dodatkowe czujniki) to realne, nieodkryte wcześniej miejsce podłączenia —
a funkcja „blokowanie ruchu w kierunku" daje krańcówki sprzętowe bez
angażowania naszego kodu.

### Wyjścia SC4-HUB wymagają osobnego zasilania 24 V

> *„In order to use these outputs, an appropriately sized 24V power supply
> must be connected to the SC4-HUB board."*

Drobiazg montażowy, ale gdyby wrzeciono „nie chciało ruszyć", to jest jedna
z pierwszych rzeczy do sprawdzenia.

## Mapowanie na plan

| Ustalenie | Temat w [`plan-rozwoju.md`](plan-rozwoju.md) |
|---|---|
| `ILimits.TrqGlobal` z API; warunkowe limitowanie momentu | **C** — siła trzypoziomowa, siła per operacja |
| HardStop homing + Offset Move; parametry tylko w ClearView | **C** — bazowanie; **H** — konfiguracja w ClearView |
| Soft limits w silniku (wymagają bazowania) | **C**, **H** |
| Grupy wyzwalania jako poprawa startu osi | **H** — weryfikacja toru `LINIA` |
| Attentions zamiast odpytywania | **B**, **F** |
| Ruchy head-tail i asymetryczne | **C**, przyszła optymalizacja cyklu |
| Rodzaje `NodeStop` (rampa vs abrupt) | **F** — tryby pracy |
| Wejścia A/B węzłów jako miejsce na czujniki | **E**, **C**, **J** |
| **Wyjście BRAKE szeregowo z obwodem osłon** | **J**, **E** — warunek konieczny |
| Obciążalność 500 mA → przekaźnik pośredniczący | **J**, **H** |
| Watchdog sieciowy — sprawdzić domyślne ustawienie | **H** |
