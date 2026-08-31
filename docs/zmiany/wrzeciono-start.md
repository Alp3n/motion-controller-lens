# Wrzeciono: kiedy się załącza i kiedy gaśnie

Temat D planu rozwoju, część wykonalna bez dodatkowego sprzętu: przełącznik
„wrzeciono rusza razem z maszyną" na ekranie Start/Stop i dwie opcje granic
programu technologa w konfiguracji maszyny (`NOTATKI_FUNKCJONALNE.md` §4,
punkty 1 i 2). Pozostałe punkty §4 — sterowanie prędkością i konfiguracja
rozpędzania — wymagają zewnętrznego regulatora PWM (temat J) i zostają otwarte.

Ustawienia (`config/spindle.json`, `SPINDLE_CONFIG`):

| Ustawienie | Domyślnie | Znaczenie |
| --- | --- | --- |
| `start_with_machine` | nie | wrzeciono rusza po naciśnięciu START (program albo cykl) i chodzi przez całą pracę |
| `start_with_program` | tak | wrzeciono załącza się na starcie programu technologa |
| `stop_after_program` | nie | wrzeciono gaśnie po zakończeniu programu technologa |
| `default_rpm` | 12000 | obroty wpisywane do komendy `SPINDLE` poza programem — **informacyjne** |

Wartości domyślne odtwarzają dokładnie zachowanie sprzed tej zmiany.

## Pliki

- `server/app/spindle.py` — nowy: `SpindleConfig`, wczytanie/zapis, zapis
  częściowy (`merged`), ostrzeżenia
- `server/app/config.py` — `SPINDLE_FILE`; `SPINDLE_OUTPUT` czytane tylko po to,
  żeby panel mógł ostrzec, że mostek nie ma podpiętego wyjścia
- `server/app/machine.py` — `apply_spindle_config`; załączenie przy starcie
  maszyny i na granicach programu w symulatorze i w `SC4HubMachine`
- `server/app/main.py` — `GET/PUT /api/spindle` (zapis częściowy)
- `server/app/static/index.html`, `app.js` — przełącznik przy START/STOP
- `server/app/static/cycle.html`, `cycle.js` — sekcja „Wrzeciono" (dwie opcje
  granic programu + obroty domyślne)
- `server/app/static/style.css` — `.check-row`
- `server/tests/test_spindle.py` — 22 testy; `server/tests/conftest.py` — plik
  konfiguracji wrzeciona w katalogu tymczasowym

## Uwagi

- **Do potwierdzenia z Tobą: co znaczą „dwie opcje" z notatki §4.** Notatka mówi
  tylko „dwie opcje do zdefiniowania w konfiguracji maszyny". Przyjąłem parę
  *załącz na starcie programu* + *wyłącz po zakończeniu programu*. Jeśli chodziło
  o coś innego (np. wybór między „wrzeciono z maszyny" a „wrzeciono z programu"),
  zmiana jest tania — to dwa pola w `SpindleConfig`.
- **Obroty nie docierają do sprzętu.** SC4-Hub ma wyłącznie wyjścia dwustanowe
  `BRAKE_0`/`BRAKE_1`; prędkość ustawia zewnętrzny regulator PWM (temat J).
  `default_rpm` trafia do komendy `SPINDLE` mostka, ale realnie nic nie zmienia.
  W trybie sprzętowym API zwraca o tym ostrzeżenie.
- **Dziś na maszynie nie przełącza się nic.** `bridge/machine.env` ma
  `SPINDLE_OUTPUT=none` — komendy wrzeciona nie ruszają żadnego wyjścia, dopóki
  nie zostanie ustawione `brake0` albo `brake1`. Panel ostrzega o tym w trybie
  sprzętowym; serwer zna tę wartość tylko, jeśli została wyeksportowana do jego
  procesu, w przeciwnym razie mówi wprost, że nie wie.
- **Bezpieczeństwo, bez zmiękczania.** `start_with_machine` znaczy, że narzędzie
  zaczyna się obracać natychmiast po naciśnięciu START, przed pierwszym ruchem.
  Panel wypisuje ostrzeżenie przy włączaniu. Niezależnie od tych ustawień sygnał
  `BRAKE_x` do regulatora **musi iść szeregowo przez obwód osłon** — producent
  ostrzega, że system może przypadkowo załączyć wyjście (ryzyko A
  w `mozliwosci-clearpath-sc.md`, temat J).
- **Czego nie da się skonfigurować:** wyłączenia wrzeciona na zakończenie pracy
  maszyny. Koniec cyklu, błąd i STOP gaszą je zawsze — to `finally` w warstwie
  maszyny, świadomie poza konfiguracją.
- **Przy okazji naprawione:** operacja `PAUZA` w symulatorze gasiła wrzeciono
  i już go nie zapalała do końca programu, choć `SC4HubMachine` po wznowieniu
  wysyłał ponowne `SPINDLE 1`. Teraz obie warstwy przywracają stan sprzed pauzy.
- **Zmiana wewnętrzna:** w symulatorze wrzeciono zapala się raz, na starcie
  programu, a nie przy każdej operacji skrawającej — inaczej ustawienie „program
  nie załącza wrzeciona" nie miałoby jak zadziałać. Kolejność komend do mostka
  poza wrzecionem pozostaje bez zmian.
