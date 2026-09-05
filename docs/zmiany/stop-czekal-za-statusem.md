# STOP na cyklu nadal czekał — winowajcą był push za STATUS/SPINDLE

Poprawka [`stop-czekal-za-pushem-profilu.md`](stop-czekal-za-pushem-profilu.md)
z 2026-09-02 (STOP omija `_command()` i jego push logikę) okazała się
**niewystarczająca** — operator zgłosił 2026-09-05, że STOP na cyklu
(pojedynczym i automatycznym) nadal czeka kilka sekund, a na ekranie
operatora (zwykłe uruchomienie programu) działa OK. Namierzone na
sprzęcie, z dodaną diagnostyką czasu w kodzie.

## Prawdziwa przyczyna

To NIE była już komenda STOP, która utykała za pushem — to była **INNA,
wcześniej zakolejkowana komenda**, czekająca na TEN SAM `self._lock`:

- odpytywanie `STATUS` z `_poll_loop()` (`main.py`, co 0.2 s) — jeśli
  akurat trwał długi ruch, to zapytanie stało w kolejce do zamka przez
  CAŁY czas trwania ruchu,
- albo sprzątanie `_run_cycle` (`SPINDLE 0` w `finally`, uruchamiane od
  razu po przerwaniu kroku przez tę samą, właśnie anulowaną, komendę).

Tylko krok cyklu (`_execute_cycle_step`) robi snapshot/restore profilu —
przywrócenie profilu po zakończeniu/przerwaniu kroku ustawia
`_profile_pending = True`. **To dlatego bug objawiał się wyłącznie na
cyklu, nigdy przy zwykłym uruchomieniu programu z ekranu operatora**
(tam profil nigdy się nie przełącza).

Sekwencja zdarzeń potwierdzona logiem:

1. MOVEXY w toku, `self._lock` trzymany przez cały czas ruchu.
2. Operator klika STOP → `_run_task.cancel()` przerywa Pythonową stronę
   MOVEXY (potwierdzone: „wykonanie 9.27s” dokładnie w chwili STOP) →
   zamek się zwalnia → `_execute_cycle_step` w `finally` przywraca
   profil → `_profile_pending = True`.
3. Zwolniony zamek dostaje **kolejny w kolejce FIFO**, NIE STOP — czyli
   zakolejkowany wcześniej STATUS (albo SPINDLE 0 ze sprzątania cyklu).
4. Ta komenda widzi `_profile_pending = True` i próbuje wypchnąć
   TRQLIMIT — ale mostek **wciąż fizycznie wykonuje oryginalny ruch**
   (bo STOP jeszcze nie dotarł na gniazdo!) i taką komendę po cichu
   ignoruje (`pollDuringMove`: „pozostałe komendy w trakcie ruchu są
   ignorowane”).
5. `_exchange()` tej komendy wisi na `readline()`, bo mostek nigdy nie
   odpowie na zignorowaną komendę — aż PRAWDZIWY ruch fizycznie się
   skończy sam. Dopiero wtedy mostek wraca do normalnej obsługi, zamek
   się zwalnia, i STOP wreszcie dostaje szansę.

Efekt: STOP w końcu działał (stąd „odpowiedź mostka 0.01s” w logu —
mostek już stał bezczynnie), ale zawsze spóźniony dokładnie o czas, jaki
zostawał do naturalnego końca przerwanego ruchu — bo to on, nie STOP,
naprawdę decydował, kiedy oś stanie.

## Naprawa

`AXCFG`/`TRQLIMIT` mają sens tylko przed komendą, która faktycznie rusza
osiami. `SC4HubMachine._command()` wypycha je teraz **tylko** przed
`MOVEZ`/`MOVEXY`/`JOG`/`HOME` — nigdy przed `STATUS`/`SPINDLE`/`OUTPUT`/
`RESET`/`STOP`. Żadna z tych „niewinnych” komend nie może już utknąć za
ignorowanym przez mostek pushem w trakcie cudzego, jeszcze
nieprzerwanego ruchu.

## Pliki

- `server/app/machine.py` — `SC4HubMachine._command()`: push tylko przed
  `_MOVE_COMMAND_PREFIXES`; dodana obszerna diagnostyka czasu (start/koniec
  każdej nie-STATUS-owej komendy, log w `_run_cycle`/`_execute_cycle_step`
  przy przerwaniu) — zostaje w kodzie na przyszłość, próg 0.3s więc milczy
  w normalnej pracy.
- `server/tests/test_sc4hub.py` — testy TRQLIMIT przepisane na komendę
  ruchu jako wyzwalacz (zamiast STATUS); nowy test
  `test_trqlimit_nie_pchany_przed_status_spindle_output` wprost sprawdza
  regresję.

## Uwagi

- **Nie zweryfikowane jeszcze fizycznie po tej konkretnej poprawce** — do
  potwierdzenia przy najbliższym teście STOP na cyklu w trakcie dłuższego
  kroku.
- Diagnostyka (printy z `time.monotonic()`, `flush=True`) zostaje na stałe
  w kodzie — tania (log tylko gdy komenda trwa >0.3s) i była kluczowa do
  namierzenia tego błędu; warto ją zachować na wypadek podobnych
  problemów w przyszłości.
