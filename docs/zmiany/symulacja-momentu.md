# Symulacja momentu osi

Status maszyny niesie obciążenie osi (`torque`, % momentu maksymalnego) razem
z informacją, **skąd ta liczba pochodzi** (`torque_source`). Symulator wylicza
ją z własnego, zmyślonego modelu; parser odczytu ze sterownika (`TRQX/Y/Z`)
jest gotowy. Dzięki temu ekrany i funkcje SMART dało się zbudować przed pracą
przy maszynie (etap 0 tematu K).

**Stan (2026-08-31): kod C++ w mostku napisany, ale NIESKOMPILOWANY** — patrz
sekcja „Blokada kompilacji" niżej. `bridge/sc4hub_bridge` na hoście
produkcyjnym dalej nie wysyła `TRQX/TRQY/TRQZ`, więc panel dalej pokazuje
kreski na prawdziwym sprzęcie.

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
  niepodłączony. **Napisane, nieskompilowane** (patrz niżej).

## Blokada kompilacji (2026-08-31)

Próba `make -C bridge` kończy się:

```
sc4hub_bridge.cpp:36:10: fatal error: pubSysCls.h: No such file or directory
```

Na hoście produkcyjnym jest zainstalowana **tylko biblioteka runtime**
(`/usr/local/lib/libsFoundation20.so*`, metoda „Systemwide Install" —
patrz `docs/sterownik-sc4-hub.md`), **nie ma nagłówków SDK**
(`inc/inc-pub/pubSysCls.h` i reszta). Wcześniej pobrany pakiet
`Linux_Software.tar.gz` trafił do scratchpada sesji (`/tmp`) i przepadł przy
restarcie maszyny (`tmpfs` — patrz „Pułapka 3" w `sterownik-sc4-hub.md`).
Katalogu `vendor/teknic/` na tym hoście **nie ma** — to ten sam otwarty punkt,
co w `docs/sterownik-sc4-hub.md` „Do zrobienia": zdecydować, czy trzymać
pakiet SDK trwale na maszynie (dla przyszłych `make -C bridge`), czy za
każdym razem pobierać go na nowo.

**Do zrobienia, żeby dokończyć etap 0:** dostarczyć pakiet
`Linux_Software.tar.gz` (albo sam katalog `inc/inc-pub`) w trwałe miejsce na
tej maszynie — najprościej `/opt/motion-controller-lens/vendor/teknic/`
(katalog już w `.gitignore`, matchuje ścieżkę z `Makefile`) — a potem
`make -C bridge`, zatrzymać `motion-controller-bridge.service`, podmienić
binarkę, wystartować z powrotem. Dopiero wtedy da się zmierzyć koszt
próbkowania `TrqMeasured` (ryzyko 3 z `funkcje-smart.md`).

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
