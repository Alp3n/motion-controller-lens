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
- [model-cyklu-maszyny.md](model-cyklu-maszyny.md) — propozycja modelu
  danych dla tematu B: `Axis`/`ParameterProfile`/`CycleStep`/`PartProgram`,
  snapshot/restore parametrów, podział na etapy.

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

PDF-y dokumentacji: [`pdf/`](pdf/) — generowane skryptem `tools/docs-pdf.py`.
