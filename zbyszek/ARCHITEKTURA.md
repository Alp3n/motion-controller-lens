# Architektura systemu — maszyna do ocinania wlewków płytek optycznych

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
└────────────┘                                        │ lokalny IPC
                                                      │ (np. socket/gRPC)
                                       ┌──────────────▼───────────────┐
┌────────────────────┐  Global Stop    │  bridge — proces SysAPI      │
│ Niezależny system  │  (wejście na    │  (Teknic SysAPI, Python/C++) │
│ bezpieczeństwa     │  SC4-HUB)       │  • ruch osi, odczyt statusu   │
│ (gotowy przekaźnik │ ──────────────► │  • komunikacja z SC4-HUB      │
│  bezpieczeństwa,   │                 └──────────────┬───────────────┘
│  E-stop, kurtyny)  │                                │ USB
└────────────────────┘                 ┌──────────────▼───────────────┐
                                       │  SC4-HUB                     │
                                       │  (do 4 osi / hub, USB do PC) │
                                       └──────────────┬───────────────┘
                                                       │ złącza silnikowe
                                       ┌──────────────▼───────────────┐
                                       │ Serwa Teknic ClearPath-SCSK  │
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
  programowe i przełożenie posuwu każdej osi; limity są obszarem roboczym przy
  walidacji programów i granicą ruchu ręcznego. Model:
  [konfiguracja-osi.md](konfiguracja-osi.md).
- **API REST dla MES** — MES po wybraniu zlecenia wywołuje
  `POST /api/mes/select-order` z numerem zlecenia i 12-cyfrowym numerem
  programu; serwer ładuje plik programu i przygotowuje maszynę.
- **WebSocket** (`/ws/status`) — status maszyny na żywo dla panelu.
- **Warstwa maszyny** — dwa tryby (zmienna środowiskowa `MACHINE_MODE`):
  - `sim` — pełny symulator (rozwój i testy bez sprzętu),
  - `sysapi` — połączenie z procesem `bridge` (SysAPI, SC4-HUB).

### 2. Bridge — proces SysAPI (`bridge/`)

Proces (Python lub C++, w zależności od dojrzałości bindingów Teknic SysAPI
pod Linuksem) łączący się z SC4-HUB po USB i wystawiający serwerowi maszyny
lokalny interfejs ruchu (IPC — np. lokalny socket albo gRPC, żeby web stack
nigdy nie stał na drodze do bezpiecznego zatrzymania osi). Odpowiada za:

- inicjalizację i sterowanie osiami ClearPath-SCSK przez SysAPI,
  (pozycja, prędkość, limity momentu per oś),
- odczyt statusu i pozycji osi dla panelu operatora,
- odczyt stanu Global Stop z SC4-HUB (informacyjnie dla UI — zatrzymanie
  fizyczne realizuje sam hub, patrz niżej),
- ewentualną obsługę wrzeciona/frezu, jeśli sterowane jako oddzielna oś
  albo przekaźnik.

### 3. System bezpieczeństwa (sprzętowy, niezależny)

Bezpieczeństwo realizuje **gotowy, niezależny, certyfikowany układ**
(przekaźnik bezpieczeństwa + E-stop + osłony/kurtyny), podłączony do
**wbudowanego wejścia Global Stop na SC4-HUB**. Nie jest częścią
oprogramowania:

- zezwolenie = 1 → ruchy dozwolone,
- Global Stop aktywny → SC4-HUB **sprzętowo** zatrzymuje wszystkie osie
  podłączone w łańcuchu, niezależnie od stanu aplikacji czy procesu bridge.

Oprogramowanie (`bridge`) tylko **czyta i pokazuje** stan tego sygnału —
nie jest odpowiedzialne za samo zatrzymanie.

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
6. Serwer wysyła kolejne ruchy przez `bridge` do serw ClearPath-SCSK;
   ruch jest możliwy tylko przy nieaktywnym Global Stop.
7. Po zakończeniu cyklu maszyna wraca do pozycji bezpiecznej i czeka na
   kolejną sztukę / kolejne zlecenie.

## Stany maszyny

```
INIT ──► NOT_HOMED ──(bazowanie)──► READY ──(START)──► RUNNING ──► READY
                                      ▲                   │
                                      │      (STOP / Global Stop / błąd)
                                      └──(RESET)── ALARM ◄┘
```
