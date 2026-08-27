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

### A. Nazewnictwo (ClearCore → SC4-Hub)
- [ ] Przejrzeć kod pod kątem `ClearCoreMachine`/`MACHINE_MODE=clearcore`
      (świadomie odłożone — osobny krok później)

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
- [ ] Etap 4: ekran definiowania cyklu + „skok do podprogramu technologa"

### C. Osie i konfiguracja ruchu
- [ ] Dodatkowe osie w `/axes` (podajnik, docisk z kontrolą momentu)
- [ ] Bazowanie HardStop + Offset Move + przycisk „HOME wszystkich osi"
      + ekran bazowania
- [ ] Siła trzypoziomowa (globalna / cykl / program technologa) —
      `ILimits.TrqGlobal`
- [ ] Prędkości max i robocze (roboczy / bazowanie / JOG) per oś
- [x] Siła/prędkość zależne od pozycji — sprawdzone: *Conditional Torque
      Limiting* w serwie (ClearView) + `TrqGlobal` z API
- [ ] Siła per operacja w programie technologa
- [ ] Soft limits w silniku jako warstwa dodatkowa (wymagają bazowania)
- [ ] Ruchy head-tail dla zagłębiania w Z; ruchy asymetryczne

### D. Wrzeciono
- [ ] Włączenie przy starcie maszyny (przełącznik)
- [ ] Włączenie przy starcie programu (dwie opcje konfigurowalne)
- [ ] Sterowanie prędkością przez zewnętrzny regulator PWM, załączany
      wyjściem `BRAKE_0`/`BRAKE_1` (decyzja: patrz temat J)
- [ ] Konfiguracja rozpędzania/hamowania na regulatorze PWM

### E. Drzwi/osłona i uprawnienia
- [ ] Wejście sygnału drzwi (PWM/binarny), aktywne tylko w trybie auto
- [ ] Warstwa ról i logowania (admin/technolog/operator)
- [ ] **Decyzja z Tobą:** PIN-y czy osobne konta
- [ ] Przegląd obwodu bezpieczeństwa z osobą uprawnioną (CE) przed produkcją

### F. Tryby pracy
- [ ] Manualny (martwy człowiek)
- [ ] Półautomatyczny (jeden cykl)
- [ ] Automatyczny (pętla do E-stop/drzwi) + start/stop

### G. Ekrany i programy
- [ ] Ekran główny (nazwa maszyny, logo WALKNER)
- [ ] Ekran diagnostyczny (admin)
- [ ] Ekran definiowania operacji cyklu
- [ ] „Zapisz jako" dla programów technologicznych

### H. Uruchomienie sprzętowe
Jedna sesja w ClearView (Windows) domyka pierwsze pięć pozycji:
- [ ] Auto-Tune osi pod obciążeniem
- [ ] Homing HardStop + Offset Move
- [ ] Soft limits w silnikach
- [ ] Warunkowe limitowanie momentu (Move Done, Absolute Position)
- [ ] Wejścia A/B węzłów („Input Actions")
- [ ] Sprawdzić dostępność g-Stop (tłumienie drgań)

Pomiary i testy:
- [ ] Weryfikacja pomiarowa toru `LINIA` + próba grup wyzwalania
- [ ] Zmierzyć domyślny watchdog sieciowy (czy w ogóle działa)
- [ ] Test: utrata zezwolenia w ruchu
- [ ] Test: komunikacja przy E-stopie
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
- [x] Przeznaczenie drugiego wyjścia: definiowane w konfiguracji maszyny
      (temat B, `CycleStep`) — podajnik/wyrzutnik/lampka/błąd, konkretny
      wybór przy budowie tego ekranu; program technologa go nie używa

### I. Odłożone
- [ ] `LUK`/`OKRAG`/`POLILINIA` w `.prg`
- [ ] GRBL/G-code jako alternatywa

## W trakcie

*(pusto)*

## Zrobione

Skrót — pełne opisy w [`README.md`](README.md) i [`zmiany/`](zmiany/):

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
