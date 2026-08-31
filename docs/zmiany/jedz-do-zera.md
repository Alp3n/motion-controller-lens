# Przycisk „JEDŹ DO ZERA"

Dojazd wszystkich osi do punktu zerowego po bazowaniu — zwykły ruch pozycyjny
do (0,0,0), **nie ponowne bazowanie**. Potrzebne, bo po JOG-u albo cyklu
maszyna stoi gdzie indziej niż zero, a operator chce się tam szybko wrócić.
Zgłoszone przy maszynie 2026-08-31.

## Pliki

- `server/app/machine.py` — `Machine.go_to_zero()` (abstrakcyjna);
  `SimulatedMachine.go_to_zero()`/`_do_go_to_zero()` — ruch grupami w
  kolejności z ekranu bazowania (`home_groups()`), bez wstępnego odjazdu Z
  w górę (w przeciwieństwie do `_do_home`); `SC4HubMachine.go_to_zero()` —
  serwer sam wysyła `MOVEZ`/`MOVEXY` do zera w tej samej kolejności, blokując
  na czas ruchu jak `home()`
- `server/app/main.py` — `POST /api/machine/go-to-zero` (`require_operator`,
  409 przy błędzie, wzorowane na `/api/machine/home`)
- `server/app/static/index.html` — przycisk pod „Bazowanie"/„Kasuj alarm"
- `server/app/static/app.js` — wywołanie endpointu, komunikat błędu w
  `#ctrl-msg` jak reszta sterowania
- `server/tests/test_homing.py`, `server/tests/test_sc4hub.py`,
  `server/tests/test_api.py` — wymóg stanu READY, kolejność ruchu w
  symulatorze i na mostku, odrzucenie pustej kolejności bazowania, limity
  programowe

## Uwagi

- **Wymaga stanu READY** (a nie tylko „nie NOT_HOMED") — odmawia też w
  trakcie RUNNING/PAUSED/HOMING/ALARM.
- **Ryzyko, nie złagodzone:** w przeciwieństwie do bazowania w symulatorze
  (`_do_home`, które zawsze najpierw podnosi Z) ten ruch **nie** podnosi Z
  przed przejazdem XY — jedzie dokładnie w kolejności skonfigurowanej na
  ekranie `/homing`. Na tej maszynie kolejność to X(1)→Y(2)→Z(3), więc XY
  jedzie do zera, zanim Z wróci na swoje. Jeśli w chwili naciśnięcia
  przycisku frez stoi nisko nad detalem albo oprzyrządowaniem, a zero XY nie
  jest bezpieczne przy tej wysokości Z, ten ruch tego nie wykryje — może
  dojść do kolizji. Do rozważenia: wymuszony odjazd Z przed XY, tak jak przy
  bazowaniu — świadomie tego NIE zrobiono, bo nie było to częścią zgłoszenia
  i zmieniłoby znaczenie „ta sama kolejność co bazowanie".
- Na sprzęcie X i Y zawsze jadą razem, jedną komendą `MOVEXY` — protokół
  mostka nie rusza nimi osobno. Jeśli w konfiguracji X i Y mają różny
  `home_order`, i tak trafiają do jednej komendy, wysłanej w miejscu
  pierwszej z nich w kolejności.
- Test end-to-end na fizycznym sterowniku **nie wykonany** — jak
  `SC4HubMachine.start_cycle` (`zmiany/cykl-na-sprzecie.md`), do zrobienia
  przy maszynie.
