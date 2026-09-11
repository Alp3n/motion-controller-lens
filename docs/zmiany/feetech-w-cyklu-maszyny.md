# Osie FEETECH pełnoprawne w cyklu maszyny (etap 4)

Zamówienie 2026-09-11: „dodaj serwa Feetech do cykli Maszyny jako
pełnoprawne serwo". Krok `RUCH` cyklu (`docs/model-cyklu-maszyny.md`) mógł
dotąd celować wyłącznie w X/Y/Z — cel na `docisk`/`podajnik` kończył się
błędem „oś nie jest obsługiwana (dziś tylko X/Y/Z)". Teraz krok `RUCH` z
celem na osi ze sterownikiem `feetech` rusza fizycznie tę oś i **czeka**,
aż serwo naprawdę dojedzie, zanim cykl przejdzie do następnego kroku.

## Architektura — zachowana zasada „Feetech obok, nie w środku"

`Machine` (symulator i mostek SC4-Hub) nadal nic nie wie o `FeetekDriver`
ani o RS485 — dostaje tylko wstrzyknięty callback `self.feetech_move:
Callable[[str, float], Awaitable[None]] | None`, ustawiany przez
`main.py` na `_feetech_cycle_move()`. To jedyny szew; `_resolve_move_targets()`
(wspólna metoda w `Machine`, używana przez oba `_run_cycle_step_body`) po
prostu rozdziela cele kroku `RUCH` na „idzie do `feetech_move`" i „zostaje
na starej ścieżce X/Y/Z" po sprawdzeniu `AxisConfig.driver`.

## Pliki

- `server/app/machine.py` — `Machine.__init__`: pole `feetech_move`.
  `Machine._resolve_move_targets()`: nowa wspólna metoda (dawniej ten sam
  kod był powielony w symulatorze i mostku) — sprawdza `_check_soft_limit`
  dla KAŻDEJ osi (feetech też), woła `feetech_move` i CZEKA na nią, zanim
  zwróci resztę celów. Oba `_run_cycle_step_body` (symulator, mostek)
  używają teraz tej metody zamiast powielonej pętli.
- `server/app/feetech_driver.py` — `FeetekDriver.wait_until_stopped()`:
  odpytuje rejestr `MOVING` (ten sam sprawdzony wzorzec co
  `tools/feetech_jog.py`), zamiast zgadywać czas z prędkości.
- `server/app/main.py` — `_feetech_move_to_and_wait()` (blokujące, jak
  `_feetech_jog`, ale pozycja ABSOLUTNA + czeka na koniec ruchu) i
  `_feetech_cycle_move()` (async, przelicza mm→rejestr odwrotnością
  `position_to_mm()`, woła powyższe pod `_feetech_lock`). Wstrzyknięte do
  `machine.feetech_move` przy starcie procesu, bezwarunkowo (niezależnie
  od `MACHINE_MODE` — RS485 to osobny fizyczny kanał).
- `server/tests/test_cycle.py` — 3 testy: ruch osi feetech przez callback
  (z resztą X/Y/Z liczoną normalnie), brak wstrzykniętego callbacku →
  czytelny alarm (nie cichy pomijanie osi), limit programowy sprawdzany
  PRZED wywołaniem `feetech_move` (błędny cel nie rusza fizycznie serwem).
- `server/tests/test_feetech_cycle_move.py` — 4 testy `_feetech_cycle_move()`
  z podstawionym `FeetekDriver` (przeliczenie mm→rejestr, nieznana oś, brak
  portu, timeout oczekiwania na koniec ruchu).

## Uwagi — ważne ograniczenia

- **Bez bazowania (etap 3, wciąż niezrobiony).** Pozycja docelowa [mm] w
  kroku `RUCH` dla osi feetech liczy się od fabrycznego zera enkodera
  serwa (magnes), NIE od zera obszaru roboczego maszyny — dokładnie ten
  sam kompromis co w `zmiany/przeliczenie-mm-osie-feetech.md`. Jeśli serwo
  kiedykolwiek zostanie ręcznie obrócone (np. przy konserwacji) bez
  ponownego wyzerowania, „stała pozycja" w cyklu przestanie odpowiadać
  rzeczywistości — **do rozstrzygnięcia przy etapie 3**.
- **Ruch blokuje krok cyklu do końca** (`wait_until_stopped`, domyślny
  timeout 10s) — krok `RUCH` z celem na osi feetech nie zwróci się,
  dopóki serwo się nie zatrzyma albo nie minie limit czasu (wtedy
  `MachineError`, cykl przechodzi w ALARM jak przy każdym innym błędzie
  kroku).
- **Nie testowane jeszcze fizycznie w pełnym cyklu na maszynie** —
  zweryfikowane w izolacji (testy jednostkowe z podstawionym sterownikiem).
  Pierwsze uruchomienie z prawdziwym `docisk`/`podajnik` w kroku `RUCH`
  cyklu wymaga obecności operatora przy maszynie.
- Kolejność wykonania w kroku (feetech vs X/Y/Z) jest dziś nieistotna — to
  dwie fizycznie niezależne magistrale, wykonują się sekwencyjnie w
  kolejności iteracji po `step.targets`, nie „jednocześnie".
