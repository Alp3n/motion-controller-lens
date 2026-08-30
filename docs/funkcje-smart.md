# Funkcje SMART — ruch z kontrolą siły

Analiza i plan wdrożenia funkcji sterowanych siłą (odczyt momentu silnika
w trakcie ruchu i reagowanie na niego), na podstawie materiału
[`../zbyszek/kontrola-sily.md`](../zbyszek/kontrola-sily.md).

Cel z Twojego opisu: technolog podaje w programie współrzędne wlewków,
a **po każdym punkcie może wstawić „funkcję smart"** — złożoną procedurę
(np. wykrycie kontaktu z materiałem, cięcie adaptacyjne, cofnięcie po
przekroczeniu siły). Funkcja jest na tyle skomplikowana, że **przygotowuje
ją programista**, a technolog tylko wybiera ją w edytorze i podaje parametry.

## Co jest potwierdzone u źródła

Sprawdzone w referencji API Teknica (`zbyszek/S-FoundationRef.chm`,
klasy `sFnd::IMotion`, `sFnd::ILimits`, `sFnd::INode`) — nie z pamięci:

| Element | Stan | Źródło |
|---|---|---|
| **Odczyt zmierzonego momentu** | `sFnd::IMotion::TrqMeasured` — *„Access the current measured torque"*, typ `ValueDouble` | `classs_fnd_1_1_i_motion.html` |
| **Jednostka: procent maksimum** | `enum _trqUnits { PCT_MAX, AMPS }`, *„default units are percentage of maximum"* | `classs_fnd_1_1_i_node.html` |
| **Ustawienie limitu momentu** | `sFnd::ILimits::TrqGlobal`, przykład: `myNode.TrqUnit(myNode.PCT_MAX); myNode.Limits.TrqGlobal = 100;` | `classs_fnd_1_1_i_limits.html` |
| Moment zadany (do porównania z zmierzonym) | `sFnd::IMotion::TrqCommanded` | j.w. |

**Wniosek: `read_torque_utilization()` z algorytmu w materiale źródłowym to
`node.Motion.TrqMeasured` przy `TrqUnit(PCT_MAX)`. Funkcja jest wykonalna
na naszym sprzęcie** — nie wymaga czujnika siły ani innych silników.

## Najważniejsze ograniczenie: gdzie ta pętla może działać

To jest ustalenie, które przesądza o całej architekturze — sprawdzone
w kodzie, nie założone.

**Mostek blokuje się na czas ruchu.** `waitMoves()`
(`bridge/sc4hub_bridge.cpp:245`) czeka na `MoveIsDone()`, a w trakcie
czekania wywołuje `pollDuringMove()` (linia 618), która obsługuje
**wyłącznie `STOP` i `STATUS`** — komentarz w kodzie mówi wprost:
*„pozostałe komendy w trakcie ruchu są ignorowane"*.

Konsekwencje:

- Serwer w Pythonie **nie może** dziś w trakcie ruchu ani zmienić prędkości,
  ani zadać ruchu względnego, ani odczytać momentu. Pętla monitorująca
  z materiału źródłowego (próbkowanie co 10 ms + reakcja) **nie da się
  napisać po stronie Pythona.**
- Obejście „tnij w wielu malutkich ruchach z Pythona" jest złe:
  każdy ruch ma własną rampę rozpędzania i hamowania, więc cięcie byłoby
  szarpane (jakość powierzchni), a do pętli reagującej na siłę doszłoby
  opóźnienie i drżenie łącza TCP.
- **Pętla musi działać w mostku (C++), przy sprzęcie.**

**Dobra wiadomość:** mostek **już ma** pętlę o odpowiedniej częstotliwości —
`waitMoves()` odpytuje co 20 ms (timeout `select()` w `pollDuringMove`)
i już teraz sprawdza w niej sygnał zezwolenia. To jest naturalne
i małoinwazyjne miejsce na wpięcie odczytu momentu i reakcji.

## Model danych — trzy poziomy

Warto je rozdzielić, bo mylenie ich prowadzi do złych decyzji:

| Poziom | Co to jest | Kto to robi | Gdzie żyje |
|---|---|---|---|
| **Procedura** | algorytm reagujący na siłę, np. `ciecie_adaptacyjne` | programista | C++ w mostku |
| **Definicja SMART** | nazwany zestaw parametrów, np. `SMART-sila` | technolog / admin | `config/smart.json`, ekran `/smart` |
| **Użycie** | jeden wiersz programu albo krok cyklu | technolog | `.prg` / `config/cycle.json` |

Procedura deklaruje, **jakie ma parametry** (nazwa, jednostka, zakres,
wartość domyślna). Definicja SMART **wypełnia je konkretnymi wartościami**
i dostaje własną nazwę. Program tylko **wskazuje definicję po nazwie**.

Dzięki temu w tabeli operacji jest **jedna dodatkowa kolumna**, a nie osiem —
parametrów jest za dużo, żeby wpychać je w wiersz.

### Osobny ekran `/smart` — definicje funkcji

Ekran na wzór edytora technologa (`/editor`), bo definicje SMART są
dokumentami użytkownika, nie ustawieniem maszyny:

- lista definicji po lewej, edycja wybranej po prawej,
- wybór **procedury** (z rejestru) → ekran sam rysuje właściwe pola,
- **„Zapisz jako"** — skopiuj istniejącą definicję pod nową nazwą i zmień
  parametry (np. `wlewek-cienki` → `wlewek-gruby`); ten sam wzorzec, co już
  działa w edytorze programów,
- usuwanie, walidacja zakresów na bieżąco.

Typowe użycie: jedna definicja na rodzaj wlewka albo materiału. Zmiana
parametrów cięcia = poprawka w jednym miejscu, a nie w każdym programie
z osobna.

### Program technologa: operacja `SMART` (format 5 `.prg`)

Wstawiana **po punkcie**, wybierana z listy jak każda inna operacja:

```
LP;OPERACJA;X;Y;Z;...;SMART;UWAGI
1;PUNKT;12.5;30;-1.5;...;;wlewek gorny
2;SMART;;;;...;SMART-sila;odetnij
3;PUNKT;12.5;-30;-1.5;...;;wlewek dolny
4;SMART;;;;...;SMART-sila;odetnij
```

Dlaczego osobna operacja, a nie kolumny przy `PUNKT`:

- odpowiada temu, co opisałeś („**wstawienie** funkcji po punkcie"),
- edytor już umie wstawiać wiersze (przycisk `+` przy operacji),
- `PUNKT` zachowuje dotychczasowe znaczenie — nic się nie psuje w istniejących
  programach,
- da się użyć `SMART` bez poprzedzającego punktu (np. sama próba kontaktu).

**Jak `SMART` wie, gdzie działać:** operuje **względnie od bieżącej pozycji**
— dokładnie jak `move_relative(+feed_mm)` w algorytmie źródłowym. Czyli
`PUNKT` ustawia narzędzie nad wlewkiem, a `SMART` wykonuje zagłębienie
z kontrolą siły. To się składa w naturalny sposób i jest alternatywą dla
dzisiejszego zagłębiania przez `PRZEJSCIA`/`PRZYROST` (tam głębokość jest
sztywna, tu decyduje siła).

Oś ruchu jest parametrem definicji (domyślnie `Z`).

**Decyzja, którą warto znać:** rodzajem operacji jest `SMART`, a nazwa
definicji siedzi w osobnej kolumnie. Kusiło, żeby wrzucić nazwy definicji
wprost do listy rodzajów operacji (`SMART-sila` obok `PUNKT`) — odrzuciłem,
bo wtedy parser `.prg` musiałby znać konfigurację definicji, a **skasowanie
definicji uczyniłoby stare programy niemożliwymi do wczytania**. Przy
osobnej kolumnie brak definicji to czytelne ostrzeżenie, a nie zepsuty plik.
W edytorze i tak wygląda to jak dwie listy obok siebie, więc dla technologa
różnicy nie ma.

### Cykl maszyny: krok `SMART`

Ten sam mechanizm i te same definicje, jako `CycleStep.kind = "SMART"` —
obok istniejących `RUCH`/`PROGRAM`/`WYJSCIE`/`PAUZA`, wybierany z tej samej
listy co one. Przydatne do docisku detalu przed cięciem albo do dojazdu do
oporu na osi podajnika.

**Definicje są wspólne** dla programu technologa i cyklu maszyny — jedna
lista, jeden ekran, to samo zachowanie. Tego wymagałeś wprost.

## „Język programisty" — jak to rozumiem i co proponuję

Skoro pętla musi być w C++ w mostku, to **językiem programisty jest C++
w `bridge/sc4hub_bridge.cpp`**. Ale technolog nie może potrzebować
programisty do każdego programu. Dlatego warstwowo:

**1. Jedna parametryzowana procedura pokrywa większość przypadków.**
Algorytm z materiału źródłowego (`smart_cut`) ma już wszystkie potrzebne
parametry: próg siły, dojazd, cofnięcie, prędkość szybka/wolna, próg
adaptacji, współczynnik kolizji, okres próbkowania. Technolog wybiera
procedurę i wypełnia pola — **bez programisty**.

**2. Rejestr nazwanych procedur.** Programista dopisuje kolejne procedury
w C++ (`ciecie_adaptacyjne`, `szukanie_kontaktu`, `miekki_docisk`,
`detekcja_kolizji` — wszystkie są opisane w materiale źródłowym). Każda
**deklaruje swój zestaw parametrów** (nazwa, jednostka, zakres, wartość
domyślna). Mostek udostępnia ten rejestr komendą `SMARTLIST`, serwer go
przekazuje, a edytor **sam rysuje właściwe pola** — ten sam wzorzec, co
dzisiejsze `OP_SCHEMA` w `editor.js`, gdzie pola zależą od rodzaju operacji.

**3. Język skryptowy w mostku — świadomie NIE na start.** Wbudowanie Lua
czy podobnego do pętli sterującej siłą to duże ryzyko (błąd skryptu = ruch
z pełną siłą, trudniejsze testowanie, gorsza przewidywalność czasowa).
Wracamy do tego tylko, jeśli rejestr procedur okaże się realnie za ciasny.

**4. Rejestr istnieje po obu stronach — i to jest celowe.** Serwer ma własny,
wbudowany opis znanych procedur (Python), a mostek swój (C++). Dzięki temu
ekran `/smart` i edytor **działają w symulatorze, bez podłączonego mostka** —
inaczej całej warstwy interfejsu nie dałoby się zbudować ani przetestować
przed pracą przy maszynie. Po połączeniu ze sprzętem `SMARTLIST` pozwala
sprawdzić, czy obie strony mówią o tym samym; rozjazd (procedura znana
serwerowi, nieznana mostkowi) musi być **czytelnym ostrzeżeniem**, a nie
cichym błędem przy starcie cyklu.

## Ekran kontroli siły i kalibracji (`/sila`)

Osobny ekran, **niezależny od samych funkcji SMART**, choć to on daje im
sensowne liczby. Trzy zadania:

### 1. Podgląd obciążenia na żywo

Moment każdej osi (`TrqMeasured`, % maksimum) jako słupek i wykres
przewijany w czasie. Działa przy **każdym** ruchu — JOG, program, cykl —
więc od razu widać, czy nóż się zakleszcza albo czy oś pracuje pod
nietypowym obciążeniem. Przydatne w codziennej pracy, nie tylko przy
kalibracji.

### 2. Charakterystyka obciążenia w ruchu — sedno sprawy

**Problem, który to rozwiązuje:** oś obciążona jest zawsze, nawet gdy nic
nie tnie — tarcie śruby i prowadnic, ciężar zespołu na osi pionowej,
bezwładność przy rozpędzaniu. Jeśli nie wiesz, ile z tych 30% to samo
przejechanie w powietrzu, to **próg siły dobierasz na oślep**.

Ekran wykonuje **próbę przejazdu**: przejeżdża wskazaną oś przez zadany
zakres, z zadaną prędkością, i zapisuje przebieg momentu. Wynik:

- minimum, średnia i maksimum momentu na tym odcinku,
- **osobno dla obu kierunków** — na osi Z ciężar sprawia, że jazda w dół
  i w górę to zupełnie inne liczby, a na osiach poziomych asymetria
  wskazuje na zakleszczanie albo źle napiętą śrubę,
- przebieg w funkcji pozycji — widać miejsca, gdzie opór rośnie (np. brud,
  zużycie prowadnicy),
- to samo przy kilku prędkościach, bo tarcie zależy od prędkości.

To jest **charakterystyka bazowa**. Dopiero z nią próg siły w definicji
SMART ma sens: „baza + zapas", a nie liczba wzięta z sufitu. I to jest
odpowiedź na Twoje „pomoże przy przygotowaniu różnych projektów" — dla
nowej maszyny albo po wymianie mechaniki robisz próbę raz i masz punkt
odniesienia.

### 3. Kalibracja moment → siła (siłomierzem)

Jedyny uczciwy sposób, żeby dostać niutony zamiast procentów. Dociskasz
narzędzie do siłomierza, wpisujesz odczyt, ekran zapamiętuje parę
(moment %, siła N). Kilka par w różnych punktach daje przelicznik
**zmierzony**, a nie wyliczony ze wzoru pomijającego sprawność śruby
(ryzyko 2 niżej). Bez siłomierza ekran dalej działa — po prostu zostajesz
przy procentach.

### 4. Pomiar częstotliwości próbkowania

Przy okazji nagrywania ekran pokazuje, **ile próbek na sekundę faktycznie
udało się odczytać**. To odpowiedź na ryzyko 3 — nie zakładamy 10 ms,
tylko mierzymy, ile magistrala SC realnie wyrabia przy trzech osiach.

### Dlaczego to może być w Pythonie, skoro pętla SMART nie może

Bo **rejestrowanie to nie reagowanie**. Charakterystykę nagrywa się po
fakcie: serwer odpytuje `STATUS` i zapisuje próbki, a jitter łącza wpływa
tylko na gęstość wykresu, nie na zachowanie maszyny. Reakcja na siłę
(zatrzymaj, cofnij, zwolnij) musi być w mostku, bo tam liczy się każde
20 ms — ale sam pomiar nie. Dzięki temu ekran `/sila` to głównie praca
w Pythonie i JS, na istniejącym pollingu statusu.

### Co zostaje zapisane

Plik `config/kalibracja.json`: charakterystyki bazowe per oś (kierunek,
prędkość, min/śr/maks) i pary kalibracyjne moment→siła, z datą pomiaru.
Trwałe, żeby po miesiącu dało się porównać („czy opór osi wzrósł?") i żeby
kolejny projekt zaczynał od danych, a nie od zera.

### Bezpieczeństwo prób

Próba przejazdu **rusza maszyną**. Dlatego: wykonywana z niskim
`TrqGlobal`, wyłącznie przy narzędziu odsuniętym od materiału, w granicach
limitów programowych osi, z tym samym STOP-em co każdy inny ruch. Ekran
musi to mówić wprost, zanim ktoś kliknie „start próby".

## Rozszerzenie protokołu mostka

Trzy komendy, wszystkie w istniejącej konwencji (tekst, jedna linia,
`OK ...` / `ERR ...`):

```
SMARTLIST                       -> OK lista procedur i ich parametrów (JSON albo klucz=wartość)
SMART <procedura> <par>=<wart>… -> wykonuje procedurę; blokuje jak każdy ruch;
                                   OK STAN=DONE|RETREAT|COLLISION MAXTRQ=.. DROGA=..
STATUS                          -> dochodzi TRQX=.. TRQY=.. TRQZ=.. (moment zmierzony, %)
```

Rozszerzenie `STATUS` o moment jest przydatne **samo w sobie**, niezależnie
od procedur SMART — operator widzi na panelu, jak obciążony jest silnik.

## Ryzyka — wprost, bez zmiękczania

**1. To jest funkcja, która celowo dociska narzędzie do materiału.**
Pętla programowa **nie jest funkcją bezpieczeństwa**. Realnym
zabezpieczeniem pozostaje:
- `ILimits.TrqGlobal` ustawiany **przed** ruchem jako twardy sufit
  w samym serwie — pętla tylko dopracowuje zachowanie *wewnątrz* tego
  limitu, nigdy go nie zastępuje,
- sprzętowy E-stop i Global Stop na SC4-Hub (bez zmian).

Błąd w pętli nie może oznaczać ruchu z pełną siłą — dlatego `TrqGlobal`
ustawiamy zawsze, nawet jeśli procedura go „pilnuje" programowo.

**2. Przeliczenie momentu na siłę wymaga kalibracji, nie samego wzoru.**
Materiał źródłowy podaje `F = 2πM/p` — to zależność **idealna, bez tarcia**.
Realna śruba ma sprawność η (dla tocznej ok. 0,9; dla trapezowej bywa
0,3–0,5), więc `F = 2πMη/p`. Pominięcie η daje **zawyżoną** ocenę siły
faktycznie działającej na nóż. Wniosek: wartości procentowe momentu
traktujemy jako **nastawę do dobrania doświadczalnie** (próba na odpadzie),
a nie jako wyliczoną w niutonach siłę. Jeśli potrzebna jest realna liczba
w N — trzeba zmierzyć siłomierzem.

**3. Częstotliwość próbkowania — do zmierzenia, nie do założenia.**
Każdy odczyt `TrqMeasured` to zapytanie do węzła po magistrali SC.
Materiał źródłowy zakłada 10 ms; nasza pętla `waitMoves` chodzi dziś co
20 ms. **Ile realnie kosztuje odczyt momentu i jak gęsto da się próbkować
przy trzech osiach — trzeba zmierzyć na maszynie** przed projektowaniem
progów reakcji.

**4. Nie da się tego zbudować ani przetestować w tej sesji.** Mostek
kompiluje się przeciw `vendor/teknic/` (SDK poza repozytorium) — katalogu
`vendor/` tu nie ma. **Kod C++ powstaje tutaj, ale kompilacja i testy
wyłącznie na Twoim mini PC przy maszynie.** Warstwę serwera, format `.prg`
i edytor da się w pełni zrobić i przetestować bez sprzętu.

**5. Zmiana charakteru maszyny.** Dziś maszyna jest sterowana pozycją —
jedzie tam, gdzie każe program. Po tej zmianie część ruchu jest sterowana
reakcją na siłę, czyli **maszyna może zatrzymać się w innym miejscu niż
zapisane w programie**. To jest sens tej funkcji, ale trzeba to widzieć
na panelu (gdzie faktycznie stanęła oś i dlaczego), inaczej diagnostyka
„czemu detal wyszedł inaczej" będzie zgadywanką.

## Proponowane etapy

Kolejność dobrana tak, żeby **najpierw zweryfikować sprzęt najmniejszym
możliwym krokiem**, a dopiero potem budować na tym resztę.

**Etap 0 — odczyt momentu na panelu.** `STATUS` w mostku dostaje
`TRQX/TRQY/TRQZ` z `TrqMeasured` (PCT_MAX); serwer przekazuje to
w `/api/status`, panel operatora pokazuje obciążenie osi. Mały, bezpieczny
krok (nic nie jeździ inaczej), a **od razu weryfikuje całą drogę odczytu na
prawdziwej maszynie** i pozwala zmierzyć koszt próbkowania (ryzyko 3).
Przydatny sam w sobie — operator widzi, czy nóż się nie zakleszcza.

**Etap 1 — model definicji + ekran `/smart`.** `server/app/smart.py`
(definicja, rejestr procedur, walidacja, plik `config/smart.json`),
`GET/PUT /api/smart`, ekran `/smart` z listą, edycją, „zapisz jako"
i usuwaniem. **Cały do zrobienia i przetestowania bez sprzętu** — dlatego
idzie przed pracą w C++. Po nim widać na ekranie, jak funkcja będzie
wyglądać, zanim cokolwiek pojedzie.

**Etap 2 — ekran `/sila`: kontrola siły i kalibracja.** Podgląd obciążenia
na żywo, próba przejazdu wyznaczająca charakterystykę bazową osi, kalibracja
siłomierzem, pomiar realnej częstotliwości próbkowania; zapis do
`config/kalibracja.json`. Interfejs i logika w Pythonie/JS — **sensowne
liczby dopiero po etapie 0**, bo bez odczytu momentu nie ma czego rysować.
Ten ekran daje progi siły do definicji SMART; bez niego dobiera się je
na oślep.

**Etap 3 — `SMART` w programie technologa.** Format 5 `.prg` (kolumna
`SMART` z nazwą definicji), walidacja w `program.py`, wybór z listy
w edytorze. Symulator wykonuje `SMART` jako zwykły ruch na zadany dystans,
z ostrzeżeniem w logu, że siła nie jest kontrolowana. **Bez sprzętu.**

**Etap 4 — `SMART` w cyklu maszyny.** Nowy rodzaj kroku na ekranie `/cycle`,
te same definicje. **Bez sprzętu.**

**Etap 5 — procedura `ciecie_adaptacyjne` w mostku.** Algorytm z materiału
źródłowego, wpięty w `waitMoves`: `TrqGlobal` jako sufit, próbkowanie,
adaptacja prędkości, cofnięcie po przekroczeniu progu, wykrycie kolizji.
Plus komendy `SMART` i `SMARTLIST`. **Wymaga maszyny** — testowane
na odpadzie, od małych sił w górę. Dopiero tu funkcja zaczyna realnie
działać.

**Etap 6 — kolejne procedury.** `szukanie_kontaktu`, `miekki_docisk`,
`detekcja_kolizji` — programista dopisuje w C++, ekran `/smart` podchwytuje
je z rejestru automatycznie.

**Etap 7 (opcjonalny) — profil siły.** Zapis przebiegu momentu z cyklu
i analiza: ocena jakości cięcia, wykrywanie zużycia noża (siła rośnie
z cyklu na cykl). W materiale źródłowym opisane jako „podpis siły".

## Czego świadomie nie planuję

Materiał źródłowy wymienia też auto-kompensację temperatury plastiku
i auto-kalibrację pozycji wlewka. Obie wymagają danych, których maszyna
dziś nie ma (czujnik temperatury; wiarygodne wykrycie kontaktu przed
kalibracją). Wracamy do nich, gdy etapy 0–4 będą działać na produkcji.
