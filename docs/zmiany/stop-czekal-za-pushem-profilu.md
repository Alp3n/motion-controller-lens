# STOP czekał kilka sekund — blokowany przez push profilu/osi

Zgłoszone przy maszynie 2026-09-02: przy dłuższym ruchu przycisk STOP na
cyklu (półautomatycznym i automatycznym) zatrzymywał osie dopiero po kilku
sekundach zamiast natychmiast — nieprzewidywalnie, zależnie od długości
bieżącego kroku. Ocenione jako niedopuszczalne (ścieżka bezpieczeństwa).

## Przyczyna

Mostek w trakcie ruchu nasłuchuje gniazda co ~20 ms (`pollDuringMove` w
`bridge/sc4hub_bridge.cpp`) i reaguje na STOP niemal natychmiast (`NodeStop
STOP_TYPE_ABRUPT` — bezpieczne, maksymalne wyhamowanie, nie teleportacja do
zera, ale rząd wielkości: dziesiątki milisekund, nie sekundy). Problem był
po stronie Pythona:

1. `stop()` anulował `_run_task` (`asyncio.CancelledError` przerywa bieżącą
   komendę ruchu w `SC4HubMachine._exchange()`).
2. To anulowanie przechodzi przez `finally:` w `_execute_cycle_step`, który
   przywraca poprzedni profil (`_set_profile(previous_profile)`) — a to
   ustawia `_profile_pending = True`.
3. `stop()` wysyłał STOP przez zwykłe `_command()`, które **najpierw**
   sprawdza `_profile_pending`/`_axes_pending` i próbuje wypchnąć
   `TRQLIMIT`/`AXCFG`, zanim wyśle właściwą komendę.
4. Mostek w trakcie ruchu **ignoruje wszystko poza STOP/STATUS**
   (`pollDuringMove`, komentarz „pozostałe komendy w trakcie ruchu są
   ignorowane") — więc TRQLIMIT wysłany w tym momencie nigdy nie dostawał
   odpowiedzi. `_exchange()` wisiał na `readline()` **aż ruch skończył się
   sam**, i dopiero wtedy STOP w ogóle trafiał na gniazdo.

Efekt: STOP działał (mostek go w końcu dostawał), ale zawsze spóźniony o
czas pozostały do naturalnego końca aktualnego ruchu — im dłuższy krok, tym
dłuższe opóźnienie. Dokładnie to zgłosił operator.

## Naprawa

`SC4HubMachine.stop()` ma teraz własną, minimalną ścieżkę do gniazda —
omija `_command()` i jego push logikę całkowicie, woła `_exchange("STOP")`
wprost, pod tym samym zamkiem (dla bezpieczeństwa dostępu do gniazda), ale
bez TRQLIMIT/AXCFG. **Świadomie bez reconnectu**, mimo że `_command()` go
robi: STOP przerywa ruch na już otwartym łączu (tylko takie łącze mogło ten
ruch zlecić), a próba reconnectu dodałaby do 3 s zwłoki w rzadkim
przypadku zerwanego połączenia — czyli dokładnie to, co ta poprawka ma
eliminować. Gdy łącza nie ma, `_exchange()` i tak zwraca czytelny błąd
„brak połączenia z mostkiem SC4-Hub", tylko szybciej.

## Pliki

- `server/app/machine.py` — `SC4HubMachine.stop()` przepisany, patrz
  docstring w kodzie.
- `server/tests/test_sc4hub.py` — 3 nowe testy: STOP pomija push profilu
  mimo `_profile_pending=True`, pomija push osi mimo `_axes_pending=True`,
  i że `stop()` faktycznie anuluje `_run_task`.
- `server/tests/test_spindle.py` — fixture `_bridge()` fejkował tylko
  `_command`, nie `_exchange`/`_writer`. Skoro `stop()` teraz woła
  `_exchange()` bezpośrednio, test `test_mostek_zapala_wrzeciono...`
  (który na końcu woła `m.stop()`) **naprawdę otworzył gniazdo do
  `127.0.0.1:8500`** — czyli do prawdziwego, działającego na tej maszynie
  mostka sprzętowego — i wysłał na nie prawdziwy STOP. Nieszkodliwe przy
  bezczynnej maszynie, ale to przypadkowe omijanie izolacji testów od
  sprzętu. Naprawione: `_bridge()` fejkuje teraz też `_exchange` i ustawia
  `_writer`/`_reader`, tak jak `_connected_machine()` w `test_sc4hub.py`.

## Uwagi

- **Ta poprawka sama w sobie okazała się niewystarczająca** — operator
  zgłosił 2026-09-05, że STOP na cyklu nadal czeka kilka sekund. Prawdziwą,
  pełną przyczynę (inna komenda, zakolejkowana PRZED STOP-em, utykająca za
  tym samym pushem) opisuje
  [`stop-czekal-za-statusem.md`](stop-czekal-za-statusem.md) — dopiero ta
  druga poprawka, potwierdzona fizycznie, naprawiła problem do końca. Ta
  poprawka (STOP omija własny push) zostaje w kodzie jako nadal potrzebny,
  ale niewystarczający sam z siebie, element rozwiązania.
- Znalezisko przy okazji tej naprawy (patrz wyżej, `test_spindle.py`) warto
  zapamiętać przy pisaniu kolejnych testów `SC4HubMachine`: fejkowanie
  wyłącznie `_command` nie izoluje od sieci, jeśli testowany kod (albo
  przyszła zmiana) zacznie wołać `_exchange` bezpośrednio.
