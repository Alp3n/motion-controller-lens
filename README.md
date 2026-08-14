# motion-controller-lens

Maszyna do **ocinania wlewków z plastikowych płytek optyki** (frezowanie
wystających, niepotrzebnych elementów po wtrysku), budowana od zera na serwach
**Teknic ClearPath** ze sterownikiem **Teknic ClearCore**, z aplikacją webową
do obsługi i sterowania oraz API dla systemu **MES**.

## Jak to działa

1. **Technolog** przygotowuje program ocinania (współrzędne wlewków i rodzaj
   operacji) w webowym edytorze albo w Excelu — prosty plik tekstowy `.prg`,
   bez programowania. Nazwa pliku to 12-cyfrowy numer programu (12 NC).
2. **Operator** wybiera zlecenie w MES; MES wywołuje API maszyny i podaje
   numer programu — maszyna sama ładuje konfigurację.
3. **Serwer maszyny** (aplikacja webowa) pokazuje zlecenie i operacje,
   operator naciska START, a serwer wysyła ruchy do sterownika ClearCore.
4. **Bezpieczeństwo** realizuje niezależny, gotowy układ bezpieczeństwa —
   ClearCore czyta tylko jeden sygnał zezwolenia na dedykowanym wejściu.

Szczegóły: [docs/ARCHITEKTURA.md](docs/ARCHITEKTURA.md),
format programów: [docs/FORMAT_PROGRAMU.md](docs/FORMAT_PROGRAMU.md).

## Struktura repozytorium

```
docs/                  architektura i specyfikacja formatu programu
programs/              pliki programów .prg (przykłady; docelowo zasób sieciowy)
server/                serwer maszyny: API REST + WebSocket + panel WWW (Python/FastAPI)
  app/main.py          endpointy API (MES, programy, sterowanie)
  app/program.py       parser/walidator plików .prg
  app/machine.py       warstwa maszyny: symulator + łącze TCP do ClearCore
  app/static/          panel operatora (/) i edytor technologa (/editor)
firmware/clearcore/    firmware C++ sterownika ClearCore (osie, wrzeciono,
                       sygnał zezwolenia, protokół TCP)
```

## Uruchomienie serwera (tryb symulacji — bez sprzętu)

```bash
cd server
pip install -r requirements.txt
PROGRAMS_DIR=../programs uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Panel operatora: http://localhost:8000/
- Edytor technologa: http://localhost:8000/editor
- Dokumentacja API (OpenAPI): http://localhost:8000/docs

W panelu można zasymulować wybór zlecenia w MES (numer zlecenia + 12-cyfrowy
numer programu, np. `583912004711`), wykonać bazowanie i uruchomić cykl —
symulator odtwarza ruchy w czasie rzeczywistym, łącznie z utratą sygnału
zezwolenia.

### Tryb sprzętowy (ClearCore)

```bash
MACHINE_MODE=clearcore CLEARCORE_HOST=192.168.0.50 \
PROGRAMS_DIR=/mnt/programy uvicorn app.main:app --host 0.0.0.0 --port 8000
```

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
