# Ekran bazowania i przycisk „HOME wszystkich osi"

Temat C planu rozwoju: kolejność bazowania osi, tryb HardStop z limitem momentu
i offsetem, osobny ekran `/homing` oraz przycisk dojazdu do HOME na środku
klawiszy strzałek XY (wymóg z `NOTATKI_FUNKCJONALNE.md` §1).

## Pliki

- `server/app/axes.py` — `AxisConfig` dostaje `home_order`, `home_mode`,
  `home_torque`, `home_offset`; `home_groups()` (osie pogrupowane po kolejności),
  `merge_homing()`, `homing_warnings()`, `with_current_values()`
- `server/app/machine.py` — `Machine.home_groups()`; `SimulatedMachine._do_home()`
  bazuje grupami w zadanej kolejności zamiast sekwencji na sztywno
- `server/app/main.py` — `GET/PUT /api/homing`, trasa `/homing`; zapis `/api/axes`
  zachowuje pola bazowania
- `server/app/static/homing.html`, `homing.js` — nowy ekran: tabela, podgląd
  wynikowej kolejności, lista tego, czego ekran **nie** robi
- `server/app/static/index.html`, `app.js`, `style.css` — przycisk `⌂` na środku
  strzałek XY, ten sam handler co „Bazowanie"; link do `/homing` w nagłówkach
- `server/app/static/axes.html`, `axes.js` — kolumna „Bazowanie [mm/min]"
  przeniesiona na `/homing`
- `server/tests/test_homing.py` — 25 testów: kolejność, walidacja, ostrzeżenia,
  scalanie zapisu, sekwencja symulatora, API

## Uwagi

- **Parametry HardStop nie trafiają do serwa.** *Homing Torque Limit* i *Offset
  Move* ustawia się wyłącznie w ClearView (Windows) — w pliku konfiguracji są
  jako zapis tego, co ma być w serwie. Serwer ich nie wysyła i nie egzekwuje;
  ekran mówi to wprost, a API zwraca ostrzeżenie.
- **Na sprzęcie kolejność z ekranu nie działa.** Mostek dostaje jedną komendę
  `HOME`, a całą sekwencję wykonuje serwo wg własnej konfiguracji. Kolejność,
  prędkość i offset zmieniają zachowanie **tylko w symulatorze**. W trybie
  sprzętowym `/api/homing` dokłada o tym ostrzeżenie.
- **Domyślna kolejność odtwarza dotychczasowe zachowanie** (X i Y razem, potem Z)
  — pliki konfiguracji sprzed tej zmiany działają bez edycji. Odjazd Z w górę
  przed ruchem w XY zostaje bezwarunkowy, niezależnie od ustawionej kolejności.
- **Zmiana zachowania:** bazowanie z pustą kolejnością (wszystkie osie na 0) jest
  teraz odrzucane z komunikatem zamiast wykonywać pusty ruch.
- Oś dodatkowa (podajnik, docisk) z ustawioną kolejnością **nie pojedzie** —
  mostek nie ma dla niej komend ruchu. Ekran i API to sygnalizują.
- Ryzyko, którego ta zmiana nie usuwa: bazowanie do oporu nie zastępuje
  fizycznych krańcówek jako niezależnego zabezpieczenia przed wyjechaniem poza
  zakres przy utracie pozycji — patrz `NOTATKI_FUNKCJONALNE.md`, „Sugestie" §2.
