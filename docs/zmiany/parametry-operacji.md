# Parametry operacji: POSUW, PRZEJSCIA, PRZYROST

Format `.prg` w wersji 2 dokłada trzy opcjonalne kolumny do sekcji
`[OPERACJE]`: własny posuw operacji oraz wielokrotne przejścia na głębokość
(zadawane liczbą przejść albo przyrostem na przejście).

Bez zmian w mostku — całość realizuje serwer, składając istniejące komendy
`MOVEZ`/`MOVEXY`.

## Pliki

- `server/app/program.py` — nagłówki V1/V2, pola `feed`, `passes`,
  `depth_step` w `Operation`, walidacja parametrów, funkcja `pass_depths()`,
  zapis zawsze w formacie 2.
- `server/app/machine.py` — wykonanie przejść i posuwu operacji
  w symulatorze i w trybie sprzętowym.
- `server/app/static/editor.html`, `editor.js` — trzy nowe kolumny
  w edytorze; wypełnienie `PRZEJSCIA` czyści `PRZYROST` i odwrotnie.
- `docs/FORMAT_PROGRAMU.md` — specyfikacja formatu 2.
- `server/tests/test_program.py` — 9 testów formatu 2 i podziału głębokości.

## Zgodność wstecz

Parser czyta oba formaty. `FORMAT;1` z ośmioma kolumnami działa bez zmian;
nagłówek musi pasować do zadeklarowanej wersji, więc rozjazd jest wykrywany
z numerem linii zamiast dawać dziwny błąd kolumn. Zapis idzie zawsze
w formacie 2 — plik awansuje przy pierwszym zapisie w edytorze.

## Podział głębokości

Od powierzchni materiału (**Z = 0**) do `Z` operacji, ostatnie przejście
zawsze trafia dokładnie w zadane `Z`. Po każdym przejściu wycofanie na
`Z_BEZPIECZNE` — przy `PUNKT` daje to wiercenie przerywane, przy `LINIA`
powrót na początek odcinka.

`PRZYROST` jest zaokrąglany w górę do całkowitej liczby przejść, które są
potem **równe** — nie ma resztkowego cienkiego przejścia na końcu.

## Zweryfikowane na sprzęcie

Program testowy na trzech serwach, przebieg osi Z:

```
op=1 (PUNKT, Z=-3, PRZEJSCIA=3)   -1.00 → -2.00 → -3.00
op=2 (LINIA, Z=-1, PRZYROST=0.5)  -0.50 → -1.00
```

z wycofaniem na Z=10 po każdym przejściu.

## Uwagi

- Powierzchnia materiału jest **założona na Z = 0**. Jeśli detal ma być
  bazowany inaczej, podział przejść trzeba będzie odnieść do osobnego pola
  w nagłówku.
- W `programs/` został plik testowy `583912009999.prg` — do usunięcia,
  jeśli nie jest potrzebny.
- Łuki i pozostałe operacje z propozycji ([`../nowe-operacje-programu.md`](../nowe-operacje-programu.md))
  nie są realizowane — uzgodniono, że odcinki wystarczą.
