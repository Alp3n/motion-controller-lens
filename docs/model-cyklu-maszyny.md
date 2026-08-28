# Model cyklu maszyny i programu detalu — propozycja

Projekt modelu danych z tematu B w [`plan-rozwoju.md`](plan-rozwoju.md).
To jest **propozycja do przejrzenia, nie zaimplementowany kod** — zanim
zacznę pisać, chcę Twojego potwierdzenia co do podziału na etapy niżej.

## Punkt wyjścia — co już jest

- **`Axis`** istnieje jako `AxisConfig` w `server/app/axes.py`, ale
  **na sztywno ograniczony do trzech osi**: `AXIS_NAMES = ("x", "y", "z")`
  przewija się przez `parse_axes`, `default_axes`, `to_dict`, ekran `/axes`.
  Żeby dodać podajnik czy docisk, ta stała musi przestać być stałą.
- **`PartProgram`** (12NC) już istnieje jako `Program`/`Operation` w
  `server/app/program.py` — parser, walidator, edytor. Nie trzeba tego
  przepisywać, tylko **podłączyć pod cykl maszyny** jako krok, który cykl
  wywołuje.
- **`ParameterProfile`** i **`CycleStep`** nie istnieją — to jest właściwy
  zakres tego dokumentu.
- Maszyna stanów jest dziś płaska: `INIT → NOT_HOMED → READY → RUNNING →
  READY`, z `ALARM` w bok (`server/app/machine.py`, `MachineState`). Cykl
  maszyny potrzebuje własnych stanów pośrednich (podawanie, docisk, wywołanie
  programu detalu, wyrzut), zagnieżdżonych w `RUNNING`.

## Proponowane encje

```
Axis            — nazwa (dowolna, nie tylko x/y/z), AxisConfig (już istnieje)
ParameterProfile — nazwany zestaw: prędkość, przyspieszenie/hamowanie,
                   TrqGlobal (limit momentu, patrz mozliwosci-clearpath-sc.md)
                   — per oś
CycleStep        — jeden krok cyklu maszyny: rodzaj (ruch / wywołanie
                   programu detalu / ustawienie wyjścia / pauza / czekaj na
                   wejście), ParameterProfile do użycia, opcjonalnie
                   wyjście cyfrowe (BRAKE_0/BRAKE_1 — patrz temat J)
PartProgram      — to już jest: Program + Operation z program.py, bez zmian
                   w formacie .prg
```

Kluczowa decyzja projektowa (zgodna z tym, co już ustaliliśmy): **wyjście
cyfrowe (podajnik/wyrzutnik/lampka/błąd) jest polem `CycleStep`, nie
`Operation`.** Program technologa (`.prg`) go nie widzi i nie może go użyć —
to warstwa admina, nie technologa.

## Snapshot/restore parametrów osi

To jest mechanizm, nie nowa struktura danych — `ParameterProfile` już go
obsługuje przez to, że **cykl i program detalu odwołują się do różnych
profili tej samej osi**:

```
wejście do programu detalu:
    snapshot = { oś: aktywny ParameterProfile dla każdej osi używanej w cyklu }
    dla każdej osi w programie detalu: zastosuj ParameterProfile programu detalu
    wykonaj program detalu (Operation po Operation, jak dziś)
finally:
    dla każdej osi: przywróć ParameterProfile ze snapshotu
```

`finally`, nie `except` — przywrócenie musi zajść **także przy błędzie
i przerwaniu (STOP)**, zgodnie z ustaleniem w `DECYZJE_2026-08-25.md` §3.
Naturalne miejsce w kodzie: tam, gdzie `Machine` dziś wywołuje operacje
programu (`_run_operations` czy odpowiednik w `machine.py`) — opakowane
w `try/finally` na poziomie „wejście/wyjście z programu detalu”.

## Skok do podprogramu technologa

Wzorzec z `inspiracje-mic488.md` (punkt 2: `JUMP`/`RETURN`) przeniesiony na
nasz model: `CycleStep` typu „wywołaj program detalu” **jest** tym skokiem —
nie potrzebujemy osobnej etykiety/powrotu, bo cały krok kończy się, gdy
program detalu (skończona lista `Operation`) się skończy. To jest prostsze
niż MIC488, bo nasze programy detalu nie mają własnych pętli/skoków — są
listą operacji wykonywanych po kolei, tak jak dziś.

## Co się zmienia w istniejącym kodzie

| Plik | Zmiana |
|---|---|
| `server/app/axes.py` | `AXIS_NAMES` z stałej krotki na listę wynikającą z konfiguracji — **to jest praca, którą można zacząć niezależnie od reszty**, patrz Etap 1 |
| `server/app/machine.py` | nowe stany cyklu (albo pod-maszyna stanów w `RUNNING`); miejsce na snapshot/restore |
| `server/app/main.py` | nowe endpointy: CRUD `ParameterProfile`, CRUD/kolejność `CycleStep`, uruchomienie cyklu |
| `server/app/static/` | nowy ekran definiowania cyklu (temat G), analogiczny do `/editor` |
| `config/` | nowy plik konfiguracyjny cyklu (obok `axes.json`), albo rozszerzenie istniejącego |

`server/app/program.py` **zostaje bez zmian** — to jest mocna strona tego
podziału: format `.prg` i tak, co robi technolog, jest już gotowe i przyjęte.

## Proponowane etapy — żeby nie robić wszystkiego naraz

1. **Uogólnić `AXIS_NAMES`** w `axes.py` na konfigurowalną listę osi (start:
   dalej x/y/z, ale niesztywne w kodzie) — mała, testowalna zmiana,
   fundament pod dodanie podajnika/docisku. Nie wymaga jeszcze `CycleStep`
   ani UI.
2. **`ParameterProfile`** jako struktura danych + zapis/odczyt (wzorzec
   identyczny do `AxisConfig`: dataclass, `to_dict`/`from_dict`, plik JSON).
   Podłączenie `TrqGlobal` do warstwy `Machine` (dziś nieużywane w mostku).
3. **`CycleStep`** + mechanizm snapshot/restore, na modelu symulatora
   (`MACHINE_MODE=sim`) — bez UI, tylko logika i testy.
4. **Ekran definiowania cyklu** (temat G) — dopiero gdy 1–3 działają
   i są przetestowane.

Każdy etap to osobny, przeglądalny PR — zgodnie z tym, jak dotąd
pracowaliśmy w tej sesji.

## Pytania, które zostają otwarte

- Ile i jakie kroki cyklu przewidujemy na start? (`DECYZJE_2026-08-25.md`
  wymienia: podawanie → bazowanie/docisk → program detalu → przywrócenie →
  wyrzut → powtórz — to 4 rodzaje kroków plus pętla)
- Czy `ParameterProfile` żyje w osobnym pliku, czy jako rozszerzenie
  `config/axes.json`?
- Format zapisu `CycleStep` — JSON jak `axes.json`, czy coś bliższe `.prg`
  (skoro to też program, tylko poziomu admina)?
