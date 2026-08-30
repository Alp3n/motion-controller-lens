# motion-controller-lens

Maszyna do **odcinania wlewków z plastikowych płytek optyki** (frezowanie
wystających, niepotrzebnych elementów po wtrysku), budowana od zera na serwach
**Teknic ClearPath-SC**, sterowanych bezpośrednio z PC przez bibliotekę
**Teknic sFoundation** (mostek do **SC4-Hub** po USB), z aplikacją webową
do obsługi i sterowania oraz API dla systemu **MES**.

## Jak to działa

1. **Technolog** przygotowuje program odcinania (współrzędne wlewków i rodzaj
   operacji) w webowym edytorze albo w Excelu — prosty plik tekstowy `.prg`,
   bez programowania. Nazwa pliku to 12-cyfrowy numer programu (12 NC).
2. **Operator** wybiera zlecenie w MES; MES wywołuje API maszyny i podaje
   numer programu — maszyna sama ładuje konfigurację.
3. **Serwer maszyny** (aplikacja webowa) pokazuje zlecenie i operacje,
   operator naciska START, a serwer wysyła ruchy przez **mostek `bridge/`**
   do serw ClearPath-SC podłączonych przez SC4-Hub.
4. **Bezpieczeństwo** realizuje niezależny, gotowy układ bezpieczeństwa
   (przekaźnik bezpieczeństwa, E-stop, kurtyny) podłączony do wbudowanego
   wejścia **Global Stop** na SC4-Hub — hub zatrzymuje wszystkie osie
   sprzętowo, niezależnie od oprogramowania.

Szczegóły: [docs/ARCHITEKTURA.md](docs/ARCHITEKTURA.md),
format programów: [docs/FORMAT_PROGRAMU.md](docs/FORMAT_PROGRAMU.md).

## Struktura repozytorium

```
docs/                  architektura i specyfikacja formatu programu
programs/              pliki programów .prg (przykłady; docelowo zasób sieciowy)
server/                serwer maszyny: API REST + WebSocket + panel WWW (Python/FastAPI)
  app/main.py          endpointy API (MES, programy, sterowanie)
  app/program.py       parser/walidator plików .prg
  app/machine.py       warstwa maszyny: symulator + łącze TCP do mostka bridge/
  app/axes.py          konfiguracja osi: długości, limity, przełożenia
  app/static/          panel operatora (/), konfiguracja osi (/axes),
                       edytor technologa (/editor)
config/axes.json       konfiguracja osi maszyny (tworzona przy pierwszym zapisie)
bridge/                mostek do SC4-Hub (C++, Teknic sFoundation), wystawia
                       serwerowi TCP na porcie 8500 — docs/zmiany/mostek-sc4hub.md
tools/                 skrypty pomocnicze: start z pulpitu, PDF-y dokumentacji
```

## Uruchomienie serwera (tryb symulacji — bez sprzętu)

Najprościej — skrypt startowy (sam tworzy środowisko i instaluje zależności;
wymaga Pythona 3.10+):

- **Windows**: podwójne kliknięcie `start.bat` (otworzy też przeglądarkę)
- **Linux/macOS**: `./start.sh`

Albo ręcznie:

```bash
cd server
pip install -r requirements.txt
PROGRAMS_DIR=../programs uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Panel operatora: http://localhost:8000/
- Konfiguracja osi: http://localhost:8000/axes
- Edytor technologa: http://localhost:8000/editor
- Dokumentacja API (OpenAPI): http://localhost:8000/docs

## Uruchomienie całości z pulpitu (maszyna albo symulator)

```bash
tools/zainstaluj-skrot.sh      # zakłada skrót „Maszyna — odcinanie wlewków" na pulpicie
```

Kliknięcie skrótu uruchamia mostek SC4-Hub (jeśli jest zbudowany i widzi
sprzęt), serwer maszyny i panel w przeglądarce; bez sprzętu wchodzi w tryb
symulacji i mówi o tym wprost. Zamknięcie okna zatrzymuje wszystko.
Bez pulpitu: `tools/uruchom-maszyne.sh [sim|maszyna]`.

## Dokumentacja w PDF

```bash
tools/docs-pdf.py              # docs/**.md -> docs/pdf/*.pdf
```

W panelu można zasymulować wybór zlecenia w MES (numer zlecenia + 12-cyfrowy
numer programu, np. `583912004711`), wykonać bazowanie i uruchomić cykl —
symulator odtwarza ruchy w czasie rzeczywistym, łącznie z utratą sygnału
Global Stop.

### Tryb sprzętowy (SC4-Hub, przez mostek `bridge/`)

```bash
MACHINE_MODE=clearcore CLEARCORE_HOST=127.0.0.1 \
PROGRAMS_DIR=/mnt/programy uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Wymaga uruchomionego mostka `bridge/sc4hub_bridge` widzącego SC4-Hub po USB —
budowanie i konfiguracja: [docs/zmiany/mostek-sc4hub.md](docs/zmiany/mostek-sc4hub.md).
Nazwy `MACHINE_MODE=clearcore`/`CLEARCORE_HOST` to dziedzictwo pierwotnej
architektury (miał być sterownik ClearCore — odrzucony, patrz
[docs/sterownik-sc4-hub.md](docs/sterownik-sc4-hub.md)); zmiana na neutralną
nazwę jest zaplanowana, ale jeszcze nie zrobiona —
[docs/plan-rozwoju.md](docs/plan-rozwoju.md).

## API dla MES

Po wybraniu zlecenia MES wywołuje:

```
POST /api/mes/select-order
{ "order_id": "ZL-2026-001", "program_number": "583912004711" }
```

Serwer ładuje i waliduje plik `583912004711.prg` z katalogu programów
i przygotowuje maszynę. Błędny lub brakujący program zwraca opisowy błąd
(404/422) — bez ryzyka startu z niepełną konfiguracją.

## Testy

```bash
cd server
pip install -r requirements.txt
python -m pytest
```
