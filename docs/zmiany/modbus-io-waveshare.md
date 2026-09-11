# Sterownik Modbus RTU dla modułów I/O Waveshare (temat L)

Standardowy moduł do obsługi dwóch modułów I/O na magistrali RS485 współ-
dzielonej z serwami FEETECH: **SKU 26244** (Modbus RTU IO 8CH, cyfrowy
8DI/8DO) i **SKU 25821** (Modbus RTU Analog Input 8CH, 12-bit). Budowa
analogiczna do `feetech_protocol.py`/`feetech_driver.py`, ale to
**prawdziwy Modbus RTU**, nie protokół własny — inna ramka, inny
baudrate (9600, nie 115200), więc osobne połączenie (`ModbusDriver`),
mimo wspólnej magistrali fizycznej z serwami.

Zamówione przez użytkownika 2026-09-11: „to podłączam fizycznie te dwa
moduły i będą to nasze I/O — zbuduj standardowy moduł wykorzystania w
naszych programach".

## Pliki

- `server/app/modbus_protocol.py` — budowanie ramek (read coils/discrete
  inputs/holding/input registers, write single coil/register), CRC16,
  parsowanie odpowiedzi (w tym wyjątki Modbus, bit błędu 0x80). Adresy
  rejestrów modułu **analogowego** (`ADDR_ANALOG_CHANNELS`,
  `ADDR_ANALOG_DATA_TYPE`, `ADDR_DEVICE_ADDRESS`, `ADDR_UART_PARAMS`,
  `ADDR_SOFTWARE_VERSION`) — z instrukcji producenta.
- `server/app/modbus_driver.py` — `ModbusDriver`: port przez `termios`
  (jak `FeetekDriver`), context manager, odczyty/zapisy ogólne (coils,
  discrete inputs, holding/input registers) + `read_analog_channels()`
  wysokopoziomowe dla modułu analogowego.
- `server/tests/test_modbus_protocol.py` — 14 testów, w tym **CRC16
  zweryfikowane niezależnie względem przykładu z instrukcji producenta**
  (`01 04 00 00 00 08` → `F1 CC`).
- `server/tests/test_modbus_driver.py` — 8 testów `ModbusDriver` na
  podstawionym `_exchange`, bez portu.
- `tools/test_waveshare_io.py` — test łączności: `--analog` (potwierdzony
  odczyt 8 kanałów), `--digital-probe` (sondowanie modułu cyfrowego kilkoma
  typowymi próbami, bo mapa jego rejestrów nie jest potwierdzona).

## Co jest potwierdzone, a co nie

**Potwierdzone u źródła** (instrukcja producenta modułu analogowego,
zweryfikowane też niezależnie przeliczeniem CRC16 — nie tylko
zaufaniem podsumowaniu): odczyt 8 kanałów analogowych to funkcja 0x04
(Read Input Registers) pod adresami 0x0000-0x0007; rejestr typu/zakresu
per kanał pod 0x1000+kanał; adres urządzenia pod 0x4000; parametry UART
pod 0x2000. Domyślnie: adres 1, 9600 N81, zakres 0-20mA.

**Częściowo potwierdzone empirycznie 2026-09-11**, moduł cyfrowy (SKU
26244) fizycznie podłączony, `tools/test_waveshare_io.py --digital-probe`
na adresie fabrycznym 1:
- `read_holding_registers(0x4000, 1)` → **`[1]`** — zgadza się z
  rzeczywistym adresem urządzenia. **Silny dowód**, że ten moduł dzieli
  ten sam układ rejestrów konfiguracyjnych co moduł analogowy (0x2000
  UART, 0x4000 adres, 0x8000 wersja) — nie tylko przypuszczenie.
- `read_coils(addr=0, count=8)` → `[False]*8`, bez błędu — prawdopodobnie
  8 wyjść cyfrowych (DO0-DO7), wszystkie wyłączone (zgodne z rzeczywistością
  — nic nie było załączone).
- `read_discrete_inputs(addr=0, count=8)` → `[False]*8`, bez błędu —
  prawdopodobnie 8 wejść cyfrowych (DI0-DI7).
- `read_holding_registers(0x1000, 1)` → `[0]` — rejestr istnieje i się
  czyta, znaczenie dla TEGO modułu (w analogowym to typ/zakres kanału)
  jeszcze niezinterpretowane.

**Wciąż nie w 100% pewne:** odczyt bez błędu potwierdza, że coś sensownie
odpowiedziało pod tymi adresami/funkcjami — nie potwierdza jeszcze
JEDNOZNACZNIE, że to naprawdę DO/DI (a nie np. martwe/nieużywane
rejestry, które akurat też zwracają zera bez wyjątku). Pełne
potwierdzenie wymaga zapisu (`write_single_coil`) i obserwacji fizycznego
efektu (dioda na module) — `ModbusDriver` celowo **nie ma** jeszcze
wysokopoziomowych metod dla tego modułu (`read_digital_*`), tylko ogólne
`read_coils`/`read_discrete_inputs`/`write_single_coil`.
- **Dokładne bajty poleceń zmiany adresu/baudrate modułu analogowego** —
  instrukcja podała przykłady (`00 06 40 00 00 02 10 1A` itd.), ale
  **niezależne przeliczenie CRC16 dla tych konkretnych przykładów NIE
  zgodziło się** (wyszło `1C 1A`/`42 1B`, instrukcja podawała `10
  1A`/`42 18`) — podejrzenie błędu przepisania/OCR w źródle podsumowania,
  nie w naszym CRC16 (który zgodził się dokładnie dla przykładu
  odczytu). **Nie używać tych dwóch przykładów zmiany adresu/baudrate
  bez ponownej weryfikacji** — sam adres rejestru (0x4000, 0x2000) jest
  prawdopodobnie poprawny, forma polecenia (funkcja 0x06 write single
  register) też, ale dokładne bajty danych/CRC wymagają potwierdzenia
  przed wysłaniem do prawdziwego urządzenia.

## Uwagi

- **Kolizja adresów jak przy serwach 2026-09-10:** oba moduły fabrycznie
  mają prawdopodobnie adres 1 — podłączenie obu naraz przed zmianą
  adresu jednego z nich powtórzy dokładnie ten sam problem co z dwoma
  serwami na ID 1. `tools/test_waveshare_io.py` ostrzega o tym wprost.
- **Świadomie NIE zintegrowane jeszcze z `Machine`/cyklem/programem** —
  to warstwa protokołu i sterownik magistrali, testowalna bez sprzętu.
  Integracja („nasze programy" z prośby użytkownika — prawdopodobnie
  krok `WYJSCIE` w cyklu, może operacje `.prg`) to następny krok, po
  fizycznym potwierdzeniu na sprzęcie i ustaleniu, do czego konkretnie
  mają służyć te I/O (który wyjście/wejście do czego).
- **Nie zweryfikowane fizycznie** — użytkownik dopiero podłącza moduły w
  trakcie tej rozmowy. `tools/test_waveshare_io.py` czeka na uruchomienie
  na sprzęcie.
