# Prowadzenie za rękę i baza nazwanych punktów PTP

Analiza wykonalności trybu "antygrawitacyjnego" (operator pcha oś ręką,
serwo płynnie podąża za pchnięciem) i decyzja o faktycznie zbudowanym
zakresie. Powiązane: [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md),
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md), [`zmiany/luzowanie-osi.md`](zmiany/luzowanie-osi.md).

**Ryzyko sprzętowe potwierdzone 2026-09-07: zbyt niski limit momentu
(np. 2%) potrafi wywołać twardy fault serwa** ("Node ... Move blocked by
drive shutdown/disable/limit", ten sam błąd co wcześniej przy cięciu na
bardzo niskich limitach) — wymaga Kasuj alarm. Szczegóły i zalecenia:
[`zmiany/reset-nie-czyscil-axisenabled.md`](zmiany/reset-nie-czyscil-axisenabled.md),
aktualizacja 2026-09-07. Zacznij od wyższego limitu (8-10%).

## Cel zgłoszony przez użytkownika (2026-09-06)

Operator chce fizycznie pchać oś w jednym z kierunków, maszyna ma to
"wyczuć" i wykonać ruch w tym kierunku (prawdziwy tryb podatny/compliant,
jak w cobocie, z regulowanym oporem). W trakcie takiego prowadzenia zapisuje
bieżącą pozycję jako nazwany punkt. Punkty mają trafić na listę z pełnym
CRUD (dodaj/edytuj/usuń) i być wybieralne z listy w operacji PUNKT programu
technologa.

## Wynik badania: prawdziwy tryb podatny jest NIEOSIĄGALNY na tym sprzęcie

Sprawdzone wyczerpująco w nagłówkach SDK
(`vendor/teknic/Linux_Software/sFoundation/inc/inc-pub/*.h`):

- Jedyne metody startu ruchu sterowalne z hosta to `MovePosnStart` (i warianty:
  `MovePosnHeadTailStart`, `MovePosnAsymStart`) oraz `MoveVelStart`
  (`pubCpmCls.h`, klasa `CPMmotion`/`IMotion`). **Brak jakiegokolwiek
  `MoveTrqStart`/trybu komendowania momentem** — przeszukanie całego
  katalogu `inc-pub` pod kątem `MoveTrq|TorqueMode|TrqMode|ForceMode` nie
  dało wyników.
- Moment istnieje w API wyłącznie jako **limit** (`ILimits.TrqGlobal`) i
  **odczyt** (`Motion.TrqMeasured`) — ogranicza ruch w Position Mode,
  nie zastępuje go trybem sterowania momentem.
- `TPIO_MODE_IN` (`pubIscRegs.h:2899,2915`, komentarz "Torque mode enable")
  to bit **statusowy/diagnostyczny** wewnątrz `tpIOreg` — rejestr wspólny
  dla całej rodziny ClearPath (w tym starszych MC/SD ze Step&Dir), czytający
  stan fizycznej linii sprzętowej, **nie** przełącznik trybu programowalny
  z poziomu SDK.
- `docs/sterownik-sc4-hub.md` potwierdza fakt architektoniczny: komunikacja
  z serwami serii SC idzie własnym protokołem szeregowym Teknica przez
  SC4-Hub/USB (sFoundation), nie przez Step&Dir — więc nawet mechanizmy
  trybu z rodziny Step&Dir/Analog nie mają tu zastosowania.
- Wcześniejsza, niezależna analiza projektu (`mozliwosci-clearpath-sc.md`,
  oparta na pełnym manualu ClearPath-SC rev. 1.45) dochodzi do tego samego
  wniosku: moment "zwykle ustawia się przez ClearView i nie zmienia w
  trakcie aplikacji" — żadna wzmianka o trybie momentu jako alternatywie
  dla Position Mode.

**Wniosek: nie da się zbudować serwa aktywnie "podążającego" za ręką
operatora (admittance/compliant control z hosta) na tym sprzęcie przez
sFoundation SDK.** To ograniczenie API/architektury drive'u, nie kwestia
nakładu pracy.

## Doprecyzowanie operatora (2026-09-07): przybliżenie przez niski limit momentu

Pierwsza wersja tego ekranu (opisana niżej w historii zmian) użyła
**RELEASE/HOLD** — pełne zdjęcie momentu. Operator doprecyzował, że nie
o to mu chodziło: silnik ma zostać **włączony**, tylko z **niskim limitem
momentu** (np. 5%). Dokładny opis: "gdy wybiorę jakąś oś to silnik ma być
włączony i ustawmy mały moment np 5%, jak nacisnę na oś to odczytasz
zwiększenie siły, jak pozycja zmieni się to zaczynasz jechać z prędkością
proporcjonalną do siły i sprawdzasz ustawienia limitu dla tego kierunku."

To da się zbudować z **już istniejących** elementów, bez czekania na
cokolwiek od Teknica:

- `TRQLIMIT` (limit momentu, `zmiany/limit-momentu-sprzet.md`) — obniżany
  na czas prowadzenia, przywracany po zakończeniu.
- `TRQX/Y/Z` (odczyt momentu, etap 0 tematu K) — do podglądu na ekranie.
- Pozycja z `STATUS` — do wykrycia, że serwo "przegrywa" z naciskiem: przy
  niskim limicie momentu serwo w Position Mode nie potrafi w pełni
  utrzymać zadanej pozycji pod zewnętrzną siłą większą niż ten limit,
  więc rzeczywista pozycja zaczyna odjeżdżać od ostatnio zadanej.
- `JOG` (już istniejąca komenda ruchu pojedynczej osi) — do "doganiania"
  wykrytego odchylenia nowym, małym ruchem w tym samym kierunku.

**Mechanizm (`hand_guide_step()` w `app/machine.py`):** co ~150 ms
przeglądarka woła `/api/machine/hand-guide/tick`. Serwer liczy odchylenie
(rzeczywista pozycja − ostatnio zadana). Poniżej martwej strefy (0.05 mm)
nic nie robi. Powyżej — wysyła `JOG` w kierunku odchylenia, z dystansem
stałym (0.3 mm) i posuwem rosnącym proporcjonalnie do wielkości odchylenia
(50–600 mm/min, nasycenie przy 3 mm). To **przybliżenie** trybu podatnego,
nie prawdziwe sterowanie momentem — może być mniej płynne niż prawdziwy
compliant control, do oceny/dostrojenia progów przy pierwszym teście na
sprzęcie.

**Bezpieczeństwo:** limit momentu (ustawiany przez operatora, 0.5–20%) jest
głównym ograniczeniem — niezależnie od błędów w logice doganiania, siła,
jaką oś może wywrzeć, zostaje ograniczona przez `TrqGlobal`. Dodatkowo:
`JOG` respektuje limity programowe osi (`_check_soft_limit`) tak samo jak
zwykły ręczny JOG. Wzorem przytrzymania JOG na panelu operatora, pętla
działa jako "martwy człowiek" po stronie przeglądarki (`tick()` w pętli
`setTimeout`) — zamknięcie karty albo utrata sieci po prostu przestaje
generować kolejne wywołania, żaden wątek nie zostaje aktywny po stronie
serwera.

**Wcześniej rozważane RELEASE/HOLD** (`zmiany/luzowanie-osi.md`) — pełne
zdjęcie momentu, zero oporu — zostało odrzucone przez operatora jako
niewłaściwe podejście, ale przy okazji ustalono ważny fakt: **wszystkie
trzy osie tej maszyny są samohamowne** (nie opadają pod własnym ciężarem
bez momentu, mechaniczna cecha przekładni/śruby) — co i tak jest istotne
dla oceny bezpieczeństwa niskiego limitu momentu na Z (najgorszy scenariusz
przy zbyt niskim limicie to unieruchomienie osi, nie niekontrolowany spadek).

## Zbudowany zakres

1. **Baza nazwanych punktów** (`server/app/punkty.py`, `config/punkty.json`,
   `/api/punkty`, ekran `/punkty`) — pełny CRUD (dodaj/edytuj/usuń/"zapisz
   jako"), ten sam wzorzec co definicje SMART (`app/smart.py`). Wiązanie
   punktu z operacją programu jest **jednorazowe** (decyzja 2026-09-06):
   wybór z listy w edytorze wypełnia pola X/Y/Z operacji PUNKT, a
   późniejsza zmiana punktu w bazie nie wpływa na już zapisane programy.
2. **Ekran `/nauczanie`** — przycisk "Prowadź X/Y/Z" (start/stop) + pole
   limitu momentu, podgląd pozycji i momentu na żywo, pole nazwy + "Zapisz
   punkt". `POST /api/machine/hand-guide/start|tick|stop` w `main.py`,
   logika w `Machine.hand_guide_start/tick/stop` (`app/machine.py`) —
   wspólna dla symulatora i sprzętu, tylko ustawianie/przywracanie limitu
   momentu jest nadpisane w `SC4HubMachine` (symulator nie ma realnej siły
   zewnętrznej, więc nic tam nie ustawia).
3. **Picker w edytorze programu** (`editor.js`) — przy operacji PUNKT
   dodatkowy `<select>` z listą nazwanych punktów; wybór wypełnia X/Y/Z
   tego wiersza i wraca do stanu "— punkt —" (jednorazowe działanie, nie
   trwałe pole).

## Pliki

- `server/app/punkty.py` — model, walidacja, plik `config/punkty.json`.
- `server/app/config.py` — `PUNKTY_FILE`.
- `server/app/machine.py` — `hand_guide_step()` (czysta funkcja decyzyjna),
  `Machine.hand_guide_start/tick/stop`, nadpisania `_hand_guide_set_torque`/
  `_hand_guide_restore_torque` w `SC4HubMachine`.
- `server/app/main.py` — `GET/PUT /api/punkty`, `POST /api/machine/hand-guide/*`,
  strony `/punkty` i `/nauczanie`.
- `server/app/static/punkty.html`, `punkty.js` — ekran CRUD listy punktów.
- `server/app/static/nauczanie.html`, `nauczanie.js` — ekran prowadzenia za rękę.
- `server/app/static/editor.js` — picker punktów w operacji PUNKT.
- Linki nawigacyjne dopisane w `index.html`, `smart.html`, `sila.html`,
  `cycle.html`, `editor.html`.
- `server/tests/test_punkty.py` — 13 testów (model, plik, API punktów).
- `server/tests/test_hand_guide.py` — 13 testów (funkcja decyzyjna, symulator).
- `server/tests/test_sc4hub.py` — 2 testy (TRQLIMIT ustawiany/przywracany).
- `server/tests/test_api.py` — 5 testów endpointów `hand-guide`.

## Naprawiony błąd (2026-09-07): nieaktualna pozycja w pętli doganiania

Pierwszy test na sprzęcie: oś X „niby działała", ale pozostałe osie nie
chciały się ruszyć, a zatrzymanie po puszczeniu było opóźnione ("jedzie
sam bez kontroli, zatrzymuje się po jakimś czasie"). Przyczyna:
**`SC4HubMachine.jog()` nie aktualizuje `self.status.x/y/z` po ruchu** —
robi to dopiero osobna pętla `_poll_loop()` w `main.py`, co 200 ms,
całkowicie niezależnie od wywołań `jog()`. `hand_guide_tick()` zapamiętywał
więc jako "cel doganiania" **nieaktualną** pozycję, a kolejne porównania
odchylenia wypadały z przestarzałych danych — stąd niekontrolowany dalszy
ruch (porównanie nie odzwierciedlało już rzeczywistości) i, przy innym
zbiegu czasowym `_poll_loop`, brak wykrycia jakiegokolwiek nacisku na
pozostałych osiach. W symulatorze błąd był niewidoczny, bo tam pozycja
aktualizuje się synchronicznie w miejscu ruchu.

**Naprawa:** `hand_guide_tick()` woła `await self.poll_status()` zarówno
PRZED odczytem bieżącej pozycji, jak i PO wykonaniu ruchu doganiającego —
dla `SC4HubMachine` to realne zapytanie STATUS do mostka; dla symulatora
to nadal no-op (pozycja już świeża). Dodano też limit prędkości doganiania
(`max_feed`) jako parametr ustawiany przez operatora na ekranie — różne
osie mają różne tarcie i wymagają innej prędkości.

## Druga korekta (2026-09-07): sygnał to moment, nie przesunięcie

Pierwszy fizyczny test: oś Y działała "przez chwilę dość dobrze", X miała
wyczuwalne szarpnięcia, Z "bardzo ciężko" (ledwo reagowała). Operator
zaproponował inny model: **"siła powyżej limitu → jedziemy X mm; jeśli
siła nadal powyżej limitu → jedziemy dalej; jak nie → hamujemy"** — i
zapytał, ile razy na sekundę da się to sprawdzać.

**Zmiana:** główny sygnał „czy ktoś naciska" to teraz **odczyt momentu
względem ustawionego limitu** (próg: 80% limitu), nie przesunięcie
pozycji. Przesunięcie zostaje tylko do ustalenia KIERUNKU (potrzebny
choćby ślad ruchu). To tłumaczy, dlaczego Z ledwo reagowała: jeśli ta oś
jest mechanicznie sztywniejsza, realny nacisk mógł nie dawać wystarczającego
przesunięcia pozycji, żeby przekroczyć starą martwą strefę (0.05 mm),
mimo że moment już się nasycał na limicie. Krok stał się **stały**
(dystans + posuw, oba ustawiane przez operatora na ekranie) zamiast
skalowanego do wielkości odchylenia — moment i tak nasyca się na limicie
i nie niesie dalej informacji "jak mocno", więc skalowanie po odchyleniu
nie miało solidnej podstawy.

**Odpowiedź na pytanie o częstotliwość:** protokół mostka pozwala na
JEDNĄ komendę na raz (`_command()` serializuje przez `asyncio.Lock`,
`docs/zmiany/stop-czekal-za-statusem.md`) — nie da się odczytać momentu
W TRAKCIE trwania ruchu JOG, tylko PRZED i PO. Częstotliwość sprawdzania
jest więc z grubsza `1 / (czas jednego kroku)`, gdzie czas kroku ≈
`dystans_mm / posuw_mm_na_min * 60s` (plus koszt samych komend STATUS —
zmierzony wcześniej na ~7ms dla 3 osi naraz, pomijalny wobec czasu ruchu).
Przykłady dla domyślnych 1 mm:

| posuw [mm/min] | czas kroku | sprawdzeń/s |
|---:|---:|---:|
| 400 (domyślnie) | ~150 ms | ~6-7 |
| 200 | ~300 ms | ~3 |
| 800 | ~75 ms | ~12-13 |

Mniejszy krok (np. 0.3 mm) przy tym samym posuwie proporcjonalnie zwiększa
częstotliwość (krótszy pojedynczy ruch), ale każdy krok to pełny cykl
rozpędzenie-hamowanie JOG-a — więcej kroków na sekundę oznacza więcej
takich cykli, czyli bardziej "szarpaną" motorykę. To jest **nieunikniony
kompromis przy tej architekturze** (jedno połączenie, jedna komenda na
raz): żeby sprawdzać częściej BEZ szarpania, trzeba by umieć przerwać
trwający ruch na podstawie świeżego odczytu siły w trakcie jego trwania —
a to wymagałoby drugiego, równoległego połączenia do mostka (zmiana w
C++) albo pętli czasu rzeczywistego bezpośrednio w mostku (temat SMART,
etap 5, dalej niezaimplementowany). Krok i posuw są teraz parametrami
ustawianymi przez operatora właśnie po to, żeby dało się ten kompromis
dostroić osobno dla każdej osi bez zmiany kodu.

## Trzecia wersja (2026-09-07): moment względem spoczynku, nie limitu

Po fault-cie opisanym wyżej operator zaakceptował, że RELEASE/HOLD
wystarcza do samego pozycjonowania, ale chciał jeszcze przetestować
prowadzenie z wyczuwaniem siły — z inną koncepcją: **silniki zostają na
normalnym (pełnym) limicie momentu przez cały czas**, nigdy go nie
obniżamy. Zamiast tego program zapamiętuje odczyt momentu w spoczynku
(w chwili startu) i wyłapuje **małą zmianę** względem niego (bufor
histerezy, np. 0.3%) — nawet przy pełnym momencie realny nacisk ręką
lekko podnosi obciążenie, bo serwo się mu przeciwstawia. To strukturalnie
wyklucza fault z drugiej wersji: TrqGlobal nigdy nie schodzi poniżej
normalnej, bezpiecznej wartości z profilu.

**Mechanizm typu "jedno naciśnięcie = jeden krok" (edge-triggered):**
- Stan „uzbrojony" (armed): czekamy na PIERWSZE przekroczenie progu.
- Przekroczenie progu → jeden krok JOG (stały dystans + posuw, kierunek ze
  znaku zmiany) → stan „rozbrojony" (nie reagujemy na dalsze trzymanie).
- Powrót momentu w okolice spoczynku → ponowne uzbrojenie → gotowe na
  KOLEJNE, osobne naciśnięcie.

To odpowiada wprost opisowi operatora: "jak wyczujemy że siła wzrasta lub
maleje to robimy ruch... jak siła spadnie to się zatrzymujemy... dopiero
kolejne naciśnięcie powoduje następną iterację." Implementacja:
`hand_guide_step()` w `app/machine.py` (czysta funkcja, edge detection),
`Machine.hand_guide_start/tick/stop` — bez żadnych nadpisań w
`SC4HubMachine` (nie ma już nic związanego z TRQLIMIT do wysyłania/
przywracania, więc kod jest teraz prostszy niż w drugiej wersji).

## Poprawka debounce (2026-09-08): pojedynczy krok wracał sam

Pierwszy test trzeciej wersji na sprzęcie: operator zgłosił, że po
naciśnięciu widać delikatny ruch, ale oś **sama wraca do poprzedniej
pozycji** — nie dawało się jej przestawić ani na plus, ani na minus. Log
pokazał dokładny wzorzec: `JOG Z 1.000`, ~2s później `JOG Z -1.000` —
krok w jedną stronę, zaraz potem krok DOKŁADNIE w przeciwną, mimo
JEDNEGO naciśnięcia. Najbardziej prawdopodobna przyczyna: przejściowy
odczyt momentu tuż po zakończeniu ruchu (hamowanie na końcu profilu
JOG-a, osiadanie mechaniki) mylnie odczytany jako NOWE, przeciwne
naciśnięcie — dotychczasowy mechanizm uzbrajał się z powrotem po
JEDNYM odczycie w granicach progu, więc pojedynczy przejściowy skok
wystarczał, żeby złapać kolejny (fałszywy) krok w przeciwną stronę.

**Naprawa:** ponowne uzbrojenie wymaga teraz `HAND_GUIDE_SETTLE_TICKS`
(domyślnie 3) KOLEJNYCH odczytów w spoczynku z rzędu, nie jednego.
Pojedynczy przejściowy skok tuż po ruchu zeruje licznik uspokojenia, ale
sam nie może wywołać kolejnego kroku — trzeba naprawdę poczekać, aż oś
się uspokoi. Kod: `hand_guide_step()` w `app/machine.py` (parametr
`settle_count` zamiast prostego `armed`).

## Uwagi

- **Nie zweryfikowane jeszcze fizycznie po tej poprawce** — logika (kiedy reagować, w którą
  stronę, z jaką prędkością) jest pokryta testami, ale progi (martwa strefa
  0.05 mm, nasycenie przy 3 mm, posuw 50–600 mm/min) są **prowizoryczne** i
  prawie na pewno będą wymagały dostrojenia po pierwszym realnym teście —
  to nie jest parametr bezpieczeństwa (tym jest limit momentu), tylko
  kwestia tego, czy prowadzenie "czuje się" dobrze.
- Gdyby w przyszłości pojawiła się potrzeba prawdziwego trybu podatnego —
  jedyna droga to prawdopodobnie funkcje poza publicznym API Teknica dla
  tej rodziny napędów (kontakt z producentem) albo inny sprzęt; nie ma
  sensu do tego wracać bez nowych informacji od Teknica.
