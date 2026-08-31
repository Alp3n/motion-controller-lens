# Dokumentacja

Plan pracy:

- [plan-rozwoju.md](plan-rozwoju.md) — tematy do zaimplementowania,
  wyciągnięte z całej dokumentacji, z uzasadnieniem i proponowaną kolejnością.
- [kanban.md](kanban.md) — te same tematy jako karty do śledzenia postępu.

Specyfikacje:

- [ARCHITEKTURA.md](ARCHITEKTURA.md) — architektura systemu: serwer maszyny,
  sterownik, integracja z MES.
- [FORMAT_PROGRAMU.md](FORMAT_PROGRAMU.md) — format plików programów `.prg`.

Ustalenia i analizy:

- [sterownik-sc4-hub.md](sterownik-sc4-hub.md) — sprzętem jest SC4-Hub, a nie
  ClearCore: konsekwencje, proponowany mostek sFoundation, otwarte ryzyka.
- [uruchomienie-lokalne.md](uruchomienie-lokalne.md) — odstępstwa od README przy
  uruchamianiu symulatora i wynik weryfikacji.
- [uruchomienie-windows.md](uruchomienie-windows.md) — postawienie środowiska
  testowego i uruchamianie w VS Code na Windows 11.
- [nowe-operacje-programu.md](nowe-operacje-programu.md) — propozycja rozszerzenia
  zbioru operacji `.prg`, format 2, przebudowa edytora technologa.
- [konfiguracja-osi.md](konfiguracja-osi.md) — model osi: długość, punkt
  bazowania, limity programowe, przełożenie posuwu; komenda `AXCFG`.
- [inspiracje-mic488.md](inspiracje-mic488.md) — co warto przenieść z kontrolera
  WObit MIC488 (tablica pozycji, przerwania, tryby bazowania) i znalezione
  ryzyko: SC4-Hub nie ma I/O wymaganego przez plany (PWM wrzeciona).
- [mozliwosci-clearpath-sc.md](mozliwosci-clearpath-sc.md) — czego nie
  wykorzystujemy z serw (mamy wersję Advanced): limit momentu z API, bazowanie
  do oporu, grupy wyzwalania, zdarzenia; ryzyko: system może przypadkowo
  załączyć wyjście BRAKE.
- [funkcje-smart.md](funkcje-smart.md) — ruch z kontrolą siły (temat K):
  odczyt momentu `TrqMeasured` potwierdzony u źródła, dlaczego pętla musi
  być w mostku a nie w Pythonie, definicje SMART i ekran `/smart`, operacja
  `SMART` w `.prg` i w cyklu, **ekran `/sila` do kontroli siły i kalibracji**
  (charakterystyka obciążenia w ruchu), etapy i ryzyka.
- [model-cyklu-maszyny.md](model-cyklu-maszyny.md) — propozycja modelu
  danych dla tematu B: `Axis`/`ParameterProfile`/`CycleStep`/`PartProgram`,
  snapshot/restore parametrów, podział na etapy.
- [propozycja-head-tail-asymetria.md](propozycja-head-tail-asymetria.md) —
  propozycja ruchów head-tail (zagłębianie w Z) i asymetrycznych
  (przyspieszenie ≠ hamowanie), temat C; pytania do decyzji, celowo bez
  kodu — to zmiana zachowania ruchu w materiale.

Zmiany w kodzie opisujemy w [`zmiany/`](zmiany/) — jeden plik na zmianę,
nazwa od zmiany. Konwencja: [`../CLAUDE.md`](../CLAUDE.md).

- [zmiany/mostek-sc4hub.md](zmiany/mostek-sc4hub.md) — mostek `bridge/`
  zastępujący firmware ClearCore; poprawki stanów cyklu w serwerze.
- [zmiany/operacje-grupy-a.md](zmiany/operacje-grupy-a.md) — PROSTOKAT, SZYBKI,
  WRZECIONO i format 3.
- [zmiany/status-i-zatrzymanie.md](zmiany/status-i-zatrzymanie.md) — jeden poller
  statusu, STOP w trakcie ruchu, odtwarzanie połączenia, komunikaty alarmu.
- [zmiany/edytor-przebudowa.md](zmiany/edytor-przebudowa.md) — pola zależne od
  rodzaju operacji, walidacja na bieżąco, podgląd toru, przestawianie wierszy.
- [zmiany/parametry-operacji.md](zmiany/parametry-operacji.md) — format 2:
  własny posuw operacji i wielokrotne przejścia na głębokość.
- [zmiany/luzowanie-osi.md](zmiany/luzowanie-osi.md) — zdejmowanie momentu
  z osi do ręcznego przestawiania; poprawka gubionych błędów bazowania.
- [zmiany/narzedzia-usb-sc4hub.md](zmiany/narzedzia-usb-sc4hub.md) — przypinanie
  huba do sterownika Exar zamiast `cdc_acm`.
- [zmiany/ekran-konfiguracji-osi.md](zmiany/ekran-konfiguracji-osi.md) — ekran
  `/axes`, plik konfiguracji osi, limity w serwerze i w mostku.
- [zmiany/uruchamianie-i-pdf.md](zmiany/uruchamianie-i-pdf.md) — skrót na
  pulpicie uruchamiający całe środowisko oraz generator PDF-ów dokumentacji.
- [zmiany/srodowisko-testowe-vscode.md](zmiany/srodowisko-testowe-vscode.md) —
  konfiguracja VS Code (interpreter, debugger, testy) zweryfikowana na
  Ubuntu 24.04.
- [zmiany/osie-dodatkowe-etap1.md](zmiany/osie-dodatkowe-etap1.md) —
  konfiguracja osi przyjmuje dowolne osie ponad wymagane X/Y/Z (etap 1
  tematu B).
- [zmiany/profile-parametrow-etap2.md](zmiany/profile-parametrow-etap2.md) —
  profile parametrów ruchu (prędkość, rampy, limit momentu) i `/api/profiles`
  (etap 2 tematu B).
- [zmiany/cykl-maszyny-etap3.md](zmiany/cykl-maszyny-etap3.md) — kroki cyklu
  maszyny, `/api/cycle` i snapshot/restore profilu wokół programu detalu
  (etap 3 tematu B).
- [zmiany/ekran-cyklu-etap4.md](zmiany/ekran-cyklu-etap4.md) — ekran
  `/cycle` do definiowania i uruchamiania cyklu (etap 4 tematu B).
- [zmiany/poprawka-podgladu-pozycji.md](zmiany/poprawka-podgladu-pozycji.md) —
  błąd JS zatrzymywał skrypt panelu, przez co nie działał WebSocket i podgląd
  pozycji.
- [zmiany/dodawanie-osi-ekran.md](zmiany/dodawanie-osi-ekran.md) — ekran
  `/axes` pozwala dopisać oś ponad X/Y/Z, oznaczoną jako „tylko
  konfiguracja” (bez wsparcia mostka).
- [zmiany/predkosci-jog-bazowanie.md](zmiany/predkosci-jog-bazowanie.md) —
  prędkość JOG i bazowania konfigurowalne per oś na ekranie `/axes`;
  bazowanie działa tylko w symulatorze. Zawiera też poprawkę: zapis zerował
  pola, gdy serwer nie został zrestartowany po `git pull`.
- [zmiany/ekran-profili.md](zmiany/ekran-profili.md) — ekran `/profiles`:
  siła trzypoziomowa (globalny/cykl/program) i prędkość, edycja i
  przełączanie aktywnego profilu.
- [zmiany/tryby-pracy.md](zmiany/tryby-pracy.md) — tryb automatyczny (cykl
  w pętli) i manualny JOG „martwy człowiek"; opisuje też znaleziony błąd
  zawieszający cały serwer przy kroku cyklu bez realnego ruchu.
- [zmiany/zapisz-jako-program.md](zmiany/zapisz-jako-program.md) — kopiowanie
  programu technologa pod nowym numerem NC w edytorze.
- [zmiany/ekran-glowny.md](zmiany/ekran-glowny.md) — poprawiona nazwa maszyny
  (literówka „ocinanie” → „odcinanie” w całym repo) i miejsce na logo WALKNER
  w nagłówku panelu operatora.
- [zmiany/sila-per-operacja.md](zmiany/sila-per-operacja.md) — kolumna
  MOMENT w programie technologa (format 4 pliku `.prg`), limit siły tylko
  dla jednej operacji; dziś wyłącznie zapis w pliku, jak w profilach.
- [zmiany/cykl-na-sprzecie.md](zmiany/cykl-na-sprzecie.md) — `SC4HubMachine`
  dostaje `start_cycle` (brakowało go od etapu 4 tematu B — `/cycle` nie
  działał na sprzęcie). Pierwsze testy automatyczne dla tej klasy. Nie
  zweryfikowane na fizycznym sterowniku.
- [zmiany/porzadek-konfiguracji.md](zmiany/porzadek-konfiguracji.md) — poprawka
  `.gitignore` (wzorce nie łapały `server/config/`) i opis rozjazdu: konfiguracja
  w dwóch katalogach, część śledzona w gicie — propozycja uporządkowania.
- [zmiany/wyjscia-fizyczne.md](zmiany/wyjscia-fizyczne.md) — wyjścia
  `BRAKE_0`/`BRAKE_1` podpięte do aplikacji: komenda `OUTPUT` w mostku, krok
  `WYJSCIE` przełącza fizyczne wyjście, przeznaczenie i gaszenie przy STOP.
- [zmiany/role-i-logowanie.md](zmiany/role-i-logowanie.md) — osobne konta
  (admin/technolog/operator), ekran logowania, dziennik zmian „kto co zmienił"
  i ekran diagnostyczny `/diagnostics`; co z tego NIE jest zabezpieczeniem.
- [zmiany/wrzeciono-start.md](zmiany/wrzeciono-start.md) — kiedy wrzeciono się
  załącza (start maszyny, start programu) i kiedy gaśnie; obroty dalej bez
  wpływu na sprzęt (brak PWM w SC4-Hub).
- [zmiany/ekran-bazowania.md](zmiany/ekran-bazowania.md) — ekran `/homing`
  (kolejność osi, HardStop, limit momentu, offset) i przycisk „HOME wszystkich
  osi"; parametry HardStop to zapis dla ClearView, nie konfiguracja serwa.
- [zmiany/nazewnictwo-sc4hub.md](zmiany/nazewnictwo-sc4hub.md) — nazwy w kodzie
  z „ClearCore" na „SC4-Hub" (`SC4HubMachine`, `MACHINE_MODE=sc4hub`,
  `BRIDGE_HOST`); stare nazwy dalej przyjmowane, host produkcyjny bez zmian.

- [zmiany/ekran-smart.md](zmiany/ekran-smart.md) — model definicji SMART,
  `/api/smart` i ekran `/smart` z „zapisz jako" (etap 1 tematu K); procedura
  w mostku jeszcze nie istnieje.
- [zmiany/cykl-na-sprzecie.md](zmiany/cykl-na-sprzecie.md) — `ClearCoreMachine`
  dostaje `start_cycle` (brakowało go od etapu 4 tematu B — `/cycle` nie
  działał na sprzęcie). Pierwsze testy automatyczne dla tej klasy. Nie
  zweryfikowane na fizycznym sterowniku.
- [zmiany/symulacja-momentu.md](zmiany/symulacja-momentu.md) — obciążenie osi
  w statusie (`torque` + `torque_source`); symulator podstawia wartości
  zmyślone, parser `TRQX/Y/Z` ze sterownika gotowy (etap 0 tematu K).
- [zmiany/smart-w-programie-i-cyklu.md](zmiany/smart-w-programie-i-cyklu.md) —
  operacja `SMART` w `.prg` (format 5) i krok `SMART` w cyklu maszyny, jedne
  definicje dla obu (etapy 3 i 4 tematu K); na sprzęcie mostek odmawia.
- [zmiany/skill-uruchom-projekt.md](zmiany/skill-uruchom-projekt.md) — skill
  Claude Code uruchamiający panel serwera jednym poleceniem, bezpiecznie na
  hoście produkcyjnym i na checkoucie deweloperskim.
- [zmiany/jedz-do-zera.md](zmiany/jedz-do-zera.md) — przycisk „JEDŹ DO ZERA"
  na panelu operatora: dojazd do (0,0,0) po bazowaniu, bez ponownego
  bazowania; ryzyko kolizji, bo nie podnosi Z przed ruchem XY.
- [zmiany/token-mes.md](zmiany/token-mes.md) — opcjonalny token
  (`X-MES-Token`) dla `POST /api/mes/select-order`; domyślnie wyłączony,
  nie zmienia istniejącego zachowania dopóki nie ustawi się `MES_TOKEN`.
- [zmiany/limit-momentu-sprzet.md](zmiany/limit-momentu-sprzet.md) — limit
  momentu profilu dociera do serw (`TRQLIMIT`, `ILimits.TrqGlobal`, etap 2b
  tematu B). Napisane i skompilowane osobno, **niewdrożone** — ważna
  kolejność wdrożenia (mostek przed Pythonem), inaczej zrywa połączenie.
- [zmiany/ekran-sila.md](zmiany/ekran-sila.md) — ekran `/sila`: podgląd
  momentu na żywo i ręczna kalibracja moment→siła (etap 2 tematu K,
  częściowo — bez automatycznej próby przejazdu, bo ta rusza maszyną).

PDF-y dokumentacji: [`pdf/`](pdf/) — generowane skryptem `tools/docs-pdf.py`.
