# Plan rozwoju — tematy do zaimplementowania

Zestawienie tematów wyciągniętych z `docs/*.md`, `zbyszek/*.md` i `notatki.txt`
(stan na 2026-08-26). Karty do śledzenia postępu: [`kanban.md`](kanban.md).
To jest żywy dokument — aktualizuję go, gdy coś z listy zrobimy albo gdy
ustalimy coś nowego, zamiast zakładać kolejny plik.

## Skąd wzięte tematy

- `zbyszek/DECYZJE_2026-08-25.md` — najświeższe ustalenia architektoniczne
  (sesja robocza, jeszcze nie scalone do głównych dokumentów repo).
- `zbyszek/NOTATKI_FUNKCJONALNE.md` i `notatki.txt` — szczegółowe wymagania
  funkcjonalne (bazowanie, siły/prędkości, wrzeciono, drzwi, tryby pracy,
  ekrany, uprawnienia).
- `docs/sterownik-sc4-hub.md` — sekcja „Do zrobienia" (zadania sprzętowe).
- `docs/nowe-operacje-programu.md` — rozszerzenia formatu `.prg`, część
  świadomie odłożona.

## A. Uporządkowanie nazewnictwa sprzętu (ClearCore → SC4-Hub)

**Dlaczego to ważne teraz:** to jest źródło pomyłek przy dalszej pracy — kod
i główne dokumenty nadal mówią „ClearCore", a sprzęt i przyjęta architektura
to SC4-Hub/bridge od dwóch tygodni. `zbyszek/README.md` i
`zbyszek/ARCHITEKTURA.md` miały już poprawione wersje, ale leżały osobno,
nie w głównych plikach.

- [x] Scalone `zbyszek/README.md` → `README.md` i `zbyszek/ARCHITEKTURA.md` →
      `docs/ARCHITEKTURA.md` — **z korektą**: `zbyszek/` używał nazwy
      „Teknic SysAPI" i opisywał `bridge/` hipotetycznie (Python/C++,
      IPC przez socket/gRPC); faktycznie zbudowany i przetestowany na
      sprzęcie mostek (sesja 2026-08-14) używa biblioteki **sFoundation**
      i protokołu TCP na porcie 8500 — to zostało poprawione przy scalaniu,
      zamiast przepisać nieaktualną wersję. `zbyszek/README.md` i
      `zbyszek/ARCHITEKTURA.md` usunięte jako zbędne po scaleniu;
      `zbyszek/DECYZJE_2026-08-25.md` i `zbyszek/NOTATKI_FUNKCJONALNE.md`
      zostają — to wciąż niezrealizowane źródło dla tematów B–G.
- [x] `firmware/clearcore/` **usunięty** (decyzja: kod martwy, nic do
      wgrania). Protokół, który opisywał, przeniesiony do
      `docs/ARCHITEKTURA.md` (sekcja „Protokół mostka"), zaktualizowany o
      `AXCFG` i realny stan implementacji w `bridge/`.
- [ ] Przejrzeć `server/app/machine.py` i inne pliki pod kątem nazw
      `ClearCoreMachine`, `MACHINE_MODE=clearcore`, `CLEARCORE_HOST` —
      **odłożone świadomie** (decyzja): zostają jako nazwa historyczna, do
      zmiany osobnym krokiem później, żeby nie mieszać z porządkami
      w dokumentacji.

Źródło: `zbyszek/DECYZJE_2026-08-25.md` §1, §6; `docs/sterownik-sc4-hub.md`
„Do zrobienia".

## B. Model dwuwarstwowy: cykl maszyny vs program detalu — fundament

To jest temat, od którego zależy większość reszty (C–F) — beze modelu danych
nie ma gdzie podłączyć dodatkowych osi, profili siły ani trybów pracy.
Ustalony jako **następny krok** w `DECYZJE_2026-08-25.md`, jeszcze nie
zaprojektowany.

- [ ] Zaprojektować model danych: `Axis`, `ParameterProfile`, `CycleStep`,
      `PartProgram` (12NC — już częściowo istnieje jako `.prg`/`program.py`),
      `Operation`.
- [ ] Warstwa „cyklu maszyny" (poziom admina): podawanie → bazowanie/docisk →
      wywołanie programu detalu → przywrócenie parametrów → wyrzut → powtórz.
- [ ] Mechanizm snapshot/restore parametrów osi wokół programu 12NC — **także
      przy błędzie/przerwaniu, nie tylko przy sukcesie** (analogicznie do
      try/finally) — te same osie fizyczne, różne parametry w cyklu i w
      programie detalu.
- [ ] Ekran definiowania ruchów cyklu maszyny — analogiczny do edytora
      technologa, plus operacja „skok do wybranego podprogramu technologa".

Źródło: `zbyszek/DECYZJE_2026-08-25.md` §2, §3, §5, §7;
`zbyszek/NOTATKI_FUNKCJONALNE.md` §3.

## C. Dodatkowe osie i konfiguracja ruchu

- [ ] Rozszerzyć model `/axes` o dodatkowe osie (podajnik automatyczny, oś
      bazowania/docisku z kontrolą momentu) — dziś model zna tylko X/Y/Z
      (`docs/konfiguracja-osi.md`).
- [ ] Bazowanie bez wyłączników krańcowych: użyć wbudowanej funkcji bazowania
      serwa; przycisk „dojazd do HOME wszystkich osi"; oddzielny ekran
      konfiguracji bazowania (osobno od ekranu prędkości/siły).
- [ ] Konfiguracja siły — **trzy poziomy**: globalna (domyślnie 20%), ruch
      podczas cyklu maszyny (per zdefiniowany ruch, domyślnie 15%), ruch
      podczas programu technologa (domyślnie 10%).
- [ ] Prędkości maksymalne (per oś) i robocze osobno dla: ruchu roboczego,
      bazowania, trybu JOG.
- [ ] Siła/prędkość konfigurowalne **na każdym kroku programu**, zależnie od
      pozycji — sprawdzić w bibliotece Teknic (sFoundation/SysAPI), jakie
      funkcje są dostępne pod to zastosowanie.
- [ ] W programie technologa: możliwość ustawienia siły per operacja (jeśli
      nieustawiona — wartość domyślna z ekranu parametrów maszyny).

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §1, §2; `notatki.txt`.

## D. Wrzeciono

- [ ] Włączenie wrzeciona przy starcie maszyny — przełącznik na ekranie
      Start/Stop.
- [ ] Włączenie wrzeciona przy starcie programu — dwie opcje konfigurowalne
      w konfiguracji maszyny.
- [ ] Sterowanie prędkością wrzeciona przez wyjście PWM.
- [ ] Włącz/wyłącz wrzeciona jako osobny port cyfrowy I/O.
- [ ] Konfiguracja rozpędzania i hamowania wrzeciona dla sterowania PWM.

**Blokada, nie „do sprawdzenia":** dziś mostek ma tylko
`SPINDLE_OUTPUT=none/brake0/brake1` (włącz/wyłącz na wyjściu huba).
**SC4-Hub nie ma wyjścia PWM ani analogowego** — sterowania prędkością
wrzeciona nie da się na nim zrobić bez dodatkowego sprzętu. Patrz temat **J**
niżej; rozstrzygnąć **przed** rozpoczęciem tego tematu.

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §4; `notatki.txt`;
[`inspiracje-mic488.md`](inspiracje-mic488.md).

## E. Bezpieczeństwo: drzwi/osłona i uprawnienia — ryzyka wprost

- [ ] Dodatkowy port wejściowy dla sygnału drzwi (PWM ~100Hz albo 0/1),
      aktywny tylko w pracy automatycznej, z niezależnym włącz/wyłącz
      w konfiguracji.

  **Ryzyko, nie do zmiękczenia:** sygnał drzwi czytany programowo **nie jest
  certyfikowaną funkcją bezpieczeństwa**. Ma tylko uzupełniać sprzętowy
  Global Stop na SC4-Hub (kurtyna/wyłącznik drzwiowy → Global Stop fizycznie
  odcina zezwolenie), nie go zastępować. Odczyt PWM w softcie służy do
  diagnostyki i logiki trybu automatycznego.

- [ ] Warstwa ról i logowania: admin / technolog / operator, z dostępem do
      `/axes`, `/editor`, panelu operatora odpowiednio.

  **Ryzyko, nie do zmiękczenia:** PIN-y zaproponowane w notatkach
  (`123321`, `456`, `789`) są bardzo słabe dla ekranu, który realnie wpływa
  na bezpieczeństwo (konfiguracja siły/prędkości). Wspólny PIN na rolę też
  nie pozwala rozliczyć, kto zmienił parametry. **Do ustalenia z Tobą:**
  zostawiamy PIN-y (i jeśli tak, to jakie), czy przechodzimy na osobne konta.

- [ ] Przed uruchomieniem produkcyjnym: przegląd całego obwodu
      bezpieczeństwa (E-stop, Global Stop, kurtyny, kategoria wg
      PN-EN ISO 13849-1) **z osobą uprawnioną do oceny ryzyka maszyn**
      (dyrektywa maszynowa, CE) — to nie jest coś, co rozstrzygamy tylko na
      podstawie tych notatek.

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §5, §9 i sekcja „Sugestie i pytania".

## F. Tryby pracy

- [ ] Manualny — przytrzymanie przycisku wybranej osi = ruch, puszczenie =
      zatrzymanie (funkcja „martwego człowieka").
- [ ] Półautomatyczny — jeden pełny cykl.
- [ ] Automatyczny — pętla nieskończona cyklu maszyny do odczytu E-Stop lub
      otwarcia drzwi, plus przyciski start/stop na ekranie.

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §6.

## G. Ekrany i zarządzanie programami

- [ ] Ekran główny — prosty, niezbędne przyciski i komunikaty, nazwa maszyny
      „Demontaż pinów z optyki", logo WALKNER.
- [ ] Ekran diagnostyczny (tylko admin) — definiowanie, praca ręczna,
      półautomatyczna i automatyczna z funkcjami zabezpieczeń.
- [ ] Ekran definiowania operacji cyklu — osobne okno/zakładka.
- [ ] Kopiowanie programów technologicznych — opcja „zapisz jako".

Inspiracja funkcjonalna: sterownik MD488 jako punkt odniesienia (ale bez
konfiguracji siły — nasze serwa Teknic mają to natywnie); ekrany mają
wyglądać inaczej, bardziej rozbite na funkcjonalności.

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §7, §8, §10.

## H. Uruchomienie sprzętowe (blokujące, ale poza softwarem)

Te zadania nie są kodem — wymagają fizycznej obecności przy maszynie i (w
części) komputera z Windows. Zostawiam je na liście, bo blokują przejście
z symulatora na produkcję.

- [ ] Auto-Tune każdej osi pod obciążeniem — wymaga Windows z ClearView;
      zapisać `.mtr` i wczytywać z Linuksa (`LoadingConfigFile`).
- [ ] Skonfigurować homing w ClearView — dziś bazowanie to tylko zerowanie
      programowe, na maszynie z mechaniką nie wystarczy.
- [ ] Zweryfikować pomiarowo tor operacji `LINIA` (interpolacja przybliżona;
      zmierzone odchylenie czasu przejazdu, ale nie geometrii toru).
- [ ] Test: utrata zezwolenia (Global Stop) w trakcie ruchu.
- [ ] Test: zachowanie komunikacji przy wciśniętym E-stopie (czy odcina
      magistralę DC, czy mostek to odróżnia od awarii łącza).
- [ ] Instalacja i weryfikacja reguły udev (`tools/99-teknic-sc4hub.rules`)
      przez przewtyknięcie huba.
- [ ] Obciążalność wyjść `BRAKE_0`/`BRAKE_1` pod stycznik wrzeciona.

Źródło: `docs/sterownik-sc4-hub.md` „Do zrobienia".

## I. Odłożone / niski priorytet

- [ ] `LUK`, `OKRAG`, `POLILINIA` (operacje grupy B w `.prg`) — świadomie
      pominięte, wraca tylko jeśli łuki okażą się faktycznie potrzebne przy
      ocinaniu wlewków (dziś odcinki wystarczają).
- [ ] GRBL/G-code jako alternatywny sposób programowania — zaplanowane jako
      rozszerzenie na później, niski priorytet.

Źródło: `docs/nowe-operacje-programu.md`; `zbyszek/DECYZJE_2026-08-25.md` §5.5.

## J. Skąd wziąć wejścia i wyjścia — decyzja blokująca D i E

Wyszło z porównania z kontrolerem MIC488
([`inspiracje-mic488.md`](inspiracje-mic488.md)). SC4-Hub jest hubem
komunikacyjnym do silników, nie sterownikiem maszyny: ma **2 wyjścia**
(`BRAKE_0`, `BRAKE_1`), **1 wejście Global Stop** i **2 wejścia ogólnego
przeznaczenia na węzeł** (6 przy trzech serwach). Dla porównania MIC488 ma
20 wejść, 8 wyjść i 2 wejścia analogowe.

Zaplanowane funkcje, które nie mają dziś gdzie się podłączyć:

- sterowanie prędkością wrzeciona (temat D) — **brak wyjścia PWM
  i analogowego**,
- włącz/wyłącz wrzeciona — zajmie jedno z dwóch wyjść,
- sygnał drzwi/osłony (temat E),
- podajnik, wyrzutnik, lampka sygnalizacyjna, sygnał błędu.

- [x] Sprawdzone (2026-08-26): Teknic **nie ma** modułu I/O z PWM pasującego
      do naszej architektury. `CCIO-8` (rozszerzenie I/O Teknica) ma PWM, ale
      wymaga hosta ClearCore — u nas nieużywalny. `POWER4-HUB` to tylko
      rozdzielacz zasilania, bez I/O. Same `BRAKE_0`/`BRAKE_1` na SC4-Hub to
      zwykłe wyjścia 24VDC włącz/wyłącz, bez PWM.
- [x] **Decyzja (Twoja):** zewnętrzny regulator PWM do wrzeciona, załączany
      zwykłym sygnałem on/off z jednego z wyjść `BRAKE_0`/`BRAKE_1`
      (`SPINDLE_OUTPUT=brake0` albo `brake1` w `bridge/machine.env` — dziś
      `none`). SC4-Hub daje tylko włącz/wyłącz; PWM generuje już zewnętrzny
      regulator. Nic więcej po stronie mostka nie trzeba zmieniać poza
      przełączeniem tej jednej zmiennej.
- [ ] Sprawdzić obciążalność `BRAKE_0`/`BRAKE_1` pod wejście enable
      zewnętrznego regulatora (jest już w temacie H).
- [ ] Wybrać konkretny model zewnętrznego regulatora PWM do wrzeciona.
- [ ] Drugie wyjście (`BRAKE_0` albo `BRAKE_1`, to które zostanie wolne) wciąż
      potrzebne na coś z: podajnik, wyrzutnik, lampka, sygnał błędu — do
      rozstrzygnięcia przy temacie C/G.

**Zastrzeżenie co do źródła:** `teknic.com` i lustro instrukcji na
`manualslib.com` są zablokowane siecowo w tej sesji (polityka egress) — ustalenia
powyżej pochodzą z cytatów wyszukiwarki wskazujących na oficjalną instrukcję
ClearPath-SC (sekcja „Sc4-Hub Specifications", str. 104) i stronę produktową
SC4-Hub, **nie z bezpośredniego odczytu tych stron**. Zgodnie z zasadą
weryfikacji faktów u źródła — potwierdź to sam otwierając
`https://teknic.com/sc4-hub/` i instrukcję ClearPath-SC, zanim to się stanie
podstawą zakupu sprzętu.

Źródło: [`inspiracje-mic488.md`](inspiracje-mic488.md);
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md); wyszukiwanie web 2026-08-26
(cytujące teknic.com/sc4-hub/ i ClearPath-SC User Manual str. 104 —
niezweryfikowane bezpośrednio, patrz zastrzeżenie wyżej).

## Proponowana kolejność — do potwierdzenia

To jest **propozycja**, nie decyzja — ustalmy razem, czy się zgadzasz:

1. **A** (nazewnictwo) — ✅ zrobione poza zmianą nazw w kodzie.
2. **B** (model danych cyklu/programu) — fundament pod C–G, największe ryzyko
   architektoniczne, więc warto to rozstrzygnąć najpierw. Wzorce warte
   podpatrzenia (tablica pozycji, podprogramy, przerwania) opisane
   w [`inspiracje-mic488.md`](inspiracje-mic488.md).
3. **J** (skąd I/O) — ✅ rozstrzygnięte (zewnętrzny regulator PWM przez
   `BRAKE_0`/`BRAKE_1`), nie blokuje już D. Zostają drobiazgi: obciążalność
   wyjścia, wybór modelu regulatora, przeznaczenie drugiego wyjścia.
4. **C, D, F** (osie, wrzeciono, tryby pracy) — budują się na B.
5. **E** (drzwi, uprawnienia) — wymaga decyzji od Ciebie (PIN-y vs konta).
6. **G** (ekrany) — najlepiej równolegle z C–F, w miarę jak funkcje powstają.
7. **H** — osobny tor, fizyczny, nie blokuje pracy nad softwarem, ale blokuje
   produkcję.
8. **I** — dopiero jeśli się okaże potrzebne.
