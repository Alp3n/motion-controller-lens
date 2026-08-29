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
Ustalony jako **następny krok** w `DECYZJE_2026-08-25.md`.

- [x] Zaprojektować model danych (propozycja gotowa do przeglądu):
      [`model-cyklu-maszyny.md`](model-cyklu-maszyny.md) — `Axis`,
      `ParameterProfile`, `CycleStep`, `PartProgram` (12NC — już istnieje
      jako `.prg`/`program.py`, bez zmian). Wyjście cyfrowe jako pole
      `CycleStep`, nie `Operation` — zgodnie z wcześniejszą decyzją.
      **Podzielone na 4 etapy wdrożenia** — patrz dokument.
- [x] **Etap 1:** `AXIS_NAMES` → `REQUIRED_AXES` (X/Y/Z, wymagane zawsze) +
      `parse_axes`/`save`/`to_dict` w `server/app/axes.py` zachowują dowolne
      osie ponad te trzy (walidacja nazwy: małe litery/cyfry/podkreślenie).
      `work_area()` świadomie zostaje ograniczone do X/Y/Z (zakres cięcia
      `.prg`, nie dotyczy podajnika/docisku). `ClearCoreMachine._push_axis_config`
      w `machine.py` **celowo dalej wysyła `AXCFG` tylko dla X/Y/Z** — protokół
      mostka nie zna innych liter osi; osie dodatkowe czekają na rozszerzenie
      protokołu (temat C). Sprawdzone end-to-end przez `/api/axes` (PUT z
      dodatkową osią „podajnik” zapisuje i zwraca ją poprawnie) i 4 nowe
      testy w `test_axes.py`. 63/63 testów przechodzi.
- [x] **Etap 2:** `ParameterProfile` + `AxisParams` w `server/app/profiles.py`
      (prędkość maks., rampy, limit momentu), plik `config/profiles.json`,
      endpointy `GET/PUT /api/profiles` i `POST /api/profiles/active`.
      Trzy profile domyślne z wartościami z notatek §2 (20/15/10%).
      Prędkość maksymalna **działa w symulatorze** (test mierzy czas ruchu).
      **Limit momentu nie trafia jeszcze do sprzętu** — protokół mostka nie
      ma komendy momentu; w trybie sprzętowym API zwraca o tym ostrzeżenie.
      21 nowych testów, 84/84 przechodzi. Szczegóły:
      [`zmiany/profile-parametrow-etap2.md`](zmiany/profile-parametrow-etap2.md).
- [ ] **Etap 2b:** doprowadzić limit momentu (i rampy) do sprzętu — komenda
      w protokole mostka + `ILimits.TrqGlobal` w `bridge/sc4hub_bridge.cpp`.
      **Wymaga sprzętu i SDK Teknica** (`vendor/`, poza repo) — nie da się
      tego skompilować ani przetestować w środowisku sesji.
- [x] **Etap 3:** `CycleStep`/`Cycle` w `server/app/cycle.py` (kroki `RUCH`,
      `PROGRAM`, `WYJSCIE`, `PAUZA`), plik `config/cycle.json`, endpointy
      `GET/PUT /api/cycle` i `POST /api/machine/cycle/start`.
      **Snapshot/restore profilu w `try/finally`** — wraca przy zakończeniu,
      błędzie i przerwaniu (STOP); dwa testy pilnują tego wprost i padają po
      usunięciu `finally`. Sprawdzone end-to-end: cykl podanie → docisk →
      program detalu → wyrzut przełącza profile `cykl`/`program` i wraca na
      `globalny`. 26 nowych testów, 110/110 przechodzi. Szczegóły:
      [`zmiany/cykl-maszyny-etap3.md`](zmiany/cykl-maszyny-etap3.md).
      Świadomie poza zakresem: pętla cyklu (tryb automatyczny — temat F),
      krok „czekaj na wejście" (brak czytelnych wejść), `WYJSCIE` na sprzęcie
      (brak komendy w protokole — etap 2b).
- [x] **Etap 4:** ekran `/cycle` — tabela kroków z walidacją na bieżąco
      (lustro `CycleStep.validate()`), przestawianie wierszy, zapis,
      uruchomienie cyklu i podgląd na żywo (który krok, jaki profil, stan
      wyjść). Krok `PROGRAM` realizuje „skok do podprogramu technologa"
      z `NOTATKI_FUNKCJONALNE.md` §3. Sprawdzone w przeglądarce
      (Playwright/Chromium), bez błędów JS. Szczegóły:
      [`zmiany/ekran-cyklu-etap4.md`](zmiany/ekran-cyklu-etap4.md).

**Temat B zamknięty** w zakresie, jaki da się zrobić bez sprzętu. Co z niego
zostaje na później: `WYJSCIE` i limit momentu na maszynie (etap 2b), pętla
cyklu (temat F), ruch osi innych niż X/Y/Z (temat C).

Źródło: `zbyszek/DECYZJE_2026-08-25.md` §2, §3, §5, §7;
`zbyszek/NOTATKI_FUNKCJONALNE.md` §3.

## C. Dodatkowe osie i konfiguracja ruchu

- [x] Model i ekran `/axes` przyjmują dodatkowe osie (podajnik automatyczny,
      oś bazowania/docisku z kontrolą momentu) — backend od etapu 1 tematu B,
      teraz też interfejs: dodawanie/usuwanie z ekranu, odznaka „tylko
      konfiguracja”. Szczegóły:
      [`zmiany/dodawanie-osi-ekran.md`](zmiany/dodawanie-osi-ekran.md).
- [ ] **Pozostaje najważniejsze:** rozszerzyć protokół mostka (`AXCFG` i
      komendy ruchu dla liter osi spoza X/Y/Z), żeby dodana oś faktycznie
      jeździła — dziś zapisuje się tylko w konfiguracji. Wymaga C++ i sprzętu.
- [ ] Bazowanie bez wyłączników krańcowych: tryb **HardStop** z parametrem
      *Homing Torque Limit*, plus *Offset Move* odwzorowujący nasz „punkt
      bazowania"; przycisk „dojazd do HOME wszystkich osi"; oddzielny ekran
      konfiguracji bazowania. **Uwaga:** parametrów bazowania nie da się
      ustawić z kodu — wyłącznie w ClearView (temat H).
- [x] Konfiguracja siły — **trzy poziomy**: globalna (domyślnie 20%), ruch
      podczas cyklu maszyny (per zdefiniowany ruch, domyślnie 15%), ruch
      podczas programu technologa (domyślnie 10%). Mechanizm (`ILimits.TrqGlobal`
      + `TrqUnit(PCT_MAX)`, `/api/profiles`) gotowy od etapu 2 tematu B; teraz
      dochodzi ekran `/profiles` do edycji i przełączania. Limit momentu
      nadal działa tylko w symulatorze — do sprzętu wymaga rozszerzenia
      protokołu mostka (C++, sprzęt). Szczegóły:
      [`zmiany/ekran-profili.md`](zmiany/ekran-profili.md).
- [x] Prędkości JOG i bazowania per oś — ekran `/axes`; JOG działa też na
      sprzęcie (trafia do mostka komendą `JOG`), bazowanie tylko w
      symulatorze (na sprzęcie steruje nim ClearView, nie nasz serwer).
      Prędkość maksymalna i robocza już istniały wcześniej (profile
      parametrów, `POSUW_ROBOCZY`/`POSUW_DOJAZDU`). Szczegóły:
      [`zmiany/predkosci-jog-bazowanie.md`](zmiany/predkosci-jog-bazowanie.md).
- [x] Siła/prędkość zależne od pozycji — **sprawdzone**: serwa mają
      *Conditional Torque Limiting* z warunkiem „Absolute Position"
      (konfiguracja w ClearView, działa w silniku). Wersję „per operacja"
      realizuje `TrqGlobal` z API. Szczegóły:
      [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).
- [x] W programie technologa: możliwość ustawienia siły per operacja (jeśli
      nieustawiona — wartość domyślna z aktywnego profilu). Kolumna `MOMENT`,
      format 4 pliku `.prg`. Jak limit momentu w profilach — dziś wyłącznie
      zapis w pliku, nie dociera do symulatora ani sprzętu. Szczegóły:
      [`zmiany/sila-per-operacja.md`](zmiany/sila-per-operacja.md).
- [ ] Rozważyć włączenie **soft limits w samym silniku** jako warstwy
      dodatkowej (dziś nieaktywne — wymagają prawdziwego bazowania).
- [ ] Rozważyć ruchy **head-tail** dla zagłębiania w Z (szybki zjazd +
      delikatne wejście w materiał w jednej komendzie) i **asymetryczne**
      (inne przyspieszenie niż hamowanie).

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §1, §2; `notatki.txt`;
[`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).

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
      w konfiguracji. **Miejsce podłączenia jest** — każdy węzeł ma dwa
      wejścia ogólnego przeznaczenia (6 przy trzech serwach), konfigurowalne
      w ClearView także jako krańcówki kierunkowe i wyzwalacze limitu
      momentu: [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).

  **Ryzyko, nie do zmiękczenia:** sygnał drzwi czytany programowo **nie jest
  certyfikowaną funkcją bezpieczeństwa**. Ma tylko uzupełniać sprzętowy
  Global Stop na SC4-Hub (kurtyna/wyłącznik drzwiowy → Global Stop fizycznie
  odcina zezwolenie), nie go zastępować. Odczyt PWM w softcie służy do
  diagnostyki i logiki trybu automatycznego. Ten sam obwód osłon musi
  **rozłączać szeregowo wyjście `BRAKE_x` sterujące wrzecionem** (temat J).

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

## F. Tryby pracy — zrobione

- [x] Manualny — przytrzymanie przycisku wybranej osi = ruch, puszczenie =
      zatrzymanie (funkcja „martwego człowieka"). Mostek nie ma komendy
      ciągłego ruchu, więc przytrzymanie realizują powtarzane krótkie
      przejazdy JOG — to wygoda operatora, nie certyfikowana funkcja
      bezpieczeństwa (tę rolę pełni sprzętowy E-stop/Global Stop).
- [x] Półautomatyczny — jeden pełny cykl. Istniał od etapu 3/4 tematu B,
      ekran `/cycle` teraz nazywa go wprost.
- [x] Automatyczny — pętla cyklu maszyny do STOP, błędu w kroku albo utraty
      sygnału zezwolenia (odczyt drzwi z tematu E jeszcze nie istnieje —
      pętla zatrzyma się na tym, co już jest). Przy pisaniu znaleziony
      i naprawiony błąd: krok bez realnego ruchu (WYJSCIE, RUCH do już
      zajętej pozycji) nigdy się nie zawieszał, więc pętla bez punktu
      zawieszenia mroziła **cały serwer**, nie tylko cykl.
      Szczegóły: [`zmiany/tryby-pracy.md`](zmiany/tryby-pracy.md).

**Nowo znalezione, nie wcześniej zgłoszone:** cykl (jeden przebieg i pętla)
działa dziś tylko w symulatorze — `ClearCoreMachine` nie ma `start_cycle`.
`/cycle` nie działał na sprzęcie już od etapu 4 tematu B; nikt tego wcześniej
nie sprawdził i nie zapisał. Wymaga C++ i fizycznego sprzętu (temat B/H).

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §6.

## G. Ekrany i zarządzanie programami

- [x] Ekran główny — to już jest panel operatora (`/`): prosty, ma
      niezbędne przyciski i komunikaty. Nazwa: nie „Demontaż pinów z optyki"
      z notatki §7 — ta nazwa jest sprzeczna z resztą repo i CLAUDE.md,
      okazała się nieaktualna (potwierdzone z Tobą) — poprawiona literówka
      w całym repo: „ocinanie" → **„odcinanie wlewków płytek optyki"**.
      Logo WALKNER: miejsce w nagłówku gotowe (`#logo` w `index.html`,
      znika automatycznie, gdy pliku nie ma), plik jeszcze nie dostarczony —
      wystarczy wrzucić `server/app/static/img/logo.png` i wypchnąć, bez
      zmian w kodzie. Szczegóły: [`zmiany/ekran-glowny.md`](zmiany/ekran-glowny.md).
- [ ] Ekran diagnostyczny (tylko admin) — definiowanie, praca ręczna,
      półautomatyczna i automatyczna z funkcjami zabezpieczeń. Wymaga
      warstwy ról (temat E) — dziś nie ma pojęcia „tylko admin".
- [x] Ekran definiowania operacji cyklu — osobne okno/zakładka. Zrobione
      jako `/cycle` już w etapie 4 tematu B — korekta tej listy, nie nowa
      praca (nikt wcześniej nie odhaczył tego punktu tutaj).
- [x] Kopiowanie programów technologicznych — opcja „zapisz jako" w edytorze
      technologa. Szczegóły:
      [`zmiany/zapisz-jako-program.md`](zmiany/zapisz-jako-program.md).

Inspiracja funkcjonalna: sterownik MD488 jako punkt odniesienia (ale bez
konfiguracji siły — nasze serwa Teknic mają to natywnie); ekrany mają
wyglądać inaczej, bardziej rozbite na funkcjonalności.

Źródło: `zbyszek/NOTATKI_FUNKCJONALNE.md` §7, §8, §10.

## H. Uruchomienie sprzętowe (blokujące, ale poza softwarem)

Te zadania nie są kodem — wymagają fizycznej obecności przy maszynie i (w
części) komputera z Windows. Zostawiam je na liście, bo blokują przejście
z symulatora na produkcję.

Sesja w ClearView (Windows) domyka naraz kilka rzeczy — warto zaplanować ją
jako **jedno wejście**, nie kilka osobnych:

- [ ] Auto-Tune każdej osi pod obciążeniem — wymaga Windows z ClearView;
      zapisać `.mtr` i wczytywać z Linuksa (`LoadingConfigFile`).
- [ ] Skonfigurować homing (tryb **HardStop**, *Homing Torque Limit*,
      *Offset Move*) — dziś bazowanie to tylko zerowanie programowe.
- [ ] Włączyć **soft limits** w silnikach (działają dopiero po bazowaniu).
- [ ] Skonfigurować **warunkowe limitowanie momentu** (Move Done, Absolute
      Position) — pod temat C.
- [ ] Skonfigurować **wejścia A/B węzłów** („Input Actions") — krańcówki
      kierunkowe, sygnał drzwi, limit momentu od wejścia.
- [ ] Sprawdzić dostępność i ustawienia **g-Stop** (tłumienie drgań) — wpływa
      na jakość powierzchni przy frezowaniu plastiku.

Pomiary i testy:

- [ ] Zweryfikować pomiarowo tor operacji `LINIA` (interpolacja przybliżona;
      zmierzone odchylenie czasu przejazdu, ale nie geometrii toru).
      Przy okazji spróbować **grup wyzwalania** (`TriggerGroup` +
      `TriggerMovesInGroup`) — usuwają niejednoczesny start osi.
- [ ] Sprawdzić **domyślny czas watchdoga sieciowego** i czy jest włączony —
      od tego zależy, czy można się oprzeć na samoczynnym zatrzymaniu przy
      zawieszeniu mostka. **Nie zakładać, że działa — zmierzyć.**
- [ ] Test: utrata zezwolenia (Global Stop) w trakcie ruchu.
- [ ] Test: zachowanie komunikacji przy wciśniętym E-stopie (czy odcina
      magistralę DC, czy mostek to odróżnia od awarii łącza).
- [ ] Test: czy wyjście `BRAKE_x` faktycznie da się przypadkowo załączyć przy
      ponownej enumeracji USB (ryzyko A w
      [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md)) —
      **z odłączonym wrzecionem.**
- [ ] Instalacja i weryfikacja reguły udev (`tools/99-teknic-sc4hub.rules`)
      przez przewtyknięcie huba.
- [x] ~~Obciążalność wyjść `BRAKE_0`/`BRAKE_1`~~ — **500 mA / 24 VDC**
      (instrukcja rev. 1.45, str. 47).

Źródło: `docs/sterownik-sc4-hub.md` „Do zrobienia";
[`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).

## I. Odłożone / niski priorytet

- [ ] `LUK`, `OKRAG`, `POLILINIA` (operacje grupy B w `.prg`) — świadomie
      pominięte, wraca tylko jeśli łuki okażą się faktycznie potrzebne przy
      odcinaniu wlewków (dziś odcinki wystarczają).
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
- [x] **Obciążalność sprawdzona: 500 mA / 24 VDC** (instrukcja ClearPath-SC
      rev. 1.45, str. 47). Wystarcza na cewkę małego przekaźnika
      pośredniczącego; **nie** podłączać stycznika bezpośrednio. API ma bity
      wykrycia przeciążenia (`GPO_OVERLOAD_BIT`).
- [ ] **Warunek konieczny (bezpieczeństwo):** sygnał `BRAKE_x` → regulator
      wrzeciona musi iść **szeregowo przez styk obwodu osłon/kurtyn**.
      Powód: producent ostrzega, że system operacyjny może **przypadkowo
      załączyć wyjście**, gdy nasza aplikacja nie trzyma portu — a u nas ten
      scenariusz realnie występuje (`cdc_acm` przejmuje hub przy każdej
      ponownej enumeracji). Bez tego wrzeciono może ruszyć bez udziału
      programu. Szczegóły i cytat:
      [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md), ryzyko A.
- [ ] Uwaga montażowa: wyjścia SC4-HUB wymagają **osobnego zasilania 24 V**
      podłączonego do płytki huba.
- [ ] Wybrać konkretny model zewnętrznego regulatora PWM do wrzeciona.
- [x] **Decyzja (Twoja):** drugie wyjście (to, które zostanie wolne po
      wrzecionie) definiuje się w **konfiguracji maszyny** (admin, cykl —
      temat B) jako dowolne przeznaczenie: podajnik, wyrzutnik, lampka,
      sygnał błędu. **Program technologa (`.prg`) z tego wyjścia nie
      korzysta** — to wyłącznie poziom cyklu maszyny.

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
