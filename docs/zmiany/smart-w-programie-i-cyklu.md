# SMART w programie technologa i w cyklu maszyny

Technolog może wstawić operację `SMART` po dowolnym punkcie programu
(format 5 pliku `.prg`, kolumna `SMART`), a admin — krok `SMART` w cyklu
maszyny. Oba wskazują tę samą definicję po nazwie, więc znaczą dokładnie to
samo. Etapy 3 i 4 tematu K.

## Pliki

- `server/app/program.py` — format 5 (`SMART` przed `UWAGI`), operacja
  `SMART`, walidacja kolizji kolumn, `smart_warnings()`.
- `server/app/cycle.py` — rodzaj kroku `STEP_SMART`, pole `smart`, walidacja,
  ostrzeżenie o nieznanej definicji.
- `server/app/smart.py` — `is_valid_name()` (wspólna reguła nazwy);
  `dojazd_mm` przyjmuje teraz wartość **ze znakiem** (kierunek osi).
- `server/app/machine.py` — `apply_smart()`, `_run_smart()` w symulatorze,
  obsługa operacji i kroku; `SC4HubMachine` **odmawia** wykonania SMART.
- `server/app/main.py` — definicje przekazywane do maszyny, ostrzeżenia
  o osieroconych nazwach w `/api/cycle`, `/api/smart` i przy zapisie programu.
- `server/app/static/editor.{html,js}` — kolumna SMART z listą definicji.
- `server/app/static/cycle.{html,js}` — krok SMART z listą definicji.
- `docs/FORMAT_PROGRAMU.md` — format 5 i operacja `SMART`.
- `server/tests/test_smart_uzycie.py` — 27 testów obu dróg użycia.

## Uwagi

- **Na maszynie to jeszcze nie działa.** Mostek nie zna komendy SMART, więc
  `SC4HubMachine` przerywa program/cykl czytelnym błędem. Świadomie: cichy
  przejazd bez kontroli siły wbiłby nóż w materiał z pełnym momentem, a
  operator zobaczyłby, że cykl „przeszedł”.
- **W symulatorze działa tylko pozornie.** `_run_smart` odtwarza kształt
  procedury (dojazd, zwolnienie, zatrzymanie na progu, cofnięcie), ale reaguje
  na moment zmyślony przez model symulatora i robi to w Pythonie — czyli tak,
  jak na maszynie zrobić się **nie da** (mostek nie oddaje sterowania w trakcie
  ruchu). Służy do sprawdzenia przepływu danych i ekranów.
- `dojazd_mm` zmieniło znaczenie: to dystans **ze znakiem**, domyślnie −5 mm,
  bo domyślną osią jest Z, a zagłębianie idzie w dół. Definicje zapisane
  wcześniej z wartością dodatnią pozostają poprawne — pojadą w górę.
- Brakująca definicja nie jest błędem pliku `.prg` ani cyklu, tylko
  ostrzeżeniem: plik jest samodzielny i może trafić na maszynę wcześniej niż
  definicja. Uruchomienie i tak przerwie się czytelnym błędem maszyny.
