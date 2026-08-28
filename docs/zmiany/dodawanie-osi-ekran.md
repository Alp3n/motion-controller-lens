# Dodawanie osi dodatkowych z ekranu `/axes`

Ekran konfiguracji osi pozwala teraz dopisać oś ponad wymagane X/Y/Z (np.
podajnik, docisk) — z jasnym oznaczeniem, że to na razie **wyłącznie zapis
w pliku konfiguracji**, nie sterowanie. Backend to już umiał (etap 1 tematu B,
`docs/zmiany/osie-dodatkowe-etap1.md`); tu dochodzi tylko interfejs.

## Pliki

- `server/app/static/axes.js` — `AXES` (sztywna krotka) zastąpione przez
  `REQUIRED_AXES` (X/Y/Z) + `extraAxes` (dynamiczne); `allAxes()` jako
  wspólne źródło listy osi dla walidacji, pasków zakresu i zapisu.
  Nowe funkcje: `addAxisRow`/`removeAxis`/`addNewAxis`. `applyAxes`
  przebudowuje całą tabelę z danych potwierdzonych przez serwer — także po
  zapisie — więc „Przywróć zapisane” poprawnie odrzuca niezapisane lokalne
  dodania/usunięcia.
- `server/app/static/axes.html` — sekcja „Dodatkowe osie” z polem nazwy
  i przyciskiem dodania; kolumna akcji w tabeli; zaktualizowany nagłówek
  i opis.
- `server/app/static/style.css` — odznaka `.axis-extra-badge` („tylko
  konfiguracja”, kolor `--warn`) i styl przycisku usuwania wiersza.

## Uwagi

- **Nazwa osi jest walidowana po stronie przeglądarki tym samym wzorcem co
  serwer** (`^[a-z][a-z0-9_]*$`, `AxisConfigError` w `app/axes.py`) —
  wpisana wielkimi literami nazwa jest normalizowana do małych przed
  sprawdzeniem, duplikat i zły format są odrzucane bez dodania wiersza.
- Dodanie i usunięcie osi jest **lokalne, dopóki admin nie kliknie „Zapisz
  konfigurację”** — ten sam wzorzec co reszta ekranu (nic nie trafia do
  pliku bez świadomego zapisu).
- Odznaka „tylko konfiguracja” pojawia się przy każdej osi spoza X/Y/Z,
  z podpowiedzią (`title`) tłumaczącą dlaczego: mostek do sterownika zna
  dziś komendy ruchu wyłącznie dla X/Y/Z (`AXCFG X|Y|Z`,
  `docs/ARCHITEKTURA.md`), więc dodana oś zapisuje parametry, ale nic
  fizycznie nie pojedzie — do czasu rozszerzenia protokołu (temat C).
- Sprawdzone w przeglądarce (Playwright/Chromium): dodanie osi z odznaką,
  odrzucenie duplikatu i złej nazwy, zapis, trwałość po przeładowaniu,
  usunięcie i ponowny zapis. Bez nowych błędów JS (jedyny to zastany,
  niezwiązany 404 na `/favicon.ico`).
