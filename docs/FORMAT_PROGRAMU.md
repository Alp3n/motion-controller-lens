# Format pliku programu (.prg) — wersje 1, 2, 3 i 4

Plik programu opisuje operacje odcinania wlewków dla jednej płytki optyki.
Założenia:

- **prosty i czytelny dla technologa** — bez programowania,
- edytowalny w edytorze webowym maszyny, w Notatniku i w **Excelu**
  (separator `;`, jak w polskim CSV),
- nazwa pliku = **12-cyfrowy numer programu (12 NC)** + rozszerzenie `.prg`,
  np. `583912004711.prg`,
- kodowanie UTF-8, jedna operacja = jedna linia.

## Budowa pliku

Plik składa się z dwóch sekcji: `[NAGLOWEK]` i `[OPERACJE]`.
Linie zaczynające się od `#` to komentarze i są pomijane.

```
# Program odcinania wlewkow — plytka soczewki 50 mm, strona lewa
[NAGLOWEK]
FORMAT;1
PROGRAM;583912004711
NAZWA;Plytka soczewki 50mm - lewa
MATERIAL;PMMA
AUTOR;J.Kowalski
DATA;2026-08-14
OBROTY_FREZU;12000
POSUW_ROBOCZY;300
POSUW_DOJAZDU;3000
Z_BEZPIECZNE;10.0

[OPERACJE]
LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI
1;PUNKT;12.500;30.000;-1.50;;;wlewek gorny
2;PUNKT;12.500;-30.000;-1.50;;;wlewek dolny
3;LINIA;40.000;10.000;-1.50;55.000;10.000;wlewek boczny - ciecie po linii
4;PAUZA;;;;;;kontrola wzrokowa przed odjazdem
```

## Sekcja [NAGLOWEK]

Pary `KLUCZ;WARTOSC`, po jednej w linii.

| Klucz           | Wymagany | Opis                                                     |
|-----------------|----------|----------------------------------------------------------|
| `FORMAT`        | tak      | wersja formatu: `1` (8 kolumn), `2` (11), `3` (12), `4` (13), `5` (14) |
| `PROGRAM`       | tak      | 12-cyfrowy numer programu — musi zgadzać się z nazwą pliku |
| `NAZWA`         | tak      | czytelna nazwa programu / detalu                         |
| `MATERIAL`      | nie      | materiał płytki (np. PMMA, PC)                           |
| `AUTOR`         | nie      | kto przygotował program                                  |
| `DATA`          | nie      | data ostatniej zmiany (RRRR-MM-DD)                       |
| `OBROTY_FREZU`  | tak      | obroty wrzeciona [obr/min]                               |
| `POSUW_ROBOCZY` | tak      | posuw podczas cięcia [mm/min]                            |
| `POSUW_DOJAZDU` | tak      | posuw dojazdów nad materiałem [mm/min]                   |
| `Z_BEZPIECZNE`  | tak      | wysokość Z bezpiecznych przejazdów [mm]                  |

## Sekcja [OPERACJE]

Pierwsza linia to nagłówek kolumn (stały):
- **format 1:** `LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI`
- **format 2:** `LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;PRZEJSCIA;PRZYROST;UWAGI`
- **format 3:** `LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;PRZEJSCIA;PRZYROST;UWAGI`
- **format 4:** `LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;MOMENT;PRZEJSCIA;PRZYROST;UWAGI`
- **format 5:** `LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;MOMENT;PRZEJSCIA;PRZYROST;SMART;UWAGI`

Nagłówek musi odpowiadać wersji podanej w `FORMAT`. Parser czyta wszystkie
wersje, a edytor zapisuje zawsze w najnowszej — starsze pliki awansują przy
pierwszym zapisie, bez utraty treści.

Kolejne linie to operacje wykonywane po kolei, od `LP=1`.
Współrzędne w **mm**, względem punktu bazowego uchwytu płytki.
Separator dziesiętny: kropka **lub** przecinek (oba akceptowane, więc plik
zapisany z Excela w polskich ustawieniach też zadziała).

### Rodzaje operacji

| OPERACJA | Wymagane kolumny | Działanie maszyny                                                                 |
|----------|------------------|-----------------------------------------------------------------------------------|
| `PUNKT`  | X, Y, Z          | dojazd nad punkt (X,Y) na `Z_BEZPIECZNE`, zagłębienie do Z posuwem roboczym, wycofanie — ocięcie wlewka w jednym punkcie |
| `LINIA`  | X, Y, Z, X2, Y2  | dojazd nad (X,Y), zagłębienie do Z, cięcie po linii do (X2,Y2) posuwem roboczym, wycofanie |
| `PROSTOKAT` | X, Y, Z, X2, Y2 | obrys prostokąta o narożnikach przeciwległych (X,Y) i (X2,Y2); tor zamyka się w punkcie startu |
| `SZYBKI` | X, Y             | przejazd bez skrawania na wysokości `Z_BEZPIECZNE`, posuwem dojazdu           |
| `WRZECIONO` | OBROTY        | zmiana obrotów wrzeciona w trakcie programu; `0` wyłącza wrzeciono            |
| `SMART`  | SMART            | wywołanie funkcji SMART — ruch reagujący na siłę, opisany definicją z ekranu „Funkcje SMART". Jedzie od miejsca, w którym stoi maszyna; dystans, oś, próg siły i prędkości są w definicji |
| `PAUZA`  | —                | zatrzymanie cyklu; operator wznawia przyciskiem START (np. kontrola wzrokowa)     |

Kolumna `UWAGI` jest dowolnym opisem dla operatora (wyświetlana na panelu).
Puste kolumny zostawia się puste (same średniki).

### Parametry operacji (format 2+)

Kolumny opcjonalne. Puste znaczy „weź wartość z nagłówka programu" (albo,
dla `MOMENT`, „weź wartość z aktywnego profilu parametrów").

`PRZEJSCIA` i `PRZYROST` przyjmują **tylko operacje skrawające**
(`PUNKT`, `LINIA`, `PROSTOKAT`). `POSUW` i `MOMENT` nie dotyczą `PAUZA`,
`WRZECIONO` ani `SMART`. `OBROTY` dotyczą wyłącznie `WRZECIONO`, a `SMART`
wyłącznie operacji `SMART`. Operacja `SMART` nie przyjmuje też współrzędnych
— jedzie od bieżącej pozycji. Złamanie tych reguł jest błędem z numerem
linii, a nie cichym zignorowaniem wartości.

| Kolumna     | Opis                                                                 |
|-------------|----------------------------------------------------------------------|
| `POSUW`     | posuw roboczy tylko dla tej operacji [mm/min]; puste = `POSUW_ROBOCZY`. Dla `SZYBKI` nadpisuje `POSUW_DOJAZDU` |
| `OBROTY`    | obroty wrzeciona [obr/min] — **wyłącznie** dla operacji `WRZECIONO`    |
| `MOMENT`    | limit siły (momentu silnika) tylko dla tej operacji, w % (0, 100]; puste = wartość z aktywnego profilu parametrów. **Dziś tylko zapis w pliku** — jak limit momentu w profilach, nie działa jeszcze w symulatorze ani na sprzęcie (protokół mostka nie ma komendy momentu) |
| `PRZEJSCIA` | liczba przejść na głębokość (liczba całkowita ≥ 1)                    |
| `PRZYROST`  | przyrost głębokości na przejście [mm]                                 |
| `SMART`     | nazwa definicji SMART — **wyłącznie** dla operacji `SMART`. Parametry (oś, dystans, próg siły, prędkości) siedzą w definicji, wspólnej z cyklem maszyny (`config/smart.json`, ekran `/smart`). **Na maszynie jeszcze nie działa** — mostek nie zna komendy SMART i przerwie program błędem; w symulatorze wykonuje się, ale reaguje na moment zmyślony przez symulator, nie na pomiar (patrz `funkcje-smart.md`) |

`PRZEJSCIA` i `PRZYROST` **wykluczają się** — wypełnij jedno albo żadne.
Bez nich operacja wykonuje jedno przejście na pełną głębokość.

Głębokość dzielona jest od powierzchni materiału (**Z = 0**) do `Z` z operacji,
a ostatnie przejście zawsze trafia dokładnie w zadane `Z`. Po każdym przejściu
narzędzie wycofuje się na `Z_BEZPIECZNE`, co odprowadza wiór — przy plastiku
ogranicza topienie i wyrwania.

Przykład: `PUNKT` z `Z = -3` i `PRZEJSCIA = 3` zagłębia się kolejno na
−1, −2 i −3 mm. To samo z `PRZYROST = 0,5` da sześć przejść co 0,5 mm.
Przy `PRZYROST` niedzielącym głębokości bez reszty przejść jest tyle, ile
trzeba, a wszystkie są równe (np. `Z = -1,2` i `PRZYROST = 0,5` → trzy
przejścia po 0,4 mm).

## Walidacja

Serwer maszyny przy ładowaniu programu sprawdza m.in.:

- zgodność numeru `PROGRAM` z nazwą pliku (12 cyfr),
- obecność wymaganych pól nagłówka i poprawność liczb,
- ciągłość numeracji `LP` (1, 2, 3, …),
- znane rodzaje operacji i komplet współrzędnych dla danego rodzaju,
- mieszczenie się współrzędnych w obszarze roboczym maszyny
  (limity konfigurowane w serwerze).

Błędy są zgłaszane z numerem linii i opisem po polsku — program z błędami nie
zostanie załadowany do produkcji.
