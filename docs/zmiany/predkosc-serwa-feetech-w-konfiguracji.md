# Prędkość/przyspieszenie serwa FEETECH w konfiguracji osi

Zamówienie 2026-09-11: „sprawdź czy możemy definiować prędkość serwa w
konfiguracji osi maszyny" + „daj podpowiedź ustawianych zakresów". Do tej
pory `move_relative_cw()` (JOG dla `docisk`/`podajnik`) używał na sztywno
zaszytych `speed=100, acc=20` — pole `vel_jog` w `AxisConfig` istniało, ale
nie miało żadnego wpływu na te dwie osie (używane tylko przez oś X/Y/Z).

## Ustalone zakresy (źródło: `zbyszek/Tabela pamięci protokół serw
SM45BL_001.xlsx`, wiersze adresów 41/44)

- **Przyspieszenie** — rejestr 0-1000, 1 jednostka = 100 kroków/s²
  (≈8,79°/s², zgadza się z wcześniej znaną wartością w
  `feetech_driver.py`). Potwierdzone wprost w tabeli źródłowej (kolumny
  „min/max wartość").
- **Prędkość** — rejestr, 1 jednostka ≈ 0,732 obr/min (potwierdzone
  przykładem z SDK producenta, `zbyszek/FTServo_Python-main.zip`,
  `sms_sts/write.py`: `V=60 → 43,92 RPM`). **Górna granica NIE jest
  jednoznacznie potwierdzona** w wyciągniętych źródłach (arkusz ma
  niespójne scalone komórki w tym miejscu, a PDF karty katalogowej nie dało
  się odczytać w tej sesji — brak `poppler-utils`/biblioteki PDF).
  Przyjęto **konserwatywny sufit 1000** (ten sam co przyspieszenie, ta sama
  rodzina rejestru profilu trapezowego) — do zweryfikowania przy okazji
  pełnego dostępu do karty katalogowej, nie traktować jako potwierdzony
  limit sprzętowy.

## Pliki

- `server/app/axes.py` — `AxisConfig.feetech_speed` (domyślnie 100) i
  `feetech_acc` (domyślnie 20), zgodne z dawnymi stałymi; walidacja zakresu;
  dopisane **od razu** do `OPTIONAL_FIELDS` (prewencyjnie — trzeci
  potencjalny przypadek tego samego wzorca błędu co `driver`/`feetech_id`,
  patrz [[driver-feetech-znikal-po-zapisie-osi]]).
- `server/app/main.py` — `_feetech_jog()`/`machine_jog_feetech()` czytają
  `feetech_speed`/`feetech_acc` z konfiguracji osi zamiast stałych.
- `server/app/static/axes.html`, `axes.js` — dwie nowe kolumny w tabeli
  osi, widoczne z inputem TYLKO dla osi ze sterownikiem `feetech`
  (rozpoznane po `driver` z odpowiedzi `GET /api/axes`); dla pozostałych
  osi kreska, bez inputu — `readAxis()` nie wysyła wtedy tych pól wcale.
  Podpowiedź zakresu w `title` nagłówka kolumny i każdego inputu. Przy
  okazji: poprawiony nieaktualny opis „dodatkowa oś nigdzie fizycznie nie
  pojedzie" (fałszywy dla `docisk`/`podajnik`, które realnie jeżdżą przez
  FEETECH) — teraz warunkowy względem sterownika osi.
- `server/tests/test_axes.py` — 6 testów (domyślne wartości, walidacja
  zakresu, round-trip, kompatybilność plików sprzed tego pola, regresja
  `with_current_values`).
- `server/tests/test_feetech_jog.py` — zaktualizowane fake'i (`_feetech_jog`
  ma teraz 4 argumenty) + nowy test potwierdzający, że wartości z
  konfiguracji osi faktycznie trafiają do wywołania.

## Uwagi

- Ekran `/axes` nadal **nie ma przełącznika sterownika** (teknic/feetech)
  ani edycji `feetech_id` — to świadomie zostaje poza zakresem tej zmiany,
  ustawia się dziś tylko edycją pliku `config/axes.json`.
- Nowo dodana oś z ekranu `/axes` („+ Dodaj oś") dalej domyślnie dostaje
  `driver: teknic` (bez pól prędkości FEETECH) — zgodne z dotychczasowym
  zachowaniem, nic fizycznie nie pojedzie, dopóki ktoś ręcznie nie ustawi
  `driver: feetech` w pliku.
