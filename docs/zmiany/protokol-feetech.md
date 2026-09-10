# Protokół natywny serw FEETECH — warstwa niska (temat L)

Pierwszy krok w stronę `FeetekDriver` dla planowanej osi 4 (SM45BL):
sama warstwa protokołu (budowanie/parsowanie ramek), testowalna bez
fizycznego sprzętu. Świadomie **nie** zintegrowane jeszcze z `Machine` —
czeka na fizyczne potwierdzenie protokołu i decyzje z
`docs/architektura-wielu-drajwerow-osi.md`.

## Pliki

- `server/app/feetech_protocol.py` — budowanie ramek (PING/READ/WRITE),
  parsowanie odpowiedzi, suma kontrolna, dekodowanie U16/I16 (znak-
  magnituda, bit 15), adresy rejestrów serii SMS (pozycja, prędkość,
  obciążenie, napięcie, temperatura, tryb, moment włączony).
- `server/tests/test_feetech_protocol.py` — 11 testów (budowanie ramek
  zgodnie z ręczną kalkulacją sumy kontrolnej, parsowanie poprawnych i
  błędnych odpowiedzi, dekodowanie liczb).
- `tools/test_feetech_servo.py` — przepisany na import z
  `app.feetech_protocol` (bez duplikacji), dodana flaga `--read`: po
  udanym PING odczytuje pozycję/prędkość/obciążenie/napięcie/temperaturę
  z pierwszej odpowiadającej kombinacji port/baud.

## Uwagi

- Adresy rejestrów wzięte wprost z `zbyszek/FTServo_Python-main.zip`
  (`scservo_sdk/sms_sts.py`) — potwierdzone u źródła, nie z pamięci.
- **Dekodowanie `PRESENT_LOAD` (bit znaku 15) nie jest potwierdzone dla
  tego konkretnego rejestru** — SDK producenta ma gotową metodę tylko dla
  pozycji/prędkości; dla obciążenia to założenie przez analogię (typowe
  dla tej rodziny protokołu). Do zweryfikowania na sprzęcie, zanim
  cokolwiek się na tym oprze poza podglądem.
- Nie zweryfikowane fizycznie — czeka na test łączności
  (`tools/test_feetech_servo.py --read`) po podłączeniu konwertera i
  zasilania 24VDC.
