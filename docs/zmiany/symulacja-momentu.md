# Symulacja momentu osi

Status maszyny niesie obciążenie osi (`torque`, % momentu maksymalnego) razem
z informacją, **skąd ta liczba pochodzi** (`torque_source`). Symulator wylicza
ją z własnego, zmyślonego modelu; parser odczytu ze sterownika (`TRQX/Y/Z`)
jest gotowy. Dzięki temu ekrany i funkcje SMART dało się zbudować przed pracą
przy maszynie (etap 0 tematu K).

**Stan (2026-08-31): DZIAŁA na prawdziwym sprzęcie.** Pakiet SDK dostarczony
(pobrany ze strony Teknica), mostek skompilowany i uruchomiony ponownie.
`GET /api/status` na hoście produkcyjnym zwraca realny pomiar, np.
`"torque": {"x": 1.2, "y": 0.1, "z": -2.7}, "torque_source": "sterownik"`.
Etap 0 tematu K jest zamknięty. Historia blokady kompilacji i jej
rozwiązania — niżej, zostawione jako zapis dla przyszłych rebuildów mostka.

## Pliki

- `server/app/machine.py` — pola `torque`/`torque_source` w `MachineStatus`;
  model `SIM_TRQ_*` i metody `_sim_torque`/`_update_sim_torque` w symulatorze;
  odczyt `TRQX/TRQY/TRQZ` ze `STATUS` w `SC4HubMachine.poll_status`.
- `server/app/static/index.html` — sekcja „Obciążenie osi [% momentu]”.
- `server/app/static/app.js` — wyświetlanie obciążenia i **źródła** danych.
- `server/app/static/style.css` — klasa `.msg.warn` (żółta): ostrzeżenie,
  które nie jest alarmem maszyny.
- `server/tests/test_smart_uzycie.py` — testy oznaczania źródła i asymetrii Z.
- `bridge/sc4hub_bridge.cpp` — `openHardware()`: `TrqUnit(PCT_MAX)` ustawiony
  raz na każdym węźle po mapowaniu osi; `statusLine()`: dopisane pola
  `TRQX=.. TRQY=.. TRQZ=..` z `Motion.TrqMeasured.Value()`, zerowe gdy port
  niepodłączony.
- `bridge/sc4hub_bridge` — binarka przebudowana i wdrożona 2026-08-31.
- `vendor/teknic/` (poza gitem, `.gitignore`) — pakiet SDK Teknica
  (`Linux_Software.tar.gz`, pobrany ze strony producenta), rozpakowany
  trwale na hoście produkcyjnym, żeby kolejny rebuild mostka nie wymagał
  ponownego pobierania.

## Historia: blokada kompilacji i jak ją rozwiązano (2026-08-31)

Pierwsza próba `make -C bridge` (bez `vendor/teknic/`) kończyła się:

```
sc4hub_bridge.cpp:36:10: fatal error: pubSysCls.h: No such file or directory
```

Na hoście była zainstalowana **tylko biblioteka runtime**
(`/usr/local/lib/libsFoundation20.so*`, metoda „Systemwide Install" —
patrz `docs/sterownik-sc4-hub.md`), **nie było nagłówków SDK**
(`inc/inc-pub/pubSysCls.h` i reszta). Wcześniej pobrany pakiet
`Linux_Software.tar.gz` trafił do scratchpada sesji (`/tmp`) i przepadł przy
restarcie maszyny (`tmpfs` — patrz „Pułapka 3" w `sterownik-sc4-hub.md`).

Rozwiązanie: użytkownik pobrał `Linux_Software.tar.gz` ponownie ze strony
Teknica (przeglądarką, na tym samym mini PC), plik trafił do
`~/snap/firefox/common/Downloads/` (Firefox jest snapem — **nie** do
zwykłego `~/Downloads`, którego na tym koncie w ogóle nie ma). Rozpakowany
do `vendor/teknic/` (`tar -xzf` zewnętrznego archiwum, potem `tar -xf
sFoundation.tar` środka) — to rozwiązuje na trwałe punkt „Do zrobienia" z
`docs/sterownik-sc4-hub.md` o trzymaniu SDK na maszynie.

**Błąd przy rebuildzie, odnotowany żeby się nie powtórzył:** `make -C
bridge` nadpisało plik binarny **w miejscu, gdzie stary mostek już
działał** (proces sprzed przebudowy, PID wciąż żywy) — powinien być
najpierw `sudo systemctl stop motion-controller-bridge.service`. Proces
przeżył nadpisanie i dalej poprawnie odpowiadał na `STATUS`, ale to był
przypadek, nie gwarancja — nadpisywanie w locie mapowanego pliku
wykonywalnego jest niezdefiniowanym zachowaniem. **Przy każdym kolejnym
rebuildzie mostka: najpierw zatrzymać usługę, dopiero potem `make`.**

Po restarcie usługi (`sudo systemctl restart
motion-controller-bridge.service`) — z koniecznym ponownym bazowaniem, bo
restart mostka resetuje stan do `NOT_HOMED` — `torque_source` zaczął
zwracać `"sterownik"` z realnymi wartościami.

**Wciąż niezrobione:** zmierzenie kosztu próbkowania `TrqMeasured` przy
trzech osiach (ryzyko 3 z `funkcje-smart.md`) — możliwe teraz, że odczyt
działa, ale nikt jeszcze tego nie zmierzył.

## Uwagi

- **Liczby z symulatora są wymyślone.** Nie pochodzą z pomiaru ani z
  dokumentacji Teknica — model to moment postojowy + opór rosnący z
  prędkością + asymetria grawitacyjna osi Z + dodatek za skrawanie rosnący
  z głębokością. Panel pokazuje to wprost („źródło: SYMULACJA”), a
  `torque_source` pozwala odróżnić to od pomiaru w każdym miejscu kodu.
  **Progów siły nie wolno na tym dobierać** — do tego jest pomiar na maszynie
  i ekran `/sila` (etapy 0 i 2 tematu K).
- Gdy pól `TRQ*` nie ma w `STATUS`, źródłem jest `brak`, a panel pokazuje
  kreski. Świadomie: zera udające pomiar byłyby gorsze niż pusty wskaźnik.
- `TrqUnit(PCT_MAX)` w kodzie mostka **niepotwierdzone wykonaniem na
  sprzęcie** — dopiero kompilacja i uruchomienie na maszynie to zweryfikuje.
  Nazwa metody i stała `PCT_MAX` pochodzą z cytatu w `funkcje-smart.md`
  (`S-FoundationRef.chm`), nie z bezpośredniego build-a przeciw nagłówkom.
