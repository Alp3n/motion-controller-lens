# Nowe I/O (Modbus) w kroku WYJSCIE cyklu maszyny

Zamówienie 2026-09-12: „trzeba dodać nowe I/O do wykorzystania w cyklu
maszyny, zostaw dwa istniejące". Krok `WYJSCIE` cyklu sterował dotąd
wyłącznie dwoma stałymi wyjściami Teknica (`wyjscie_0`/`wyjscie_1`,
BRAKE_0/BRAKE_1 na SC4-Hub). Teraz ten SAM krok może też ustawiać
dowolny kanał DO modułu I/O Modbus Waveshare (lampy sygnalizacyjne,
`wrzeciono_OUT` i inne z ekranu [[ekran-io-modbus]]) — **obok**
dotychczasowych dwóch, bez zmiany ich zachowania.

Rozważona i odrzucona alternatywa (zgłoszona przez operatora): osobny
ekran „kroki dla I/O" + krok „skocz i wróć". Niepotrzebne — jeden krok
WYJSCIE już umie wskazać dowolne wyjście z listy, tak jak krok RUCH już
umiał ruszyć dowolną oś (patrz analogiczna decyzja w
[[ekran-cyklu-osie-dodatkowe]]).

## Architektura — ten sam wzorzec co `feetech_move`

`Machine.io_modbus_write: Callable[[str, bool], Awaitable[None]] | None`
— wstrzykiwany przez `main.py`, `Machine` nadal nie zna `ModbusDriver`/
RS485 wprost (zasada „obok, nie w środku"). Nowa wspólna metoda
`Machine._write_cycle_output_if_modbus(step)`: jeśli `step.output` NIE
jest jednym z `cycle.OUTPUT_NAMES`, woła callback i zwraca `True` (krok
obsłużony); inaczej `False` (wywołujący ma obsłużyć dwa wyjścia Teknica
po staremu — symulator: tylko status, mostek: komenda `OUTPUT`).

## Pliki

- `server/app/cycle.py` — `CycleStep.validate()` nie sprawdza już nazwy
  wyjścia względem zamkniętej listy `OUTPUT_NAMES` (cycle.py nie zna
  kanałów Modbus — ta konfiguracja żyje w `main.py`/`io_modbus.py`);
  wymaga tylko niepustej nazwy. Istnienie nazwy sprawdza teraz
  `warnings()` (nowy parametr `output_names`, domyślnie = `OUTPUT_NAMES`
  dla zgodności) — ten sam wzorzec co nieznana oś w kroku RUCH.
- `server/app/machine.py` — `Machine.io_modbus_write` (pole),
  `_write_cycle_output_if_modbus()` (wspólna metoda), oba
  `_run_cycle_step_body()` (symulator, mostek) wołają ją na początku
  obsługi `STEP_OUTPUT`.
- `server/app/main.py` — `_resolve_io_modbus_channel()` (nazwa kanału
  `do3` ALBO etykieta `LG` -> nazwa kanału; wydzielone z istniejącego
  `POST /api/machine/io-modbus/write`, reużywane w obu miejscach),
  `_io_modbus_cycle_write()` (wstrzykiwane do `machine.io_modbus_write`),
  `_cycle_output_names()` (zbiór do walidacji: `OUTPUT_NAMES` ∪ nazwy ∪
  etykiety kanałów DO). `GET /api/cycle` zwraca w polu `outputs` listę
  **nazw kanałów** (stabilne identyfikatory, nie etykiety — etykieta może
  się zmienić z ekranu `/io-modbus`) złączoną z dwoma wyjściami Teknica.
- `server/app/static/cycle.html`, `cycle.js` — dropдown „Wyjście" dostaje
  kanały Modbus; `outputLabel()` dociąga etykietę z nowo pobieranego
  `GET /api/io-modbus` (obok istniejącego `GET /api/outputs` dla Teknica).
  Poprawiony opis kroku WYJSCIE.
- `server/tests/test_cycle.py`, `test_sc4hub.py` — testy routingu (kanał
  Modbus nie wysyła komendy mostka i odwrotnie), walidacji/warnings,
  regresja komunikatu błędu dla brakującej nazwy wyjścia.
- `server/tests/test_io_modbus_cycle.py` — `_cycle_output_names()`,
  `_resolve_io_modbus_channel()` (po nazwie i etykiecie),
  `_io_modbus_cycle_write()` (sukces, nieznany kanał, brak portu, błąd
  sprzętu) — z podstawionym `ModbusDriver`.

## Uwagi

- Kanał Modbus ustawiony z kroku WYJSCIE **nie trafia** do
  `Machine.status.outputs` (to osobny system stanu tylko dla dwóch wyjść
  Teknica) — jego bieżący stan widać w `GET /api/io-modbus`
  (`_io_modbus_poll_loop`, odświeżenie ~1s), tak jak ręczne przełączenie
  z ekranu `/io-modbus`.
- W `step.output` zapisuje się to, co admin wybierze z listy — dziś to
  **nazwa kanału** (`do3`), nie etykieta, żeby zmiana etykiety na ekranie
  `/io-modbus` nie „osierociła" zapisanego kroku cyklu. `warnings()`
  akceptuje OBIE formy (na wypadek ręcznej edycji pliku JSON), ale ekran
  zawsze zapisuje nazwę kanału.
- Nie testowane jeszcze fizycznie na maszynie w tej sesji — do
  zweryfikowania przy najbliższej obecności przy niej.
