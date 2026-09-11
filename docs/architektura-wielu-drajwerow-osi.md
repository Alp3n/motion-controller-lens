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
- **Feetech SM45BL (ROZSTRZYGNIĘTE OSTATECZNIE 2026-09-10, z oficjalnych
  materiałów producenta w `zbyszek/`):** ani pierwsze założenie („gołe
  PWM"), ani drugie („Modbus RTU") nie było trafne. Cytat wprost z
  `zbyszek/SM45BL start tutorial201015_3.pdf` (str. 7, tabela serii): SM45BL
  należy do **serii SMBL** (brushless, RS485), a „The communication
  protocols of the three series [SCS/STS/SMBL] are identical and
  interworking" — to znaczy **ten sam protokół pakietowy co SMS/STS**
  (ramka w stylu Dynamixel Protocol 1.0: `FF FF <ID> <DŁUGOŚĆ> <INSTRUKCJA>
  [parametry] <SUMA_KONTROLNA>`), **nie standardowy Modbus RTU** — mimo że
  tak było opisane w ogłoszeniu sprzedażowym. Potwierdzone w kodzie
  źródłowym `zbyszek/FTServo_Python-main.zip`
  (`scservo_sdk/protocol_packet_handler.py`, `scservo_sdk/scservo_def.py`).
  **To odwraca wcześniejszy wniosek** (niżej w tym dokumencie), że
  GitHub/Gitee producenta „nie pokrywają" SM45BL — pokrywają, bo to ten sam
  protokół co SMS/STS, tylko inna etykieta na pudełku.

  **Oś NIE jest głucha — realny odczyt potwierdzony adresami rejestrów**
  (`scservo_sdk/sms_sts.py`): `PRESENT_POSITION` (56-57),
  `PRESENT_SPEED` (58-59), **`PRESENT_LOAD`** (60-61 — bezpośredni
  odpowiednik naszego `TrqMeasured`/`torque_pct`), `PRESENT_VOLTAGE` (62),
  `PRESENT_TEMPERATURE` (63), `PRESENT_CURRENT` (69-70), `TORQUE_ENABLE`
  (40), `GOAL_POSITION` (42-43), `MODE` (33). Karta katalogowa
  (`zbyszek/Feetech karta katalogowa SM45BL 001.pdf`) potwierdza to samo
  wprost pod „Feedback": Load/Position/Speed/Input Voltage/Current/
  Temperature. **Uwaga o kolejności bajtów** (tutorial, pyt. 11): „SCS
  series high byte first, SMS low byte first" — SM45BL (seria SM) więc
  **low byte first**, inaczej niż SCS.

  Domyślny baudrate serii SM: **115200** (karta katalogowa i tutorial FAQ
  zgodnie). Zasilanie serwa **osobne od RS485**, 9-24V. Narzędzie
  producenta do debugowania/konfiguracji: oprogramowanie „FD" / „Servo
  Debugging Assistant" (Windows) + dongle USB SCPC-3 (CH340E) —
  `zbyszek/Instrukcja obsługi serwa z PC- FE-SCPC-C003.docx`; Waveshare
  USB-RS485, które ma użytkownik, powinien działać z tym softem tak samo
  jak SCPC-3 (obu chodzi tylko o port COM z właściwym baudrate'em).

  **Plik `zbyszek/Tabela pamięci protokół serw SM45BL_001.xlsx`** — mimo
  że pierwszy arkusz nazywa się po chińsku „磁编码SMS&STS-内存表解析"
  (analiza tabeli pamięci magnetycznego kodowania SMS&STS), **to
  prawdopodobnie właściwy, aktualny plik** (data w nazwie 220328 = nowszy
  niż tabela z 2017 wymieniona w tutorialu dla SM30BL/SM40BL) — zgodne z
  ustaleniem wyżej, że SMBL dzieli protokół/tabelę pamięci z SMS/STS. Nie
  przeanalizowano jeszcze wiersz po wierszu (do zrobienia jako następny
  krok, zamiast dalszego zgadywania nowych plików).
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

1. ~~Czy oś 4 (Feetek) i przyszłe osie ClearCore biorą udział w programie
   technologa/cyklu (`RUCH`/`PROGRAM`) na równi z X/Y/Z, czy są **osiami
   pomocniczymi**?~~ — **ROZSTRZYGNIĘTE 2026-09-10 (decyzja operatora):
   wszystkie osie z serwami SM45BL mają być PEŁNOPRAWNE** — na równi z
   X/Y/Z, nie tylko sterowane z panelu/JOG. Konsekwencja: `_run_program`,
   `_execute_cycle_step`, walidacja `CycleStep.targets` i (jeśli dotyczy)
   operacje `.prg` muszą wiedzieć o wielu driverach naraz, nie tylko o
   Teknicu. To największa pojedyncza konsekwencja architektoniczna w tym
   dokumencie — patrz „Krok integracji" niżej.
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

**Dostarczone przez użytkownika 2026-09-10** (przez upload na GitHub, nie
`doc.feetech.cn` — ta strona zostaje niedostępna z tej sesji): karta
katalogowa SM45BL, tabela pamięci (xlsx), tutorial startowy, instrukcja
oprogramowania PC (SCPC-3/FD), `FTServo_Linux-main.zip` i
`FTServo_Python-main.zip`, oraz sterownik FTDI `libftd2xx-linux-x86_64-
1.4.33.tgz` (sugeruje, że konwerter USB-RS485 może być oparty na chipie
FTDI — do potwierdzenia, standardowy sterownik jądra `ftdi_sio` zwykle
też wystarcza bez tego pakietu). Punkty 1-4 poniżej w praktyce
zaspokojone, zostawiam oryginalną listę jako zapis, czego szukaliśmy i
dlaczego. Analiza materiałów: sekcja „Największy kompromis" wyżej.

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
   `99-teknic-sc4hub.rules` dla SC4-Hub. **Sprawdzone 2026-09-09: ten
   komputer prawdopodobnie NIE ma fizycznego portu RS232** — `lspci`
   pokazuje tylko sterownik Intel AMT „Serial-Over-LAN" (wirtualny port
   do zarządzania, nieużywalny do zewnętrznego okablowania), żadnej
   dedykowanej karty UART/RS232. `/dev/ttyS0`-`ttyS31` istnieją, ale to
   niemal na pewno standardowa rejestracja sterownika jądra bez sprzętu
   za nimi (nie udało się tego ostatecznie potwierdzić —
   `/proc/tty/driver/serial` wymaga uprawnień, których ta sesja nie ma
   bez interaktywnego hasła). **Wniosek: przejściówka RS232→RS485 może
   nie mieć się do czego podłączyć** — prościej wziąć przejściówkę
   **USB→RS485** bezpośrednio (pomija RS232 w ogóle, wpina się w zwykły
   port USB, pojawia się jako `/dev/ttyUSBx`), zamiast RS232→RS485 plus
   dodatkowo USB→RS232.

   **Konkretne konwertery, które użytkownik ma pod ręką (sprawdzone przez
   wyszukiwanie 2026-09-09, nie z pamięci):**
   - **Waveshare SKU 23376** — „RS232 To RS485 (B)": wejście **RS232**
     (potwierdza problem wyżej), zasilanie zewnętrzne **6-36V DC wymagane
     osobno** (izolowany, nie zasila się samym sygnałem). Bez portu RS232
     albo dodatkowej przejściówki USB→RS232 — nieużywalny na tym
     komputerze.
   - **Waveshare SKU 23778** — „Rail-mount TTL to RS485", wejście **TTL
     UART** (3,3-5V), nie RS232 i nie USB wprost. **To lepsza opcja na
     tym komputerze**, pod warunkiem posiadania osobnej przejściówki
     **USB→TTL-UART** (popularne, tanie moduły FTDI/CP2102/CH340 — inny
     sprzęt niż powyższe dwa konwertery). Łańcuch: USB (port w tym PC) →
     USB-TTL → SKU 23778 (TTL→RS485, galwanicznie izolowany) → RS485 A/B
     do serwa. Zasilanie modułu prawdopodobnie z pinu VCC strony TTL (do
     potwierdzenia w instrukcji modułu, nie zakładam na pewno).
   - **Pytanie otwarte:** czy jest osobno przejściówka USB→TTL-UART? Bez
     niej żaden z tych dwóch konwerterów nie ma jak się podłączyć do tego
     komputera przez USB.
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

**Struktura menu strony potwierdzona przez użytkownika (2026-09-09)** —
serwis obejmuje kilka niezwiązanych rodzin serw/protokołów naraz
(HLS/SMS/STS/SCS/FU/SHC — protokół własny FT; osobno UAVCAN/CAN2.0A/
CANopen). Priorytety, co z tego pobrać/wgrać do `zbyszek/`:

1. **„Serwomechanizmy serii MODBUS-RTU"** — właściwa rodzina dla SM45BL;
   w środku szukać konkretnie strony/PDF **SM45BL** (seria może mieć kilka
   modeli).
2. **„Protokół MODBUS-RTU"** — mapa rejestrów, najważniejsze (patrz punkt 2
   listy wyżej).
3. **„Pobierz Python SDK"** — prawdopodobnie najbardziej przydatne: nasz
   serwer jest w Pythonie, gotowy kod pokaże realne użycie rejestrów i czy
   biblioteka w ogóle udostępnia odczyt pozycji/prądu.
4. **„Pobierz zestaw SDK dla systemu Linux"** — dodatkowo, niższy poziom
   (C), do porównania z Python SDK, gdyby czegoś w nim brakowało.
5. „Tabela generowania instrukcji szesnastkowych" — pomocnicze, dopiero
   jeśli powyższe nie wystarczą do zrozumienia protokołu.

**Pominąć na razie:** Arduino SDK, STM32 SDK (nie nasza platforma — host to
Linux/Python, nie embedded), pozostałe rodziny serw (HLS/SMS/STS/SCS/FU/
SHC) i pozostałe protokoły (UAVCAN/CAN2.0A/CANopen) — dotyczą innych
modeli niż SM45BL.

**Sprawdzone 2026-09-09, WNIOSEK ODWRÓCONY 2026-09-10 po materiałach od
producenta (patrz sekcja „Największy kompromis" wyżej).** Pierwotnie
uznałem: GitHub/Gitee (`github.com/ftservo`: `FTServo_Arduino/_Python/
_Linux/_stm32HAL`, oraz `gitee.com/ftservo/FTServo_Linux`) pokrywają tylko
protokół „bus servo" (katalogi `sms_sts`/`scservo_sdk`/`scscl`/`hls`), czyli
serie SMS/STS/SCS/HLS — **nie** Modbus RTU, więc niby nieprzydatne dla
SM45BL. **To była pomyłka wynikająca z zaufania etykiecie „Modbus RTU" z
ogłoszenia sprzedażowego, nie ze sprawdzenia u źródła.** Oficjalna
dokumentacja Feetecha (dostarczona przez użytkownika 2026-09-10,
`zbyszek/SM45BL start tutorial201015_3.pdf`) mówi wprost, że SM45BL (seria
SMBL) używa **tego samego protokołu co SMS/STS** — więc `FTServo_Python`/
`FTServo_Linux` **są jednak właściwym SDK**, tylko trzeba użyć modułu
`scservo_sdk`/`sms_sts` z innym baudrate'em (115200 zamiast 1000000 dla
STS). `doc.feetech.cn` (dalej niedostępny z tej sesji) nie jest już
jedynym źródłem — mamy już wystarczająco materiału w `zbyszek/`, żeby
zacząć pisać `FeetekDriver` opierając się na źródłach SDK, bez czekania na
tę stronę.

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

## Narzędzia do testu łączności: `tools/test_feetech_servo.py` (główne) + `tools/test_modbus_servo.py` (zapasowe)

Użytkownik ma konwerter **USB→RS485 z izolacją** (Waveshare, symbol do
ustalenia) — zamyka pytanie o podłączenie fizyczne.

**`tools/test_feetech_servo.py` (dodane 2026-09-10, po ustaleniu prawdziwego
protokołu — patrz sekcja „Największy kompromis" wyżej):** wysyła PING w
natywnym protokole SCS/SMS (ramka `FF FF <ID> <DŁ> 0x01 <suma kontrolna>`),
nie Modbus. Skanuje `/dev/ttyUSB*`, baudrate'y 115200 i 1000000 (domyślny
serii SM to 115200), ID serwa 1. To jest teraz **właściwe pierwsze
narzędzie do jutrzejszego testu** — protokół potwierdzony u źródła, nie
zgadywany.

**`tools/test_modbus_servo.py` (starsze, z 2026-09-09, zanim ustalono
prawdziwy protokół):** prawdziwy Modbus RTU (funkcja 0x03 + CRC16) — zostaje
jako **zapasowe** podejście, na wypadek gdyby ten konkretny egzemplarz
serwa jednak miał przełączalny tryb Modbus (nieprawdopodobne wg
dokumentacji, ale tanie do sprawdzenia, skoro narzędzie już istnieje).

Żadne z nich nie jest jeszcze właściwym sterownikiem osi — to tylko test
łączności. Właściwy `FeetekDriver` (sekcja „Co proponuję" niżej) powstanie
po analizie `scservo_sdk` z `zbyszek/FTServo_Python-main.zip` (adresy
rejestrów już znane, patrz wyżej) i próbie PING na sprzęcie.

## Plan integracji `FeetekDriver` z `Machine` (po decyzji: osie pełnoprawne)

**Zmiana podejścia po decyzji 2026-09-10:** zamiast dużego refaktoru
„`AxisDriver` jako wspólny interfejs, `Machine` składa drivery" (ryzykowne
dla X/Y/Z, które działają na produkcji), **bezpieczniejsze jest dodanie
Feetecha OBOK dzisiejszego kodu, bez dotykania ścieżki X/Y/Z**: `Machine`
dostaje opcjonalny `self.feetek: FeetekDriver | None`, a miejsca, które
muszą wiedzieć o wielu driverach (JOG, cykl, status), sprawdzają „czy ta
nazwa osi jest skonfigurowana jako Feetech (nowe pole w `config/axes.json`)
→ deleguj do `self.feetek`, inaczej → dzisiejsza ścieżka Teknika". Zero
zmiany zachowania dla X/Y/Z w każdym etapie.

**Etapy** (każdy osobno testowalny i wdrażalny, kolejność ma znaczenie —
późniejsze zależą od wcześniejszych):

- [x] **Etap 0 — protokół i driver.** `feetech_protocol.py` +
  `feetech_driver.py`, zweryfikowane fizycznie (PING, odczyt statusu,
  ruch, kierunek CW/CCW obu serw). Zrobione 2026-09-10.
- [x] **Etap 1 — status. Zrobione 2026-09-10.** Osobna pętla
  `_feetech_poll_loop` (nie `_poll_loop` X/Y/Z — inny budżet czasowy,
  odczyt termios to 0,1-0,3s na oś), `MachineStatus.feetech_raw` (nowy
  słownik `{nazwa: {position, load}}`, jednostki rejestru). Zweryfikowane
  end-to-end na sprzęcie (`GET /api/status` z oboma serwami podłączonymi).
  Szczegóły: `zmiany/status-osi-feetech.md`. **Panel jeszcze nie pokazuje
  tego wizualnie** — dane są w API, ekranu brak.
- [x] **Etap 2 — JOG, część „bez mm" zrobiona 2026-09-11.** Nowy,
  osobny endpoint `POST /api/machine/jog-feetech` (NIE `Machine.jog()` —
  świadomie osobna ścieżka, X/Y/Z bez zmian) rusza osią w kierunku
  zgodnym/przeciwnym do zegara (`DIRECTION_SIGN_CW`), przyciski na panelu
  głównym. Zweryfikowane fizycznie na obu serwach, oba kierunki, zgodnie
  z oczekiwaniem. Przy okazji naprawiony błąd współbieżności — magistrala
  RS485 jest współdzielona między tym a `_feetech_poll_loop`, teraz
  serializowane `_feetech_lock`iem. Szczegóły: `zmiany/jog-feetech.md`.
  **Zostaje:** przeliczenie mm→kroki i to, czy CW = rosnące czy malejące
  mm dla danej osi — **wciąż niewiadome**, bo serwa dalej leżą odłączone
  od mechanizmu (użytkownik: „robimy serwa bez montowania na maszynie").
  Kalibracja mm to osobny krok po fizycznym zamontowaniu.
- [ ] **Etap 3 — bazowanie.** SM45BL nie ma czytelnego dla nas wejścia
  krańcówki (do potwierdzenia) — najpewniej bazowanie **programowe**
  (zapisanie bieżącej pozycji jako zero, jak `home_mode: "programowe"` już
  istniejący w modelu `AxisConfig`), ewentualnie z użyciem rejestru OFS
  (31-32, offset zera) zamiast liczenia w Pythonie. Do ustalenia.
- [ ] **Etap 4 — cykl maszyny.** `CycleStep.targets` dziś przyjmuje
  x/y/z — rozszerzyć o dowolne skonfigurowane nazwy osi (walidacja w
  `cycle.py`), `_execute_cycle_step` deleguje ruch tej osi do
  `FeetekDriver` tak jak w etapie 2.
- [ ] **Etap 5 (jeśli potrzebne) — program technologa.** Czy operacje
  `.prg` też mają móc ruszać tymi osiami, czy to wyłącznie poziom cyklu
  maszyny (jak dziś `WYJSCIE`)? Nieustalone — pytanie do Ciebie, gdy
  dojdziemy do tego etapu.

**Multi-turn i granice zakresu:** dzisiejszy test pokazał, że komenda poza
zakresem 0-4095 jest po prostu odrzucana bez ruchu (serwo 1, cel 4294) —
tryb wielobrotowy (±7 obrotów, wspomniany w karcie katalogowej) nie jest
jeszcze używany ani potwierdzony w naszym kodzie. Dla `docisk`
(0,25mm/obrót, zakres roboczy 7mm w `config/axes.json`) cały zakres
roboczy to około 28 obrotów — **prawdopodobnie WYMAGA trybu
wielobrotowego**, żeby zmieścić się w jednym ciągłym ruchu bez ręcznego
zawijania przez Pythona. Do zbadania przy etapie 2/3, nie zakładane teraz.

## Dodatkowy wątek: moduły I/O Waveshare Modbus RTU na tej samej magistrali

Zgłoszenie użytkownika (2026-09-10): ma dwa moduły I/O tej samej firmy co
konwerter (Waveshare) — cyfrowy 8IN/8OUT i analogowy — pytanie, czy można
je podłączyć do tej samej magistrali RS485 co serwa FEETECH. **Model
dokładny jeszcze nieznany** (użytkownik sprawdzi później) — poniższe
oparte na typowych produktach Waveshare z tej kategorii, do potwierdzenia
po podaniu SKU.

- Sprawdzone (wyszukiwanie, strony produktowe Waveshare): to **prawdziwy
  Modbus RTU** (w przeciwieństwie do serw!) — np.
  [Modbus RTU IO 8CH](https://www.waveshare.com/modbus-rtu-io-8ch.htm)
  (8DI/8DO) i [Modbus RTU Analog Input 8CH (B)](https://www.waveshare.com/wiki/Modbus_RTU_Analog_Input_8CH),
  adresy 1-255, kaskadowanie wielu modułów na jednej magistrali.
- **Domyślny baudrate modułów: 9600** (N,8,1) — inny niż serwa (115200).
  Fizycznie mogą wisieć na tej samej magistrali RS485 (wielopunktowa), ale
  **jeden port ma jedną prędkość transmisji na raz** — trzeba przełączać
  baudrate między odczytem serwa a modułu I/O (driver już to umie, otwiera
  port z zadanym baudrate za każdym razem), albo przestawić moduły na
  115200 rejestrem konfiguracyjnym, jeśli to wspierane — do sprawdzenia
  po ustaleniu dokładnego modelu.
- `tools/test_modbus_servo.py` (prawdziwy Modbus RTU: funkcja 0x03 +
  CRC16, napisany 2026-09-09 zanim ustalono, że serwa go NIE używają) —
  gotowy punkt startowy do testu łączności z tymi modułami, mapa rejestrów
  do potwierdzenia z konkretnej strony wiki Waveshare po podaniu SKU.
- **Nie zaimplementowane, nie zdecydowane co dalej** — czeka na model
  modułów.
