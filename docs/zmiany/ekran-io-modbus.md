# Ekran podglądu I/O Modbus

Ekran `/io-modbus`: podgląd na żywo stanu DI/DO/AI obu modułów Waveshare
(temat L, [[io-modbus-nazwane-kanaly]]), status watchdogu, ręczne
przełączanie wyjść cyfrowych, edycja etykiet kanałów i ustawień watchdogu.

## Pliki

- `server/app/static/io-modbus.html` — trzy tabele stanu (DI/DO/AI, DO z
  przyciskiem „przełącz"), pasek statusu watchdogu, sekcja konfiguracji
  (etykiety + watchdog) z jednym przyciskiem zapisu.
- `server/app/static/io-modbus.js` — odpytywanie `GET /api/io-modbus` co
  1s (dane z pętli w tle serwera, nie odczyt na żądanie), zapis przez
  `POST /api/machine/io-modbus/write` (pojedyncze wyjście) i
  `PUT /api/io-modbus` (cała konfiguracja naraz).
- `server/app/main.py` — trasa `GET /io-modbus` (`_page`, `ROLE_ADMIN` —
  jak `/zuzycie`, bo ekran ma też edycję wymagającą admina, nie tylko
  podgląd).
- `server/app/static/index.html`, `diagnostics.html`, `zuzycie.html`,
  `sesja.js` — odnośniki do nowego ekranu, wpis w mapie ról paska sesji.

## Uwagi

- Podgląd korzysta z tej samej danej co `_io_modbus_poll_loop` (odświeżenie
  raz na sekundę z tyłu) — nie wymusza dodatkowego odczytu magistrali przy
  każdym otwarciu ekranu.
- Przypisanie etykiet edytowalne z ekranu — pierwsza okazja do skorygowania
  założonego mapowania sygnałów na kanały bez ręcznej edycji JSON.
- Nie testowane jeszcze fizycznie z aktywnym watchdogiem na prawdziwym
  sygnale `drzwi_impulsy` — do zrobienia przy podłączeniu tego wejścia.
