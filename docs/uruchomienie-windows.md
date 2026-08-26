# Uruchomienie na Windows 11 (VS Code) — przewodnik krok po kroku

Skrócona wersja i konfiguracja `.vscode/` opisana też w
`docs/zmiany/srodowisko-testowe-vscode.md`. Ten dokument tłumaczy każdy krok
od zera — dla kogoś, kto nie programował wcześniej. Oparty na `start.bat`;
**nie zweryfikowany samodzielnie na Windows** (powstał w środowisku Linux) —
do potwierdzenia przy pierwszym uruchomieniu.

## Słowniczek — zanim zaczniemy

- **Python** — język programowania, w którym napisany jest serwer maszyny
  (`server/app/`). Żeby uruchomić kod w Pythonie, komputer musi mieć
  zainstalowany „interpreter” Pythona — program, który czyta i wykonuje ten
  kod.
- **Git** — program do wersjonowania kodu: pamięta historię zmian i pozwala
  pobrać (`clone`) kopię projektu z GitHuba na dysk.
- **VS Code** — edytor kodu (program do pisania i czytania kodu, z podświetlaniem
  składni, podpowiedziami, wbudowanym terminalem i debugerem).
- **Terminal / PowerShell** — okno tekstowe, w którym wpisuje się komendy
  zamiast klikać myszką. VS Code ma wbudowany terminal (`Ctrl+`` `` `` — klawisz
  z tyldą, pod Esc).
- **Zależności (dependencies)** — gotowe biblioteki kodu, których używa ten
  projekt zamiast pisać wszystko od zera (np. **FastAPI** — framework do
  budowania serwerów WWW, **uvicorn** — program, który taki serwer faktycznie
  uruchamia i nasłuchuje połączeń). Lista jest w `server/requirements.txt`.
- **venv (virtual environment)** — osobny, odizolowany zestaw zainstalowanych
  bibliotek Pythona *tylko dla tego projektu*. Dzięki temu instalacja
  zależności jednego projektu nie psuje innych projektów na tym samym
  komputerze. Fizycznie to po prostu folder `server/.venv/`.
- **Serwer** — program, który działa w tle i nasłuchuje na porcie sieciowym
  (tu: `8000`); przeglądarka łączy się z nim pod adresem
  `http://localhost:8000/`. „localhost” znaczy „ten sam komputer”.
- **Tryb symulacji** — serwer udaje, że steruje maszyną, bez podłączonego
  sprzętu. Do nauki i testów to jest dokładnie to, czego potrzebujesz.
- **Testy (pytest)** — małe programy, które same sprawdzają, czy reszta kodu
  działa poprawnie (np. „czy parser programu `.prg` poprawnie odczytuje
  współrzędne”). Uruchamia się je zamiast ręcznie klikać całą aplikację za
  każdym razem, gdy coś zmienisz w kodzie.

## Krok 1 — zainstaluj Pythona

1. Wejdź na https://www.python.org/downloads/ i pobierz najnowszą wersję
   (3.10 lub nowszą).
2. Uruchom instalator. **Ważne:** na pierwszym ekranie zaznacz na dole
   „**Add python.exe to PATH**” — bez tego Windows nie będzie wiedział, gdzie
   szukać Pythona w terminalu.
3. Sprawdź, czy się udało — otwórz terminal (Windows: przycisk Start, wpisz
   „PowerShell”, Enter) i wpisz:

   ```powershell
   python --version
   ```

   Powinno pokazać coś w stylu `Python 3.12.4`.

## Krok 2 — zainstaluj Git

1. Pobierz z https://git-scm.com/download/win, zainstaluj z domyślnymi
   ustawieniami (Next, Next, ..., Install).
2. Sprawdź w terminalu:

   ```powershell
   git --version
   ```

## Krok 3 — zainstaluj VS Code

1. Pobierz z https://code.visualstudio.com/ i zainstaluj.
2. Otwórz VS Code. Przy pierwszym otwarciu tego projektu edytor sam
   zaproponuje instalację rozszerzenia **Python** (ms-python.python) —
   zainstaluj je (przycisk „Install”). Jeśli nie zaproponuje, wejdź w ikonę
   klocków po lewej stronie (Extensions), wpisz „Python”, zainstaluj to od
   Microsoftu.

## Krok 4 — pobierz projekt na dysk

W terminalu (PowerShell), w folderze gdzie chcesz mieć projekt (np.
`Dokumenty`):

```powershell
git clone <adres-repo>
cd motion-controller-lens
code .
```

`code .` otwiera bieżący folder w VS Code. Od teraz pracujemy z poziomu VS
Code.

## Krok 5 — postaw środowisko (venv + zależności)

W VS Code otwórz terminal: menu **Terminal → New Terminal** (albo
`` Ctrl+` ``). Domyślnie terminal otwiera się w głównym folderze projektu.

**Najprościej:** `Ctrl+Shift+P` (paleta poleceń) → wpisz „Run Task” → wybierz
**Tasks: Run Task** → wybierz „**Środowisko: utwórz venv i zainstaluj
zależności**”. VS Code zrobi to za Ciebie i pokaże wynik w terminalu.

**Albo ręcznie** (te same trzy komendy, wpisywane po kolei, Enter po każdej):

```powershell
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

- `python -m venv .venv` — tworzy folder `.venv` z odizolowanym środowiskiem
  (to może chwilę potrwać, bez komunikatu — to normalne).
- `.venv\Scripts\pip install -r requirements.txt` — instaluje w tym
  środowisku biblioteki z listy w `requirements.txt` (FastAPI, uvicorn,
  pytest i inne). Zobaczysz kilkanaście linijek `Collecting...`,
  `Installing...` — to jest w porządku.

Ten krok robisz **raz** (chyba że skasujesz folder `.venv` albo zmieni się
`requirements.txt`).

## Krok 6 — uruchom serwer (tryb symulacji)

Trzy sposoby, wybierz dowolny:

**A) Dwuklik na `start.bat`** w Eksploratorze plików Windows, w głównym
folderze projektu (`motion-controller-lens`, ten z `README.md`, `server/`,
`start.bat` obok siebie — **nie** wewnątrz folderu `server`). Otworzy się
czarne okno konsoli i automatycznie otworzy się przeglądarka.

> Jeśli uruchamiasz `start.bat` z terminala, a nie dwuklikiem — komenda
> `.\start.bat` też musi być wpisana będąc w folderze głównym, nie w
> `server`. Skrypt sam robi `cd server` w środku; uruchomiony już z
> wnętrza `server` próbuje wejść do nieistniejącego `server\server` i nic
> sensownego się nie dzieje.

**B) Z VS Code, przyciskiem F5** (debugger — pozwala też np. zatrzymywać
program w wybranym miejscu kodu, gdy będziesz się uczyć): ikona „Run and
Debug” po lewej stronie (trójkącik z pluskwą), z listy u góry wybierz
„**Serwer (symulacja)**”, kliknij zieloną strzałkę albo naciśnij F5.

**C) Ręcznie w terminalu:**

```powershell
cd server
$env:PROGRAMS_DIR = "../programs"
$env:AXES_CONFIG = "../config/axes.json"
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

W terminalu pojawi się linijka `Uvicorn running on http://0.0.0.0:8000` —
to znaczy, że serwer działa i czeka na połączenia. Otwórz w przeglądarce:

- http://localhost:8000/ — panel operatora
- http://localhost:8000/editor — edytor programów technologa
- http://localhost:8000/docs — automatyczna dokumentacja API (przydatna,
  gdy zaczniesz czytać kod endpointów w `server/app/main.py`)

Żeby zatrzymać serwer: kliknij w okno terminala i naciśnij `Ctrl+C`.

## Krok 7 — uruchom testy

Testy to sposób, żeby po każdej zmianie w kodzie szybko sprawdzić „czy nic
nie zepsułem”, bez ręcznego klikania całej aplikacji.

**Z VS Code:** ikona probówki po lewej stronie (**Testing**) → **Run All
Tests** (▶ przy nazwie na górze listy). Po chwili obok każdego testu pojawi
się zielony ✓ (przeszedł) albo czerwony ✗ (nie przeszedł, kliknij żeby
zobaczyć dlaczego).

**Albo zadanie:** `Ctrl+Shift+P` → **Tasks: Run Task** → „**Testy: pytest**”.

**Ręcznie w terminalu:**

```powershell
cd server
.venv\Scripts\pytest -q
```

Wynik w stylu `59 passed in 0.7s` oznacza, że wszystkie testy przeszły.
Czerwony napis `FAILED` przy jakimś teście pokazuje, w którym pliku i linii
coś nie zgadza się z oczekiwaniem — to jest punkt startowy do szukania
przyczyny, nie powód do paniki.

## Mapa projektu — co gdzie jest

```
server/app/main.py     — endpointy API: co się dzieje pod adresami takimi
                          jak /api/mes/select-order, /api/machine/start
server/app/machine.py  — logika maszyny: w trybie symulacji "udaje" ruchy
server/app/program.py  — czyta i sprawdza pliki .prg (programy cięcia)
server/app/axes.py     — konfiguracja osi (długości, limity)
server/app/static/     — strony WWW panelu (HTML/JS/CSS), to widzisz w
                          przeglądarce pod localhost:8000
server/tests/          — testy pytest, po jednym pliku na obszar
                          (test_api.py, test_axes.py, test_program.py)
```

Dobry pierwszy krok do nauki: uruchom serwer (krok 6), otwórz
`server/app/main.py` w VS Code i porównaj adresy w kodzie (`@app.get(...)`,
`@app.post(...)`) z tym, co widać pod http://localhost:8000/docs.

## Typowe problemy

- **`python : nie można rozpoznać nazwy...`** — Python nie jest w PATH.
  Odinstaluj i zainstaluj ponownie, zaznaczając „Add python.exe to PATH”
  (Krok 1).
- **PowerShell nie chce uruchomić `.venv\Scripts\Activate.ps1`** (błąd o
  „execution policy”) — nie jest to potrzebne w tej instrukcji: wszystkie
  komendy wołają program bezpośrednio z `.venv\Scripts\...`, bez aktywacji
  środowiska.
- **Terminal nie widzi `.venv`** — upewnij się, że jesteś w folderze
  `server` (`cd server`), a nie w głównym folderze projektu.
- **`start.bat` nic nie robi / okno mignie i znika** — najczęściej dlatego,
  że został uruchomiony z wnętrza folderu `server` zamiast z folderu
  głównego projektu. Sprawdź: otwórz terminal, wpisz `.\start.bat` i patrz,
  co się wypisze (dwuklik zamyka okno po błędzie, zanim zdążysz przeczytać —
  terminal zostawia komunikat widoczny).
