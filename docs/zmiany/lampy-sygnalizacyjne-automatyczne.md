# Lampy sygnalizacyjne (LR, LG) automatyczne wg stanu maszyny

Zamówienie 2026-09-12: „zaprogramuj wyjście lampki czerwonej LR — ma się
włączać adekwatnie do swojej roli". Dopełnione tego samego dnia: „zielona
lampa powinna włączyć się, jeśli maszyna jest gotowa — musisz
doprogramować tą funkcję". Kanały DO z etykietami `LR`/`LG` (moduł I/O
Modbus) świecą się teraz SAME, zależnie od stanu maszyny, bez udziału
operatora, kroku cyklu ani programu:

- **LR** (czerwona) = maszyna w stanie `ALARM`.
- **LG** (zielona) = maszyna w stanie `READY` (gotowa na START).
- **LY** (żółta) nie ma automatycznej roli — świadomie zostaje wyłącznie
  pod kontrolą kroku WYJSCIE cyklu (operator: „ja będę gasił sam w
  programie i zapalał po zakończeniu cyklu" — dotyczyło LG, patrz uwaga
  niżej o współistnieniu).

## Jak to działa

`main._signal_lamp_targets(state)` — czysta funkcja, zwraca
`{"LR": state == MachineState.ALARM, "LG": state == MachineState.READY}`.
`main._apply_signal_lamps(result)` — dla każdej etykiety z powyższego:
znajduje kanał po etykiecie (`_resolve_io_modbus_channel`, ta sama
funkcja co krok WYJSCIE cyklu i ręczny zapis), porównuje z wartością
**odczytaną** w tym samym obiegu `_io_modbus_poll_loop` (nie z jakimś
zapamiętanym „co ostatnio ustawiliśmy") i pisze tylko, gdy się różni.

**Samonaprawiające się, nie tylko „ustaw i zapomnij":** skoro porównanie
jest z odczytem, nie z pamięcią, ręczne przełączenie danego kanału albo
krok WYJSCIE cyklu na nim zostanie przywrócone do stanu wynikającego ze
stanu maszyny w ciągu jednego obiegu pętli (~1s, albo
`watchdog.interval_s`, jeśli watchdog jest włączony — ta sama pętla).

## Pliki

- `server/app/main.py` — `_signal_lamp_targets()`, `_apply_signal_lamps()`,
  wywołanie w `_io_modbus_poll_loop()` zaraz po odczycie, pod tym samym
  `_feetech_lock`.
- `server/app/static/io-modbus.html`, `help.html` — opis automatycznego
  zachowania kanałów LR/LG.
- `server/tests/test_signal_lamps.py` — 11 testów: mapowanie stanu->lampa
  (LR, LG, nigdy jednocześnie), zapalenie/zgaszenie obu, brak zbędnego
  zapisu gdy już zgodne, pominięcie nieskonfigurowanych etykiet,
  tolerancja błędu sprzętu.

## Uwagi

- **Etykieta, nie numer kanału** — automat zawsze szuka po etykiecie, więc
  przeniesienie jej na inny kanał z ekranu `/io-modbus` nic nie psuje.
  Usunięcie etykiety ze wszystkich kanałów po cichu wyłącza automat dla
  tej lampy (brak czym sterować), bez błędu.
- **Współistnienie z ręcznym sterowaniem LG z cyklu:** operator ma w
  produkcyjnym cyklu kroki WYJSCIE na kanale LG (gaśnie na starcie cyklu,
  zapala po jego zakończeniu — `server/config/cycle.json`, kroki 1 i 10).
  To jest REDUNDANTNE z automatem (RUNNING nie jest READY, koniec cyklu
  wraca do READY — te same chwile), ale NIE sprzeczne. Teoretycznie
  możliwe krótkie miganie, jeśli pętla automatu (co ~1s) akurat trafi w
  bardzo wąskie okno tuż przed przejściem RUNNING→READY — w praktyce
  nieistotne, bo automat i tak ustawi ten sam stan chwilę później.
  **Nie usuwałem kroków operatora** — to jego decyzja, czy je zostawić.
- **To sygnalizacja, nie funkcja bezpieczeństwa** — informuje otoczenie o
  stanie maszyny, nie zatrzymuje niczego i nie zastępuje E-stop/Global Stop.
- Rozważone, ale NIE zrobione: automatyczna rola LY. „Alarmy..." w
  pierwszym zgłoszeniu zostało urwane — jeśli operator miał na myśli coś
  szerszego niż `MachineState.ALARM` (np. alarmy zużycia osi, temat M),
  to osobna, jeszcze nieustalona decyzja.
- Nie testowane jeszcze fizycznie na maszynie w tej sesji — w
  szczególności stan ALARM (LR) nie był wywołany celowo do sprawdzenia,
  że fizyczna lampka się zapala.
