# Lampa czerwona (LR) automatyczna wg stanu maszyny

Zamówienie 2026-09-12: „zaprogramuj wyjście lampki czerwonej LR — ma się
włączać adekwatnie do swojej roli". Kanał DO z etykietą `LR` (moduł I/O
Modbus) świeci się teraz SAM, gdy maszyna jest w stanie `ALARM`, i gaśnie
sam w każdym innym stanie — bez udziału operatora, kroku cyklu ani
programu.

## Jak to działa

`main._signal_lamp_targets(state)` — czysta funkcja, zwraca
`{"LR": state == MachineState.ALARM}`. `main._apply_signal_lamps(result)`
— dla każdej etykiety z powyższego: znajduje kanał po etykiecie
(`_resolve_io_modbus_channel`, ta sama funkcja co krok WYJSCIE cyklu i
ręczny zapis), porównuje z wartością **odczytaną** w tym samym obiegu
`_io_modbus_poll_loop` (nie z jakimś zapamiętanym „co ostatnio
ustawiliśmy") i pisze tylko, gdy się różni.

**Samonaprawiające się, nie tylko „ustaw i zapomnij":** skoro porównanie
jest z odczytem, nie z pamięcią, ręczne przełączenie tego kanału albo
krok WYJSCIE cyklu na nim zostanie przywrócone do stanu wynikającego z
alarmu w ciągu jednego obiegu pętli (~1s, albo `watchdog.interval_s`,
jeśli watchdog jest włączony — ta sama pętla).

## Pliki

- `server/app/main.py` — `_signal_lamp_targets()`, `_apply_signal_lamps()`,
  wywołanie w `_io_modbus_poll_loop()` zaraz po odczycie, pod tym samym
  `_feetech_lock`.
- `server/app/static/io-modbus.html`, `help.html` — opis automatycznego
  zachowania kanału LR.
- `server/tests/test_signal_lamps.py` — 7 testów: mapowanie stanu->lampa,
  zapalenie/zgaszenie, brak zbędnego zapisu gdy już zgodne, pominięcie
  nieskonfigurowanej etykiety, tolerancja błędu sprzętu.

## Uwagi

- **Etykieta, nie numer kanału** — `LR` to dziś `do1` w domyślnym
  przypisaniu (`io_modbus.default_io()`), ale automat zawsze szuka po
  etykiecie, więc przeniesienie jej na inny kanał z ekranu `/io-modbus`
  nic nie psuje. Usunięcie etykiety `LR` ze wszystkich kanałów po cichu
  wyłącza automat (brak czym sterować), bez błędu.
- **To sygnalizacja, nie funkcja bezpieczeństwa** — informuje otoczenie,
  że maszyna jest w ALARM, nie zatrzymuje niczego i nie zastępuje
  E-stop/Global Stop.
- Rozważone, ale NIE zrobione teraz: role lampy zielonej (LG) i żółtej
  (LY) — zgłoszenie dotyczyło wyłącznie czerwonej. „Alarmy..." w
  zgłoszeniu urwane — jeśli operator miał na myśli coś szerszego niż
  `MachineState.ALARM` (np. alarmy zużycia osi, temat M), to osobna,
  jeszcze nieustalona decyzja.
- Nie testowane jeszcze fizycznie na maszynie w tej sesji.
