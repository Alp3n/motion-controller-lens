# Przycisk „JEDŹ DO ZERA"

Dojazd wszystkich osi do punktu zerowego po bazowaniu — zwykły ruch pozycyjny
do (0,0,0), **nie ponowne bazowanie**. Potrzebne, bo po JOG-u albo cyklu
maszyna stoi gdzie indziej niż zero, a operator chce się tam szybko wrócić.
Zgłoszone przy maszynie 2026-08-31.

## Pliki

- `server/app/machine.py` — `Machine.go_to_zero()` (abstrakcyjna);
  `SimulatedMachine.go_to_zero()`/`_do_go_to_zero()` i
  `SC4HubMachine.go_to_zero()` — kolejność bazowania z ekranu `/homing`
  służy tylko do ustalenia, które osie ruszyć (walidacja konfiguracji);
  kolejność RUCHU jest ustalona na sztywno: Z zawsze pierwsza, dopiero po
  dojechaniu do zera rusza XY. Na sprzęcie serwer sam wysyła `MOVEZ`, a
  dopiero po jego zakończeniu `MOVEXY`, blokując na czas ruchu jak `home()`
- `server/app/main.py` — `POST /api/machine/go-to-zero` (`require_operator`,
  409 przy błędzie, wzorowane na `/api/machine/home`)
- `server/app/static/index.html` — przycisk pod „Bazowanie"/„Kasuj alarm"
- `server/app/static/app.js` — wywołanie endpointu, komunikat błędu w
  `#ctrl-msg` jak reszta sterowania
- `server/tests/test_homing.py`, `server/tests/test_sc4hub.py`,
  `server/tests/test_api.py` — wymóg stanu READY, kolejność ruchu w
  symulatorze i na mostku (w tym: Z pierwsza niezależnie od kolejności
  bazowania), odrzucenie pustej kolejności bazowania, limity programowe

## Uwagi

- **Wymaga stanu READY** (a nie tylko „nie NOT_HOMED") — odmawia też w
  trakcie RUNNING/PAUSED/HOMING/ALARM.
- **Poprawione 2026-09-09 (decyzja operatora), wcześniej ryzyko nie
  złagodzone:** ruch szedł dokładnie w kolejności skonfigurowanej na ekranie
  `/homing` — na tej maszynie (X=1, Y=2, Z=3) oznaczało to XY przed Z, czyli
  możliwą kolizję, jeśli zero XY nie jest bezpieczne przy aktualnej wysokości
  Z. Teraz Z zawsze jedzie **pierwsza**, niezależnie od konfiguracji
  bazowania — dopiero po jej dojechaniu do zera rusza XY. Skonfigurowana
  kolejność bazowania nadal decyduje tylko o tym, **które** osie w ogóle
  biorą udział (żadna oś z `home_order=0` nie jest ruszana), nie o ich
  wzajemnej kolejności w tym ruchu.
- Na sprzęcie X i Y zawsze jadą razem, jedną komendą `MOVEXY` — protokół
  mostka nie rusza nimi osobno.
- Test end-to-end na fizycznym sterowniku **nie wykonany** — jak
  `SC4HubMachine.start_cycle` (`zmiany/cykl-na-sprzecie.md`), do zrobienia
  przy maszynie. **W szczególności ta poprawka (Z pierwsza) jeszcze nie
  potwierdzona fizycznie.**
