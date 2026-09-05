# Krok PROGRAM cyklu nie wraca już do (0,0)

Zgłoszone przy maszynie 2026-09-05: po zakończeniu programu detalu jako
kroku cyklu maszyny osie X/Y wracały do (0,0), zanim ruszał kolejny krok
cyklu — zbędny, powolny nawrót przez zero marnował czas taktu maszyny.

## Przyczyna

Powrót do (0,0) był wpisany na sztywno w `_run_operations()`
(`SimulatedMachine`) i `_run_program_operations()` (`SC4HubMachine`) —
funkcjach współdzielonych między samodzielnym uruchomieniem programu
(ekran operatora) a krokiem PROGRAM cyklu. Miało to sens przy
samodzielnym uruchomieniu (przewidywalna pozycja końcowa dla operatora),
ale w cyklu jest zbędne — zaraz po nim i tak jedzie następny krok, który
sam decyduje, dokąd ma pojechać.

## Naprawa

Powrót do (0,0) przeniesiony z `_run_operations`/`_run_program_operations`
do `_run_program()` (obie klasy) — czyli wykonuje się tylko przy
samodzielnym uruchomieniu programu, nigdy jako część kroku PROGRAM cyklu.

## Pliki

- `server/app/machine.py` — `SimulatedMachine._run_program`/
  `_run_operations`, `SC4HubMachine._run_program`/`_run_program_operations`.
- `server/tests/test_cycle.py` — nowy test
  `test_program_step_nie_wraca_do_zera` (symulator).
- `server/tests/test_sc4hub.py` — nowy test
  `test_cycle_program_step_nie_wraca_do_zera` (mostek).

## Uwagi

Zachowanie przy samodzielnym uruchomieniu programu (ekran operatora) jest
niezmienione — tam powrót do (0,0) nadal następuje po zakończeniu.
