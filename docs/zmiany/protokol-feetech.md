# Protokół natywny serw FEETECH — warstwa niska + `FeetekDriver` (temat L)

Sterownik magistrali serw FEETECH dla planowanej osi 4 (SM45BL — obecnie
dwa fizyczne serwa, docisk i podajnik): warstwa protokołu
(budowanie/parsowanie ramek) plus `FeetekDriver` (port szeregowy +
operacje wysokopoziomowe: ping, odczyt statusu, ruch pozycyjny),
testowalne bez fizycznego sprzętu. Świadomie **nie** zintegrowane jeszcze
z `Machine` — czeka na decyzje z `docs/architektura-wielu-drajwerow-osi.md`.

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
  z pierwszej odpowiadającej kombinacji port/baud; `--set-id NOWE_ID`
  zmienia ID serwa (odblokuj EPROM → zapisz → zablokuj → PING pod nowym).
- `server/app/feetech_driver.py` — `FeetekDriver`: jedna magistrala, wiele
  serw po ID, port przez `termios` (jak `tools/test_feetech_servo.py`,
  wydzielone do użycia jako context manager). `ping()`, `read_raw()`/
  `write_raw()`, `read_position()`, `read_status()`, `move_to()` (ruch
  pozycyjny w jednostkach rejestru — kroki enkodera, nie mm; odpowiednik
  `WritePosEx` z SDK producenta, zapis 7 bajtów od adresu ACC).
- `server/app/feetech_protocol.py` — dopisane adresy `ADDR_ACC`,
  `ADDR_GOAL_TIME_L/H`, `ADDR_GOAL_SPEED_L/H`, `ADDR_LOCK`, oraz
  `encode_signed16()` (odwrotność `decode_signed16`, do zapisu celu ruchu).
- `server/tests/test_feetech_driver.py` — 7 testów `FeetekDriver` na
  podstawionym `_exchange` (jak `_command`/`_exchange` w
  `test_sc4hub.py`), bez prawdziwego portu: ping, odczyt statusu, błąd
  serwa, poprawność ramki `move_to`, context manager.
- `tools/feetech_jog.py` — mały kontrolowany ruch (domyślnie 200 kroków
  enkodera, wolno) do sprawdzenia kierunku obrotu na sprzęcie; czeka na
  koniec ruchu odpytując rejestr MOVING, wypisuje pozycję przed/po.
  **Realnie rusza serwem — do uruchamiania tylko przy maszynie.**
- `server/app/feetech_driver.py` — `DIRECTION_SIGN_CW` (słownik ID→znak) i
  `FeetekDriver.move_relative_cw()` — ruch względny w jednoznacznym
  kierunku „zgodnie z zegarem", niezależnie od tego, czy dla danego ID
  rejestr rośnie czy maleje przy CW. Rzuca `KeyError` dla ID bez
  zmierzonego kierunku (celowo, zamiast zgadywać znak).

## Kierunek obrotu — zmierzone fizycznie 2026-09-10

Karta katalogowa SM45BL deklaruje „Clockwise(0→4096)" (rosnąca pozycja =
zgodnie z zegarem) dla całej serii — **u nas zmierzono inaczej dla
serwa 1**, prawdopodobnie kwestia strony obserwacji (od wału vs od tyłu
obudowy), nie błąd pomiaru. Liczy się wynik zmierzony na tym konkretnym
okablowaniu, nie deklaracja producenta:

| ID | Oś (dzisiejsze okablowanie) | CW (zgodnie z zegarem) odpowiada... |
|---|---|---|
| 1 | docisk | **malejącej** pozycji rejestru |
| 2 | podajnik | **rosnącej** pozycji rejestru |

**Metoda:** `tools/feetech_jog.py` z małym, wolnym ruchem (docisk: 200,
potem 1000 kroków przy prędkości 8-30; podajnik: 200, potem 1000, potem
500 kroków), operator przy maszynie zgłaszał obserwowany kierunek po
każdym ruchu.

**Zastrzeżenie o jakości pomiaru dla serwa 2:** pierwszy odczyt (ruch
+200, zaraz po zmianie ID, operator jeszcze nie przy maszynie) dał „w
lewo" (CCW) dla rosnącej pozycji — **sprzeczne** z późniejszym, spokojnym,
pojedynczym testem (+500, operator skupiony wyłącznie na obserwacji),
który dał „w prawo" (CW). Przyjęty **drugi, spokojniejszy odczyt** jako
wiarygodniejszy — pierwszy najpewniej był pomyłką obserwacji przy szybkich
testach pod rząd (operator sam wyraził wątpliwość zaraz potem: „nie
widzę ruch, zrobiłem znaki"). **To nie jest zweryfikowane podwójnie** —
jeśli przy integracji z `Machine` kierunek serwa 2 okaże się zły, to
pierwsze podejrzenie.

## Uwagi

- Adresy rejestrów wzięte wprost z `zbyszek/FTServo_Python-main.zip`
  (`scservo_sdk/sms_sts.py`) — potwierdzone u źródła, nie z pamięci.
- **Dekodowanie `PRESENT_LOAD` (bit znaku 15) nie jest potwierdzone dla
  tego konkretnego rejestru** — SDK producenta ma gotową metodę tylko dla
  pozycji/prędkości; dla obciążenia to założenie przez analogię (typowe
  dla tej rodziny protokołu). Do zweryfikowania na sprzęcie, zanim
  cokolwiek się na tym oprze poza podglądem.
- **Zweryfikowane fizycznie 2026-09-10.** Konwerter Waveshare SKU 15817
  (USB↔RS232/RS485/TTL) na `/dev/ttyUSB0`, jedno serwo SM-45BL-C001
  (ID:1, 115200), zasilanie 24VDC. `tools/test_feetech_servo.py --read`
  zwrócił poprawną ramkę PING i sensowny status (napięcie 23,0V, temp.
  27°C, pozycja/prędkość/obciążenie 0 w spoczynku). Po drodze: dwa serwa
  naraz na tym samym ID:1 nie odpowiadały wcale (kolizja na magistrali,
  zgodnie z ostrzeżeniem w FAQ producenta) — jedno serwo odłączone na
  czas testu, drugie do przełączenia na inne ID przed wspólnym
  podłączeniem. Konwerter podłączony do tego komputera (`walkner`) wymagał
  dodania konta do grupy `dialout` (`sudo usermod -aG dialout walkner` +
  `sudo systemctl restart ssh`) — restart ssh tym razem NIE odświeżył
  uprawnień już otwartej sesji Claude Code (w przeciwieństwie do
  wcześniejszego przypadku z grupą `motionctl`, patrz `~/.claude/CLAUDE.md`
  na tym hoście) — obejściem był `sg dialout -c '...'` per komenda, bez
  potrzeby nowego logowania.
- **ID drugiego serwa zmienione 2026-09-10** na 2 (`--set-id`, sekwencja
  odblokuj EPROM (adres 55=0) → zapisz ID (adres 5) → zablokuj (55=1) →
  PING pod nowym ID). Oba serwa podłączone razem, bez kolizji: ID 1 =
  docisk, ID 2 = podajnik. **Uwaga procesowa:** przy tej zmianie
  uruchomiłem komendę zapisu w tej samej turze, w której zapytałem
  użytkownika, czy na magistrali jest podłączone tylko jedno serwo — nie
  poczekałem na odpowiedź. Wyszło dobrze (efekt końcowy jest poprawny
  niezależnie od tego, które fizyczne serwo było podłączone), ale to był
  błąd procesowy, nie do powtórzenia przy kolejnych zapisach do sprzętu.
- Dekodowanie `present_voltage`/`present_temperature` jako wartości ×0,1
  (230 → 23,0V) — **spójne z wynikiem, ale nie potwierdzone wprost w
  SDK/dokumentacji jako jednostka tego konkretnego rejestru**, do
  ostatecznego potwierdzenia przy okazji pełniejszej analizy tabeli
  pamięci (`zbyszek/Tabela pamięci protokół serw SM45BL_001.xlsx`).
