# Ekran profili parametrów ruchu (siła trzypoziomowa)

Nowy ekran `/profiles` pokazuje i pozwala edytować trzy profile parametrów
ruchu — globalny (20%), cykl maszyny (15%), program technologa (10%) —
oraz przełączać, który jest aktywny. Sam mechanizm (`ParameterProfile`,
`/api/profiles`, snapshot/restore wokół kroku cyklu) powstał już w etapie 2
tematu B (`docs/zmiany/profile-parametrow-etap2.md`); brakowało tylko
interfejsu — do tej pory profile dało się zmienić wyłącznie surowym
wywołaniem API.

## Pliki

- `server/app/static/profiles.html`, `profiles.js` — nowy ekran: karta na
  profil (oś × prędkość maksymalna / przyspieszenie / hamowanie / limit
  momentu), przycisk „Aktywuj” per profil, wspólny zapis wszystkich profili
  naraz, walidacja jak w `/axes` i `/cycle`.
- `server/app/main.py` — trasa `GET /profiles` (istniejące API `/api/profiles`
  nie było ruszane).
- `server/app/static/style.css` — `#profiles-grid` (karty jedna pod drugą —
  w siatce 3-kolumnowej tabela z pięcioma kolumnami się nie mieściła),
  `.profile-table`.
- `server/app/static/index.html`, `axes.html`, `cycle.html`, `editor.html`
  — link „Profile parametrów” w nagłówku.
- `server/tests/test_profiles.py` — test, że strona się serwuje.

## Uwagi

- **Limit momentu działa dziś wyłącznie w symulatorze** — bez zmian względem
  etapu 2, ekran tylko to teraz jasno pokazuje. Protokół mostka nie ma
  komendy momentu; wysłanie jej wymaga C++ i fizycznego sprzętu (patrz
  `docs/plan-rozwoju.md`, temat C).
- Znaleziony i poprawiony podczas testowania w przeglądarce błąd CSS:
  odznaka „AKTYWNY” i przycisk „Aktywuj” były przełączane atrybutem
  `hidden`, ale reguła `.axis-extra-badge { display: inline-block }`
  / `.btn-row { display: flex }` ma tę samą swoistość co domyślne
  `[hidden] { display: none }` przeglądarki i — jako later w arkuszu —
  wygrywała, więc obie karty non-aktywne i tak pokazywały odznakę.
  Naprawione ustawianiem `style.display` wprost zamiast atrybutu `hidden`.
- Sprawdzone w przeglądarce (Playwright): edycja i zapis wartości, przełączenie
  aktywnego profilu (dokładnie jedna karta ma odznakę na raz), trwałość po
  przeładowaniu, blokada zapisu przy wartości 0. Prawdziwy
  `config/profiles.json` nietknięty (izolowane ścieżki testowe).
