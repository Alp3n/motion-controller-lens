# Prędkości JOG i bazowania per oś

Ekran `/axes` pozwala teraz ustawić dla każdej osi (X/Y/Z i dodatkowych)
osobną prędkość ruchu ręcznego (JOG) i prędkość dojazdu przy bazowaniu.
Prędkość maksymalna i robocza już istniały wcześniej (profile parametrów —
`vel_max`, oraz `POSUW_ROBOCZY`/`POSUW_DOJAZDU` programu technologa) i nie
były ruszane.

## Pliki

- `server/app/axes.py` — `AxisConfig` ma nowe pola `vel_jog`, `vel_home`
  (domyślnie 500/1000 mm/min — te same liczby, które wcześniej były wpisane
  na sztywno). Pola opcjonalne przy wczytywaniu pliku — stary
  `config/axes.json` bez tych kluczy nie blokuje startu serwera.
- `server/app/machine.py` — `Machine.axis_jog_feed()` i `Machine._home_feed()`
  czytają te wartości z konfiguracji osi; `SimulatedMachine._do_home()` używa
  `_home_feed()` zamiast stałych `2000`/`1000`.
- `server/app/main.py` — `JogRequest.feed` jest teraz opcjonalny; gdy panel
  nie poda posuwu, serwer sam bierze `vel_jog` skonfigurowanej osi.
- `server/app/static/axes.js`, `axes.html`, `style.css` — dwie nowe kolumny
  w tabeli osi, walidacja (>0), wartości startowe nowo dodanej osi.
- `server/tests/test_axes.py` — wsteczna zgodność pliku bez nowych pól,
  walidacja, oraz dwa testy czasowe potwierdzające, że `vel_jog`/`vel_home`
  realnie ograniczają ruch (JOG i bazowanie), a nie są samą liczbą w pliku.

## Uwagi

- **Prędkość JOG działa też na prawdziwym sprzęcie** — trafia do mostka
  komendą `JOG` tak samo jak wcześniej ręcznie wpisana wartość, tylko teraz
  źródłem jest konfiguracja osi zamiast stałej `500` w kodzie.
- **Prędkość bazowania działa dziś tylko w symulatorze.** Na prawdziwej
  maszynie bazowaniem steruje serwo — sposób najazdu i jego prędkość
  konfiguruje się w ClearView (mostek wysyła samo `HOME`, bez parametru
  posuwu). Ekran o tym jasno informuje.
- Prędkość maksymalna (`vel_max` w profilach) i robocza (`POSUW_ROBOCZY`/
  `POSUW_DOJAZDU` w programie technologa) zostały świadomie pominięte —
  już istnieją i już są egzekwowane; ten krok dokładał tylko brakujące dwie
  kategorie z punktu planu.

### Poprawka: zapis zerował pola przy nieodświeżonym serwerze

Zgłoszenie: po wpisaniu nowej prędkości JOG/bazowania i kliknięciu „Zapisz”
wszystkie pola na ekranie pustoszały, a komunikat mówił, że prędkość musi
być większa od zera. Przyczyna: przeglądarka miała już nowy `axes.js`
(wysyła `vel_jog`/`vel_home`), ale proces serwera nie został zrestartowany
po `git pull` i odpowiadał starym kodem bez tych pól. `writeAxis()` wpisywał
wtedy `undefined` do pola liczbowego — przeglądarka czyści taką wartość do
pustego napisu, co walidacja odczytuje jako zero.

Poprawka w `axes.js`: `writeAxis()` ma teraz awaryjny fallback
(`FALLBACK_VEL_JOG`/`FALLBACK_VEL_HOME` = 500/1000, te same liczby co
`DEFAULT_VEL_JOG`/`DEFAULT_VEL_HOME` w `app/axes.py`) na wypadek odpowiedzi
serwera bez tych pól — dotyczy każdej niedopasowanej wersji frontend/backend,
nie tylko tego jednego przypadku. **To nie zastępuje właściwego rozwiązania:
po każdym `git pull` trzeba zrestartować proces serwera** (sam refresh
przeglądarki nie wystarczy — restartu wymaga kod Pythona, nie tylko JS).
