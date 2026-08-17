# Uruchamianie z pulpitu i PDF-y dokumentacji

Dwa narzędzia dla obsługi maszyny: skrót na pulpicie uruchamiający całe
środowisko jednym kliknięciem oraz generator PDF-ów z dokumentacji.

## Pliki

- `tools/uruchom-maszyne.sh` — mostek (jeśli zbudowany i widzi sprzęt) →
  serwer → panel w przeglądarce; sprzątanie przy zamknięciu okna.
- `tools/zainstaluj-skrot.sh` — zakłada `maszyna-ocinanie.desktop` na pulpicie
  ze ścieżką do bieżącego katalogu repozytorium.
- `tools/docs-pdf.py` — `docs/**.md` → `docs/pdf/*.pdf` (własny konwerter
  Markdown → HTML + LibreOffice w trybie wsadowym).
- `README.md` — opis obu narzędzi.

## Uwagi

- **Tryb wybierany automatycznie**: bez działającego mostka skrypt wchodzi
  w symulację i wypisuje to wielkimi literami. Wymuszenie:
  `uruchom-maszyne.sh maszyna` (błąd zamiast cichej symulacji) albo `sim`.
- Zajęty port 8000 albo 8500 zatrzymuje start z komunikatem — dwie instancje
  serwera na jednej maszynie to gwarantowany konflikt o sprzęt.
  Porty można podmienić zmiennymi `SERVER_PORT` / `BRIDGE_PORT`.
- Mostek dostaje `SIGTERM` przy zamknięciu okna; bez tego zostawał
  z otwartym portem szeregowym i kolejny start kończył się błędem.
- Konwerter Markdown jest **wąski z założenia** — obsługuje to, czego używa
  ta dokumentacja (nagłówki, listy, tabele, bloki kodu, cytaty, odnośniki).
  Nie jest pełną implementacją CommonMark i nie ma tu być.
- PDF-y są plikami wynikowymi — po zmianie dokumentacji trzeba je przegenerować.
