# Osie dodatkowe — etap 1 (fundament)

Konfiguracja osi (`/axes`, `axes.json`) przestaje być na sztywno ograniczona
do X/Y/Z — może zawierać dowolne osie dodatkowe (podajnik, docisk), zachowane
przy zapisie i odczycie. To pierwszy z czterech etapów tematu B z
[`docs/plan-rozwoju.md`](../plan-rozwoju.md); pełny kontekst i uzasadnienie
w [`docs/model-cyklu-maszyny.md`](../model-cyklu-maszyny.md).

## Pliki

- `server/app/axes.py` — `AXIS_NAMES` → `REQUIRED_AXES` (X/Y/Z, wymagane
  zawsze); `parse_axes`/`save`/`to_dict` iterują po kluczach przekazanego
  słownika zamiast po sztywnej krotce, więc dodatkowe osie przechodzą przez
  cały łańcuch; nowa walidacja nazwy osi (małe litery/cyfry/podkreślenie).
- `server/app/machine.py` — `SC4HubMachine._push_axis_config` dalej
  wysyła `AXCFG` tylko dla `REQUIRED_AXES` — protokół mostka nie zna innych
  liter osi.
- `server/tests/test_axes.py` — 4 nowe testy: zachowanie osi dodatkowej przy
  parsowaniu/zapisie/odczycie, odrzucenie nieprawidłowej nazwy osi,
  `work_area()` ignorujące osie dodatkowe.

## Uwagi

- `work_area()` świadomie zostaje ograniczone do X/Y/Z — to zakres cięcia
  dla plików `.prg`, nie dotyczy osi dodatkowych.
- Ekran `/axes` (JS) nadal renderuje tylko X/Y/Z — dodanie osi przez UI to
  osobna praca (temat C/G). Dziś nową oś da się dodać tylko przez API.
- Rozszerzenie protokołu mostka o inne litery osi (żeby podajnik/docisk
  faktycznie ruszały fizycznie) to osobne zadanie, nie część tego etapu.
