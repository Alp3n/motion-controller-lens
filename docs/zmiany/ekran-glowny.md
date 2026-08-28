# Ekran główny (temat G)

„Ekran główny" z planu to już istniejący panel operatora (`/`) — prosty,
z niezbędnymi przyciskami i komunikatami. Z tego punktu zostały do zrobienia
dwie rzeczy: poprawna nazwa maszyny i miejsce na logo WALKNER.

## Nazwa maszyny

Notatka `NOTATKI_FUNKCJONALNE.md` §7 mówiła o nazwie „Demontaż pinów
z optyki" — sprzeczne z resztą repo (README, CLAUDE.md, wszystkie ekrany),
które od dawna używają „ocinanie/odcinanie wlewków płytek optyki".
Potwierdzone z Tobą: to notatka była nieaktualna.

Przy okazji poprawiona literówka w **całym repozytorium**: „ocinanie" →
„odcinanie" (właściwe polskie słowo). Dotyczy tytułów stron, nagłówków,
README.md, CLAUDE.md, przykładowych plików `.prg`, generatora PDF-ów
i skryptu instalującego skrót na pulpicie.

## Logo

Plik logo nie istniał w repozytorium i nie da się go wgrać z obrazka
wklejonego na czacie w tej sesji (środowisko zdalne nie zapisuje załączników
czatu na dysk). Zamiast czekać, przygotowane jest miejsce, które samo
zacznie działać, gdy plik trafi do repo:

- `server/app/static/index.html` — `<img id="logo" src="/static/img/logo.png"
  onerror="this.remove()">` w nagłówku, przed nazwą maszyny.
- `server/app/static/style.css` — `#logo { height: 32px }`.
- `server/app/static/img/README.md` — instrukcja, gdzie wrzucić plik.

**Żeby dodać logo:** wrzuć `logo.png` (albo `.svg` — wtedy zmień
rozszerzenie w `src`) do `server/app/static/img/`, zrób `git push` — nagłówek
pokaże je automatycznie, bez zmian w kodzie. Dopóki pliku nie ma, `onerror`
usuwa `<img>`, więc nagłówek wygląda normalnie (bez połamanej ikonki) —
sprawdzone w przeglądarce oboma stanami (z plikiem i bez).

## Pliki

- `server/app/static/index.html`, `style.css` — logo w nagłówku (wyżej).
- Poprawka „ocinanie" → „odcinanie": `server/app/main.py`,
  `server/app/static/{index,axes,editor,profiles}.html`, `README.md`,
  `CLAUDE.md`, `tools/docs-pdf.py`, `tools/zainstaluj-skrot.sh` (też nazwa
  generowanego pliku skrótu: `maszyna-odcinanie.desktop`),
  `programs/583912004711.prg`, `programs/583912004844.prg`, oraz kilka
  plików w `docs/`.
