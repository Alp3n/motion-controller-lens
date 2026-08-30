# Nowe operacje programu — propozycja

> **Stan realizacji (2026-08-14).** Zrealizowano całą **grupę A**
> (`PROSTOKAT`, `SZYBKI`, `WRZECIONO`) oraz parametry `PRZEJSCIA`, `PRZYROST`
> i `POSUW` — patrz [`zmiany/operacje-grupy-a.md`](zmiany/operacje-grupy-a.md)
> i [`zmiany/parametry-operacji.md`](zmiany/parametry-operacji.md).
> **Grupa B (`LUK`, `OKRAG`, `POLILINIA`) świadomie pominięta** — uzgodniono,
> że przy odcinaniu wlewków odcinki wystarczą. Reszta dokumentu pozostaje jako
> punkt wyjścia, gdyby łuki jednak okazały się potrzebne.

Dziś format `.prg` zna trzy operacje: `PUNKT`, `LINIA`, `PAUZA`
(`server/app/program.py`, `OPERATION_TYPES`). Dokument proponuje, jak
rozszerzyć ten zbiór i gdzie zaimplementować ruch.

## Czym realnie dysponujemy

### Warstwa sprzętowa (ClearPath-SC + sFoundation)

- **Ruch pozycyjny per oś**: `MovePosnStart(impulsy, absolutnie)` z limitami
  `VelLimit` (obr/min) i `AccLimit` (obr/min/s). Profil trapezowy.
- **Ruch prędkościowy**: `MoveVelStart(prędkość)`.
- **Brak interpolacji wielosiowej w sprzęcie.** Każda oś wykonuje własny
  profil. Ruch po prostej w XY realizujemy dziś tak, że dobieramy prędkości
  osi, by skończyły jednocześnie — to przybliżenie, z odchyłką na rampach.
- **Bufor 16 ruchów na węzeł.** Kolejne `MovePosnStart` wysłane w trakcie
  ruchu trafiają do bufora i startują natychmiast po zakończeniu bieżącego,
  bez czekania na komunikację. `addPostMoveDwell` jest opcjonalne (domyślnie
  wyłączone).

> **Do zweryfikowania pomiarowo:** czy między buforowanymi ruchami prędkość
> jest wygładzana, czy każdy segment kończy się zjazdem do zera. Od tego
> zależy jakość powierzchni przy łukach dzielonych na segmenty. Jeśli profil
> zjeżdża do zera, potrzebne będą ruchy typu *head-tail* (`Motion.Adv`) albo
> akceptacja falistości.

### Warstwa protokołu (mostek)

Dziś: `PING`, `STATUS`, `HOME`, `MOVEXY`, `MOVEZ`, `JOG`, `SPINDLE`, `STOP`,
`RESET`, `RELEASE`/`HOLD`. Każda komenda ruchu **blokuje do końca ruchu**.

## Gdzie implementować nowe tory — decyzja kluczowa

Łuk czy polilinię trzeba rozłożyć na krótkie odcinki. Są dwa miejsca:

| | Serwer (Python) dzieli na `MOVEXY` | Mostek (C++) dostaje `ARC`/`POLY` |
|---|---|---|
| Zmiana w mostku | żadna | nowa komenda |
| Ruch między segmentami | pełny stop — każdy segment to osobna komenda TCP z czekaniem na `OK` | płynny — mostek karmi bufor 16 ruchów |
| Jakość powierzchni | falista, wolna | zależna od wygładzania w napędzie |
| Obciążenie łącza | ~50–200 komend na łuk | 1 komenda |

**Rekomendacja: mostek.** Segmentacja po stronie serwera oznacza zatrzymanie
na każdym segmencie, bo protokół czeka na potwierdzenie — bufor napędu
zostaje pusty i cała jego zaleta przepada. Poza tym utrzymuje to obecny
podział: serwer tłumaczy program na komendy wysokopoziomowe, a sterownik nie
zna formatu `.prg`.

## Proponowane operacje

### Grupa A — tanie, bez zmian w mostku

Realizowane przez istniejące `MOVEXY`/`MOVEZ`/`SPINDLE`:

| Operacja | Opis | Kolumny |
|---|---|---|
| `PROSTOKAT` | obrys prostokąta — 4 odcinki | X,Y (róg), X2,Y2 (przeciwległy róg) |
| `WRZECIONO` | zmiana obrotów w trakcie programu | R = obr/min |
| `SZYBKI` | przejazd bez frezowania (Z bezpieczne, posuw dojazdu) | X,Y |

Dodatkowo jako **parametry operacji**, nie osobne typy:

- `PRZEJSCIA` — liczba przejść na głębokość. Zamiast jednego zagłębienia na
  `Z`, program schodzi stopniowo. Przy plastiku ogranicza topienie i wyrwania.
  Implementacja wyłącznie w serwerze, w pętli po operacji.
- `POSUW` — nadpisanie posuwu roboczego dla jednej operacji.

### Grupa B — wymaga nowej komendy w mostku

| Operacja | Opis | Kolumny |
|---|---|---|
| `LUK` | łuk od (X,Y) do (X2,Y2) o promieniu R | X,Y,Z,X2,Y2,R,KIER |
| `OKRAG` | pełny okrąg o środku (X,Y) i promieniu R | X,Y,Z,R,KIER |
| `POLILINIA` | ciągły tor przez wiele punktów | osobna składnia — patrz niżej |

`KIER` = `CW`/`CCW`. Dla `LUK` promień jednoznacznie wyznacza dwa łuki —
proponuję konwencję z G-code: **R dodatnie = łuk krótszy, R ujemne = dłuższy**.

`POLILINIA` nie mieści się w tabeli o stałej liczbie kolumn. Dwa wyjścia:
kolejne wiersze `POLILINIA` traktowane jako punkty jednego toru (czytelne
w Excelu), albo lista punktów w jednej komórce. **Proponuję pierwsze** —
technolog widzi punkt na wiersz, tak jak resztę operacji.

## Zmiana formatu pliku

Obecny nagłówek tabeli jest sztywny:
`LP;OPERACJA;X;Y;Z;X2;Y2;UWAGI`, a parser wymaga dokładnej zgodności.

Propozycja: **`FORMAT;2`** z rozszerzoną tabelą:

```
LP;OPERACJA;X;Y;Z;X2;Y2;R;KIER;POSUW;PRZEJSCIA;UWAGI
```

- Parser przyjmuje **oba formaty**: `FORMAT;1` z ośmioma kolumnami (istniejące
  pliki działają bez zmian) i `FORMAT;2` z dwunastoma.
- Zapis zawsze w `FORMAT;2`; plik `FORMAT;1` awansuje przy pierwszym zapisie
  w edytorze.
- Nowe kolumny są opcjonalne — puste znaczy „domyślne z nagłówka".

Alternatywa (odrzucona): jedna kolumna `PARAMETRY` z parami `klucz=wartość`.
Bardziej elastyczna, ale gorzej wygląda w Excelu, a to główne narzędzie
technologa.

## Edytor technologa

Dziś `editor.js` ma stałą listę `OP_TYPES` i jednakowy wiersz dla każdej
operacji — pola X2/Y2 są widoczne nawet dla `PUNKT`.

Propozycja:

1. **Pola zależne od typu operacji.** Wybór w `OPERACJA` pokazuje tylko
   sensowne kolumny; reszta wyszarzona. Definicja pól w jednym miejscu
   (`OP_SCHEMA`), wspólna dla walidacji i renderowania.
2. **Podgląd toru** — ten sam rysunek co w panelu operatora
   (`drawView`), ale rysujący edytowany program: punkty, odcinki, łuki
   i kolejność. Technolog widzi błąd geometrii, zanim plik trafi na maszynę.
3. **Walidacja na bieżąco** — obszar roboczy jest już w `/api/config`,
   więc punkt poza zakresem można pokazać od razu, a nie dopiero przy zapisie.
4. **Wstawianie i przestawianie wierszy** — dziś jest tylko „dodaj na końcu",
   a `LP` musi być ciągłe; przy edycji istniejącego programu to uciążliwe.

## Kolejność wdrożenia

1. `PRZEJSCIA` i `POSUW` jako parametry — największy zysk technologiczny
   przy zerowym ryzyku, bez zmian w mostku.
2. Format 2 w parserze + edytor z polami zależnymi od typu.
3. `PROSTOKAT`, `SZYBKI`, `WRZECIONO` — złożenia istniejących ruchów.
4. Pomiar wygładzania między buforowanymi ruchami.
5. `LUK`/`OKRAG` w mostku, na podstawie wyniku kroku 4.
6. `POLILINIA`.

## Otwarte pytania

- Czy łuki są w ogóle potrzebne przy odcinaniu wlewków, czy wystarczą odcinki?
  To decyduje, czy w ogóle wchodzimy w grupę B.
- Czy `PRZEJSCIA` mają dzielić głębokość równomiernie, czy technolog chce
  podać przyrost na przejście?
- Czy potrzebne jest chłodzenie/odciąg jako sterowany wyjściem — wtedy
  dochodzi operacja i drugie wyjście huba.
