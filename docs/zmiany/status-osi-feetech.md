# Status osi FEETECH na panelu — etap 1 integracji (temat L)

Pierwszy krok integracji `FeetekDriver` z resztą aplikacji: `Machine`
odczytuje pozycję i obciążenie skonfigurowanych osi FEETECH (`docik`,
`podajnik`) i wystawia je w `GET /api/status`. **Bez ruchu** — to tylko
odczyt, zero zmiany zachowania dla X/Y/Z. Zweryfikowane end-to-end na
fizycznym sprzęcie (oba serwa podłączone razem).

## Pliki

- `server/app/axes.py` — `AxisConfig` dostaje pola `driver` (`teknic` |
  `feetech`, domyślnie `teknic`) i `feetech_id`; walidacja (X/Y/Z nie mogą
  być `feetech`, ID w zakresie 0-253, wymagane dla `feetech`). Nowa funkcja
  `feetech_axes()` — `{nazwa osi: ID serwa}` dla skonfigurowanych osi.
- `server/app/machine.py` — `MachineStatus.feetech_raw`: `{nazwa osi:
  {"position": int, "load": int}}`, jednostki REJESTRU (nie mm — kalibracja
  w etapie 2), włączone do `to_dict()`.
- `server/app/feetech_driver.py` — `FeetekDriver.read_position_and_load()`:
  jeden odczyt (6 bajtów, rejestry 56-61) zamiast trzech osobnych, żeby
  ograniczyć liczbę rund tam-i-z-powrotem przy odpytywaniu wielu serw.
- `server/app/main.py` — `_feetech_poll_loop()`: osobna pętla, ~1s cyklu
  (odczyt po termios to rząd 0,1-0,3s na oś, nie mieści się w budżecie
  200ms pętli X/Y/Z), niezależna od `MACHINE_MODE` (RS485 to osobny kanał
  fizyczny, może być podłączony razem z symulatorem X/Y/Z). Blokujące I/O
  przez `asyncio.to_thread()`, żeby nie zamrażać reszty serwera. `config.py`:
  `FEETECH_PORT`/`FEETECH_BAUD` (domyślnie 115200).
- `config/axes.json` — `docik` → `driver: feetech, feetech_id: 1`,
  `podajnik` → `driver: feetech, feetech_id: 2` (zgodnie ze zmierzonym
  wcześniej przypisaniem ID).
- `server/tests/test_axes.py` — 9 testów walidacji `driver`/`feetech_id`
  i `feetech_axes()`.
- `server/tests/test_feetech_driver.py` — test `read_position_and_load()`.

## Uwagi

- **Dane surowe, nie mm.** `feetech_raw` pokazuje jednostki rejestru
  serwa (0-4095 na obrót) — przeliczenie na mm przez `mm_per_rev` i
  uwzględnienie kierunku (`DIRECTION_SIGN_CW`, `zmiany/protokol-feetech.md`)
  to etap 2, celowo nie zrobione tutaj.
- **Izolacja od X/Y/Z.** Osobna pętla (`_feetech_poll_loop`), osobny błąd
  nie wpływa na `_poll_loop` (X/Y/Z) — sprawdzone przez `except Exception:
  pass` na całej pętli i per-oś `try/except FeetekError` w
  `_read_feetech_status`, żeby jedno milczące serwo nie ukryło odczytu
  z pozostałych.
- **Zweryfikowane end-to-end 2026-09-10** — pełny serwer (TestClient),
  `MACHINE_MODE=sim` + prawdziwy `FEETECH_PORT=/dev/ttyUSB0`, oba serwa
  podłączone: `GET /api/status` zwrócił realną pozycję/obciążenie obu osi.
- Panel (`index.html`/`app.js`) **jeszcze nie pokazuje** `feetech_raw` —
  dane są w API, ale nie ma jeszcze widoku. Do zrobienia, jeśli chcesz to
  widzieć na ekranie, nie tylko przez API.
