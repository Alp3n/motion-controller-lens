# Operacje PROSTOKAT, SZYBKI, WRZECIONO

Trzy nowe rodzaje operacji, wszystkie złożone z istniejących komend ruchu —
**bez zmian w mostku**. Format pliku awansuje do wersji 3.

## Pliki

- `server/app/program.py` — `OPERATIONS_HEADER_V3` z kolumną `OBROTY`,
  pole `rpm` w `Operation`, `CUTTING_TYPES`, funkcja `cut_path()`,
  walidacja parametrów per rodzaj operacji.
- `server/app/machine.py` — wykonanie nowych operacji w symulatorze
  i w trybie sprzętowym; wspólna ścieżka skrawania.
- `server/app/static/editor.js`, `editor.html` — nowe rodzaje w edytorze,
  kolumna „Obroty", rysowanie prostokąta i przejazdu szybkiego w podglądzie.
- `docs/FORMAT_PROGRAMU.md` — specyfikacja formatu 3.
- `server/tests/test_program.py` — 7 testów nowych operacji.

## Zachowanie

| Operacja | Działanie |
|---|---|
| `PROSTOKAT` | obrys po narożnikach przeciwległych `(X,Y)`–`(X2,Y2)`, tor zamyka się w punkcie startu; obsługuje przejścia na głębokość |
| `SZYBKI` | przejazd nad materiałem na `Z_BEZPIECZNE`; `POSUW` nadpisuje posuw dojazdu |
| `WRZECIONO` | ustawia obroty w trakcie programu; `OBROTY;0` wyłącza wrzeciono |

`LINIA` i `PROSTOKAT` wykonuje ten sam kod — różnią się tylko listą punktów
z `cut_path()`. Dzięki temu przejścia na głębokość, posuw operacji i wycofania
działają identycznie dla obu.

## Format 3

Doszła jedna kolumna: `OBROTY`, między `POSUW` a `PRZEJSCIA`. Świadomie osobna
kolumna zamiast doklejania obrotów do `POSUW` — przeciążanie znaczenia kolumn
mści się przy czytaniu pliku w Excelu.

Parser czyta formaty 1, 2 i 3; zapis idzie zawsze w najnowszym. Rozpoznawanie
nagłówka jest teraz sterowane słownikiem `SUPPORTED_FORMATS`, więc kolejna
wersja to jedna pozycja, a nie kolejny `elif`.

## Walidacja

Reguły są egzekwowane, a nie ciche:

- `PRZEJSCIA`/`PRZYROST` tylko dla operacji skrawających,
- `POSUW` nie dla `PAUZA` i `WRZECIONO`,
- `OBROTY` wyłącznie dla `WRZECIONO`, wartość nieujemna,
- narożniki prostokąta, których nie ma wprost w kolumnach, też są sprawdzane
  względem obszaru roboczego.

## Zweryfikowane na sprzęcie

Program z wszystkimi trzema operacjami, przebieg na trzech serwach:

```
op=2  SZYBKI      -> (25, 15) na Z=10
op=3  PROSTOKAT   -> Z=-0.5: (0,0)→(20,0)→(20,10)→(0,10)→(0,0)
                     Z=-1.0: (0,0)→(20,0)→(20,10)→(0,10)→(0,0)
op=4  WRZECIONO 0 -> wrzeciono wyłączone
koniec: READY, powrót do (0,0,10)
```

Testy serwera: 42/42.
