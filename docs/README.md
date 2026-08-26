# Dokumentacja

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

PDF-y dokumentacji: [`pdf/`](pdf/) — generowane skryptem `tools/docs-pdf.py`.
