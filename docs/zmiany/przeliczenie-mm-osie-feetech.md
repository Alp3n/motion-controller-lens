# Przeliczenie pozycji osi FEETECH na mm (etap 2 kalibracji)

Zamówienie 2026-09-11: „osie dodatkowe dodaj jeszcze rzeczywistą pozycję po
przeliczeniu skoku śruby... musi być wartość tak jak teraz (pozycja
serwa) i pozycja na liniowym" — po zamontowaniu serw FEETECH do mechanizmu
(`mm_per_rev` w `config/axes.json` zmienione na zmierzony fizycznie skok
śruby: docisk 1.0 mm/obr, podajnik 8.0 mm/obr) panel operatora ma pokazać
OBOK surowej pozycji rejestru także przeliczoną pozycję w mm.

To temat L, **etap 2** z `docs/architektura-wielu-drajwerow-osi.md`
(„kalibracja mm, po zamontowaniu serw") — wcześniej świadomie odłożony,
bo serwa nie były jeszcze zamontowane.

## Pliki

- `server/app/feetech_driver.py` — `COUNTS_PER_REV = 4096` (karta
  katalogowa SM45BL: „Clockwise(0→4096)") i `position_to_mm(position,
  mm_per_rev)` — czyste przeliczenie skali, bez zależności od sprzętu,
  łatwe do testowania.
- `server/app/main.py` — `_read_feetech_status()` przyjmuje teraz też
  konfigurację osi (`machine.axes`) i dolicza `position_mm` do wpisu każdej
  skonfigurowanej osi (pomijane, gdy oś nieznana albo odczyt się nie udał).
  `_feetech_poll_loop()` przekazuje `machine.axes` do wywołania.
- `server/tests/test_feetech_driver.py` — 4 testy `position_to_mm()`
  (pełny obrót, ułamek obrotu, zero, zachowanie znaku rejestru).
- `server/tests/test_feetech_status.py` — 3 testy `_read_feetech_status()`
  z podstawionym `FeetekDriver` (doliczanie `position_mm`, pominięcie bez
  konfiguracji osi, pominięcie przy błędzie serwa).
- `server/app/static/app.js`, `index.html` — panel „Osie dodatkowe
  (FEETECH)" pokazuje `X mm (rej. N) obc. L`; opis pod panelem
  zaktualizowany (usunięte nieaktualne „bezpieczne przed montażem" — serwa
  są już zamontowane).

## Uwagi

- **To WYŁĄCZNIE przeliczenie skali (obrót → mm), nie pozycja bazowana.**
  Rejestr serwa ma własne, fabryczne zero (absolutne z magnesu enkodera),
  niepowiązane z zerem obszaru roboczego maszyny (`soft_min`/`soft_max`).
  Bazowanie osi FEETECH to osobny, wciąż niezrobiony krok — **etap 3**.
- **Znak nie jest ujednolicony między osiami.** `position_to_mm()` celowo
  NIE odwraca znaku względem `DIRECTION_SIGN_CW` (który mówi tylko, czy
  CW zwiększa czy zmniejsza rejestr dla danego ID, nie który kierunek jest
  „dodatni" dla osi) — decyzja o kierunku dodatnim per oś to też etap 3.
- `COUNTS_PER_REV = 4096` przyjęte wprost z karty katalogowej — **nie
  zweryfikowane empirycznie wielokrotnym obrotem o dokładnie 360°**
  (weryfikacja fizyczna kierunku CW/CCW w `zmiany/protokol-feetech.md`
  sprawdzała TYLKO znak, nie liczbę jednostek na pełny obrót).
