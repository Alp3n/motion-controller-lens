# Tryby pracy (temat F)

Trzy tryby z planu: **półautomatyczny** (jeden cykl) już istniał od etapu 3/4
tematu B — ekran `/cycle` nazywa go teraz wprost. Nowe w tym kroku:
**automatyczny** (cykl w pętli, bez zatrzymania) i **manualny** („martwy
człowiek" — ruch JOG tylko przy przytrzymanym przycisku).

## Pliki

- `server/app/machine.py` — `start_cycle(loop: bool = False)` i `_run_cycle`
  owinięte w `while True`; kończy pętlę STOP, błąd w kroku albo utrata
  sygnału zezwolenia (to ostatnie już obsługiwał `set_safety_enable()`, nic
  nowego nie trzeba było dopisywać). Nowe pole statusu `cycle_loop`.
- `server/app/main.py` — `/api/machine/cycle/start` przyjmuje opcjonalne
  `{"loop": true}` (domyślnie `false` — brak body działa jak dawniej).
- `server/app/static/cycle.html`, `cycle.js` — drugi przycisk startu
  („Automatyczny — pętla"), tryb widoczny w wierszu stanu.
- `server/app/static/app.js`, `index.html`, `style.css` — przyciski JOG
  reagują teraz na przytrzymanie (mousedown/touchstart), nie na kliknięcie:
  powtarzają krótkie przejazdy co najwyżej co 50 ms, dopóki przycisk jest
  wciśnięty; puszczenie (także poza przyciskiem, oraz utrata fokusu karty)
  przestaje je wysyłać. Wizualne podświetlenie podczas trzymania.
- `server/tests/test_cycle.py` — 4 nowe testy trybu automatycznego.

## Uwagi

- **Znaleziony i naprawiony błąd zawieszający cały serwer:** krok cyklu bez
  żadnego realnego ruchu (WYJSCIE, albo RUCH do pozycji, w której oś już
  jest) nie zawieszał się na niczym — bez punktu zawieszenia `while True`
  w trybie automatycznym nigdy nie oddawał sterowania do event loopa
  asyncio, więc **mroził cały serwer** (żadne żądanie HTTP ani WebSocket nie
  dostawały odpowiedzi), nie tylko cykl. Złapane przy pisaniu testu — proces
  testowy zawisł na 100% CPU. Naprawa: `await asyncio.sleep(0)` po każdym
  kroku w `_run_cycle`. Test `test_start_cycle_loop_yields_even_without_real_movement`
  odtwarza dokładnie ten przypadek pod twardym limitem czasu
  (`asyncio.wait_for`), żeby regresja kończyła się czytelnym failem, a nie
  zawieszeniem całego przebiegu testów.
- **Manualny JOG „martwy człowiek" to wygoda operatora, nie certyfikowana
  funkcja bezpieczeństwa** — tę rolę pełni sprzętowy E-stop i Global Stop na
  SC4-Hub. Mostek (i symulator) nie mają komendy „jedź, dopóki nie każę
  stanąć" — tylko ruch o zadany dystans — więc przytrzymanie jest
  realizowane powtarzaniem krótkich przejazdów. Bieżący przejazd (krok
  z listy, zwykle ułamek sekundy) kończy się po puszczeniu, zanim oś
  faktycznie stanie — przy większym kroku i dużej prędkości JOG to
  opóźnienie jest zauważalne; do precyzyjnej pracy warto ustawić mały krok.
- **Cykl (jeden przebieg i automatyczny) działa dziś wyłącznie
  w symulatorze** — `ClearCoreMachine` nie ma jeszcze implementacji
  `start_cycle`/wykonania kroków przez mostek. To nie jest regresja tego
  kroku — `/cycle` nie działał na sprzęcie już od etapu 4 tematu B, po
  prostu nikt wcześniej tego nie sprawdził i nie zapisał. Ekran `/cycle`
  teraz o tym informuje wprost. Domknięcie wymaga C++ i fizycznego sprzętu.
