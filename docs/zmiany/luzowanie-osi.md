# Luzowanie osi

Zdejmowanie momentu z serwa, żeby dało się przestawić oś ręcznie — każda oś
osobno albo wszystkie na raz. Dostępne z panelu operatora i przez API.

## Pliki

- `bridge/sc4hub_bridge.cpp` — komendy `RELEASE`/`HOLD <X|Y|Z|ALL>`, pole
  `REL=` w odpowiedzi `STATUS`, załączanie momentu per oś zamiast hurtem.
- `server/app/machine.py` — `set_released()`, `released_axes` w statusie,
  blokada ruchu na zluzowanej osi; `home()` waliduje synchronicznie.
- `server/app/main.py` — `POST /api/machine/release`; `home()` jest teraz
  awaitowane.
- `server/app/static/index.html`, `app.js`, `style.css` — sekcja „Luzowanie
  osi" z czterema przyciskami i wyraźnym oznaczeniem stanu.
- `server/tests/test_api.py` — 5 testów luzowania.

## Zachowanie

- `RELEASE`/`HOLD` działają **także w stanie ALARM** — po alarmie operator
  często potrzebuje właśnie zluzować oś, żeby ruszyć nią ręcznie.
- Odrzucane w trakcie ruchu maszyny (`RUNNING`, `HOMING`).
- Zluzowana oś **nie jest po cichu dociskana** przy komendzie ruchu — JOG,
  bazowanie i START odmawiają z czytelnym komunikatem, dopóki oś nie zostanie
  zaciśnięta. Zaskoczenie operatora byłoby tu groźniejsze niż niewygoda.
- Zaciśnięcie (`HOLD`) wymaga sygnału zezwolenia, bo załącza moment.
  Zluzowanie nie wymaga — to odebranie energii.

## Poprawiony błąd

`POST /api/machine/home` wywoływał `asyncio.create_task(machine.home())`
wewnątrz `try/except MachineError`. Zadanie startuje dopiero po powrocie
z endpointu, więc wyjątek **nigdy nie trafiał do `except`** — bazowanie
zawsze zwracało `200`, a błąd ginął jako nieobsłużony wyjątek zadania.
Operator naciskał „Bazowanie" przy braku zezwolenia i nie dostawał żadnej
informacji. Teraz `home()` waliduje synchronicznie i sam uruchamia ruch
w tle, a endpoint go awaituje.

## Ustalenie sprzętowe

**Enkoder liczy dalej przy zluzowanej osi.** Po ręcznym przestawieniu pozycja
zmienia się i utrzymuje, bez dryfu na postoju. Zero nie jest gubione, więc po
zaciśnięciu nie trzeba bazować od nowa.

## Uwagi

- **Oś pionowa bez hamulca opadnie** po zluzowaniu. SC4-Hub ma dwa wyjścia
  hamulca (`BRAKE_0`, `BRAKE_1`) z trybem `BRAKE_AUTOCONTROL`, który zwalnia
  hamulec razem z załączeniem odpowiadającego węzła — do wykorzystania przy
  zabudowie mechaniki. Ostrzeżenie jest widoczne w panelu.
- Przetestowane na gołych serwach. Zachowanie z obciążoną mechaniką
  (opadanie, hamulce) nieprzetestowane.
