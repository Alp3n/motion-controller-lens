# Ekran zużycia osi (temat M, krok 3)

Ekran `/zuzycie` — podgląd danych zebranych przez `zuzycie.record_run()`
(temat M, krok 1-2): podsumowanie bieżącej doby per oś i wykresy trendu
długoterminowego. **Sam podgląd, bez alarmów i powiadomień** — to
świadomie osobne, jeszcze niezrobione kroki (4-5).

## Pliki

- `server/app/zuzycie.py` — wydzielona `_aggregate_entries()` (wspólna
  logika sumowania/uśredniania, używana teraz zarówno przez rollup do
  trendu, jak i przez nową `summarize_today()`); `summarize_today()` liczy
  podsumowanie bieżącej doby na żywo, bez zapisu/kasowania pliku.
- `server/app/main.py` — `GET /api/zuzycie` (`require_technolog`): zwraca
  `{"dzisiaj": {...}, "trend": [...]}`. Strona `/zuzycie`
  (`require_technolog`, spójne z rolą podglądu z `analiza-zuzycia-osi.md`).
- `server/app/static/zuzycie.html`, `zuzycie.js` — tabela „dzisiaj" +
  wykresy słupkowe trendu, jeden per oś (małe wielokrotności — osie mają
  różne skale dystansu, wspólna oś Y by je spłaszczyła). Rysowanie ręczne
  na `<canvas>`, bez biblioteki wykresów — ten sam wzorzec co `/sila`.
  Linki nawigacyjne dopisane w `index.html` i `sila.html`.
- `server/tests/test_zuzycie.py` — 3 nowe testy `summarize_today()`.

## Uwagi

- **Dziś obejmuje wyłącznie X/Y/Z** — osie FEETECH (`docisk`, `podajnik`)
  jeszcze nie są wliczane do zużycia; `zuzycie.summarize_recording()` zna
  tylko `AXES = ("x", "y", "z")`. Rozszerzenie o osie FEETECH to osobna
  praca (przecięcie tematów L i M), niezrobiona teraz — ekran jawnie o tym
  informuje operatora.
- Endpoint API nie ma osobnego testu na poziomie HTTP (wzorem innych
  cienkich endpointów w `main.py`, np. `_read_feetech_status`) —
  zweryfikowany ręcznie (izolowany `ZUZYCIE_DIR`, `TestClient`), logika
  leżąca pod spodem (`summarize_today`, `read_trend`) jest w pełni
  pokryta testami jednostkowymi.
- Zweryfikowane na produkcji po restarcie usługi.
