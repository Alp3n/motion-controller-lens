# Środowisko testowe pod Linuksa i VS Code

Dodano konfigurację VS Code, żeby po otworzeniu repo edytor od razu widział
właściwy interpreter Pythona, umiał odpalić serwer w debugerze i uruchamiać
testy z panelu Testing. Zweryfikowano na czystym Ubuntu 24.04 / Python 3.11:
`server/.venv` + `pip install -r requirements.txt` + `pytest` — 59/59 zielone,
serwer w trybie symulacji odpowiada 200 na `/`, `/axes`, `/editor`, `/docs`.

## Pliki

- `.vscode/settings.json` — interpreter `server/.venv/bin/python`, testy
  pytest z `cwd=server` (import `app.*` wymaga uruchomienia z katalogu
  `server/`, inaczej `ModuleNotFoundError: app`).
- `.vscode/launch.json` — konfiguracje debugowania: „Serwer (symulacja)”
  (uvicorn z `--reload`) i „Testy (pytest)”.
- `.vscode/tasks.json` — zadania: utworzenie venv i instalacja zależności,
  start serwera, uruchomienie testów.
- `.vscode/extensions.json` — rekomendacja `ms-python.python` i
  `ms-python.debugpy`.

## Uwagi

- Poprawka z `docs/uruchomienie-lokalne.md` (brak `ensurepip` na Ubuntu 22.04)
  nie wystąpiła na Ubuntu 24.04 — `python3 -m venv` od razu miał działający
  `pip`. Obejście z tamtego dokumentu zostaje aktualne dla starszych Ubuntu.
- `.venv/` jest już w `.gitignore` — środowisko trzeba utworzyć lokalnie
  (zadanie „Środowisko: utwórz venv i zainstaluj zależności” w VS Code albo
  `./start.sh`).
- Nietestowane: tryb sprzętowy `MACHINE_MODE=sc4hub` (dawniej `clearcore`)/SC4-Hub oraz firmware
  — jak dotąd, bo tu nie ma sprzętu.
