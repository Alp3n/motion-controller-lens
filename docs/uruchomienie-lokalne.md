# Uruchomienie lokalne — odstępstwa od README

Ustalenia z 2026-08-14, stacja robocza: Ubuntu 22.04.5 LTS, Python 3.10.12.

Serwer w trybie symulacji uruchamia się zgodnie z README, ale dwie rzeczy nie
działają „z pudełka". Obie dotkną każdego na czystej Ubuntu.

## 1. `./start.sh` wywala się na tworzeniu venva

Skrypt robi `python3 -m venv .venv`, ale w systemie brakuje modułu
**`ensurepip`** (Ubuntu wydziela go do pakietu `python3-venv`), a `pip` nie
istnieje globalnie. Venv nie powstaje i skrypt kończy się błędem.

**Rozwiązanie docelowe** — doinstalować pakiety systemowe:

```bash
sudo apt install -y python3-venv python3-pip
```

**Obejście bez roota** — utworzyć venv bez pipa i wstrzyknąć pip ręcznie:

```bash
cd server
python3 -m venv --without-pip .venv
curl -sS -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
.venv/bin/python /tmp/get-pip.py
.venv/bin/pip install -r requirements.txt
```

Po tym `./start.sh` działa normalnie, bo widzi gotowe `.venv`.

## 2. Wznowienie po operacji `PAUZA` nie jest opisane

Nie ma endpointu `/api/machine/resume`. Po zatrzymaniu na operacji `PAUZA`
(stan `PAUSED`) maszynę wznawia się **ponownym** wywołaniem:

```
POST /api/machine/start
```

Obsługuje to `server/app/machine.py` — `start()` w stanie `PAUSED` wywołuje
`resume()` zamiast startować cykl od nowa. README o tym milczy.

## Wynik weryfikacji

Sprawdzone na symulatorze (`MACHINE_MODE=sim`, `PROGRAMS_DIR=../programs`):

- **Testy: 20/20 przechodzi.** Jedno ostrzeżenie
  `StarletteDeprecationWarning` o `httpx` w `TestClient` — nieszkodliwe.
- Endpointy `/`, `/editor`, `/docs` odpowiadają 200.
- `POST /api/mes/select-order` z numerem `583912004711` wczytał program
  „Plytka soczewki 50mm - lewa" (PMMA, 12000 obr/min, 4 operacje).
- Pełny cykl: bazowanie → `READY` → START → operacje 1–2 (`PUNKT`),
  operacja 3 (`LINIA`, przejazd 40→55 mm w X na Z = −1,5) → operacja 4
  (`PAUZA`) zatrzymała maszynę w `PAUSED` z wyłączonym wrzecionem → wznowienie
  → powrót do `READY` w pozycji (0, 0, 10).

Symulator odtwarza ruchy w czasie rzeczywistym, zgodnie z opisem w README.

## Uwaga o kopii roboczej

Projekt pobrano jako **archiwum ZIP gałęzi `main`**, bo w systemie nie ma
`git`. To snapshot bez historii i bez remote'a — `git pull` i `git push` tu nie
zadziałają. Do normalnej pracy nad kodem:

```bash
sudo apt install -y git
```

## Nietestowane

- Tryb sprzętowy `MACHINE_MODE=clearcore` — brak ClearCore. Sprzęt na maszynie
  to SC4-Hub, patrz [`sterownik-sc4-hub.md`](sterownik-sc4-hub.md).
- Firmware z `firmware/clearcore/`.
