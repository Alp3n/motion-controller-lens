# Sterownik: SC4-Hub zamiast ClearCore

Ustalenia z 2026-08-14. Dokument opisuje rozbieżność między sprzętem, który
faktycznie jest na maszynie, a architekturą założoną w repozytorium — oraz
proponowaną drogę wyjścia.

## Problem

Repozytorium zakłada **Teknic ClearCore**: samodzielny sterownik z własnym
firmware C++ (`firmware/clearcore/`), do którego serwer wysyła komendy
wysokopoziomowe po **Ethernecie** (TCP, port 8500). Interpolację ruchu,
bazowanie i ciągły nadzór nad sygnałem zezwolenia wykonuje firmware.

Maszyna ma natomiast **Teknic SC4-Hub** z serwami **ClearPath-SC**.

## Czym jest SC4-Hub

Hub komunikacyjno-I/O dla serw ClearPath-SC. Łączy **komputer** z silnikami
po **USB** (alternatywnie RS-232) — do 4 silników na hub, do 4 hubów
połączonych w łańcuch, czyli 16 osi na jednym porcie. Zasilanie 15–30 V.

Nie ma tam firmware do wgrania i nie ma Ethernetu. **Sterownikiem ruchu staje
się PC**, przez bibliotekę Teknica **sFoundation** (C++, Windows/Linux;
oficjalnych bindingów Pythona brak).

Wejścia/wyjścia huba:

- 2 wyjścia — nominalnie sterowanie hamulcami 24 V, ale wg SDK **mogą pracować
  jako wyjścia ogólnego przeznaczenia** (`BRAKE_0`, `BRAKE_1`),
- 1 wejście **Global Stop** — zatrzymuje wszystkie osie jednocześnie,
- każdy węzeł (silnik) udostępnia **2 wejścia ogólnego przeznaczenia** (A, B).

Źródła: [teknic.com/sc4-hub](https://teknic.com/sc4-hub/),
[instrukcja ClearPath-SC](https://teknic.com/files/downloads/Clearpath-SC%20User%20Manual.pdf),
`Beta_SDK_Examples/SC4-IO/SC4-IO.cpp` z pakietu sFoundation.

> **Korekta wcześniejszego ustalenia.** W pierwszej analizie napisano, że
> SC4-Hub nie ma wyjścia nadającego się do sterowania wrzecionem. To nieprawda:
> przykład `SC4-IO.cpp` opisuje oba wyjścia jako *„commonly used to control
> 24V Power Off Brakes, **or as general purpose outputs**"*. Jedno z nich może
> więc sterować przekaźnikiem/stycznikiem wrzeciona 24 V — pozostaje sprawdzić
> obciążalność w specyfikacji huba.

## Konsekwencje dla repozytorium

- **`firmware/clearcore/` jest bezużyteczne** — nie ma czego flashować. Cała
  logika ruchu musi przenieść się na PC.
- **Klasa sprzętowa nie zadziała w obecnej formie** — łączy się po TCP do
  `CLEARCORE_HOST:8500` (`server/app/machine.py`). *(Nazwy z tamtego czasu;
  dziś to `SC4HubMachine` i `BRIDGE_HOST` —
  [`zmiany/nazewnictwo-sc4hub.md`](zmiany/nazewnictwo-sc4hub.md).)*
- Serwa **muszą być serii SC**. ClearPath MC/SD (step & direction) SC4-Hub nie
  obsługuje. *Potwierdzone: na maszynie są serwa ClearPath-SC.*

Bez zmian zostaje wszystko powyżej szwu `Machine`: panel operatora, edytor
technologa, API MES, parser i walidator `.prg`.

## Proponowana architektura: mostek sFoundation

Serwer rozmawia z maszyną wyłącznie przez klasę `Machine`
(`server/app/machine.py`), a klasa sprzętowa (dziś `SC4HubMachine`)
tłumaczy program na **prosty
protokół tekstowy** (`PING`, `STATUS`, `HOME`, `MOVEXY`, `MOVEZ`, `JOG`,
`SPINDLE`, `STOP`, `RESET` — opis w `firmware/clearcore/README.md`; mostek
dokłada `RELEASE`/`HOLD` i `AXCFG`).

Ten protokół jest gotowym szwem. Zamiast przepisywać warstwę Pythona, piszemy
na PC **demona C++ na sFoundation**, który wystawia *dokładnie ten sam*
protokół na `127.0.0.1:8500`. Serwer uruchamiamy wtedy z:

```
MACHINE_MODE=clearcore CLEARCORE_HOST=127.0.0.1
```

i **nie zmieniamy ani linijki Pythona**. Istniejący `firmware/clearcore/main.cpp`
przestaje być kodem do wgrania, ale pozostaje **dobrą specyfikacją** tego, co
mostek ma robić.

## Ryzyka do rozstrzygnięcia

### 1. Bezpieczeństwo — założenie bez zmian

Wymóg z README (niezależny, certyfikowany układ sprzętowo odcinający zasilanie
mocy serw) obowiązuje tak samo. Wejście **Global Stop w SC4-Hub to funkcja
sterowania, nie funkcja bezpieczeństwa** — Teknic nie deklaruje dla niej
kategorii bezpieczeństwa.

Przy PC jako sterowniku wymóg jest wręcz **ważniejszy** niż przy ClearCore:
nierealtime'owy Linux na łączu USB oznacza, że zawieszenie procesu albo
wypięcie kabla nie może zostawić osi w ruchu.

*Stan: układ bezpieczeństwa na maszynie jest gotowy (potwierdzone przez
użytkownika).*

### 2. Interpolacja XY — otwarte

ClearCore robił interpolację w firmware. ClearPath-SC wykonuje własne profile
**per oś**, komendowane po serialu; skoordynowany ruch po dowolnej linii z
zadanym posuwem nie jest tym, co ta magistrala robi natywnie.

Operacje `PUNKT` (zagłębienie w miejscu) są bezpieczne. Problem dotyczy
operacji **`LINIA`**, gdzie liczy się tor — mostek może musieć dzielić linię
na segmenty i pilnować synchronizacji osi.

> **Częściowa odpowiedź (2026-08-26).** Dokumentacja sFoundation daje
> **grupy wyzwalania** (Triggered Moves, funkcja Advanced — nasze serwa ją
> mają): ruchy wysyła się do wszystkich osi z flagą `isTriggered`, a potem
> jedną komendą (`TriggerMovesInGroup`) startują równocześnie. Usuwa to
> **niejednoczesny start osi**, ale nie odchyłkę na rampach — każda oś nadal
> jedzie własnym profilem. To poprawa, nie interpolacja. Szczegóły:
> [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md). Weryfikacja
> pomiarowa toru nadal potrzebna.

### 3. Realtime i utrata łączności

Do zaprojektowania: zachowanie mostka przy utracie USB, zawieszeniu serwera
i przy `STOP` w trakcie ruchu.

> **Częściowa odpowiedź (2026-08-26).** Silnik ma **watchdog sieciowy** —
> jego wygaśnięcie z braku ruchu od hosta wywołuje `NodeStop`, czyli przy
> zawieszeniu mostka osie zatrzymują się same. Wyjścia `BRAKE_x` też
> rozłączają się przy utracie łączności z PC. **Nie wiadomo jednak, jaki jest
> domyślny czas watchdoga ani czy jest włączony** — dokumentacja API tego nie
> podaje. Do zmierzenia, zanim uznamy to za warstwę ochrony. Szczegóły:
> [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).
>
> **Częściowe potwierdzenie (2026-08-30, host produkcyjny).** Znaleziono
> mechanizm, który wygląda jak realizacja tego watchdoga: **Group Shutdown**
> (`IGrpShutdown`/`ShutdownWhenGet` w sFoundation) jest **włączony
> (`enabled=1`) na wszystkich trzech węzłach** i aktywnie wymusza alarm
> `EStopped`, dopóki żaden mostek nie jest z nimi połączony — patrz sekcja
> „Dioda stanu na silniku” niżej. Dokładna maska bitów wyzwalających
> (`statusMask`) nie została jednoznacznie rozszyfrowana (pola wielobitowe w
> `mnStatusReg`, niejednoznaczne przy generycznym dekodowaniu `StateStr()`) —
> nie jest to więc pewne w 100%, tylko najbardziej spójna z obserwacjami
> hipoteza.

## Pakiet sFoundation dla Linuksa

`Linux_Software.tar.gz` ze strony [teknic.com/downloads](https://teknic.com/downloads/)
(wydanie z 2026-08-13, ~1,9 MB; ten sam plik pobrany ponownie 2026-08-30 miał
identyczny rozmiar). Zawiera źródła sFoundation, sterownik USB do SC4-Hub,
dokumentację i przykłady.

Przykłady istotne dla nas:

- **`Beta_SDK_Examples/SCNetworkReport`** — wykrywa huby i raportuje widziane
  węzły. Nasz test rozpoznawczy.
- **`Beta_SDK_Examples/SC4-IO`** — wyjścia huba, Global Stop, wejścia węzłów.
- **`Beta_SDK_Examples/NodeAlerts-Status`** — status/alarmy węzła, ale
  **UWAGA: ten przykład sam z siebie robi `EnableReq(true)` (podaje moment
  przez 10 s) i kasuje alarmy, w tym EStop** — nie uruchamiać bez zrozumienia,
  co robi. Na potrzeby czystej diagnostyki (bez uzbrajania silnika) napisano
  własny, okrojony odpowiednik — patrz „Diagnostyka bez ryzyka ruchu” niżej.
- `SDK_Examples/Example-Homing`, `Example-Motion`, `Beta_SDK_Examples/MotionDualAxis`
  — bazowanie i ruch osi.

### Pułapka: cdc_acm przechwyci hub

Z `ExarKernelDriver/driver_readme.txt`:

> *Your system might have a built-in cdc_acm driver that will take control of
> the SC4-Hub. That driver is adequate for establishing communications with the
> board, but it is **NOT fully compatible with sFoundation**.*

Hub **wyenumeruje się sam** jako `/dev/ttyACM0` i będzie wyglądał na
działający, ale sFoundation nie będzie z nim poprawnie współpracować. Trzeba
zainstalować dołączony sterownik Exar (wymaga roota i nagłówków jądra).

Uwaga: kernel ma w drzewie zarówno `cdc-acm.ko`, jak i `xr_serial.ko` — obie
mogą przejąć urządzenie, więc kolejność ładowania ma znaczenie.

## Stan środowiska (stacja robocza, 2026-08-14)

Ubuntu 22.04.5 LTS, kernel 6.8.0-40-generic. Teknic weryfikował procedurę m.in.
na Ubuntu 24.04, które ma ten sam kernel.

| Element | Stan |
|---|---|
| Nagłówki jądra (`/usr/src/linux-headers-6.8.0-40-generic`) | jest, `build` dowiązany |
| `xr_serial.ko`, `cdc-acm.ko` w drzewie | są, żaden niezaładowany |
| `g++` 11.4.0, `make` 4.3 | zainstalowane |
| Użytkownik w grupie `dialout` | tak (po `usermod` i restarcie) |
| `git` | **brak** (nieblokujące) |

To była **inna maszyna** niż produkcyjny host `walkner-motion-controller`
opisany od sekcji „Uruchomienie mostka na hoście produkcyjnym” niżej —
różny Ubuntu (22.04 vs 26.04) i różny kernel (6.8 vs 7.0), stąd część
przeszkód (kompilator, Secure Boot) różni się między sesjami.

## Gdzie leży SDK

`vendor/teknic/` w repozytorium — katalog jest w `.gitignore`, bo to kod
producenta pobierany z jego strony.

> Pakiet trzymano początkowo w scratchpadzie sesji i **został skasowany między
> sesjami**. Stąd trwała lokalizacja w projekcie.

- `vendor/teknic/Linux_Software/` — rozpakowany pakiet (źródła, przykłady,
  sterownik USB, licencja).
- `vendor/teknic/lib/` — instalacja single-user: `libsFoundation20.so`
  (854 KB), dowiązanie `libsFoundation20.so.1`, `MNuserDriver20.xml`.

Biblioteka zbudowana bez błędów (tylko ostrzeżenia `-Wwrite-strings` w
`LibXML`). Przykłady buduje się z `make RPATH=<...>/vendor/teknic/lib`.

> **Stan na hoście produkcyjnym, zanim doinstalowano SDK (2026-08-30 rano):**
> `vendor/teknic/` nie było na tej maszynie — `bridge/sc4hub_bridge` był w
> repo skompilowany (z zaszytym `RUNPATH` wskazującym na ścieżkę z zupełnie
> innego komputera, `/home/w/projects/motion-controller-lens/vendor/teknic/lib`),
> ale nie odpalał się (`error while loading shared libraries:
> libsFoundation20.so.1: cannot open shared object file`). Rozwiązane —
> patrz „Uruchomienie mostka na hoście produkcyjnym” niżej: bibliotekę
> zainstalowano **systemowo** w `/usr/local/lib` (oficjalna metoda „Systemwide
> Install” z `readme.txt` pakietu), co działa niezależnie od zaszytego
> `RUNPATH` — dynamiczny linker sam spada do standardowych ścieżek, gdy
> `RUNPATH` nie istnieje.

## Instalacja sterownika Exar

Skrypt `Teknic_SC4Hub_USB_Driver/ExarKernelDriver/Install_DRV_SCRIPT.sh`
(już ustawiony jako wykonywalny). Wymaga **roota i prawdziwego terminala** —
w trakcie działania czeka na naciśnięcie klawisza. Co robi:

1. Buduje `xr_usb_serial_common.ko` przeciw bieżącemu jądru i kopiuje do
   `/lib/modules/$(uname -r)/kernel/drivers/usb/serial`, `depmod -a`, `insmod`.
2. Dopisuje `xr_usb_serial_common` do `/etc/modules`, czyli **moduł wraca po
   restarcie**.
3. Prosi o podłączenie huba, po czym sam **odpina go od `cdc_acm`** i przypina
   do `cdc_xr_usb_serial`.

Uruchomienie (z katalogu skryptu — skrypt to sprawdza):

```bash
cd vendor/teknic/Linux_Software/Teknic_SC4Hub_USB_Driver/ExarKernelDriver
sudo ./Install_DRV_SCRIPT.sh
```

**SC4-Hub ma USB ID `2890:0213`** — po tym rozpoznajemy go w `lsusb`
i `/sys/bus/usb/devices/*/modalias` (skrypt szuka wzorca `v2890p0213`).

### Wymagany `gcc-12` (dotyczy stacji roboczej z kernelem 6.8.0-40)

Moduł jądra musi być zbudowany **tym samym kompilatorem co jądro**. Kernel
6.8.0-40 (HWE) zbudowano `gcc-12`, a `build-essential` na 22.04 daje `gcc-11` —
skrypt przerywa się na `gcc-12: not found`. Rozwiązanie:

```bash
sudo apt install -y gcc-12
```

`gcc-12` instaluje się obok `gcc-11` i nie podmienia domyślnego kompilatora.
Nie trzeba podawać `CC=` — Makefile jądra sam sięga po właściwą wersję.

Uwaga: skrypt trzeba powtórzyć **po każdej aktualizacji jądra** — moduł jest
wiązany z konkretną wersją jądra i jej kompilatorem, DKMS tu nie ma. Na hoście
produkcyjnym (kernel 7.0.0-30, Ubuntu 26.04) `gcc` w systemie (15.2.0)
**dokładnie odpowiadał** kompilatorowi, którym zbudowano ten kernel — problem
z niedopasowaną wersją tam nie wystąpił, za to wystąpił inny (patrz niżej).

## Plan rozpoznania

1. ~~`apt install build-essential` + `usermod -aG dialout` + przelogowanie.~~ **zrobione**
2. ~~Budowa `libsFoundation20.so`, instalacja single-user.~~ **zrobione**
3. ~~Budowa narzędzia `SCNetworkReport`.~~ **zrobione**, linkuje się poprawnie
   (`ldd` wskazuje na `vendor/teknic/lib`).
4. ~~Instalacja sterownika Exar.~~ **zrobione** (po doinstalowaniu `gcc-12`).
5. ~~Podłączenie SC4-Hub po USB.~~ **zrobione**
6. ~~Weryfikacja enumeracji i przypięcia sterownika.~~ **zrobione**
7. ~~Uruchomienie `SCNetworkReport`.~~ **zrobione — 3 węzły wykryte.**

## Wynik rozpoznania (2026-08-14)

### Warstwa USB — działa w całości

To była najbardziej ryzykowna część i jest zamknięta:

```
Bus 002 Device 007: ID 2890:0213 Teknic, Inc ClearPath 4-axis Comm Hub
```

- oba interfejsy (`2-1.2:1.0`, `2-1.2:1.1`) przypięte do `cdc_xr_usb_serial`,
  **nie** do `cdc_acm` — czyli sterownik Exar zadziałał zgodnie z ostrzeżeniem
  z `driver_readme.txt`,
- moduł `xr_usb_serial_common` załadowany,
- port `/dev/ttyXRUSB0`, grupa `dialout`, użytkownik ma dostęp.

### Pułapka: `cdc_acm` wraca przy każdej enumeracji

Skrypt Teknica przepina hub na sterownik Exar **jednorazowo**. Po każdym
resecie huba (włączenie 24 V, przewtyknięcie kabla, restart szafy) urządzenie
enumeruje się od nowa i `cdc_acm` przejmuje je z powrotem — pojawia się
`/dev/ttyACM0` zamiast `/dev/ttyXRUSB0`, a sFoundation zgłasza
„No SC4-HUB's found".

Rozwiązanie: `tools/sc4hub-rebind.sh` (ręcznie) i `tools/99-teknic-sc4hub.rules`
(automatycznie, przez udev). Szczegóły:
[`zmiany/narzedzia-usb-sc4hub.md`](zmiany/narzedzia-usb-sc4hub.md).

Na hoście produkcyjnym oba pliki były **już przygotowane i zainstalowane**
(`/etc/udev/rules.d/99-teknic-sc4hub.rules`, `/usr/local/sbin/sc4hub-rebind.sh`)
z wcześniejszej sesji wdrożeniowej, mimo że sterownik Exar nigdy nie był tam
jeszcze faktycznie zainstalowany — zadziałały bez zmian po instalacji
sterownika 2026-08-30.

### Sieć silników — działa

Po zasileniu huba (24 V) **oraz** magistrali DC silników i po przepięciu
sterownika, `SCNetworkReport` widzi komplet osi:

```
Node[0]  CPM-SCSK-2310S-RLNA-1-8-D   S/N 90404362   FW 1.8.0 EEFF
Node[1]  CPM-SCSK-2310S-RLNA-1-8-D   S/N 90406231   FW 1.8.0 EEFF
Node[2]  CPM-SCSK-2310S-RLNA-1-8-D   S/N 90406002   FW 1.8.0 EEFF
```

Trzy identyczne serwa SCSK (NEMA 23), pierścień zamknięty, komunikacja
end-to-end od Pythona przez sFoundation do silników. **Droga mostka
sFoundation jest potwierdzona jako wykonalna.**

Wcześniejsze błędy i ich przyczyny:

| Objaw | Przyczyna |
|---|---|
| `Port failed to initialize`, `err=0x80040601` | wyłączone 24 V huba i brak zasilania silników — pętla prądowa przerwana |
| `No SC4-HUB's found` przy sprawnym USB | `cdc_acm` przejął hub po ponownej enumeracji |

### Potwierdzone: pełny cykl na sprzęcie

Mostek (`bridge/`, patrz [`zmiany/mostek-sc4hub.md`](zmiany/mostek-sc4hub.md))
przejechał **cały program `583912004711` na trzech serwach**: wybór zlecenia
w MES → bazowanie → operacje 1–3 → `PAUZA` → wznowienie → powrót do zera.
Pozycje trafione co do impulsu, wrzeciono przełączane zgodnie z programem.
Serwer Pythona nie wymagał żadnej zmiany w logice — protokół tekstowy
zadziałał jako szew dokładnie tak, jak zakładano.

### Jednostki osi

Odczytane z serwa: **800 imp/obr** (`Info.PositioningResolution`).
Śruba kulowa: **5 mm/obr**. Razem **160 imp/mm**.

Od czasu wprowadzenia ekranu konfiguracji osi `mm/obr` jest ustawiane
**osobno dla każdej osi** i przysyłane przez serwer komendą `AXCFG`
(patrz [`konfiguracja-osi.md`](konfiguracja-osi.md)); `MM_PER_REV`
w `machine.env` jest już tylko wartością startową mostka.

Wpisanie tej rozdzielczości na sztywno (błędnie 6400) dawało ruch 8× wolniejszy
przy pozornie poprawnym odczycie pozycji — błąd skracał się w przeliczeniu tam
i z powrotem. Dlatego mostek czyta ją ze sprzętu, a nie z konfiguracji.

### Mapowanie osi — ustalone

Ustalone trybem `--identify` i utrwalone w `bridge/machine.env` **po numerach
seryjnych**, żeby przełożenie wtyków go nie zmieniło:

| Oś | Węzeł | S/N | Rola |
|---|---|---|---|
| Z | `Node[0]` | 90404362 | oś frezu |
| X | `Node[1]` | 90406231 | pozioma |
| Y | `Node[2]` | 90406002 | pionowa |

Kolejność w pierścieniu **nie** odpowiada kolejności osi — domyślne mapowanie
0→X, 1→Y, 2→Z byłoby błędne. Potwierdzone ponownie 2026-08-30 na hoście
produkcyjnym (`SCNetworkReport` zwrócił te same trzy numery seryjne).

### Auto-Tune: kiedy blokuje, a kiedy nie

Pole `userID` wszystkich trzech węzłów to **`Unloaded`** — to fabryczna
konfiguracja (nadal aktualne 2026-08-30). Zgodnie z dokumentacją Teknica serwa
ClearPath-SC są *„pre-configured for **unloaded** use only"* i **wymagają
uruchomienia Auto-Tune po sprzężeniu z mechaniką**.

Auto-Tune jest funkcją **ClearView, który działa tylko na Windows** — na
Linuksie nie ma odpowiednika. Konsekwencja:

- **potrzebny jednorazowo komputer z Windows** (albo maszyna wirtualna
  z przekazaniem USB), żeby zestroić każdą oś pod jej rzeczywiste obciążenie
  i zapisać konfigurację (`File → Save Configuration`, plik `.mtr`),
- **wczytanie gotowego `.mtr` działa już z Linuksa** przez sFoundation —
  przykład `Beta_SDK_Examples/LoadingConfigFile`.

**Konfiguracja fabryczna jest właściwa dla serw bez mechaniki** — i w takim
stanie przejechano cały cykl. Blokada dotyczy wyłącznie pracy pod obciążeniem:
po sprzężeniu z mechaniką **nie należy uruchamiać osi przed Auto-Tune**.

Źródło: [instrukcja ClearPath-SC](https://teknic.com/files/downloads/Clearpath-SC%20User%20Manual.pdf),
`Beta_SDK_Examples/LoadingConfigFile/LoadingConfigFile.cpp`.

### Dioda stanu na silniku — kody i diagnoza z 2026-08-30

Znaczenie diody LED na obudowie silnika ClearPath-SCSK (Appendix A instrukcji,
[Clearpath-SC User Manual](https://teknic.com/files/downloads/Clearpath-SC%20User%20Manual.pdf)):

| Zachowanie diody | Stan CPSC | Znaczenie |
|---|---|---|
| Zielona, migocząca | Enabled | praca normalna — **uzwojenia pod napięciem, silnik może ruszyć w każdej chwili** |
| Zielona, ciągła | Disabled | praca normalna — uzwojenia bez napięcia |
| Żółta, mrugająca | Shutdown | odpytać sterownik o kod wyjątku (aplikacja albo ClearView przez port diagnostyczny) |
| Czerwona, mrugająca | Fatal Error | możliwa awaria sprzętowa — zgłosić RMA, jeśli się utrzymuje |
| Zgaszona | brak/za niskie zasilanie DC bus | podać zasilanie DC, sprawdzić zgodność zasilacza z wymaganiami |

Dioda okresowo gaśnie na chwilę niezależnie od powyższego stanu — to sygnał
aktywnej komunikacji z hostem, nakłada się na wzorzec z tabeli.

**Chronologia diagnozy (2026-08-30, host produkcyjny):**

1. Operator zgłosił diody pomarańczowe na wszystkich trzech silnikach
   (poprzednio, podczas testów 2026-08-14 – 08-26, były zielone) i brak
   możliwości sterowania ręcznego z panelu WWW.
2. Ustalono, że panel działał w `MACHINE_MODE=sim` — więc nigdy nie mógł
   dotykać sprzętu niezależnie od diod. To wyjaśniało brak sterowania, ale
   nie diody.
3. Odtworzono SDK i sterownik Exar na hoście produkcyjnym (opisane w
   sekcjach wyżej i w „Uruchomienie mostka…” niżej), żeby móc odpytać sprzęt.
4. **Odrzucona hipoteza:** niepodłączone wejście Global Stop na hubie.
   Bezpośredni odczyt `IGrpShutdown::GetGlobalStopInputState()` pokazał
   **„NOT asserted” (OK/run)** — wejście jest w porządku.
5. **Odrzucona hipoteza:** zatrzaśnięty, nieaktualny alarm. Wysłanie
   `Motion.NodeStopClear()` (bez `EnableReq`, bez ruchu) czyściło alarm
   `EStopped` na chwilę, ale **wracał natychmiast** po kolejnym odczycie —
   więc coś aktywnie go wymuszało, nie był to tylko stary ślad.
6. **Ustalenie:** `IGrpShutdown::ShutdownWhenGet()` pokazało **Group
   Shutdown włączony (`enabled=1`) na wszystkich trzech węzłach**,
   `stopType=0x91`. To skonfigurowana funkcja sFoundation, nie usterka ani
   przypadkowy stan pinów.
7. **Robocza interpretacja** (niepotwierdzona w 100% — patrz zastrzeżenie w
   sekcji „3. Realtime i utrata łączności” wyżej): Group Shutdown to
   prawdopodobnie realizacja opisanego wcześniej **watchdoga sieciowego** —
   węzły trzymają się w `EStopped`, dopóki żaden mostek aktywnie się z nimi
   nie połączy i nie skonfiguruje/skasuje tego stanu. Zgodne z tym, że po
   uruchomieniu `sc4hub_bridge` (patrz niżej) diody powinny się zmienić —
   **do potwierdzenia wizualnie przez operatora**, nie zweryfikowane w tej
   sesji wprost.

**Wniosek:** silniki są sprawne (`ShutdownState: OK` w rejestrze, żadnych
innych alarmów poza `EStopped`). Pomarańczowa dioda była najprawdopodobniej
**poprawnym stanem bezpieczeństwa** przy braku aktywnego mostka, a nie
usterką sprzętową. Nie próbowano obchodzić Group Shutdown programowo poza
jednorazowym, jawnie potwierdzonym przez użytkownika testem `NodeStopClear()`.

### Diagnostyka bez ryzyka ruchu — narzędzia

Zamiast przykładu `NodeAlerts-Status` z SDK (który sam włącza `EnableReq` i
czyści alarmy), na potrzeby tej sesji napisano dwa małe, dedykowane programy
(nie ma ich w repozytorium — żyły w scratchpadzie sesji, do odtworzenia w
razie potrzeby wg poniższego opisu):

- **`ReadOnlyStatus`** — otwiera port, dla każdego węzła drukuje
  `Info.*`, `Status.RT` (rejestr statusu), `Status.Alerts`, oraz
  `ShutdownWhenGet()` (konfigurację Group Shutdown) i
  `GetGlobalStopInputState()` na poziomie portu. **Nie wywołuje** `EnableReq`,
  `AlertsClear`, `NodeStopClear` ani żadnej komendy ruchu.
- **`ClearEStop`** — dla każdego węzła: jeśli alarm `EStopped` jest obecny,
  wywołuje wyłącznie `Motion.NodeStopClear()`, potem odczytuje rejestry
  ponownie. **Nie wywołuje** `EnableReq` ani `AlertsClear` na innych alarmach.

Oba budowane bezpośrednio przez `g++` (nie przez Makefile przykładu, żeby
uniknąć konfliktu `main()` przy współdzielonym katalogu), np.:

```bash
g++ -std=c++11 -O3 -I"<SF>/inc/inc-pub" -o ReadOnlyStatus ReadOnlyStatus.cpp \
    -L"<SF>/sFoundation" -Wl,-rpath="<SF>/sFoundation" -lsFoundation20 -lpthread
```

### Do sprawdzenia: E-stop a komunikacja

Jeśli układ bezpieczeństwa odcina magistralę DC silników, to wciśnięty E-stop
**zabija także komunikację** — maszyna nie tylko staje, ale przestaje widzieć
osie. Mostek musi odróżniać ten stan od awarii łącza i wracać do pracy po
zwolnieniu E-stopu. Test: przebieg `SCNetworkReport` z wciśniętym E-stopem.

**Uwaga (2026-08-30):** operator potwierdził, że **wejście Global Stop na
SC4-Hub nie jest obecnie do niczego podłączone** („używamy bez tego”) — a
mimo to komunikacja z węzłami działała bez zarzutu przez cały czas diagnozy
(czyt./zapis rejestrów przez USB). To nie jest jeszcze test z prawdziwym,
certyfikowanym E-stopem maszyny (osobny układ, patrz sekcja 1 wyżej) — ten
test nadal czeka.

### Uwaga na przyszłość: diagnostyka pętli

Gdyby port znowu przestał się otwierać (`err=0x80040601`), kolejność sprawdzania:
24 V huba (dioda) → zasilanie magistrali DC silników → czerwona zworka
„end-of-loop" (zamyka pierścień, położenie zależy od liczby silników) →
obsadzenie złącz sekwencyjnie od pierwszego, bez przerw.

Źródło: [Troubleshooting MSP/ClearView Communication](https://www.teknic.com/files/downloads/USB-Communications.pdf).

## Uruchomienie mostka na hoście produkcyjnym (2026-08-30)

Host `walkner-motion-controller`: Ubuntu 26.04 LTS, kernel 7.0.0-30-generic,
Secure Boot **włączony**. Inna maszyna niż stacja robocza z sekcji
rozpoznania (2026-08-14) — część przeszkód jest inna.

### Pułapka 1: literówka w sterowniku Exar na nowszych nagłówkach jądra

Build `xr_usb_serial_common.ko` kończył się błędem:

```
error: 'struct usb_cdc_country_functional_desc' has no member named
'wCountyCode0'; did you mean 'wCountryCode0'?
```

Stary kod sterownika Teknica (z paczki z 2026-08-13) używa nazwy pola
`wCountyCode0` — literówki, którą jądro Linux miało w
`include/uapi/linux/usb/cdc.h` przez lata i **poprawiło na `wCountryCode0`**
w międzyczasie. Na starszych nagłówkach (stacja robocza, 6.8.0-40) literówka
jeszcze tam była, więc kompilował się bez zmian; na 7.0.0-30 już nie.

**Poprawka:** zmienić `cfd->wCountyCode0` na `cfd->wCountryCode0` w
`xr_usb_serial_common.c` (jedno wystąpienie, linia z `memcpy` kopiującym
`country_codes`). Ten sam offset i typ pola w strukturze — tylko nazwa się
zmieniła. Po poprawce moduł buduje się czysto.

### Pułapka 2: Secure Boot blokuje niepodpisany moduł

Po zbudowaniu, `insmod` kończył się:

```
insmod: ERROR: could not insert module xr_usb_serial_common.ko: Key was rejected by service
```

Przyczyna: `mokutil --sb-state` → `SecureBoot enabled`,
`/sys/kernel/security/lockdown` → `integrity`. Jądro odrzuca niepodpisane,
własnoręcznie zbudowane moduły.

**Rozwiązanie: podpisanie kluczem MOK** (Machine Owner Key) — Secure Boot
zostaje włączony, dochodzi jeden zaufany klucz tylko dla tego modułu:

```bash
# Generacja klucza (raz), jako root:
openssl req -new -x509 -newkey rsa:2048 -keyout MOK.priv -outform DER \
    -out MOK.der -nodes -days 36500 \
    -subj "/CN=motion-controller-lens SC4-Hub driver signing/"

# Podpisanie już zbudowanego .ko (BEZ ponownego `make` — inaczej nadpisze
# podpis niepodpisanym modułem):
/usr/src/linux-headers-$(uname -r)/scripts/sign-file sha256 MOK.priv MOK.der \
    xr_usb_serial_common.ko

# Instalacja modułu jak w Install_DRV_SCRIPT.sh (cp do /lib/modules/...,
# depmod -a, dopisanie do /etc/modules, insmod).

# Zgłoszenie klucza do enrollmentu — ustawia jednorazowe hasło:
sudo mokutil --import MOK.der
sudo reboot
```

Po restarcie, **na fizycznej konsoli maszyny** (nie przez SSH — MOK Manager
działa tylko na lokalnym wyświetlaczu, przed siecią i systemem) pojawia się
niebieski ekran **MOK Manager**: `Enroll MOK` → `Continue` → `Yes` → podać
hasło z `mokutil --import`. Po tym restart kończy się normalnie i moduł się
ładuje.

**Pułapka przy pierwszym podejściu:** restart bez wcześniejszego
`mokutil --import` **nie pokazuje żadnego ekranu** — nic nie zostało
zgłoszone do zatwierdzenia (`mokutil --list-new` puste), więc UEFI nie ma
czego pytać. Kolejność musi być: podpisz → `mokutil --import` → dopiero
`reboot`.

Klucz i skrypt trzymane w `/root/module-signing/` na hoście produkcyjnym
(poza repozytorium — to sekret podpisujący, nie kod).

### Pułapka 3: `/tmp` to `tmpfs` — restart kasuje scratchpad

Cały pobrany pakiet SDK i zbudowane narzędzia diagnostyczne, trzymane w
scratchpadzie sesji (`/tmp/claude-*/...`), **znikają przy każdym restarcie
maszyny** (`tmpfs`, pamięć RAM). Sterownik jądra (`/lib/modules/...`,
`/root/module-signing/`) i biblioteka zainstalowana systemowo
(`/usr/local/lib/`) **przetrwały** — to zwykłe dyski, nie `tmpfs`.

Konsekwencja: po każdym restarcie w trakcie tej sesji trzeba było od nowa
pobrać `Linux_Software.tar.gz` i zbudować `libsFoundation20.so` oraz
narzędzia diagnostyczne w scratchpadzie — sama biblioteka i sterownik jądra
zostawały nietknięte.

### Trwała instalacja biblioteki

Zamiast kopiować SDK do `vendor/teknic/` w repozytorium (utrudnione przez
to, że `/opt/motion-controller-lens` należy do `motionctl`, a bieżący
użytkownik administracyjny — `walkner` — nie ma tam prawa zapisu),
zainstalowano `libsFoundation20.so` **systemowo**, zgodnie z oficjalną
metodą „Systemwide Install” z `readme.txt` pakietu:

```bash
sudo cp libsFoundation20.so /usr/local/lib/
sudo cp MNuserDriver20.xml /usr/local/lib/
sudo ldconfig
ldconfig -p | grep sFoundation   # weryfikacja
```

Już skompilowany `bridge/sc4hub_bridge` (miał zaszyty `RUNPATH` wskazujący na
nieistniejącą ścieżkę z komputera dewelopera) zaczął się od razu poprawnie
linkować — dynamiczny linker sam spada na standardowe ścieżki (`ldconfig`),
gdy `RUNPATH` nie wskazuje niczego istniejącego. **Nie trzeba było
przebudowywać mostka.**

### Weryfikacja mostka — bez ryzyka ruchu

Kod `bridge/sc4hub_bridge.cpp` sprawdzony przed uruchomieniem: `EnableReq`
(moment na silniku) wywołuje wyłącznie `enableAxes()`, a to wywołują
wyłącznie komendy `HOME`/`MOVEXY`/`MOVEZ`/`JOG`/`SPINDLE` z protokołu
tekstowego. Samo uruchomienie procesu (`main()` → `openHardware()` →
`serve()`) tylko otwiera port i nasłuchuje na `127.0.0.1:8500` — nic nie
włącza automatycznie.

Test ręczny (pierwszy plan, przed wpięciem w usługę systemd):

```bash
cd bridge
sudo bash -c 'set -a; . ./machine.env; set +a; ./sc4hub_bridge'
```

Wypisał poprawne mapowanie osi (zgodne z `machine.env`), rozdzielczość
(800 imp/obr → 160 imp/mm), **„zezwolenie (Global Stop): aktywne"**, i zaczął
nasłuchiwać. Z drugiego terminala, komendami **ograniczonymi celowo do
nieruchowych** (`PING`, `STATUS`, `RESET`):

```bash
printf 'PING\r\nSTATUS\r\nRESET\r\nSTATUS\r\n' | nc -q1 127.0.0.1 8500
```

Odpowiedzi czyste: `OK PONG`, `OK STATE=NOT_HOMED EN=1 X=0.000 Y=0.000
Z=0.000 SP=0 REL=-`, `OK`, to samo po `RESET`. Potwierdza pełną drogę
USB → sFoundation → mostek → protokół tekstowy, bez włączania silników.

### Uruchomienie produkcyjne

Po weryfikacji ręcznej:

```bash
sudo systemctl enable motion-controller-bridge.service   # autostart po restarcie
sudo systemctl start motion-controller-bridge.service
sudo systemctl status motion-controller-bridge.service   # active (running), User=motionctl
```

Następnie w `/etc/systemd/system/motion-controller-lens.service` zmieniono:

```
Environment=MACHINE_MODE=clearcore
```

(było `sim`; `CLEARCORE_HOST=127.0.0.1`, `CLEARCORE_PORT=8500` już tam były),
`daemon-reload` + `restart motion-controller-lens.service`. Weryfikacja
odczytem, bez wysyłania żadnej komendy ruchu:

```bash
curl -s http://localhost:8000/api/status
# {"state":"NOT_HOMED","safety_enable":true,"position":{"x":0.0,"y":0.0,"z":0.0}, ...}
```

Zgodne z tym, co pokazywał mostek — cały łańcuch panel ↔ mostek ↔
sFoundation ↔ sprzęt jest połączony.

**Stan na koniec sesji (2026-08-30): `MACHINE_MODE=clearcore` jest aktywny w
produkcji.** Panel WWW od teraz wysyła realne komendy do prawdziwego
sprzętu.

> **Uwaga do nazw (temat A, zrobione później).** Tryb nazywa się dziś
> `sc4hub`, a adres mostka `BRIDGE_HOST`/`BRIDGE_PORT`. Wpisy `clearcore`
> i `CLEARCORE_*` w usłudze systemd **nie wymagają zmiany** — serwer
> przyjmuje je nadal jako nazwy historyczne. Szczegóły:
> [`zmiany/nazewnictwo-sc4hub.md`](zmiany/nazewnictwo-sc4hub.md).

> **Korekta (2026-08-30, sesja późniejsza).** Powyższe „czeka na
> potwierdzenie” już nieaktualne — w logu serwera widać udane
> `POST /api/machine/home` i wielokrotne `POST /api/machine/jog` (200 OK)
> jeszcze tego samego dnia, po starcie w trybie `clearcore`. Użytkownik
> potwierdził fizycznie przy maszynie: **ruch osi X/Y/Z i bazowanie
> działają poprawnie na sprzęcie.** `GET /api/status` zwraca `"state":
> "READY"`. Pierwsza realna komenda ruchu (temat tego zastrzeżenia) już się
> odbyła i została zweryfikowana — nie jest to już krok oczekujący.

## Do zrobienia

Przed zabudową mechaniki:

- [ ] **Auto-Tune każdej osi pod obciążeniem** — wymaga Windows z ClearView;
      zapisać `.mtr` i wczytywać z Linuksa (`LoadingConfigFile`).
- [ ] **Skonfigurować homing w ClearView** — dziś bazowanie jest tylko
      zerowaniem programowym, co na maszynie z mechaniką nie wystarczy.
- [ ] Zweryfikować pomiarowo tor operacji `LINIA` (interpolacja przybliżona).

Testy, których jeszcze nie zrobiono:

- [x] ~~STOP w trakcie ruchu~~ — zatrzymanie w 30 ms, maszyna staje, `ALARM`
      z komunikatem. Patrz [`zmiany/status-i-zatrzymanie.md`](zmiany/status-i-zatrzymanie.md).
- [ ] Utrata zezwolenia w trakcie ruchu — wymaga fizycznego zadziałania
      układu bezpieczeństwa.
- [ ] Zachowanie komunikacji przy wciśniętym E-stopie (czy odcina magistralę DC)
      — **prawdziwego, certyfikowanego E-stopu maszyny**, nie wejścia Global
      Stop na hubie (to niepodłączone, komunikacja mimo to działa — patrz wyżej).
- [x] ~~Reguła udev (`tools/99-teknic-sc4hub.rules`) — instalacja i weryfikacja
      przez przewtyknięcie huba.~~ Potwierdzone działające na hoście
      produkcyjnym 2026-08-30 (było już zainstalowane z wcześniejszej sesji).
- [x] ~~Pierwsze realne bazowanie na hoście produkcyjnym~~ — potwierdzone
      fizycznie przez użytkownika 2026-08-30: bazowanie i ruch osi X/Y/Z
      działają poprawnie na sprzęcie.
- [ ] Dokładne rozszyfrowanie maski `ShutdownWhenGet()` odpowiedzialnej za
      Group Shutdown (robocza interpretacja: realizacja watchdoga sieciowego
      — niepotwierdzona w 100%, patrz sekcja 3 „Ryzyka do rozstrzygnięcia”).
- [ ] Zdecydować, czy trzymać `vendor/teknic/` w `/opt/motion-controller-lens`
      na hoście produkcyjnym (dla `make -C bridge` przy przyszłych zmianach),
      czy zostać przy samej instalacji systemowej (`/usr/local/lib`) — obecnie
      tylko to drugie jest zrobione.

Pozostałe:

- [x] ~~Obciążalność wyjść `BRAKE_0`/`BRAKE_1` pod stycznik wrzeciona.~~
      **500 mA / 24 VDC** (instrukcja ClearPath-SC rev. 1.45, str. 47) —
      wystarcza na przekaźnik pośredniczący, nie na stycznik bezpośrednio.
      Uwaga: producent ostrzega, że system operacyjny może **przypadkowo
      załączyć** to wyjście — wymagane szeregowe wpięcie w obwód osłon.
      Patrz [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md).
- [ ] Zdecydować o losie `firmware/clearcore/` — usunąć czy zostawić jako
      specyfikację protokołu (mostek go implementuje).
- [x] ~~Przenieść pakiet Teknica do `vendor/teknic/` (poza gitem).~~
- [x] ~~Ustalić mapowanie węzłów na osie.~~
- [x] ~~Potwierdzić wykonalność mostka sFoundation.~~
- [x] ~~Zainstalować sterownik Exar i uruchomić mostek na hoście
      produkcyjnym.~~ 2026-08-30 — patrz „Uruchomienie mostka na hoście
      produkcyjnym” wyżej. `MACHINE_MODE=clearcore` aktywny.
