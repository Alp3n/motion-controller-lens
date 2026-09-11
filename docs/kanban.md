# Kanban — plan rozwoju

Karty odpowiadają tematom z [`plan-rozwoju.md`](plan-rozwoju.md) — tam jest
uzasadnienie i źródło każdego punktu, tu tylko status pracy. Przenoszę karty
między kolumnami ręcznie, w miarę postępu (wytnij linię i wklej w innej
kolumnie, albo po prostu zmień nagłówek sekcji, do której należy).

Format czytelny w zwykłym Markdown (GitHub, VS Code) — nie wymaga żadnego
rozszerzenia. Jeśli wolisz wizualną tablicę z przeciąganiem kart, to samo
da się odwzorować w GitHub Projects (Issues + widok Board) — powiedz, jeśli
mam to założyć.

## Do zrobienia

### B. Model cyklu maszyny i programu detalu
- [x] Zaprojektować model — propozycja w `model-cyklu-maszyny.md`, do przeglądu
- [x] Etap 1: `AXIS_NAMES` → `REQUIRED_AXES` w `axes.py`, dowolne osie ponad
      X/Y/Z zachowane; mostek dalej dostaje `AXCFG` tylko dla X/Y/Z
- [x] Etap 2: `ParameterProfile` + `/api/profiles`; prędkość działa w symulatorze,
      moment na razie tylko po stronie serwera (ostrzeżenie w trybie sprzętowym)
- [x] Etap 2b: moment do sprzętu — `TRQLIMIT` wdrożone i **fizycznie
      zweryfikowane 2026-09-01**: limit 8% zatrzymał ruch pod obciążeniem.
      Poprawiony też mylący komunikat alarmu (zatrzymanie przez limit
      zgłaszało się jako gołe „przekroczono czas ruchu" — teraz nazywa
      przyczynę, `HadTorqueSaturation()`). Rampy dalej tylko przechowywane.
      Szczegóły: `zmiany/limit-momentu-sprzet.md`
- [x] Etap 3: `CycleStep` + `/api/cycle` + snapshot/restore profilu w `try/finally`
      (wraca przy błędzie i przy STOP; `WYJSCIE` na razie tylko w symulatorze)
- [x] Etap 4: ekran `/cycle` — tabela kroków, walidacja, uruchomienie
      i podgląd na żywo; krok PROGRAM = skok do podprogramu technologa
- [x] `SC4HubMachine.start_cycle` dopisany — RUCH/PROGRAM/PAUZA przez
      istniejące komendy mostka (MOVEZ/MOVEXY/SPINDLE), WYJSCIE dalej tylko
      w statusie (brak komendy w protokole). **Nie zweryfikowane na
      fizycznym sterowniku** — do potwierdzenia przy uruchomieniu
      sprzętowym (temat H). `zmiany/cykl-na-sprzecie.md`

### C. Osie i konfiguracja ruchu
- [x] Dodatkowe osie w `/axes` (dodawanie/usuwanie, odznaka „tylko konfiguracja”)
- [ ] Rozszerzyć protokół mostka, żeby dodana oś faktycznie jeździła (C++, sprzęt)
- [x] Ekran bazowania `/homing` (kolejność osi, HardStop/programowe, limit
      momentu, offset, prędkość) + przycisk „HOME wszystkich osi" na środku
      strzałek XY. Parametry HardStop dalej tylko zapis dla ClearView;
      kolejność działa tylko w symulatorze (na sprzęcie sekwencję robi serwo)
- [x] Siła trzypoziomowa (globalna / cykl / program technologa) — mechanizm
      i API gotowe od etapu 2 tematu B, teraz ekran `/profiles`. Limit
      momentu dalej tylko w symulatorze (protokół mostka bez komendy
      momentu — C++, wymaga sprzętu)
- [x] Prędkości JOG i bazowania per oś (max i robocza już były gotowe —
      profile parametrów, `POSUW_ROBOCZY`/`POSUW_DOJAZDU`); bazowanie tylko
      w symulatorze, JOG też na sprzęcie
- [x] Przycisk „JEDŹ DO ZERA" na panelu operatora, pod przyciskiem bazowania
      — dojazd wszystkich osi do punktu zerowego (po zbazowaniu, gdy maszyna
      stoi gdzie indziej), w tej samej kolejności co bazowanie. To ruch
      pozycyjny, nie ponowne bazowanie. **Poprawione 2026-09-09 (decyzja
      operatora):** kolejność ruchu ustalona na sztywno — Z zawsze jedzie
      pierwsza, dopiero po dojechaniu do zera rusza XY, niezależnie od
      skonfigurowanej kolejności bazowania. Wcześniej ryzyko kolizji
      (XY przed Z na tej maszynie) nie było złagodzone — teraz jest.
      **Poprawka jeszcze nie zweryfikowana na fizycznym sterowniku.**
      Szczegóły: `zmiany/jedz-do-zera.md`
- [x] Siła/prędkość zależne od pozycji — sprawdzone: *Conditional Torque
      Limiting* w serwie (ClearView) + `TrqGlobal` z API
- [x] Siła per operacja w programie technologa — kolumna MOMENT, format 4
      `.prg`; jak profile, dziś tylko zapis w pliku
- [ ] **`accel`/`decel` z `config/profiles.json` nie są wysyłane do mostka**
      (znalezione 2026-09-09 przy zgłoszeniu zbyt wolnego cyklu) — realne
      przyspieszenie to zawsze jedna globalna wartość `ACC_RPM_PER_SEC`
      z `bridge/machine.env`, nie per-oś/per-profil. Wymaga rozszerzenia
      protokołu `AXCFG` (C++, mostek) o przyspieszenie. Do czasu naprawy:
      pola `accel`/`decel` na ekranie `/profiles` **nic nie robią** na
      sprzęcie. Szczegóły: `sterownik-sc4-hub.md` (sekcja „Limity
      prędkości/przyspieszenia").
- [ ] Soft limits w silniku jako warstwa dodatkowa (wymagają bazowania)
- [ ] Ruchy head-tail dla zagłębiania w Z; ruchy asymetryczne — propozycja
      z pytaniami do decyzji w `propozycja-head-tail-asymetria.md`,
      świadomie niezaimplementowane bez ustalenia z Tobą
- [x] Prowadzenie za rękę + baza nazwanych punktów PTP — **zrobione
      2026-09-07** w zakresie technicznie osiągalnym: prawdziwy tryb
      podatny (torque mode z hosta) okazał się **nieosiągalny na tym
      sprzęcie** (brak takiego API w SDK Teknica, potwierdzone wyczerpująco
      — `prowadzenie-za-reke.md`). Trzy iteracje przybliżenia: RELEASE/HOLD
      (działa, ale to zwykłe luzowanie) → niski TrqGlobal + doganianie
      (wywoływał twardy fault serwa pod realnym oporem, patrz
      `zmiany/reset-nie-czyscil-axisenabled.md`) → **finalnie: normalny
      limit momentu przez cały czas + wykrycie małej zmiany odczytu
      momentu względem spoczynku, jedno naciśnięcie = jeden krok JOG**
      (`hand_guide_step()`, ekran `/nauczanie`) — bez ryzyka faultu, bo
      TrqGlobal nigdy nie schodzi poniżej normalnej wartości.
      Osobno: baza punktów z pełnym CRUD (`/punkty`, `app/punkty.py`),
      picker punktów w operacji PUNKT edytora (jednorazowe wypełnienie
      X/Y/Z, bez trwałego wiązania po nazwie). **Zweryfikowane fizycznie
      2026-09-09: działa, ale nieintuicyjne i niestabilne** — zostaje na
      później do dostrojenia (szczegół problemu jeszcze nieokreślony).
      Progi doganiania dalej prowizoryczne. Szczegóły:
      `zmiany/baza-nazwanych-punktow.md`, `prowadzenie-za-reke.md`.

### D. Wrzeciono
- [x] Włączenie przy starcie maszyny — przełącznik na panelu operatora
- [x] Włączenie/wyłączenie na granicach programu technologa — dwie opcje
      na ekranie `/cycle` (do potwierdzenia, czy o te dwie chodziło)
- [ ] Sterowanie prędkością przez zewnętrzny regulator PWM, załączany
      wyjściem `BRAKE_0`/`BRAKE_1` (decyzja: patrz temat J)
- [ ] Konfiguracja rozpędzania/hamowania na regulatorze PWM

### E. Drzwi/osłona i uprawnienia
- [ ] Wejście sygnału drzwi (PWM/binarny), aktywne tylko w trybie auto —
      konkretny przepis na odczyt w kodzie (`cpm.InA`/`cpm.InB`):
      `przyklady-sdk-teknica.md` §5
- [x] Warstwa ról i logowania (admin/technolog/operator) — **osobne konta**
      (Twoja decyzja), `tools/konta.py`, dziennik zmian „kto co zmienił"
- [x] `POST /api/mes/select-order` — opcjonalny token `X-MES-Token`
      (`MES_TOKEN` w środowisku), domyślnie wyłączony, więc bez zmiany
      zachowania dopóki się go nie ustawi. **Włączenie na produkcji nie
      zrobione** — wymaga koordynacji z konfiguracją MES i restartu usługi.
      Szczegóły: `zmiany/token-mes.md`
- [ ] Przegląd obwodu bezpieczeństwa z osobą uprawnioną (CE) przed produkcją

### F. Tryby pracy — zrobione (ekran `/cycle` + panel operatora)
- [x] Manualny (martwy człowiek) — JOG na panelu reaguje na przytrzymanie
- [x] Półautomatyczny (jeden cykl) — istniał od etapu 3/4 tematu B
- [x] Automatyczny (pętla do STOP/błędu/utraty zezwolenia) + start/stop —
      drzwi jeszcze nie istnieją jako sygnał (temat E), zatrzyma się na tym,
      co już jest: STOP, błąd w kroku, utrata sygnału zezwolenia
- [x] **Wznowienie po alarmie bez ponownego bazowania** (2026-09-01,
      zgłoszone po pierwszym pełnym teście cyklu na sprzęcie) — `RESET` na
      już zbazowanej maszynie wraca do `READY`, nie wymusza `NOT_HOMED`
      (Global Stop na tym sprzęcie nie odcina zasilania serw, potwierdzone
      przez operatora). Żółte ostrzeżenie na panelu każe obejrzeć maszynę.
      Szczegóły: `zmiany/wznowienie-bez-bazowania.md`
- [~] **Częściowo naprawione (2026-09-01):** `RESET` nie zerował znacznika
      „oś załączona" w mostku (`axisEnabled[]`) — naprawione, ale ten sam
      błąd („Node @ 0 error ... Move blocked by drive shutdown/disable/
      limit", oś Z) **wystąpił ponownie po wdrożeniu**, tym razem głębiej
      w ruchu (bliżej celu cięcia). Nowa hipoteza: limit momentu podczas
      cięcia w materiale (testowane 5-8%, bardzo nisko) może wywoływać
      twardy fault na serwie, nie tylko łagodne zatrzymanie. **Wymaga
      fizycznej weryfikacji z wyższym limitem momentu** — nie do zrobienia
      zdalnie. Szczegóły: `zmiany/reset-nie-czyscil-axisenabled.md`

### G. Ekrany i programy
- [x] Ekran główny (nazwa poprawiona, miejsce na logo gotowe — czeka na plik)
- [x] Ekran diagnostyczny `/diagnostics` (admin) — stan, tryby pracy, przegląd
      konfiguracji, konta i sesje, dziennik zmian
- [x] Ekran definiowania operacji cyklu — `/cycle`, zrobione już w etapie 4
      tematu B (korekta listy, nie nowa praca)
- [x] „Zapisz jako" dla programów technologicznych

### H. Uruchomienie sprzętowe
Jedna sesja w ClearView (Windows) domyka pierwsze pięć pozycji:
- [x] Auto-Tune osi pod obciążeniem — **zrobiony fizycznie 2026-09-06**,
      pliki `.mtr` zapisane pod ustaloną nazwą (`os-X-...`, wg konwencji
      z `auto-tune-osi.md`). Wczytywanie `.mtr` na Linuksie okazało się
      **niepotrzebne**: kreator zapisuje wyniki strojenia bezpośrednio w
      nieulotnej pamięci samego nośnika ClearPath-SC, potwierdzone w SDK
      (`PT_CFG_T` w `mnParamDefs.h`) — szczegóły w `auto-tune-osi.md` §4.3.
- [ ] Homing HardStop + Offset Move — **zablokowane 2026-09-06**: HardStop
      wymaga dojazdu do fizycznego końca osi, a na tej maszynie po drodze
      można zaczepić o inne elementy. Czeka na przygotowanie dodatkowych
      blokad/ograniczników mechanicznych (Zbyszek), zanim da się to zrobić
      bezpiecznie. Bazowanie programowe (obecne rozwiązanie) zostaje w
      użyciu do tego czasu.
- [ ] Soft limits w silnikach
- [ ] Warunkowe limitowanie momentu (Move Done, Absolute Position)
- [ ] Wejścia A/B węzłów („Input Actions")
- [ ] Sprawdzić dostępność g-Stop (tłumienie drgań)

Pomiary i testy:
- [x] Zweryfikować cykl maszyny (`SC4HubMachine.start_cycle`) na sprzęcie —
      **2026-09-01, działa poprawnie.** Przy okazji znaleziony i naprawiony
      problem: wymuszone bazowanie po RESET, patrz temat F wyżej
- [ ] Weryfikacja pomiarowa toru `LINIA` + próba grup wyzwalania —
      `TriggerGroup`/`TriggerMovesInGroup` potwierdzone w naszym SDK,
      gotowy wzorzec: `przyklady-sdk-teknica.md` §6
- [ ] Zmierzyć domyślny watchdog sieciowy (czy w ogóle działa)
- [ ] Test: utrata zezwolenia w ruchu
- [x] Test: komunikacja przy E-stopie w spoczynku — **pierwsze realne
      zadziałanie E-stop na sprzęcie, 2026-09-01.** Global Stop nie odcina
      zasilania serw (sygnał logiczny), komunikacja działa. Znaleziona i
      naprawiona luka: utrata zezwolenia w spoczynku nie alarmowała (tylko
      cichy status), teraz alarmuje jak w ruchu. Szczegóły:
      `zmiany/alarm-w-spoczynku.md`. **Zostaje:** ten sam test w trakcie
      ruchu (osobna, nieprzetestowana pozycja wyżej)
- [x] **Naprawione (2026-09-01):** `POST /api/machine/stop` zwracał 500
      zamiast czytelnego błędu, gdy mostek odrzucił komendę — jedyny
      endpoint sterowania bez obsługi `MachineError`. Szczegóły:
      `zmiany/stop-nie-lapal-bledu.md`
- [ ] **Nowe, nienaprawione (znalezione 2026-09-01):** przy incydencie
      „Node @ 1 error" (błąd SDK na węźle osi X, przyczyna źródłowa
      nieustalona) `poll_status()` zaczął rzucać `MachineError` przy
      **każdym** kolejnym `STATUS` — `_poll_loop()` łapie to cicho
      (`contextlib.suppress`), więc panel zamroził się na starych danych
      na kilka minut, bez żadnego oznaczenia, że komunikacja z mostkiem
      jest zerwana. Potrzebny sygnał dla operatora (licznik nieudanych
      prób / pole `bridge_ok` w statusie / baner na panelu). Szczegóły:
      `zmiany/stop-nie-lapal-bledu.md`
- [ ] Sprawdzić komendę `OUTPUT` mostka na sprzęcie — **skompilowana i
      wdrożona od 2026-09-01** (kolejne rebuildy mostka przy okazji etapów
      0/2b), ale nikt jeszcze nie przełączył `BRAKE_0`/`BRAKE_1` naprawdę
- [ ] Test: czy USB re-enumeracja załącza `BRAKE_x` (bez wrzeciona!)
- [x] ~~Reguła udev — instalacja i weryfikacja~~ — potwierdzona działająca
      na hoście produkcyjnym 2026-08-30, patrz `sterownik-sc4-hub.md`
- [x] Obciążalność wyjść `BRAKE_0`/`BRAKE_1` — 500 mA / 24 VDC

### J. Skąd I/O — decyzja podjęta, drobiazgi zostają
- [x] Obciążalność `BRAKE_0`/`BRAKE_1` — **500 mA / 24 VDC**; użyć przekaźnika
      pośredniczącego, nie stycznika bezpośrednio
- [ ] **Bezpieczeństwo:** `BRAKE_x` → regulator wrzeciona **szeregowo przez
      obwód osłon** (system może przypadkowo załączyć wyjście)
- [ ] Osobne zasilanie 24 V do płytki SC4-HUB (warunek działania wyjść)
- [ ] Wybór konkretnego modelu zewnętrznego regulatora PWM do wrzeciona
- [x] **Wyjścia podpięte fizycznie** — komenda `OUTPUT` w mostku, krok
      `WYJSCIE` przełącza `BRAKE_0`/`BRAKE_1`; kod mostka nieskompilowany
      (brak SDK), do sprawdzenia na sprzęcie
- [x] Przeznaczenie drugiego wyjścia: definiowane w konfiguracji maszyny
      (temat B, `CycleStep`) — podajnik/wyrzutnik/lampka/błąd, konkretny
      wybór przy budowie tego ekranu; program technologa go nie używa

### K. Funkcje SMART (ruch z kontrolą siły)
Nowy temat — technolog wstawia „funkcję smart" po punkcie w programie;
procedurę pisze programista, technolog wybiera ją i podaje parametry.
Analiza, model danych i ryzyka: [`funkcje-smart.md`](funkcje-smart.md).
Potwierdzone u źródła: `IMotion::TrqMeasured` daje odczyt momentu (PCT_MAX).
Pętla musi być w mostku (C++) — Python nie może nic robić w trakcie ruchu.
Trzy poziomy: **procedura** (C++, programista) → **definicja SMART**
(nazwany zestaw parametrów, np. `SMART-sila`, własny ekran z „zapisz jako")
→ **użycie** (wiersz programu albo krok cyklu, z listy jak inne operacje).
Definicje wspólne dla programu technologa i cyklu maszyny.
- [x] Etap 0: `STATUS` z odczytem momentu (`TRQX/Y/Z`) + podgląd na panelu.
      **Działa na prawdziwym sprzęcie od 2026-08-31** — `torque_source:
      "sterownik"`, realne wartości. Symulator dalej podstawia wartości
      zmyślone, oznaczone jako „symulacja". SDK Teknica dostarczone trwale
      do `vendor/teknic/` na hoście. **Koszt próbkowania zmierzony
      (2026-09-01): ~7 ms na 3 osie** — 10 ms z materiału źródłowego
      nierealne, 20 ms (obecna pętla) ma na to miejsce. Etap 0 zamknięty
      w całości. Szczegóły: `zmiany/symulacja-momentu.md`
- [x] Etap 1: model definicji + `/api/smart` + **ekran `/smart`** (lista,
      edycja, „zapisz jako", usuwanie) — `zmiany/ekran-smart.md`
- [~] Etap 2: **ekran `/sila`** — zrobione: podgląd momentu na żywo, ręczna
      kalibracja siłomierzem (`config/kalibracja.json`), **wykres przebiegu
      momentu i prędkości w czasie z podziałem na operacje** (nagrywanie
      podczas uruchomienia, zostaje widoczne po fakcie — zgłoszone
      2026-09-01, bo na żywo dzieje się za szybko). **Zostaje:** automatyczna
      próba przejazdu (charakterystyka bazowa osi: tarcie, ciężar, oba
      kierunki, kilka prędkości) — świadomie odłożona, bo rusza maszyną i
      wymaga ustalenia profilu ruchu przy maszynie. Oś X pokazywała w
      spoczynku stały moment ok. -2.9%, podczas gdy Y/Z były bliskie zera —
      **wyjaśnione fizycznie 2026-09-09 (bez budowy automatycznej próby
      przejazdu):** napięcie śruby X, poprawa po smarowaniu, patrz
      `funkcje-smart.md`. Automatyczna próba przejazdu zostaje odłożona
      dalej jako osobny temat (charakterystyka tarcia/ciężaru osi), nie
      pilna z powodu tej konkretnej obserwacji. Pomiar częstotliwości
      próbkowania **zrobiony osobno, bez próby przejazdu** (patrz Etap 0
      wyżej) — nie wymagał ruchu. Szczegóły: `zmiany/ekran-sila.md`,
      `zmiany/przebieg-nagrywanie.md`
- [x] Etap 3: operacja `SMART` w `.prg` (format 5) + wybór z listy
      w edytorze — `zmiany/smart-w-programie-i-cyklu.md`. Na sprzęcie mostek
      **odmawia** wykonania (lepsze niż ruch bez kontroli siły), w symulatorze
      działa pozornie — na momencie zmyślonym, nie na pomiarze
- [x] Etap 4: krok `SMART` w cyklu maszyny (`/cycle`) — ta sama definicja
      i ta sama ścieżka wykonania co operacja w programie technologa
- [ ] Etap 5: procedura `ciecie_adaptacyjne` + `SMART`/`SMARTLIST` w mostku
      *(C++, wymaga `vendor/` i maszyny — tu zaczyna realnie działać)*
- [ ] Etap 6: kolejne procedury (`szukanie_kontaktu`, `miekki_docisk`,
      `detekcja_kolizji`)
- [ ] Etap 7 (opcjonalny): profil siły — jakość cięcia, zużycie noża

Dwa ryzyka z etapu 2 (ekran `/sila`):
- [x] **Zmierzone (2026-09-01):** odczyt `TrqMeasured` na 3 osiach kosztuje
      ~7 ms — 10 ms z materiału źródłowego nierealne, 20 ms wystarcza.
- [ ] **Do dobrania doświadczalnie:** przełożenie % momentu → siła na nożu
      (wzór ze źródła pomija sprawność śruby) — czeka na pierwsze pary
      w ekranie `/sila` (kalibracja siłomierzem już dostępna)

### L. Architektura wielu sterowników (drajwerów) osi
- [x] **Decyzja 2026-09-10: wszystkie osie z serwami SM45BL (docisk,
      podajnik, kolejne) mają być PEŁNOPRAWNE** — na równi z X/Y/Z, nie
      tylko sterowane z panelu. Podejście integracji zmienione na
      bezpieczniejsze: Feetech OBOK dzisiejszego kodu Teknika (X/Y/Z bez
      zmian w każdym etapie), nie jeden wspólny refaktor `Machine`. Pięć
      etapów rozpisanych w `architektura-wielu-drajwerow-osi.md` (status:
      status/odczyt → JOG → bazowanie → cykl maszyny → program technologa,
      etap 0 gotowy).
- [ ] **Propozycja spisana 2026-09-09** (część nadal otwarta): driver per
      oś zamiast jednej klasy `Machine` na cały sprzęt, pod moduł
      ClearCore (kroki + I/O). Cztery pytania do ustalenia przed
      kodowaniem tej części. Ustalone przy okazji:
      ClearCore to firmware do napisania od zera (Microchip Studio/
      Windows), nie gotowe SDK — drugi projekt w stylu `bridge/`.
- [x] **Materiały SM45BL dostarczone i przeanalizowane 2026-09-10** —
      **protokół OSTATECZNIE ustalony: to NIE Modbus RTU** (wcześniejsze
      dwa założenia, „gołe PWM" i „Modbus RTU", obie mylne) — SM45BL
      (seria SMBL) używa **tego samego protokołu co SMS/STS** (ramka jak
      Dynamixel Protocol 1.0), potwierdzone wprost w oficjalnym tutorialu
      producenta i w kodzie `FTServo_Python`. Odczyt pozycji/prędkości/
      **obciążenia**/napięcia/prądu/temperatury potwierdzony konkretnymi
      adresami rejestrów — oś nie jest „głucha". Narzędzie testowe
      poprawione pod właściwy protokół: `tools/test_feetech_servo.py`
      (nowe, główne), `tools/test_modbus_servo.py` zostaje jako zapasowe.
      Szczegóły: `architektura-wielu-drajwerow-osi.md`.
- [x] **Warstwa niska protokołu napisana 2026-09-10** (przed
      potwierdzeniem fizycznym, żeby nie czekać bezczynnie) —
      `server/app/feetech_protocol.py` (budowanie/parsowanie ramek
      PING/READ/WRITE, 11 testów bez sprzętu), `tools/test_feetech_servo.py`
      przepisany pod ten moduł + flaga `--read` (odczyt pozycji/prędkości/
      obciążenia/napięcia/temperatury po udanym PING). **Świadomie
      niezintegrowane z `Machine`** — czeka na test fizyczny i na
      rozstrzygnięcie pytań otwartych wyżej. Szczegóły:
      `zmiany/protokol-feetech.md`.
- [x] **Test łączności fizycznej — UDANY 2026-09-10.** Konwerter Waveshare
      SKU 15817 (USB↔RS232/RS485/TTL) na `/dev/ttyUSB0`, jedno serwo
      SM-45BL-C001 (ID:1, 115200 wg etykiety), zasilanie 24VDC. PING
      zwrócił poprawną ramkę (`ff ff 01 02 00 fc`), odczyt statusu
      sensowny: napięcie 23,0V (przy zasilaniu 24VDC), temperatura 27°C,
      pozycja/prędkość/obciążenie 0 (spoczynek). **Protokół natywny SMS
      potwierdzony fizycznie**, nie tylko z dokumentacji. Po drodze:
      dwa serwa naraz na ID:1 nie odpowiadały (kolizja magistrali) —
      potwierdzona potrzeba zmiany ID przed łączeniem obu razem (patrz
      FAQ producenta). Szczegóły debugowania: `zmiany/protokol-feetech.md`.
- [x] **ID drugiego serwa zmienione 2026-09-10** —
      `tools/test_feetech_servo.py --set-id` (nowa flaga: odblokuj EPROM →
      zapisz ID → zablokuj → PING pod nowym ID). Oba serwa podłączone
      razem, bez kolizji: **ID 1 = docisk** (pozycja 4094, 23,1V, 23°C),
      **ID 2 = podajnik** (pozycja 0, 23,0V, 27°C) — nazwy zgodne z osiami
      dodanymi wcześniej w `config/axes.json`. Szczegóły debugowania:
      `zmiany/protokol-feetech.md`.
- [x] **`FeetekDriver` napisany i test ruchu wykonany 2026-09-10** —
      `server/app/feetech_driver.py` (ping/read/write/move_to, 18 testów
      bez sprzętu). Pierwszy realny ruch obu serw na maszynie
      (`tools/feetech_jog.py`, operator obserwował fizycznie) i
      **kierunek CW/CCW zmierzony**: serwo 1 (docisk) — CW = malejąca
      pozycja; serwo 2 (podajnik) — CW = rosnąca pozycja. Zapisane jako
      `DIRECTION_SIGN_CW` + `move_relative_cw()`. Pomiar dla serwa 2 miał
      jedną sprzeczną, odrzuconą próbę po drodze (do potwierdzenia
      ponownie przy integracji) — szczegóły: `zmiany/protokol-feetech.md`.
- [x] **Etap 1 integracji (status) zrobiony 2026-09-10** — `Machine`
      odpytuje `docisk`/`podajnik` (`config/axes.json`: `driver: feetech`,
      `feetech_id`), `GET /api/status` zwraca pozycję/obciążenie (jednostki
      rejestru, nie mm — kalibracja to etap 2). Osobna pętla, niezależna od
      X/Y/Z, zweryfikowana end-to-end na sprzęcie. **Panel pokazuje to
      wizualnie** (dopisane tego samego dnia — poprawka stale'j notatki
      wyżej). Szczegóły: `zmiany/status-osi-feetech.md`.
- [x] **Etap 2 — JOG bez mm, zrobiony 2026-09-11** (decyzja: „robimy
      serwa bez montowania na maszynie"): `POST /api/machine/jog-feetech`
      + przyciski na panelu, ruch w kierunku zgodnym/przeciwnym do zegara
      (nie mm — to wciąż niewiadome, wymaga zamontowania). Przy okazji
      naprawiony błąd współbieżności (magistrala RS485 współdzielona
      z pętlą statusu, teraz `_feetech_lock`iem). Zweryfikowane fizycznie,
      oba serwa, oba kierunki. Szczegóły: `zmiany/jog-feetech.md`.
- [x] **Naprawiony błąd 2026-09-11: zapis z ekranu `/axes` kasował
      `driver: feetech`.** Odkryte przez zauważenie zmiany na dysku, nie
      zgłoszenie — `docisk`/`podajnik` wróciły po zapisie `vel_jog` do
      `driver: teknic`. Przyczyna i naprawa (drugi raz ten sam wzorzec
      błędu, co dla pól bazowania): `zmiany/driver-feetech-znikal-po-zapisie-osi.md`.
- [x] **Etap 2 dokończony 2026-09-11: przeliczenie mm.** Serwa fizycznie
      zamontowane (`mm_per_rev` w `config/axes.json` zmierzone: docisk
      1.0, podajnik 8.0 mm/obr) — `position_to_mm()` (`feetech_driver.py`,
      `COUNTS_PER_REV=4096` wg karty katalogowej), `_read_feetech_status()`
      dolicza `position_mm` obok surowego rejestru, panel operatora
      pokazuje oba. **Bez bazowania** — mm liczone od fabrycznego zera
      enkodera, nie od zera obszaru roboczego; znak nieujednolicony między
      osiami. Szczegóły: `zmiany/przeliczenie-mm-osie-feetech.md`.
- [x] **Prędkość/przyspieszenie serwa konfigurowalne, 2026-09-11**
      (zamówienie: „sprawdź czy możemy definiować prędkość serwa w
      konfiguracji osi" + „daj podpowiedź ustawianych zakresów"):
      `AxisConfig.feetech_speed`/`feetech_acc` (dawne stałe 100/20 z
      `feetech_driver.py` — teraz per oś, edytowalne z ekranu `/axes`, tylko
      dla osi ze sterownikiem feetech). Zakresy potwierdzone u źródła
      (`zbyszek/Tabela pamięci... .xlsx`): przyspieszenie 0-1000 pewne
      (100 kroków/s²/jedn.), górna granica prędkości NIE w pełni
      potwierdzona (przyjęty konserwatywny sufit 1000, do weryfikacji).
      Szczegóły: `zmiany/predkosc-serwa-feetech-w-konfiguracji.md`.
- [x] **Etap 4 zaimplementowany 2026-09-11: osie FEETECH pełnoprawne w
      cyklu maszyny** (zamówienie: „dodaj serwa Feetech do cykli Maszyny
      jako pełnoprawne serwo"). Krok `RUCH` z celem na `docisk`/`podajnik`
      rusza fizycznie oś i CZEKA na koniec ruchu (rejestr `MOVING`), zamiast
      kończyć się błędem „dziś tylko X/Y/Z". `Machine.feetech_move` —
      wstrzyknięty callback z `main.py`, `Machine` nadal nie zna
      `FeetekDriver`/RS485 wprost (zasada „Feetech obok, nie w środku"
      zachowana). **Bez bazowania (etap 3, wciąż niezrobiony)** — pozycja w
      mm liczy się od fabrycznego zera enkodera, nie zera obszaru
      roboczego; nie testowane jeszcze fizycznie w pełnym cyklu na
      maszynie. Szczegóły: `zmiany/feetech-w-cyklu-maszyny.md`.
- [ ] **Zostaje z etapów FEETECH:** bazowanie (etap 3), ew. program
      technologa (etap 5) — patrz `architektura-wielu-drajwerow-osi.md`.
- [x] **Moduły I/O Modbus RTU Waveshare — oba moduły zweryfikowane
      fizycznie, 2026-09-11** (zamówienie: „to nasze I/O, zbuduj
      standardowy moduł"): SKU 26244 (cyfrowy 8DI/8DO, adres 1) i SKU
      25821 (analogowy, adres 2 — zmieniony z fabrycznego 1, żeby uniknąć
      kolizji z modułem cyfrowym) na TEJ SAMEJ magistrali co serwa, ale
      **prawdziwy Modbus RTU** (nie protokół FEETECH), osobne połączenie
      (9600 baud, nie 115200). `modbus_protocol.py` + `modbus_driver.py`,
      26 testów, w tym CRC16 zweryfikowane niezależnie względem przykładu
      z instrukcji producenta. **Mapa rejestrów obu modułów POTWIERDZONA
      FIZYCZNIE**: cyfrowy — zapis coil 0 → ON + obserwacja diody DO0;
      analogowy — 8 kanałów odczytanych poprawnie (naprawiony przy okazji
      błąd `_exchange()` obcinający dłuższe odpowiedzi). Szczegóły:
      `zmiany/modbus-io-waveshare.md`.
- [x] **Nazwane kanały I/O + watchdog, zaimplementowane 2026-09-11**
      (zamówienie: lista sygnałów LG/LR/LY/osłona_1/drzwi_podajnika/
      Start/Stop/wrzeciono_OUT/wrzeciono_start/wrzeciono-stop/
      temperatura_wrzeciona/prąd_wrzeciona/drzwi_impulsy, odczyt co ~1s,
      watchdog na `drzwi_impulsy` współpracujący z `osłona_1`,
      włącz/wyłącz w konfiguracji): `app/io_modbus.py`
      (`IoConfig`/`ChannelConfig`/`WatchdogConfig`, `default_io()`, 11
      testów), pętla w tle w `main.py`, `GET/PUT /api/io-modbus`,
      `POST /api/machine/io-modbus/write`. **Przypisanie sygnałów do
      konkretnych kanałów DO/DI/AI to na razie założenie kolejności, nie
      potwierdzone okablowanie** — do weryfikacji przy podłączeniu.
      Watchdog domyślnie wyłączony, nie testowany jeszcze na prawdziwym
      sygnale. Szczegóły: `zmiany/io-modbus-nazwane-kanaly.md`.
- [x] **Ekran `/io-modbus`, zbudowany 2026-09-11** (zamówienie: „zbuduj
      ekran do podglądu I/O"): podgląd na żywo DI/DO/AI (odpytywanie co
      1s), status watchdogu, ręczne przełączanie wyjść, edycja etykiet
      kanałów i ustawień watchdogu (jeden zapis). `ROLE_ADMIN` jak
      `/zuzycie`. Szczegóły: `zmiany/ekran-io-modbus.md`.

### M. Analiza zużycia osi/narzędzia i powiadomienia o incydentach
- [x] **Krok 1-2 zaimplementowane 2026-09-10:** zbieranie zużycia osi
      (dystans per oś, moment śr./maks. tam, gdzie mierzony na sprzęcie)
      po każdym zakończonym przebiegu, bez dużych baz danych — szczegóły
      tylko z bieżącej doby (`config/zuzycie/YYYY-MM-DD.jsonl`), trwały
      trend bez limitu czasowego, jedna linia per oś per dzień aktywności
      (`config/zuzycie/trend.jsonl`). Decyzja 2026-09-10: alarmy na
      poziomie maszyny, ale e-mail i zgłoszenia do modułu FAP wysyła
      **wMES**, nie nasz serwer — zdejmuje ryzyko nowego sekretu SMTP i
      kontraktu API wychodzącego do MES. Szczegóły:
      `zmiany/zuzycie-osi-zbieranie.md`, pełna analiza:
      `analiza-zuzycia-osi.md`.
- [x] **Krok 3 zaimplementowany 2026-09-10:** ekran `/zuzycie` — tabela
      „dzisiaj" per oś (przebiegi, dystans, moment śr./maks.) i wykresy
      trendu (słupkowe, jeden per oś, małe wielokrotności). **Dziś tylko
      X/Y/Z** — osie FEETECH jeszcze nie wliczane do zużycia (osobna
      praca, przecięcie tematów L i M). Szczegóły: `zmiany/ekran-zuzycia-osi.md`.
- [x] **Krok 4 zaimplementowany 2026-09-10:** definicje alarmów zużycia
      wzorem `/smart` (`app/zuzycie_alarmy.py`, `GET/PUT
      /api/zuzycie/alarmy`, CRUD na ekranie `/zuzycie` — podniesionym do
      `require_admin` z tego powodu) — oś + metryka (dystans/moment maks.)
      + okres (dzień/tydzień) + próg. Ocena po każdym zakończonym
      przebiegu (ten sam punkt co zapis danych), stan tylko w pamięci
      procesu (nietrwały). **Bez wysyłki powiadomień** — to robi wMES.
      Zweryfikowane end-to-end na produkcji (zapis/odczyt/sprzątanie przez
      `curl`), 23 nowe testy. Szczegóły: `zmiany/ekran-zuzycia-osi.md`.
- [ ] **Krok 5 odłożony 2026-09-11 (decyzja operatora):** integracja z
      wMES czeka na ustalenie dostępu/wymagań z tamtą stroną — nie do
      zgadnięcia bez tej rozmowy. `GET /api/zuzycie/alarmy` już istnieje
      jako częściowy fundament. Ewentualnie osobno: rozszerzenie zbierania
      zużycia o osie FEETECH (nieustalone, nie w pierwotnym planie kroków).

### I. Odłożone
- [ ] `LUK`/`OKRAG`/`POLILINIA` w `.prg`
- [ ] GRBL/G-code jako alternatywa

## W trakcie

*(pusto)*

## Zrobione

Skrót — pełne opisy w [`README.md`](README.md) i [`zmiany/`](zmiany/):

- [x] **Temat A zamknięty** — nazwy w kodzie: `SC4HubMachine`,
      `MACHINE_MODE=sc4hub`, `BRIDGE_HOST`/`BRIDGE_PORT` (stare nazwy
      dalej działają)
- [x] Format `.prg` — operacje grupy A (`PROSTOKAT`, `SZYBKI`, `WRZECIONO`)
- [x] Parametry operacji: `POSUW`, `PRZEJSCIA`, `PRZYROST` (format 2)
- [x] Mostek `bridge/` (SC4-Hub przez sFoundation) — pełny cykl na sprzęcie
- [x] Ekran konfiguracji osi (`/axes`) + plik `config/axes.json`
- [x] Przebudowa edytora technologa (pola zależne od operacji, podgląd toru)
- [x] Jeden poller statusu, STOP w trakcie ruchu, komunikaty alarmu
- [x] Luzowanie osi (zdjęcie momentu do ręcznego przestawiania)
- [x] Narzędzia USB SC4-Hub (przypięcie do sterownika Exar)
- [x] Skrót na pulpicie + generator PDF dokumentacji
- [x] Środowisko testowe VS Code (Windows/Linux)
- [x] Scalenie dokumentacji SC4-Hub (`README.md`, `docs/ARCHITEKTURA.md`) i
      usunięcie `firmware/clearcore/`
