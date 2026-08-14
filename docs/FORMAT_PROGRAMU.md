# Format pliku programu (.prg) — wersja 1

Plik programu opisuje operacje ocinania wlewków dla jednej płytki optyki.
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
# Program ocinania wlewkow — plytka soczewki 50 mm, strona lewa
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
| `FORMAT`        | tak      | wersja formatu, obecnie `1`                              |
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
`LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI`

Kolejne linie to operacje wykonywane po kolei, od `LP=1`.
Współrzędne w **mm**, względem punktu bazowego uchwytu płytki.
Separator dziesiętny: kropka **lub** przecinek (oba akceptowane, więc plik
zapisany z Excela w polskich ustawieniach też zadziała).

### Rodzaje operacji

| OPERACJA | Wymagane kolumny | Działanie maszyny                                                                 |
|----------|------------------|-----------------------------------------------------------------------------------|
| `PUNKT`  | X, Y, Z          | dojazd nad punkt (X,Y) na `Z_BEZPIECZNE`, zagłębienie do Z posuwem roboczym, wycofanie — ocięcie wlewka w jednym punkcie |
| `LINIA`  | X, Y, Z, X2, Y2  | dojazd nad (X,Y), zagłębienie do Z, cięcie po linii do (X2,Y2) posuwem roboczym, wycofanie |
| `PAUZA`  | —                | zatrzymanie cyklu; operator wznawia przyciskiem START (np. kontrola wzrokowa)     |

Kolumna `UWAGI` jest dowolnym opisem dla operatora (wyświetlana na panelu).
Puste kolumny zostawia się puste (same średniki).

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
