# JOG serw FEETECH: tryb koła zamiast skoków pozycyjnych

Zgłoszenie operatora 2026-09-11: JOG `docisk`/`podajnik` jeździł "skokami",
a zmiana `feetech_speed` w konfiguracji osi nic nie dawała. Diagnoza:
każde przytrzymanie przycisku wysyłało nowy, BARDZO mały przejazd
pozycyjny (`FEETECH_JOG_STEP` — 30 jednostek rejestru, ~0,73% obrotu) co
250 ms — serwo zdążało rozpędzić się, dojechać i **zatrzymać** w ułamku
tego czasu, więc realnie stało bezczynnie większość każdego cyklu, a
"prędkość" rejestru nie miała szans wpłynąć na coś tak krótkiego.

Zamówienie: „musimy zmienić tryb, żeby serwo pracowało płynnie; na
ręcznym ma jechać do końca osi jak trzymam przycisk kierunku, jak puszczę
to ma się zatrzymać; w programie jedzie na pozycję z zakresu długości osi
[bez zmian]".

## Zmiana: tryb 1 serwa ("koło", stała prędkość)

Serwo SM45BL ma (poza dzisiejszym trybem 0 — pozycyjnym) tryb 1: ciągły
obrót sterowany samym rejestrem `GOAL_SPEED` (znak-magnituda, jak pozycja),
bez podawania celu — kręci się, aż zapiszesz prędkość 0 albo zmienisz
tryb. To właściwe narzędzie do "trzymaj = jedź, puść = stój" zamiast
powtarzanych mikro-przejazdów.

**RUCH cyklu zostaje bez zmian** — tryb 0 (pozycyjny), pozycja z zakresu
`soft_min`/`soft_max` osi, tak jak w `zmiany/feetech-w-cyklu-maszyny.md`.

## Pliki

- `server/app/feetech_protocol.py` — `MODE_POSITION`/`MODE_WHEEL` (adres
  `ADDR_MODE`, z tabeli pamięci producenta).
- `server/app/feetech_driver.py` — `set_mode()`, `wheel_speed_cw()`
  (ustawia tryb koła + prędkość ze znakiem, ten sam sens co
  `move_relative_cw`/`DIRECTION_SIGN_CW`), `wheel_stop()` (prędkość 0 +
  OD RAZU przywraca tryb pozycyjny). `move_to()` teraz OBRONNIE przywraca
  tryb pozycyjny przed każdym zapisem celu — RUCH cyklu i JOG nie muszą
  koordynować, kto ostatni zmienił tryb.
- `server/app/main.py`:
  - `_feetech_jog(servo_id, speed_cw)` — teraz woła `wheel_speed_cw`, nie
    `move_relative_cw`.
  - `_feetech_jog_stop(servo_id)` — woła `wheel_stop`.
  - `POST /api/machine/jog-feetech` — pozostaje jako HEARTBEAT
    (przeglądarka trzyma przycisk, wysyła co ~250ms); zamiast małego kroku
    ustawia prędkość ciągłą i przedłuża `_feetech_wheel_deadline[axis]`.
  - **Nowy** `POST /api/machine/jog-feetech/stop` — puszczenie przycisku,
    zatrzymuje NATYCHMIAST (nie czeka na strażnika).
  - `_feetech_wheel_stop_reason()` — czysta funkcja decydująca, czy oś ma
    się zatrzymać sama: `"watchdog"` (minął termin heartbeatu — dead man's
    switch, bo tryb koła nie ma go wbudowanego) albo `"limit"` (pozycja
    poza `soft_min`/`soft_max`).
  - `_feetech_poll_loop()` — gdy trwa JOG koła, odpytuje częściej (co
    150ms zamiast 1s) i pełni rolę strażnika: woła `_feetech_jog_stop`,
    jeśli `_feetech_wheel_stop_reason()` zwróci powód.
- `server/app/static/app.js` — `stopFeetechJog()` wysyła teraz jawny
  `POST /jog-feetech/stop` (dawniej tylko czyścił stan lokalny — z trybem
  koła serwo kręciłoby się dalej bez tego).
- `server/app/static/index.html`, `axes.html`, `axes.js` — zaktualizowane
  opisy (płynny ruch, auto-stop na limicie, `feetech_speed` używane przez
  JOG i RUCH).
- `server/tests/test_feetech_driver.py` — nowe testy `set_mode`,
  `wheel_speed_cw` (znak wg `DIRECTION_SIGN_CW`), `wheel_stop`, oraz
  poprawione istniejące testy `move_to`/`move_relative_cw` pod dodatkowy
  zapis trybu.
- `server/tests/test_feetech_jog.py` — przepisany pod nowy kontrakt: JOG
  jako heartbeat/prędkość, endpoint stop, `_feetech_wheel_stop_reason` w
  izolacji (watchdog, limit, brak konfiguracji/pozycji).

## Uwagi — ważne ograniczenia

- **Auto-stop na limicie to NAJLEPSZY WYSIŁEK, nie twardy limit.** Odczyt
  pozycji po RS485 trwa rzędu 0,1-0,3s (`_read_feetech_status`), a pętla
  strażnika przy aktywnym JOG odpytuje co 150ms — przy większych
  prędkościach (operator ustawił `feetech_speed=500` dla obu osi, co daje
  ok. 6 mm/s dla `docisk` przy jego skoku śruby 1 mm/obr) możliwy jest
  zauważalny naddźwig za limit, szczególnie na krótkich osiach: `docisk`
  ma tylko 7 mm zakresu programowego (-9..-2), więc naddźwig rzędu 1 mm to
  znacząca część całego zakresu. **Docelowa twarda ochrona to limity
  przejazdu skonfigurowane w samym serwie** (rejestry EPROM „najmniejszy/
  największy limit kąta" z tabeli pamięci producenta) — nieskonfigurowane
  jeszcze, wymaga osobnej pracy z fizyczną weryfikacją (jak zmiana ID czy
  pomiar kierunku CW). Do rozważenia jako następny krok, zwłaszcza dla
  `docisk` przy obecnej wysokiej prędkości.
- **Watchdog (0,6s) jest siecią bezpieczeństwa, nie głównym mechanizmem
  zatrzymania** — normalne puszczenie przycisku zatrzymuje przez jawny
  `/jog-feetech/stop`, natychmiast.
- Nie testowane jeszcze fizycznie na maszynie w tej sesji (brak dostępu do
  przeglądarki) — do zweryfikowania przy najbliższej obecności przy
  maszynie: płynność ruchu, zatrzymanie na puszczeniu przycisku,
  zachowanie przy zbliżaniu się do limitu.
