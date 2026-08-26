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
- [ ] Zaprojektować `Axis`, `ParameterProfile`, `CycleStep`, `PartProgram`, `Operation`
- [ ] Warstwa cyklu maszyny (podawanie → bazowanie/docisk → program detalu → przywrócenie → wyrzut)
- [ ] Mechanizm snapshot/restore parametrów osi (z obsługą błędu/przerwania)
- [ ] Ekran definiowania ruchów cyklu + operacja „skok do podprogramu technologa"

### C. Osie i konfiguracja ruchu
- [ ] Dodatkowe osie w `/axes` (podajnik, docisk z kontrolą momentu)
- [ ] Bazowanie bez krańcówek + przycisk „HOME wszystkich osi" + ekran bazowania
- [ ] Siła trzypoziomowa (globalna / cykl / program technologa)
- [ ] Prędkości max i robocze (roboczy / bazowanie / JOG) per oś
- [ ] Siła/prędkość konfigurowalne per krok programu
- [ ] Siła per operacja w programie technologa

### D. Wrzeciono
- [ ] Włączenie przy starcie maszyny (przełącznik)
- [ ] Włączenie przy starcie programu (dwie opcje konfigurowalne)
- [ ] Sterowanie prędkością przez PWM
- [ ] Włącz/wyłącz na osobnym porcie I/O
- [ ] Konfiguracja rozpędzania/hamowania PWM

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
- [ ] Auto-Tune osi pod obciążeniem (Windows/ClearView)
- [ ] Homing w ClearView
- [ ] Weryfikacja pomiarowa toru `LINIA`
- [ ] Test: utrata zezwolenia w ruchu
- [ ] Test: komunikacja przy E-stopie
- [ ] Reguła udev — instalacja i weryfikacja
- [ ] Obciążalność wyjść `BRAKE_0`/`BRAKE_1`

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
