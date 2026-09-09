# Propozycja: architektura wielu sterowników (drajwerów) osi

Zgłoszenie użytkownika (2026-09-09): planowana oś czwarta na serwie
**Feetek, sterowanie PWM, 45 kg**, oraz w dalszej perspektywie moduł
**Teknic ClearCore** do silników krokowych i I/O. Cel: dodawać nowe typy
napędów bez przebudowy aplikacji. **To propozycja do przeczytania i
decyzji, nie gotowy kod** — podobnie jak
[`propozycja-head-tail-asymetria.md`](propozycja-head-tail-asymetria.md).

## Co dziś stoi na przeszkodzie

`Machine` (`server/app/machine.py`) to dziś **jedna klasa aktywna na raz**
(`SimulatedMachine` albo `SC4HubMachine`), obsługująca WSZYSTKIE osie
jednym protokołem/połączeniem (`jog`/`home`/`go_to_zero`/... na poziomie
całej maszyny, nie pojedynczej osi). X i Y są dodatkowo połączone sprzętowo
w jedną komendę `MOVEXY` — mostek nie rusza nimi osobno — ale to dotyczy
wyłącznie X/Y, nie osi dodatkowych.

Otwarty punkt z `kanban.md` (temat C): „rozszerzyć protokół mostka o
`AXCFG` i komendy ruchu dla osi spoza X/Y/Z" zakładał, że **każda** oś,
nawet dodatkowa, jedzie przez ten sam mostek SC4-Hub/Teknic. Ta propozycja
to zmienia: oś 4 (Feetek) w ogóle nie przechodzi przez mostek Teknica.

## Rekomendacja: driver per oś, nie driver per maszyna

Wspólny interfejs `AxisDriver` (`move_to`/`jog`/`home`/`read_status`, z
częścią pól/metod **opcjonalną** — patrz niżej) i osobna implementacja na
typ sprzętu: `TeknicSC4HubDriver` (dzisiejszy `SC4HubMachine`, nadal
obsługuje X/Y/Z razem, bo `MOVEXY` tego wymaga), `FeetekPwmDriver`,
`ClearCoreDriver`. `Machine` przestaje BYĆ jednym sterownikiem, zaczyna
SKŁADAĆ drivery po nazwie osi (`self.drivers: dict[str, AxisDriver]`,
z X/Y/Z wskazującymi na ten sam obiekt Teknica).

**Zalety:** X/Y/Z (krytyczne dla toru cięcia) zostają bez zmian na
sprawdzonym Teknicu; nowe osie faktycznie zaczynają się ruszać (dziś się
NIE ruszają — zapisują się tylko w konfiguracji, patrz `kanban.md` temat
C) bez czekania na rozszerzenie protokołu mostka (C++); dodanie kolejnego
typu napędu w przyszłości to nowa klasa driver + wpis w konfiguracji, nie
zmiana rdzenia aplikacji.

## Największy kompromis: możliwości sterowników są NIERÓWNE

To nie jest tylko kwestia różnych protokołów transportowych — to różne
**kategorie** sprzętu:

- **ClearPath-SC (dziś, X/Y/Z):** serwo z enkoderem, zamknięta pętla,
  odczyt momentu (`TrqMeasured`), limit momentu jako twardy sufit,
  faulty/alarmy zgłaszane przez sterownik.
- **Feetech SM45BL (skorygowane 2026-09-09 — konkretny model podany przez
  użytkownika):** to **nie** jest hobbystyczne serwo RC sterowane gołym
  sygnałem PWM, jak pierwotnie założyłem niżej w tym dokumencie na
  podstawie samego słowa „PWM" w pierwszym zgłoszeniu — to przemysłowy
  serwonapęd **brushless z komunikacją Modbus RTU** (RS485, rejestry).
  Modbus RTU zwykle daje hostowi odczyt pozycji i często prądu/momentu z
  powrotem przez rejestry — więc ta oś prawdopodobnie **nie** jest głucha
  jak zakładałem. **Nadal do potwierdzenia u źródła** (dopiero instrukcja/
  mapa rejestrów SM45BL rozstrzygnie, jakie dane faktycznie wraca i w jakim
  trybie pracy — pozycja/prędkość/moment), patrz materiały do przygotowania
  niżej.
- **ClearCore (kroki + I/O):** silniki krokowe to zwykle sterowanie w
  pętli otwartej **bez enkodera** (chyba że dokupiony osobno) — brak
  informacji zwrotnej o rzeczywistej pozycji, zgubienie kroków pod
  obciążeniem jest niewykrywalne przez oprogramowanie.

**Konsekwencja dla wspólnego interfejsu:** `AxisDriver` musi mieć
pola/metody **opcjonalne** (nie każdy driver wspiera odczyt momentu, nie
każdy wspiera limit siły), a ekrany muszą jawnie pokazywać operatorowi,
których funkcji dana oś **nie ma** — dokładnie jak dziś `/diagnostics`
świadomie pokazuje „czego nie ma" (drzwi, moment na sprzęcie), zamiast
fałszywie zielonych pól.

## Pytania do ustalenia, zanim zacznę kodować

1. Czy oś 4 (Feetek) i przyszłe osie ClearCore biorą udział w programie
   technologa/cyklu (`RUCH`/`PROGRAM`) na równi z X/Y/Z, czy są **osiami
   pomocniczymi** (podajnik, docisk) sterowanymi tylko z panelu/JOG i
   konfiguracji cyklu? To determinuje, ile logiki wykonawczej
   (`_run_program`, `_execute_cycle_step`) w ogóle musi wiedzieć o wielu
   driverach naraz.
2. Czy Feetek faktycznie nie daje żadnego feedbacku pozycji/momentu —
   proszę potwierdzić z dokumentacji konkretnego modelu/sterownika PWM,
   zanim to na stałe założę w kodzie (zasada weryfikacji faktów u źródła
   z `CLAUDE.md`). To zmienia zakres tego, co ta oś w ogóle może robić.
3. Jak fizycznie podłączony będzie Feetek do tego komputera — osobny
   mikrokontroler/moduł PWM po USB/UART (host wysyła komendę do niego,
   jak dziś do mostka Teknica), czy bezpośrednio z GPIO hosta? Determinuje,
   czy trzeba pisać drugi „mini-mostek" w stylu `bridge/`, czy driver
   rozmawia wprost.
4. ClearCore do steppera/IO — osobny fizyczny kontroler (Ethernet? USB?)
   obok istniejącego SC4-Hub, każdy ze swoim połączeniem? Trzeba potwierdzić
   model komunikacji, zanim zaprojektuję drugi `_command`/`_exchange`
   obok tego z `SC4HubMachine`.

## Materiały do przygotowania (FEETECH SM45BL) — `zbyszek/`

Wzorem tego, co już tam jest dla Teknica (instrukcja użytkownika, referencja
SDK, przykłady kodu — patrz listing katalogu), pod SM45BL przydałoby się:

1. **Instrukcja/karta katalogowa SM45BL** (specyfikacja mechaniczna i
   elektryczna: napięcie zasilania, prąd znamionowy/szczytowy, moment,
   masa, wymiary, złącza) — odpowiednik `Clearpath-SC User Manual.pdf`.
2. **Protokół komunikacyjny Modbus RTU — mapa rejestrów**, to najważniejszy
   dokument: adresy rejestrów komend (pozycja/prędkość/moment zadany),
   rejestrów odczytu (pozycja rzeczywista, prąd/moment jeśli jest, status,
   kody alarmów), dostępne tryby pracy (pozycyjny/prędkościowy/momentowy),
   domyślny baudrate/parzystość/adres węzła (node ID) na wyjściu z fabryki
   i sposób jego zmiany. Bez tego nie da się ustalić, czy ta oś może
   uczestniczyć w limicie siły/SMART (patrz wyżej) — to odpowiednik
   `S-FoundationRef.chm` dla Teknica.
3. **Przykłady kodu / biblioteka producenta** dla Modbus RTU (Python/C, jeśli
   Feetech coś udostępnia) — jak `ClearPath_SC_Beta_Examples.zip`
   przyspieszyło pracę z SDK Teknica.
4. **Narzędzie konfiguracyjne producenta** (jeśli istnieje, jak ClearView
   dla Teknica) — nazwa, wymagania (Windows?), do czego służy (np. zmiana
   adresu węzła, tryb pracy, ewentualny odpowiednik Auto-Tune).
5. **Konkretny model/wersja przejściówki USB↔RS485**, którą planujesz użyć
   do podłączenia do tego komputera (Linux) — sterownik w jądrze,
   ewentualna reguła udev pod stały port, tak jak dziś
   `99-teknic-sc4hub.rules` dla SC4-Hub.
6. **Numer firmware/wersji SM45BL**, jeśli jest widoczny na etykiecie/w
   dokumentacji — mapy rejestrów Modbus bywają różne między wersjami tego
   samego modelu, więc warto mieć pewność, że instrukcja pasuje do
   egzemplarza, który faktycznie kupisz.

Jeśli producent ma osobne dokumenty PDF na komunikację i na mechanikę —
oba, tak jak dla Teknica jest osobno manual serva i osobno referencja SDK.

**Sprawdzone 2026-09-09:** `https://gitee.com/ftservo/FTServo_Linux`
(podane jako link) to biblioteka Feetecha dla serw **magistralowych serii
SMS/STS** — protokół własny producenta po UART (`/dev/ttyUSBx`), **nie
Modbus RTU**, i **bez śladu SM45BL** w widocznej strukturze repo
(`src/`, `examples/SMS_STS/...`, licencja MIT). Przydatne jako wzorzec
stylu komunikacji Feetecha (ramki, half-duplex UART), ale **nie zastępuje**
punktu 2 z listy wyżej — mapy rejestrów Modbus RTU konkretnie dla SM45BL
tu nie ma. `doc.feetech.cn` (strona z dokumentacją, podany wcześniej link)
jest niedostępna z tej sesji (zablokowany dostęp sieciowy, jak
`teknic.com`/`manualslib.com` — patrz `plan-rozwoju.md` sekcja J) — do
otwarcia ręcznie i wklejenia/wgrania do `zbyszek/`.

## Sprawdzone 2026-09-09: ClearCore to osobny mikrokontroler, nie SDK do podłączenia

`https://github.com/Teknic-Inc/ClearCore-library` (podane w rozmowie) —
kluczowe ustalenie, odpowiada na pytanie 4 wyżej: **ClearCore to nie jest
biblioteka, którą host linkuje do rozmowy z gotowym urządzeniem** (jak
sFoundation dla SC4-Hub). To **firmware, który sam piszesz i wgrywasz NA
płytkę ClearCore** (mikrokontroler SAME53, C++, środowisko **Microchip
Studio** — Windows, wymaga wersji 7.0.1645+). Struktura repo:
`libClearCore/` (API do silników krokowych/ClearPath i I/O), `Tools/`
(narzędzia do wgrywania firmware pod Windows), `LwIP/` (stos Ethernet).
Komunikacja z hostem: **USB albo Ethernet**, ale protokołu na tej
komunikacji **nie ma gotowego** — trzeba go samemu zaprojektować i
zaimplementować **po obu stronach**: we własnym firmware na ClearCore
(używając `libClearCore` do sterowania krokami/I/O) i w Pythonie po
stronie serwera.

**Konsekwencja dla tej propozycji:** to praktycznie powtórka tego, co już
raz zrobiono dla SC4-Hub (`bridge/sc4hub_bridge.cpp` + protokół TCP na
porcie 8500, patrz `ARCHITEKTURA.md`) — tylko że tu embedded część
(firmware ClearCore) zastępuje dzisiejszy Linux-owy `bridge/`, a nie
istnieje jeszcze w ogóle. To realny, osobny projekt firmware'owy (Windows +
Microchip Studio do wgrywania), nie „doinstaluj SDK i podłącz kabel" jak
przy SM45BL/Modbus. Warto to jasno oddzielić w planowaniu: `FeetekPwmDriver`
(lepiej: `FeetekModbusDriver` po korekcie wyżej) to głównie praca po
stronie Pythona nad istniejącym protokołem producenta; `ClearCoreDriver`
to dodatkowo praca firmware'owa od zera, zanim jakikolwiek driver Pythona
będzie miał z czym rozmawiać.

## Co proponuję jako pierwszy krok

Nie kodować całości od razu. Zacząć od wydzielenia interfejsu `AxisDriver`
i przepisania DZISIEJSZEGO `SC4HubMachine` tak, żeby sam siebie widział
jako jeden driver obsługujący grupę X/Y/Z (zero zmiany zachowania, tylko
przełożenie istniejącego kodu pod nowy kształt) — to weryfikuje, że
abstrakcja się broni, zanim dojdzie drugi, zupełnie inny sprzęt. Dopiero
potem dopisać `FeetekPwmDriver` dla osi 4.
