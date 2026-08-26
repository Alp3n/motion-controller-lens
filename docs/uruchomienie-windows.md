# Uruchomienie na Windows 11 (VS Code)

Instrukcja pod `.vscode/` z `docs/zmiany/srodowisko-testowe-vscode.md`.
Oparta na `start.bat`; **nie zweryfikowana samodzielnie na Windows** (ten
dokument powstał w środowisku Linux) — do potwierdzenia przy pierwszym
uruchomieniu.

## Wymagania

- [Python 3.10+](https://www.python.org/downloads/) — przy instalacji zaznacz
  „Add python.exe to PATH”.
- [Git](https://git-scm.com/download/win).
- [VS Code](https://code.visualstudio.com/) + rozszerzenie **Python**
  (ms-python.python) — repo samo je zaproponuje przy otwarciu.

## Postawienie środowiska

```powershell
git clone <adres-repo>
cd motion-controller-lens
code .
```

W VS Code: `Ctrl+Shift+P` → **Tasks: Run Task** →
„Środowisko: utwórz venv i zainstaluj zależności”.

Albo ręcznie w terminalu (PowerShell):

```powershell
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Uruchomienie serwera (tryb symulacji)

Najprościej: podwójne kliknięcie `start.bat` w katalogu głównym repo
(otwiera też przeglądarkę).

Z VS Code: **Run and Debug** (`Ctrl+Shift+D`) → „Serwer (symulacja)” → F5.

Ręcznie:

```powershell
cd server
$env:PROGRAMS_DIR = "../programs"
$env:AXES_CONFIG = "../config/axes.json"
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Panel: http://localhost:8000/ · testy API: http://localhost:8000/docs

## Testy

Z VS Code: panel **Testing** (ikonka probówki) → **Run All Tests** — albo
`Ctrl+Shift+P` → **Tasks: Run Task** → „Testy: pytest”.

Ręcznie:

```powershell
cd server
.venv\Scripts\pytest -q
```
