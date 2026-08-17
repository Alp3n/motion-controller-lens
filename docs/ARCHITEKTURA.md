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
└────────────┘                                        │ Ethernet (TCP,
                                                      │ protokół tekstowy)
                                       ┌──────────────▼───────────────┐
┌────────────────────┐  1 sygnał       │  Sterownik Teknic ClearCore  │
│ Niezależny system  │  zezwolenia     │  (firmware C++)              │
│ bezpieczeństwa     │ ──────────────► │  • interpolacja ruchów       │
│ (gotowy przekaźnik │  (wejście DI)   │  • obsługa serw ClearPath    │
│  bezpieczeństwa,   │                 │  • odczyt sygnału zezwolenia │
│  E-stop, kurtyny)  │                 └──────────────┬───────────────┘
└────────────────────┘                                │ złącza silnikowe
                                       ┌──────────────▼───────────────┐
                                       │ Serwa Teknic ClearPath (MC)  │
                                       │ osie X / Y / Z + wrzeciono   │
                                       └──────────────────────────────┘
```

## Komponenty

### 1. Serwer maszyny (`server/`)

Aplikacja webowa w Pythonie (FastAPI) uruchamiana na komputerze przemysłowym
przy maszynie. Zapewnia:

- **Panel operatora** (`/`) — wybór/podgląd zlecenia, START/STOP, bazowanie,
  status osi, sygnał zezwolenia, postęp operacji, panel JOG (ruch ręczny).
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
  - `clearcore` — połączenie TCP ze sterownikiem ClearCore.

### 2. Firmware ClearCore (`firmware/clearcore/`)

Program w C++ na sterownik Teknic ClearCore (biblioteka ClearCore w C++).
Odpowiada za:

- wykonywanie ruchów osi X/Y/Z na serwach ClearPath,
- załączanie wrzeciona/frezu,
- prosty tekstowy protokół TCP (port 8500) — komendy `HOME`, `MOVE`,
  `SPINDLE`, `STOP`, `STATUS`,
- **odczyt jednego sygnału zezwolenia** z niezależnego systemu
  bezpieczeństwa na dedykowanym wejściu cyfrowym — bez zezwolenia żaden
  ruch nie zostanie wykonany, a trwający ruch jest natychmiast przerywany.

> Uwaga o serwach: ClearPath serii **MC** ma kontroler ruchu w silniku i jest
> sterowany sygnałami cyfrowymi (np. tryb Pulse Burst Positioning). Firmware
> używa API `MotorDriver` biblioteki ClearCore — tryb pracy silnika
> skonfigurowany w programie ClearPath MSP musi odpowiadać trybowi ustawionemu
> w firmware (patrz `firmware/clearcore/README.md`).

### 3. System bezpieczeństwa (sprzętowy, niezależny)

Bezpieczeństwo realizuje **gotowy, niezależny, certyfikowany układ**
(przekaźnik bezpieczeństwa + E-stop + osłony/kurtyny). Nie jest częścią
oprogramowania. Oprogramowanie (ClearCore) **tylko czyta** jeden sygnał
zezwolenia na dedykowanym wejściu:

- zezwolenie = 1 → ruchy dozwolone,
- zezwolenie = 0 → natychmiastowe zatrzymanie i blokada startu; odcięcie
  zasilania mocy silników realizuje układ bezpieczeństwa niezależnie od
  oprogramowania.

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
6. Serwer wysyła kolejne ruchy do ClearCore; ClearCore wykonuje je tylko przy
   aktywnym sygnale zezwolenia.
7. Po zakończeniu cyklu maszyna wraca do pozycji bezpiecznej i czeka na
   kolejną sztukę / kolejne zlecenie.

## Stany maszyny

```
INIT ──► NOT_HOMED ──(bazowanie)──► READY ──(START)──► RUNNING ──► READY
                                      ▲                   │
                                      │      (STOP / brak zezwolenia / błąd)
                                      └──(RESET)── ALARM ◄┘
```
