# Ostrzeżenie o braku MOMENT na operacji skrawającej

Operacja skrawająca (`PUNKT`/`LINIA`/`PROSTOKAT`) bez własnej wartości MOMENT
dziedziczy limit momentu z profilu aktualnie aktywnego w chwili wykonania —
a ten bywa różny (np. `globalny` przy uruchomieniu wprost vs profil kroku
cyklu, zwykle niższy). Zgłoszone przy maszynie 2026-09-02: ten sam program
działał poprawnie uruchomiony bezpośrednio, ale zawodził jako krok cyklu,
bo operacje nie miały ustawionego MOMENT (naprawione na maszynie ręcznie
przez wpisanie MOMENT=8 i przełączenie profilu kroku na `cykl`). Zamiast
wymuszać MOMENT (czasem poleganie na profilu jest zamierzone — szybkie,
płytkie operacje), technolog dostaje ostrzeżenie przy odczycie i zapisie
programu.

## Pliki

- `server/app/program.py` — nowa funkcja `torque_warnings(program)`, zwraca
  ostrzeżenie dla każdej operacji skrawającej bez `torque_pct`
- `server/app/main.py` — wynik `torque_warnings()` doklejony do pola
  `warnings` w `GET`/`PUT /api/programs/{number}`
- `server/tests/test_program.py` — testy: ostrzeżenie przy braku MOMENT,
  brak ostrzeżenia gdy ustawiony, brak ostrzeżenia dla operacji
  nieskrawających (`SZYBKI`, `WRZECIONO`)

## Uwagi

Front-end (`editor.js`) renderuje `warnings` generycznie — nie wymagał zmian.
