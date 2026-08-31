# Architektura systemu — maszyna do odcinania wlewków płytek optycznych

## Cel maszyny

Maszyna frezuje (ocina) wlewki — wystające, niepotrzebne elementy po wtrysku —
z plastikowej płytki optyki. Operacje (współrzędne i rodzaj cięcia) definiuje
technolog w prostym pliku programu. Maszyna ładuje program automatycznie po
wybraniu zlecenia w systemie MES.

## Schemat systemu

```
┌────────────┐   nr programu (12 NC)   ┌──────────────────────────────┐
│    MES     │ ──────────────────────► │  Serwer maszyny (aplikacja   │
│ (zlecenia) │      REST API           │  webowa + API, Python)       │
└────────────┘                         │                              │
                                       │  • panel operatora (WWW)     │
        katalog plików programów       │  • edytor technologa (WWW)   │
┌────────────┐                         │  • parser plików .prg        │
│ Pliki .prg │ ◄─────────────────────► │  • API REST + WebSocket      │
│ (12 cyfr)  │      odczyt/zapis       └──────────────┬───────────────┘
└────────────┘                                        │ TCP lokalny,
                                                      │ port 8500
                                       ┌──────────────▼───────────────┐
┌────────────────────┐  Global Stop    │  bridge (sc4hub_bridge, C++, │
│ Niezależny system  │  (wejście na    │  Teknic sFoundation)         │
│ bezpieczeństwa     │  SC4-Hub)       │  • ruch osi, odczyt statusu   │
│ (gotowy przekaźnik │ ──────────────► │  • komunikacja z SC4-Hub      │
│  bezpieczeństwa,   │                 └──────────────┬───────────────┘
│  E-stop, kurtyny)  │                                │ USB
└────────────────────┘                 ┌──────────────▼───────────────┐
                                       │  SC4-Hub                     │
                                       │  (do 4 osi / hub, USB do PC) │
                                       └──────────────┬───────────────┘
                                                       │ złącza silnikowe
                                       ┌──────────────▼───────────────┐
                                       │ Serwa Teknic ClearPath-SC    │
                                       │ osie X / Y / Z (+ kolejne)   │
                                       └──────────────────────────────┘
```

## Komponenty

### 1. Serwer maszyny (`server/`)

Aplikacja webowa w Pythonie (FastAPI) uruchamiana na komputerze przemysłowym
(mini PC, Linux) przy maszynie. Zapewnia:

- **Panel operatora** (`/`) — wybór/podgląd zlecenia, START/STOP, bazowanie,
  status osi, sygnał Global Stop, postęp operacji, panel JOG (ruch ręczny).
- **Edytor technologa** (`/editor`) — tworzenie i edycja programów w formie
  tabeli, bez programowania; zapis do pliku w formacie opisanym w
  [FORMAT_PROGRAMU.md](FORMAT_PROGRAMU.md).
- **Konfiguracja osi** (`/axes`) — długość fizyczna, punkt bazowania, limity
  programowe, przełożenie posuwu oraz prędkość JOG każdej osi; limity są
  obszarem roboczym przy walidacji programów i granicą ruchu ręcznego.
  Model: [konfiguracja-osi.md](konfiguracja-osi.md).
- **Konfiguracja bazowania** (`/homing`) — kolejność bazowania osi, sposób
  (HardStop / programowe zerowanie), limit momentu, offset i prędkość dojazdu.
  Parametry HardStop to **zapis tego, co ma być ustawione w ClearView** —
  serwer ich nie wysyła; na sprzęcie sekwencję wykonuje serwo po jednej
  komendzie `HOME`. Szczegóły:
  [zmiany/ekran-bazowania.md](zmiany/ekran-bazowania.md).
- **Profile parametrów** (`/profiles`) — trzy poziomy siły i prędkości
  (globalny/cykl/program technologa), edycja i przełączanie aktywnego
  profilu. Limit momentu dziś tylko w symulatorze — protokół mostka nie ma
  jeszcze tej komendy. Szczegóły:
  [zmiany/profile-parametrow-etap2.md](zmiany/profile-parametrow-etap2.md),
  [zmiany/ekran-profili.md](zmiany/ekran-profili.md).
- **Cykl maszyny** (`/cycle`) — kroki poziomu admina wokół programu detalu
  (RUCH, PROGRAM, WYJSCIE, PAUZA), uruchomienie jako jeden przebieg
  (półautomatyczny) albo pętla bez zatrzymania (automatyczny, temat F).
  Szczegóły: [model-cyklu-maszyny.md](model-cyklu-maszyny.md),
  [zmiany/cykl-na-sprzecie.md](zmiany/cykl-na-sprzecie.md).
- **API REST dla MES** — MES po wybraniu zlecenia wywołuje
  `POST /api/mes/select-order` z numerem zlecenia i 12-cyfrowym numerem
  programu; serwer ładuje plik programu i przygotowuje maszynę.
- **WebSocket** (`/ws/status`) — status maszyny na żywo dla panelu.
- **Warstwa maszyny** (`app/machine.py`) — dwa tryby (zmienna środowiskowa
  `MACHINE_MODE`):
  - `sim` — pełny symulator (rozwój i testy bez sprzętu),
  - `sc4hub` — połączenie TCP z mostkiem `bridge/` (SC4-Hub), adres
    z `BRIDGE_HOST`/`BRIDGE_PORT`. Dawne nazwy `clearcore`,
    `CLEARCORE_HOST` i `CLEARCORE_PORT` **dalej są przyjmowane** (hosty
    produkcyjne mają je w usłudze systemd) —
    [`zmiany/nazewnictwo-sc4hub.md`](zmiany/nazewnictwo-sc4hub.md).

### 2. Mostek do SC4-Hub (`bridge/`)

Wcześniejsza koncepcja repozytorium zakładała samodzielny sterownik
**Teknic ClearCore** z własnym firmware C++. Sprzętem na maszynie jest
natomiast **Teknic SC4-Hub** (komunikacja z serwami po USB, bez firmware do
wgrania) — ClearCore odrzucony, decyzja ostateczna. Historia i konsekwencje
tej rozbieżności: [sterownik-sc4-hub.md](sterownik-sc4-hub.md).

`bridge/sc4hub_bridge.cpp` to zbudowany i **przetestowany na sprzęcie** (pełny
cykl programu na trzech serwach) demon C++ na bibliotece Teknic
**sFoundation** (`vendor/teknic/lib/libsFoundation20.so`, poza gitem —
pobierana ze strony producenta). Łączy się z SC4-Hub po USB i wystawia
serwerowi maszyny dokładnie ten protokół tekstowy po TCP (port 8500), jaki
pierwotnie miał realizować firmware ClearCore — patrz
[„Protokół mostka"](#protokół-mostka-tcp-port-8500) niżej. Dzięki temu
warstwa `app/machine.py` nie wymagała zmiany logiki przy przejściu na
SC4-Hub — protokół zadziałał jako szew dokładnie tak, jak zakładano. Budowa
i konfiguracja: [zmiany/mostek-sc4hub.md](zmiany/mostek-sc4hub.md).

Odpowiada za:

- inicjalizację i sterowanie osiami ClearPath-SC przez sFoundation (pozycja,
  prędkość, limity),
- odczyt statusu i pozycji osi dla panelu operatora,
- odczyt stanu Global Stop z SC4-Hub (informacyjnie dla UI — zatrzymanie
  fizyczne realizuje sam hub, patrz niżej),
- sterowanie wrzecionem przez wyjścia huba (`brake0`/`brake1` — dziś tylko
  włącz/wyłącz, bez PWM).

> Wcześniejsza wersja tego dokumentu (robocza notatka z sesji 2026-08-25)
> opisywała ten komponent jako „proces SysAPI", hipotetycznie w Pythonie
> lub C++, komunikujący się z serwerem przez lokalny socket/gRPC — zanim
> mostek został faktycznie zbudowany. Powyższy opis to stan rzeczywisty,
> zweryfikowany na sprzęcie 2026-08-14: biblioteka to **sFoundation**, nie
> „SysAPI" (to dwie różne nazwy z materiałów Teknica — trzymamy się tej
> potwierdzonej budową i działaniem), a protokół to TCP, nie gRPC.

### 3. System bezpieczeństwa (sprzętowy, niezależny)

Bezpieczeństwo realizuje **gotowy, niezależny, certyfikowany układ**
(przekaźnik bezpieczeństwa + E-stop + osłony/kurtyny), podłączony do
**wbudowanego wejścia Global Stop na SC4-Hub**. Nie jest częścią
oprogramowania:

- zezwolenie = 1 → ruchy dozwolone,
- Global Stop aktywny → SC4-Hub **sprzętowo** zatrzymuje wszystkie osie
  podłączone w łańcuchu, niezależnie od stanu aplikacji czy procesu bridge.

Oprogramowanie (`bridge`) tylko **czyta i pokazuje** stan tego sygnału —
nie jest odpowiedzialne za samo zatrzymanie. Global Stop w SC4-Hub to
funkcja sterowania, nie funkcja bezpieczeństwa w sensie certyfikacji —
Teknic nie deklaruje dla niej kategorii bezpieczeństwa; niezależny układ
sprzętowy pozostaje jedynym elementem, na którym opiera się bezpieczeństwo.

### 4. Pliki programów (`programs/`)

Katalog (docelowo zasób sieciowy) z plikami `NNNNNNNNNNNN.prg`, gdzie
`NNNNNNNNNNNN` to 12-cyfrowy numer programu (12 NC) — ten sam numer, który MES
podaje po wybraniu zlecenia. Format pliku: prosty, czytelny dla technologa,
edytowalny także w Excelu — patrz [FORMAT_PROGRAMU.md](FORMAT_PROGRAMU.md).

## Przepływ produkcyjny

1. Technolog przygotowuje program w edytorze (lub w Excelu) i zapisuje go pod
   12-cyfrowym numerem w katalogu programów.
2. Operator wybiera zlecenie w MES.
3. MES wywołuje API maszyny, podając numer zlecenia i numer programu.
4. Serwer ładuje i waliduje plik programu, pokazuje operatorowi zlecenie
   i listę operacji.
5. Operator zakłada płytkę, potwierdza i naciska START.
6. Serwer wysyła kolejne ruchy przez `bridge` do serw ClearPath-SC
   podłączonych przez SC4-Hub; ruch jest możliwy tylko przy nieaktywnym
   Global Stop.
7. Po zakończeniu cyklu maszyna wraca do pozycji bezpiecznej i czeka na
   kolejną sztukę / kolejne zlecenie.

## Stany maszyny

```
INIT ──► NOT_HOMED ──(bazowanie)──► READY ──(START)──► RUNNING ──► READY
                                      ▲                   │
                                      │      (STOP / Global Stop / błąd)
                                      └──(RESET)── ALARM ◄┘
```

## Protokół mostka (TCP, port 8500)

Komendy tekstowe, jedna na linię; odpowiedź `OK ...` lub `ERR <opis>`.
Zaimplementowane w `bridge/sc4hub_bridge.cpp` — pierwotnie zdefiniowane pod
firmware ClearCore, zachowane bez zmian jako gotowy szew między warstwą
Pythona a sprzętem. Same nazwy w serwerze są już neutralne
(`MACHINE_MODE=sc4hub`, `BRIDGE_HOST`) — patrz
[`zmiany/nazewnictwo-sc4hub.md`](zmiany/nazewnictwo-sc4hub.md).

```
PING                      -> OK PONG
STATUS                    -> OK STATE=READY EN=1 X=12.500 Y=-3.000 Z=10.000 SP=0 REL=-
HOME                      -> bazowanie osi (dziś: zerowanie programowe, patrz uwaga niżej)
MOVEXY <x> <y> <posuw>    -> interpolowany ruch XY [mm, mm/min]
MOVEZ <z> <posuw>         -> ruch osi Z
JOG <X/Y/Z> <dyst> <posuw>-> ruch ręczny
SPINDLE <0/1> [obr/min]   -> wrzeciono wył/zał
STOP                      -> zatrzymanie natychmiastowe
RESET                     -> kasowanie alarmu
RELEASE <X/Y/Z/ALL>       -> zdjęcie momentu (ruch ręczny osią)
HOLD <X/Y/Z/ALL>          -> przywrócenie momentu
AXCFG <X|Y|Z> MMREV=<mm/obr> [SOFTMIN=<mm> SOFTMAX=<mm>] [LEN=<mm>] [HOME=<minus|plus|srodek>]
                          -> konfiguracja osi (limity, przełożenie) — patrz konfiguracja-osi.md
```

`STATUS` zawiera pole `REL=` z literami zluzowanych osi (albo `-`). W stanie
`ALARM` na końcu linii dochodzi `MSG=<powód>` — pole jest zawsze ostatnie,
bo tekst zawiera spacje.

**Świadome uproszczenia mostka** (stan na 2026-08-14, patrz
[zmiany/mostek-sc4hub.md](zmiany/mostek-sc4hub.md) po szczegóły):

- `HOME` to dziś zerowanie programowe (bieżąca pozycja = zero), nie
  prawdziwe bazowanie — homing ClearPath-SC wymaga konfiguracji w ClearView
  (Windows), jeszcze nie zrobionej.
- Interpolacja XY jest przybliżona (prędkości osi dobrane, by skończyły
  jednocześnie) — dla operacji `LINIA` wymaga weryfikacji pomiarowej toru.
- Wrzeciono tylko śledzone (`SPINDLE_OUTPUT=none` domyślnie) — sterowanie
  PWM nie jest zrobione.

Serwer maszyny sam tłumaczy operacje programu (`.prg`) na sekwencję tych
komend — mostek nie zna formatu programów i pozostaje prosty.
