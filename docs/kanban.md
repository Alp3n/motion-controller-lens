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
- [ ] Etap 2b: moment i rampy do sprzętu — komenda w protokole mostka (C++,
      wymaga SDK i sprzętu)
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
      pozycyjny, nie ponowne bazowanie. **Ryzyko nie złagodzone:** nie
      podnosi Z przed ruchem XY, w przeciwieństwie do bazowania — możliwa
      kolizja przy niskim Z. Nie zweryfikowane na fizycznym sterowniku.
      Szczegóły: `zmiany/jedz-do-zera.md`
- [x] Siła/prędkość zależne od pozycji — sprawdzone: *Conditional Torque
      Limiting* w serwie (ClearView) + `TrqGlobal` z API
- [x] Siła per operacja w programie technologa — kolumna MOMENT, format 4
      `.prg`; jak profile, dziś tylko zapis w pliku
- [ ] Soft limits w silniku jako warstwa dodatkowa (wymagają bazowania)
- [ ] Ruchy head-tail dla zagłębiania w Z; ruchy asymetryczne — propozycja
      z pytaniami do decyzji w `propozycja-head-tail-asymetria.md`,
      świadomie niezaimplementowane bez ustalenia z Tobą

### D. Wrzeciono
- [x] Włączenie przy starcie maszyny — przełącznik na panelu operatora
- [x] Włączenie/wyłączenie na granicach programu technologa — dwie opcje
      na ekranie `/cycle` (do potwierdzenia, czy o te dwie chodziło)
- [ ] Sterowanie prędkością przez zewnętrzny regulator PWM, załączany
      wyjściem `BRAKE_0`/`BRAKE_1` (decyzja: patrz temat J)
- [ ] Konfiguracja rozpędzania/hamowania na regulatorze PWM

### E. Drzwi/osłona i uprawnienia
- [ ] Wejście sygnału drzwi (PWM/binarny), aktywne tylko w trybie auto
- [x] Warstwa ról i logowania (admin/technolog/operator) — **osobne konta**
      (Twoja decyzja), `tools/konta.py`, dziennik zmian „kto co zmienił"
- [ ] `POST /api/mes/select-order` dalej bez uwierzytelnienia — token dla MES
      albo ograniczenie sieciowe, do zrobienia osobno
- [ ] Przegląd obwodu bezpieczeństwa z osobą uprawnioną (CE) przed produkcją

### F. Tryby pracy — zrobione (ekran `/cycle` + panel operatora)
- [x] Manualny (martwy człowiek) — JOG na panelu reaguje na przytrzymanie
- [x] Półautomatyczny (jeden cykl) — istniał od etapu 3/4 tematu B
- [x] Automatyczny (pętla do STOP/błędu/utraty zezwolenia) + start/stop —
      drzwi jeszcze nie istnieją jako sygnał (temat E), zatrzyma się na tym,
      co już jest: STOP, błąd w kroku, utrata sygnału zezwolenia

### G. Ekrany i programy
- [x] Ekran główny (nazwa poprawiona, miejsce na logo gotowe — czeka na plik)
- [x] Ekran diagnostyczny `/diagnostics` (admin) — stan, tryby pracy, przegląd
      konfiguracji, konta i sesje, dziennik zmian
- [x] Ekran definiowania operacji cyklu — `/cycle`, zrobione już w etapie 4
      tematu B (korekta listy, nie nowa praca)
- [x] „Zapisz jako" dla programów technologicznych

### H. Uruchomienie sprzętowe
Jedna sesja w ClearView (Windows) domyka pierwsze pięć pozycji:
- [ ] Auto-Tune osi pod obciążeniem
- [ ] Homing HardStop + Offset Move
- [ ] Soft limits w silnikach
- [ ] Warunkowe limitowanie momentu (Move Done, Absolute Position)
- [ ] Wejścia A/B węzłów („Input Actions")
- [ ] Sprawdzić dostępność g-Stop (tłumienie drgań)

Pomiary i testy:
- [ ] Zweryfikować cykl maszyny (`SC4HubMachine.start_cycle`) na sprzęcie
- [ ] Weryfikacja pomiarowa toru `LINIA` + próba grup wyzwalania
- [ ] Zmierzyć domyślny watchdog sieciowy (czy w ogóle działa)
- [ ] Test: utrata zezwolenia w ruchu
- [ ] Test: komunikacja przy E-stopie
- [ ] Sprawdzić komendę `OUTPUT` mostka na sprzęcie (napisana, nieskompilowana)
- [ ] Test: czy USB re-enumeracja załącza `BRAKE_x` (bez wrzeciona!)
- [ ] Reguła udev — instalacja i weryfikacja
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
- [~] Etap 0: `STATUS` z odczytem momentu (`TRQX/Y/Z`) + podgląd na panelu.
      **Serwer i panel gotowe** (`zmiany/symulacja-momentu.md`); symulator
      podstawia wartości ZMYŚLONE, oznaczone w statusie jako „symulacja".
      **Zostaje C++:** dopisać `TRQ*` do odpowiedzi `STATUS` w mostku
      i zmierzyć koszt próbkowania *(maszyna)*
- [x] Etap 1: model definicji + `/api/smart` + **ekran `/smart`** (lista,
      edycja, „zapisz jako", usuwanie) — `zmiany/ekran-smart.md`
- [ ] Etap 2: **ekran `/sila` — kontrola siły i kalibracja**: podgląd na
      żywo, próba przejazdu (charakterystyka bazowa osi: tarcie, ciężar,
      oba kierunki, kilka prędkości), kalibracja siłomierzem, pomiar
      próbkowania, zapis `config/kalibracja.json`. Kod bez sprzętu,
      sensowne liczby po etapie 0
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

Dwa ryzyka domyka etap 2 (ekran `/sila`), zamiast zostawiać je otwarte:
- [ ] **Do zmierzenia na maszynie:** ile realnie kosztuje odczyt
      `TrqMeasured` i jak gęsto da się próbkować przy trzech osiach
- [ ] **Do dobrania doświadczalnie:** przełożenie % momentu → siła na nożu
      (wzór ze źródła pomija sprawność śruby)

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
