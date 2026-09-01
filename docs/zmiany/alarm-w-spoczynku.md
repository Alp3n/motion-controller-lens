# Alarm przy utracie sygnału zezwolenia w spoczynku

Zgłoszone przy maszynie 2026-09-01, przy pierwszym realnym zadziałaniu
E-stop/Global Stop na SC4-Hub: operator zobaczył tylko cichy status
„sygnał zezwolenia: BRAK — ruch zablokowany" na panelu — bez alarmu, bez
wymuszonego potwierdzenia. Utrata tego samego sygnału **w trakcie ruchu**
od dawna wywołuje prawdziwy alarm (`waitMoves()` w mostku,
`SimulatedMachine.set_safety_enable` w symulatorze) — luka była w
przypadku „maszyna stoi w spoczynku (READY/NOT_HOMED), a ktoś naciska
E-stop".

## Mechanizm

Zamiast budować osobny mechanizm powiadomień, zmiana **rozszerza istniejący
alarm** na przypadek spoczynku — panel, `ALARM: ...`, wymóg „Kasuj alarm"
(RESET) już istniały i działały, tylko nie były wyzwalane w tej sytuacji.

- **Mostek:** `statusLine()` (odpytywana co 200 ms niezależnie od ruchu)
  sprawdza teraz: jeśli `!safetyEnabled()` i stan to `READY` albo
  `NOT_HOMED`, wywołuje `setAlarm("utrata sygnału zezwolenia — sprawdź
  maszynę (E-stop/Global Stop)")`. Naturalne miejsce — to jedyny punkt
  odpytywany regularnie bez względu na to, czy coś się rusza.
- **Symulator:** `set_safety_enable()` rozszerzony z `(RUNNING, HOMING,
  PAUSED)` na wszystkie stany poza `ALARM`/`INIT` — dla READY/NOT_HOMED
  woła `_abort()` z osobnym komunikatem („sprawdź maszynę"), dla
  RUNNING/HOMING/PAUSED zostaje dotychczasowy („zatrzymanie awaryjne").

Po odzyskaniu sygnału **nic się nie dzieje automatycznie** — maszyna
zostaje w `ALARM`, dopóki operator nie zrobi „Kasuj alarm" (RESET).
Dzięki wcześniejszej zmianie (`zmiany/wznowienie-bez-bazowania.md`) RESET
na już zbazowanej maszynie wraca do `READY` z żółtym ostrzeżeniem
„obejrzyj maszynę", zamiast wymuszać pełne bazowanie — te dwie zmiany
składają się w spójną całość: czerwony alarm wymusza świadome
potwierdzenie, żółte ostrzeżenie przypomina o obejrzeniu maszyny już po
potwierdzeniu.

## Pliki

- `bridge/sc4hub_bridge.cpp` — sprawdzenie na początku `statusLine()`.
- `server/app/machine.py` — `SimulatedMachine.set_safety_enable()`
  rozszerzony o gałąź dla stanów spoczynkowych.
- `server/tests/test_homing.py` — pięć nowych testów: alarm w READY,
  alarm w NOT_HOMED, inny komunikat w RUNNING (bez regresji), brak alarmu
  po odzyskaniu sygnału, brak nadpisywania komunikatu przy powtórnej
  utracie w trakcie już trwającego alarmu.

## Uwagi

- **Nie dotyczy `INIT`** — przed otwarciem portu/połączeniem z mostkiem
  `safetyEnabled()` i tak zwraca `false` (brak `port`), więc bez wyłączenia
  tego przypadku każdy start aplikacji alarmowałby natychmiast.
- **Nie dotyczy `HOMING`** — bazowanie ma własną, dokładniejszą obsługę
  utraty zezwolenia w trakcie sekwencji (`doHome()` w mostku sprawdza to
  bezpośrednio w pętli `WasHomed()`, z osobnym komunikatem „w trakcie
  bazowania"). Rozszerzanie tu na `HOMING` dublowałoby to bez potrzeby.
- Nic nowego do przetestowania po stronie `SC4HubMachine` — parsowanie
  `STATE=ALARM`/`MSG=...` już działa ogólnie (`poll_status()`), mostek po
  prostu zaczyna z niego korzystać w nowej sytuacji. Test tej ścieżki
  wymagałby prawdziwego mostka (nie da się jej odtworzyć podstawionym
  `_exchange`), więc pokrycie jest tylko przez symulator.
- **Nie zweryfikowane fizycznie po tej konkretnej zmianie** — wdrożone po
  zgłoszeniu problemu, ale zanim operator zdążył ponownie sprawdzić
  zachowanie na sprzęcie. Do potwierdzenia: czy po zwolnieniu E-stop przy
  maszynie w spoczynku panel faktycznie pokazuje `ALARM: ... sprawdź
  maszynę` i czy „Kasuj alarm" poprawnie go czyści.
