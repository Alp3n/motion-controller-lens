# Inspiracje z kontrolera MIC488 — co warto przenieść do nas

Analiza instrukcji obsługi **WObit MIC488** (programowalny, 4-osiowy kontroler
trajektorii, wersja instrukcji 1.74 z 10.11.2020) pod kątem funkcji, których
brakuje w naszym sterowniku. W `NOTATKI_FUNKCJONALNE.md` §10 wskazany jako
punkt odniesienia funkcjonalnego (tam zapisany jako „MD488").

Źródło: `zbyszek/controler ruchy x4_przykład_instrukcja.pdf` — numery stron
w nawiasach odsyłają do tego pliku.

## Czym jest MIC488 i gdzie leży różnica sprzętowa

MIC488 steruje do 4 napędami sygnałami **KROK/KIERUNEK/ZEZWOLENIE** (CLK/DIR/EN,
maks. 64 kHz) — czyli „ślepo" wysyła impulsy, nie wiedząc, czy silnik faktycznie
się poruszył. Opcjonalnie czyta 4 enkodery inkrementalne, żeby tę pozycję
**nadzorować z zewnątrz** i korygować błędy (str. 5–6, 16).

Nasze **ClearPath-SC to serwa z zamkniętą pętlą wewnątrz silnika** —
enkoder, regulator i kontrola momentu siedzą w samym napędzie, a my rozmawiamy
z nim komendą pozycji przez sFoundation. Cała warstwa MIC488 służąca do
pilnowania silnika krokowego (`POSCTR`, `KP`, `KP_SPEED`, `ENCRES`, `MOTRES`,
korekcja pozycji) jest u nas **niepotrzebna** — rozwiązuje problem, którego
nie mamy.

Wartość tego dokumentu leży gdzie indziej: MIC488 to **dojrzały produkt
z przemyślaną warstwą aplikacyjną** — programem ruchu, tablicą pozycji,
przerwaniami, diagnostyką. I to jest dokładnie ta warstwa, której u nas
jeszcze nie ma (tematy B–G w [`plan-rozwoju.md`](plan-rozwoju.md)).

## Co warto przenieść — funkcje ważne dla nas

### 1. Tablica pozycji — nazwane pozycje w pliku CSV (str. 25–26)

Najciekawszy pomysł w całej instrukcji. MIC488 trzyma **osobno program
(co robić) i tablicę pozycji (gdzie)**: do 200 rekordów, każdy zawiera
pozycje dla wszystkich 4 osi. Program odwołuje się do nich **po nazwie**:

```
MOVEPTP @POZYCJA_ZALADUNKU     // jedź do pozycji o tej nazwie
WAITPOS                        // czekaj aż wszystkie osie dojadą
```

Tablica zapisywana jest jako **plik `.csv`, edytowalny w Excelu** — dokładnie
ta sama filozofia, co nasz format `.prg` dla technologa.

**Dlaczego to dla nas ważne:** w temacie B (warstwa cyklu maszyny) potrzebujemy
miejsca na pozycje kroków cyklu — podawania, docisku, wyrzutu. Trzymanie ich
jako nazwanych pozycji w osobnym pliku, a nie wklejonych liczbowo w program,
oznacza, że po przezbrojeniu mechaniki poprawia się **jedno miejsce**, a nie
każde wystąpienie współrzędnej w programie. Ten sam rekord u nich obsługuje
też parametry interpolacji i okręgu — jeden mechanizm, wiele zastosowań.

### 2. Program ruchu ze skokami i podprogramami (str. 28–30, 40)

Język WBL ma etykiety, `JUMP`, `RETURN`, `IF/ELSE/ENDIF`, `WHILE/ENDWHILE`,
`SWITCH/CASE`, zmienne użytkownika i funkcje matematyczne. Struktura typowego
programu to **pętla główna wołająca podprogramy**:

```
PETLA_GLOWNA:
  JUMP SPRAWDZ_STOP
  JUMP WYKONAJ
JUMP PETLA_GLOWNA
```

**Dlaczego to dla nas ważne:** para `JUMP` + `RETURN` to jest dokładnie
mechanizm, który opisałeś w `NOTATKI_FUNKCJONALNE.md` §3 — „wstawienie
w dowolnym miejscu **skoku do wybranego podprogramu technologa**". MIC488
pokazuje, że to działa i jak minimalnie musi wyglądać: etykieta + skok +
powrót. Warto zwrócić uwagę na ich zastrzeżenie: jeśli podprogram kończy się
`JUMP`, a nie `RETURN`, **kasuje się stos powrotów** — to jest pułapka, którą
u siebie trzeba albo zablokować, albo jasno opisać.

### 3. Przerwania — reakcja na zdarzenie bez odpytywania (str. 30–31)

MIC488 potrafi przerwać wykonywaną komendę i skoczyć do etykiety, gdy:

- zmieni się stan wejścia (zbocze rosnące / opadające / oba),
- **zmieni się stan napędu** (`CFGINT_M1`…`CFGINT_M4`),
- minie 10 ms / 100 ms / 1000 ms (przerwanie cykliczne),
- ktoś zapisze rejestr przez Modbus.

Są dwa rodzaje: `INT_` przerywa **w trakcie** bieżącej komendy, `HARDINT_`
czeka na jej zakończenie.

**Dlaczego to dla nas ważne:** temat E (drzwi/osłona) i F (tryb automatyczny
przerywany E-stopem) to są dokładnie takie reakcje. Bez mechanizmu przerwań
kończy się na sprawdzaniu warunku w pętli, co działa wolno i nierówno.
Rozróżnienie „przerwij natychmiast" vs „dokończ ruch i przerwij" jest u nas
istotne — przerwanie w środku zagłębiania frezu to co innego niż przerwanie
między operacjami.

### 4. Konfigurowalna reakcja na błąd — `ERRCTR` (str. 15)

Przy wykryciu zatrzymania napędu MIC488 pozwala wybrać, **co ma się stać**:

| Wartość | Reakcja |
|---|---|
| `OFF` | brak reakcji |
| `ERRMODE0` | zatrzymanie napędu + zmiana statusu |
| `ERRMODE1` | jw. + **pauza wykonywanego programu** |
| `ERRMODE2` | jw. + **włączenie wyjścia OUT8** (sygnalizacja na zewnątrz) |

Do tego `ERR_TIME` — po jakim czasie zablokowania uznajemy to za błąd
(domyślnie 2000 ms).

**Dlaczego to dla nas ważne:** u nas reakcja na błąd jest dziś zaszyta na
sztywno (`ALARM` i koniec). Ten stopniowany model — od zignorowania, przez
pauzę, po sygnał na zewnątrz — jest dobrym wzorcem, zwłaszcza że nasze serwa
mają **natywną kontrolę momentu**, więc wykrycie kolizji będzie u nas
dokładniejsze niż u nich. Warto mieć gdzie tę informację skierować.

### 5. Status per oś, nie tylko per maszyna (str. 18–19, 45)

Każdy napęd ma własny rejestr statusu z czytelnym zestawem stanów:
`M_OFF`, `M_ON`, `M_SPEED`, `M_POS_SEARCH`, `M_POS_OK`, `M_POS_ERROR`,
`M_POS_HOMING`, `M_POS_CORRECTION`, `M_POS_LIM_L`, `M_POS_LIM_R`.

**Dlaczego to dla nas ważne:** dziś mamy jeden stan całej maszyny
(`INIT`/`NOT_HOMED`/`READY`/`RUNNING`/`ALARM`). Przy rozbudowie o dodatkowe
osie (podajnik, docisk — temat C) jeden wspólny stan przestanie wystarczać:
podajnik może jechać, gdy oś Z stoi. Osobne `M_POS_LIM_L` / `M_POS_LIM_R`
dla obu kierunków to też drobiazg, który u nas by się przydał — operator od
razu wie, w którą stronę oś się zablokowała.

### 6. Tryby bazowania — w tym bazowanie do oporu mechanicznego (str. 16)

Pięć trybów, ustawianych nastawą `HOME`:

- `HOME0` — dojazd do czujnika i stop,
- `HOME1` — dojazd, stop, powolny **odjazd do zaniku sygnału**,
- `HOME2` — dojazd, stop, powolny **przejazd za czujnik**,
- `HOME3` — **dojazd do mechanicznej blokady**, stop, powolny odjazd do
  sygnału INDEX z enkodera,
- `HOME4` — jak `HOME3`, ale od czujnika krańcowego.

Ruch powrotny zawsze na 20% prędkości bazowania.

**Dlaczego to dla nas ważne:** `HOME3` to jest odpowiedź na Twoje założenie
z `NOTATKI_FUNKCJONALNE.md` §1 — **bazowanie bez wyłączników krańcowych,
przez dojazd do oporu**. MIC488 pokazuje, że to jest normalna, produkcyjna
praktyka, a nie obejście. Nasze ClearPath-SC mają tę funkcję natywnie
(*hard stop homing*), konfigurowaną w ClearView — czyli u nas jest ona
lepsza niż tam, bo wykrycie oporu robi sam serwonapęd po momencie, a nie
zewnętrzny sterownik po enkoderze.

Wzorzec wart przeniesienia to **dwustopniowość**: szybki dojazd, potem powolny
odjazd na małej prędkości do dokładnego punktu. To właśnie daje powtarzalność.

### 7. Kreator konfiguracji osi (str. 15, 17)

Zamiast kazać liczyć przelicznik ręcznie, MIC488 ma okno, w którym podaje się:
typ ruchu (liniowy/obrotowy), jednostki, typ i parametry napędu, przełożenie —
a program **wylicza `GEAR` sam** (przykład: 64 · 200 / 5 mm = 2560).

**Dlaczego to dla nas ważne:** w [`konfiguracja-osi.md`](konfiguracja-osi.md)
zapisaliśmy wprost ryzyko: „limity nie chronią przed złym przełożeniem — przy
błędnym `mm/obr` oś jedzie o inny dystans, niż wynika z zadanej pozycji".
Kreator, który liczy tę wartość z rzeczy, które monter zna z maszyny (skok
śruby, przełożenie przekładni), usuwa najczęstsze źródło tego błędu. To tania
zmiana o dużym efekcie.

### 8. Symulacja wejść i wyjść w oknie diagnostycznym (str. 22)

Okno podglądu I/O pozwala **ręcznie przełączać stany wejść i wyjść** — i co
istotne: *„Symulacja wejść działa także w funkcjach czujników bazujących
i krańcowych"*.

**Dlaczego to dla nas ważne:** mamy symulator maszyny (`MACHINE_MODE=sim`),
ale nie mamy sposobu, żeby z panelu wymusić stan pojedynczego sygnału. Przy
testowaniu logiki drzwi, Global Stop czy czujnika obecności detalu to jest
różnica między „da się przetestować przy biurku" a „trzeba iść do maszyny
i wpiąć zworkę".

### 9. Debugowanie programu ruchu (str. 26–27)

Program można uruchomić, **wstrzymać, wykonywać krokowo**, podejrzeć aktualnie
wykonywaną linię (zaznaczoną w edytorze) i wartości do 12 wybranych zmiennych
w czasie pracy. Są też breakpointy (od firmware 1.10).

**Dlaczego to dla nas ważne:** temat B zakłada, że admin będzie definiował
cykl maszyny. Bez podglądu „która linia się teraz wykonuje i jakie są
wartości" diagnostyka takiego cyklu sprowadza się do zgadywania. W naszym
edytorze technologa mamy już podgląd toru — to jest naturalne rozszerzenie
w stronę wykonania.

### 10. Drobiazgi warte zapamiętania

- **`PULSE(wyjście, czas)`** (str. 31) — zmienia stan wyjścia po zadanym
  czasie, bez blokowania programu. Proste, a oszczędza pisania obsługi
  czasu przy każdym impulsie (np. wyrzutnik pneumatyczny, lampka).
- **Liczniki czasu** (str. 37) — 16 timerów o podstawie 10 ms i 16 o podstawie
  1 s. Do mierzenia czasu cyklu (Twoje założenie ~10 s/detal) i do timeoutów.
- **Filtracja i polaryzacja wejść** (str. 19) — `IO_FILTER` (minimalny czas
  sygnału) i `IO_LEVEL` (czy aktywny jest stan wysoki czy niski). Ustawienie
  „aktywny przy braku sygnału" to standardowy sposób na wykrycie **przerwanego
  przewodu** czujnika.
- **Autostart programu** (str. 23) — program z pamięci uruchamiany
  automatycznie po włączeniu zasilania albo aktywacją wejścia.
- **Skalowanie wejścia analogowego** (str. 19, 32) — `AIN_LOVAL`/`AIN_HIVAL`
  przeliczają 0–10 V na dowolny zakres, wartość idzie wprost do zadawania
  prędkości. Wzorzec pod potencjometr prędkości na pulpicie.
- **Pamięć nieulotna na żądanie** (str. 30) — rejestry 1000–2000 zapisywane
  do pamięci trwałej dopiero komendą, nie przy każdej zmianie. U nas
  odpowiednikiem jest zapis `config/axes.json` — warto zachować tę samą
  zasadę: zapis świadomy, nie ciągły.

## Czego świadomie nie kopiujemy

| Funkcja MIC488 | Dlaczego nie |
|---|---|
| Sterowanie KROK/KIERUNEK | ClearPath-SC sterujemy komendą pozycji przez sFoundation; impulsy są nam niepotrzebne. |
| Nadzór pozycji z enkodera (`POSCTR`, `KP`, `KP_SPEED`, `MOTRES`, `ENCRES`) | To proteza dla silników krokowych gubiących kroki. Nasze serwa mają pętlę zamkniętą wewnątrz. |
| Limity pamięci (4000 komend, 200 pozycji, 2000 rejestrów) | To ograniczenia układu wbudowanego. Na PC nie obowiązują — kopiujemy **pojęcia**, nie limity. |
| Modbus jako główne API | Mamy REST + WebSocket, lepiej dopasowane do MES i panelu WWW. Modbus ma u nas sens wyłącznie do rozmowy z urządzeniami (patrz niżej). |
| Interpolacja kołowa (`DOCIRC`, `DOARC`) | Grupa B operacji `.prg` została świadomie odłożona — przy ocinaniu wlewków odcinki wystarczają ([`nowe-operacje-programu.md`](nowe-operacje-programu.md)). Wracamy do tego tylko, jeśli łuki okażą się potrzebne. |

Warto natomiast odnotować, jak oni rozwiązali **interpolację wieloosiową**
(str. 34): przy `MOVELIN2` parametry ruchu bierze się z **osi o największym
dystansie do przejechania**, a pozostałe osie są przeliczane względem niej.
To jest sensowniejsze niż to, co robi dziś nasz mostek (dobieranie prędkości
tak, by osie skończyły jednocześnie) i może się przydać przy weryfikacji
pomiarowej toru operacji `LINIA` — zadanie otwarte w
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md).

## Znalezione ryzyko: SC4-Hub nie ma wejść/wyjść, których wymagają nasze plany

Porównanie z MIC488 obnaża konkretną lukę sprzętową, którą trzeba rozstrzygnąć,
zanim zaczniemy kodować tematy D i E.

**MIC488 ma:** 20 wejść cyfrowych, 8 wyjść tranzystorowych (200 mA), 2 wejścia
analogowe 0–10 V, moduł rozszerzeń +8/+8, 3 porty szeregowe (str. 46).

**SC4-Hub ma:** 2 wyjścia (`BRAKE_0`, `BRAKE_1`), 1 wejście Global Stop
i 2 wejścia ogólnego przeznaczenia na każdym węźle silnika — czyli 6 przy
trzech serwach ([`sterownik-sc4-hub.md`](sterownik-sc4-hub.md)).

Konsekwencje, wprost:

- **Sterowania prędkością wrzeciona przez PWM nie da się zrobić na SC4-Hub** —
  hub nie ma wyjścia PWM ani analogowego. Założenie z
  `NOTATKI_FUNKCJONALNE.md` §4 wymaga dodatkowego sprzętu. Realne opcje do
  rozważenia: **falownik (VFD) sterowany po Modbus RTU** z PC — na PC to
  proste, a MIC488 pokazuje ten wzorzec (tryb Modbus master, str. 32);
  moduł I/O po USB/Ethernet; albo osobny sterownik wrzeciona z wejściem
  analogowym plus przetwornik.
- **Wyjść jest dwa i oba mogą być już potrzebne** — jedno na włącz/wyłącz
  wrzeciona. Podajnik, wyrzutnik, lampka sygnalizacyjna, sygnał błędu
  (odpowiednik `ERRMODE2`) nie mają gdzie się podłączyć.
- **Obciążalność `BRAKE_0`/`BRAKE_1` pod stycznik wrzeciona pozostaje
  niesprawdzona** — to zadanie już jest na liście w
  [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md), ale teraz widać, że nie jest
  to drobiazg: od tego zależy, czy w ogóle mamy czym załączyć wrzeciono.

To nie podważa wyboru SC4-Hub — jako sterownik **ruchu** jest znacznie lepszy
od MIC488 (serwa z pętlą zamkniętą, kontrola momentu, natywne bazowanie do
oporu). Ale SC4-Hub jest hubem **komunikacyjnym do silników**, nie sterownikiem
maszyny z bogatym I/O, i tej roli nie udźwignie. Trzeba świadomie zdecydować,
skąd weźmiemy resztę wejść i wyjść.

## Uwaga o bezpieczeństwie

Deklaracja zgodności MIC488 (str. 49) obejmuje **wyłącznie dyrektywę EMC**
(2004/108/WE) — kompatybilność elektromagnetyczną. Instrukcja nie deklaruje
dla żadnego wejścia kategorii bezpieczeństwa. Czyli dokładnie ta sama sytuacja,
co z Global Stop w SC4-Hub: **funkcja sterowania, nie funkcja bezpieczeństwa**.
Żaden z tych sterowników nie zastępuje niezależnego, certyfikowanego obwodu
E-stop/kurtyn — i porównanie z MIC488 niczego tu nie zmienia.

## Mapowanie na nasz plan

| Punkt z tej analizy | Temat w [`plan-rozwoju.md`](plan-rozwoju.md) |
|---|---|
| Tablica pozycji, program ze skokami i podprogramami | **B** — model cyklu maszyny i programu detalu |
| Status per oś, tryby bazowania, kreator osi | **C** — osie i konfiguracja ruchu |
| Reakcja na błąd (`ERRCTR`), timery, `PULSE` | **C** / **F** |
| Sterowanie wrzecionem (PWM — patrz ryzyko wyżej) | **D** — wrzeciono |
| Przerwania, filtracja i polaryzacja wejść | **E** — drzwi/osłona, **F** — tryby pracy |
| Symulacja I/O, krokowe wykonanie, podgląd zmiennych | **G** — ekrany |
| Braki I/O w SC4-Hub | **nowy temat — do rozstrzygnięcia przed D i E** |
