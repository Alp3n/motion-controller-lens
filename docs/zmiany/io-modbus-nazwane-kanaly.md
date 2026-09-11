# Nazwane kanały I/O Modbus + watchdog

Standardowy moduł do wykorzystania I/O modułów Waveshare (temat L,
patrz [[modbus-io-waveshare]] za protokół/sterownik niskiego poziomu) w
reszcie aplikacji: konfiguracja nazwanych kanałów (etykieta na kanał
DO/DI/AI), pętla odpytująca w tle i API do odczytu/zapisu po nazwie, plus
prosty mechanizm watchdog dla wejścia pulsującego.

## Pliki

- `server/app/io_modbus.py` — `IoConfig`/`ChannelConfig`/`WatchdogConfig`,
  `default_io()` (przypisania kanałów wg zgłoszonej listy sygnałów),
  `load()`/`save()` (JSON, zapis atomowy, wzorzec jak `outputs.py`).
- `server/app/config.py` — `MODBUS_IO_PORT` (domyślnie = `FEETECH_PORT`,
  ta sama magistrala fizyczna), `MODBUS_IO_BAUD` (9600), `IO_MODBUS_FILE`
  (`config/io_modbus.json`).
- `server/app/main.py` — `io_modbus_cfg` wczytywana przy starcie,
  `_read_io_modbus()`/`_io_modbus_poll_loop()` (odpytuje oba moduły co
  `watchdog.interval_s`, licząc czas od ostatniej zmiany kanału pulsu),
  zadanie tła w `lifespan()`, endpointy `GET/PUT /api/io-modbus`,
  `POST /api/machine/io-modbus/write`.
- `server/tests/test_io_modbus.py` — 11 testów: domyślne przypisania,
  roundtrip, odrzucenie nieznanego kanału, domyślny watchdog, wyszukiwanie
  po etykiecie, zapis/odczyt pliku.

## Przypisania kanałów (domyślne, `default_io()`)

Z prośby: `DO0=LG, DO1=LR, DO2=LY, DO3=wrzeciono_OUT, DO4=wrzeciono_start,
DO5=wrzeciono-stop` / `DI0=osłona_1, DI1=drzwi_podajnika, DI2=Start,
DI3=Stop, DI4=drzwi_impulsy` / `AI0=temperatura_wrzeciona,
AI1=prąd_wrzeciona`. Reszta kanałów pusta (`label=""`).

**To założenie kolejności, NIE potwierdzone fizyczne okablowanie.**
Moduł cyfrowy (adres 1) i analogowy (adres 2) same w sobie nie wiedzą, co
jest do nich podłączone — do potwierdzenia przez użytkownika przy
faktycznym podłączeniu sygnałów (lampy, drzwi, wrzeciono). Do tego czasu
`IoConfig` da się w pełni przeedytować przez `PUT /api/io-modbus` bez
zmiany kodu.

## Watchdog (diagnostyczny, NIE funkcja bezpieczeństwa)

Zasada: `pulse_channel` (domyślnie `di4` = `drzwi_impulsy`) powinien
zmieniać wartość co jakiś czas; jeśli nie zmienia się dłużej niż
`stale_after_s`, sygnał uznajemy za "zastały" — możliwy sygnał awarii
czujnika impulsów albo zablokowanych drzwi podajnika. Współpracuje z
`guard_channel` (domyślnie `di0` = `osłona_1`) tylko jako dodatkowy kontekst
w statusie, nie jako blokada ruchu.

Domyślnie **wyłączony** (`enabled=False`) — włącza się z poziomu
konfiguracji (`PUT /api/io-modbus`), zgodnie z prośbą "z możliwością
wyłączenia i włączenia w konfiguracji".

**Jak w całym projekcie: żadne wejście czytane tu programowo nie jest
certyfikowaną funkcją bezpieczeństwa** — realną warstwą bezpieczeństwa
pozostaje sprzętowy E-stop/Global Stop, niezależny od tego kodu.

## Uwagi

- Odczyt DO/DI/AI dzieje się jedną wspólną blokadą magistrali
  (`_feetech_lock` w `main.py`, który mimo nazwy chroni CAŁĄ współdzieloną
  magistralę RS485 — Feetech i Modbus razem), więc pętla I/O i pętla
  Feetech nie depczą sobie nawzajem w trakcie normalnej pracy usługi.
  Nie chroni to nadal przed ad-hoc skryptami spoza procesu serwera —
  patrz ta sama uwaga w [[modbus-io-waveshare]].
- Watchdog nie był jeszcze testowany fizycznie na prawdziwym sygnale
  `drzwi_impulsy`/`osłona_1` — tylko logika w izolacji (testy jednostkowe).
- Brak jeszcze osobnego ekranu do podglądu/konfiguracji tych kanałów w
  panelu — dziś tylko API (`GET/PUT /api/io-modbus`,
  `POST /api/machine/io-modbus/write`). Ekran to naturalny następny krok,
  do potwierdzenia.
