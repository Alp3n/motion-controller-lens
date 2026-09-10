# Propozycja: moduł analizy zużycia osi/narzędzia i powiadomień o incydentach

Zgłoszenie użytkownika (2026-09-09): ekran z analizą zużycia osi (średnie
i maksymalne zużycie na godzinę/zmianę/tydzień), definicja progów
alarmowych z powiadomieniem **e-mail** i do systemu **MES (moduł FAP)**,
moduł analizy cykli maszyny, długoterminowa analiza zużycia osi/narzędzia.
Dane zbieramy „dopiero na spokojnie po cyklu" — nie w czasie rzeczywistym
podczas ruchu (potwierdza znane już ograniczenie architektoniczne z tematu
K: mostek blokuje się na czas ruchu, Python nic nie może zrobić w trakcie,
patrz `funkcje-smart.md`). **To systematyzacja tematu do notatek, nie
gotowy kod** — zbyt wiele otwartych decyzji (metryka zużycia, magazyn
długoterminowy, kontrakt z MES, dane SMTP), podobnie jak
[`propozycja-head-tail-asymetria.md`](propozycja-head-tail-asymetria.md).

## Co już mamy, na czym można się oprzeć

- `Machine._record_sample()`/`self.recording` (`server/app/machine.py`) —
  próbkuje pozycję i moment co ~200 ms **w trakcie** ruchu (RUNNING/
  PAUSED), ale to bufor **ulotny**: zaczyna się od zera przy każdym
  starcie, ucięty do 6000 próbek (~20 minut). Dziś służy tylko do wykresu
  na `/sila` po jednym uruchomieniu (`zmiany/przebieg-nagrywanie.md`). To
  naturalny punkt zaczepienia dla „obróbki po cyklu" — wymaga rozszerzenia
  o TRWAŁY zapis wyniku (dziś ginie przy kolejnym starcie).
- Odczyt momentu na sprzęcie (`TRQX/Y/Z`) — działa, `torque_source:
  "sterownik"` (temat K etap 0). Najbardziej naturalna dzisiejsza metryka
  obciążenia osi.
- **Czego NIE ma:** żadnego kodu do wysyłki e-mail (brak SMTP w projekcie),
  żadnej integracji **wychodzącej** do MES (dzisiejsza integracja jest
  wyłącznie przychodząca: `POST /api/mes/select-order` — MES woła NAS, nie
  odwrotnie, `zmiany/token-mes.md`), żadnego magazynu danych
  długoterminowych (wszystkie `config/*.json` to bieżąca konfiguracja, nie
  historia zdarzeń).

## Decyzje podjęte 2026-09-10

- **Alarmy na poziomie maszyny, powiadomienia (e-mail, MES/FAP) po stronie
  wMES** — nasz serwer NIE wysyła e-maili ani nie woła MES. To zdejmuje
  główne ryzyko z bloku 4 niżej (nowy sekret SMTP, kontrakt API wychodzący
  do MES) — nasza odpowiedzialność kończy się na wykryciu przekroczenia
  progu i wystawieniu tego gdzieś, skąd wMES to odczyta (dokładny kształt —
  do ustalenia, patrz blok 4).
- **Bez dużych baz danych — dwuwarstwowy model zapisu:** szczegółowe dane
  trzymane tylko z **bieżącej doby**; potem zapisywana jest **średnia dla
  osi** (i maksimum), a te uśrednione wpisy **zbierane bez ograniczenia w
  czasie** (trend rośnie wolno — jedna linia per oś per dzień aktywności),
  żeby dało się zobaczyć długoterminowy trend pracy poszczególnej osi pod
  kątem predykcji maintenance. Rozstrzyga blok 2 niżej.
- **Krok 1-2 z proponowanej kolejności (metryka + zbieranie/zapis po
  przebiegu) zaimplementowany 2026-09-10** — `server/app/zuzycie.py`,
  szczegóły: `zmiany/zuzycie-osi-zbieranie.md`. Metryka na start: dystans
  [mm] per oś (suma) + moment (średnia, maksimum) tam, gdzie mierzony na
  sprzęcie. Wciąż bez ekranu (krok 3) i bez alarmów (krok 4).

## Cztery osobne bloki, żeby się nie pomieszały

### 1. Metryka „zużycia" — do ustalenia, zanim cokolwiek zakoduję

„Zużycie osi/narzędzia" nie ma jednej oczywistej definicji. Kandydaci:

- **Liczba cykli/operacji cięcia** — proste, ale nie odróżnia lekkiego
  cięcia od ciężkiego.
- **Skumulowany dystans przejechany [mm]** — dobre dla zużycia
  mechanicznego (śruba, prowadnice), niezależne od siły, działa też
  w symulatorze.
- **Skumulowany moment × czas** (całka obciążenia w czasie) — najbliżej
  rzeczywistego zużycia napędu, ale wymaga zaufania do pomiaru momentu
  (mamy go tylko na sprzęcie, nie w symulatorze — patrz zastrzeżenia w
  `funkcje-smart.md`) i przelicznika moment→siła, którego jeszcze nie
  mamy (temat K etap 2, kalibracja na `/sila`).
- **Czas pracy pod obciążeniem powyżej progu** — prostsze niż całka,
  łatwiejsze do wytłumaczenia operatorowi.
- Osobna metryka dla **narzędzia** (frez) niż dla **osi** (śruba/napęd) —
  to dwa różne obiekty zużycia, mieszanie ich w jednej liczbie byłoby
  mylące. Zgłoszenie wspomina oba („zużycia osi **lub** narzędzia").

**Zdecydowane 2026-09-10, zaimplementowane:** skumulowany dystans [mm] per
oś (suma) + moment (średnia, maksimum) tam, gdzie mierzony na sprzęcie —
patrz `zmiany/zuzycie-osi-zbieranie.md`. Osobna metryka „zużycia
narzędzia" (licznik operacji cięcia) **jeszcze nie zaimplementowana** —
zostaje jako rozszerzenie, gdy będzie potrzebna.

### 2. Przechowywanie długoterminowe — ROZSTRZYGNIĘTE i zaimplementowane 2026-09-10

Agregacja godzina/zmiana/tydzień wymaga TRWAŁEGO zapisu, nie bufora w
pamięci procesu (jak dawny `recording`). Ustalone z użytkownikiem: **bez
dużych baz danych**, dwuwarstwowo —

- **Szczegóły tylko z bieżącej doby:** surowe wpisy (jeden na zakończony
  przebieg — cykl albo pojedynczy program), w pliku dnia
  `config/zuzycie/YYYY-MM-DD.jsonl`. Zostają surowe (nie zagregowane od
  razu), więc przyszły ekran może z nich policzyć „na godzinę"/„na zmianę"
  dowolnie, bez zamrażania definicji „zmiany" w formacie zapisu.
- **Trend bez ograniczenia w czasie:** przy pierwszym zapisie po zmianie
  dnia poprzedni plik dnia jest sprowadzany do JEDNEJ linii per oś
  (liczba przebiegów, suma dystansu, średni/maks. moment) dopisywanej
  trwale do `config/zuzycie/trend.jsonl`, po czym kasowany. Trend rośnie
  wolno (najwyżej kilka linii dziennie), bezpiecznie bez limitu — to dane
  pod długoterminową predykcję maintenance.
- **Format:** JSON Lines, jak istniejący `app/audit.py` — bez nowej
  zależności, zgodnie z tym, że reszta projektu nie używa bazy danych.

Szczegóły implementacji: `zmiany/zuzycie-osi-zbieranie.md`.
**Wciąż otwarte:** dokładna definicja „zmiany" (stałe godziny czy
konfigurowalne) — potrzebna dopiero przy budowie ekranu (krok 3), bo dziś
i tak trzymamy surowe zdarzenia z całego dnia.

### 3. Definicja alarmu — wzorem definicji SMART

Nazwany próg (np. „X-zużycie-dzienne-krytyczne": metryka, oś/narzędzie,
okres, wartość progowa) — CRUD jak `/smart` (`app/smart.py`,
`zmiany/ekran-smart.md`), żeby dało się dodawać reguły bez zmiany kodu.
**Kiedy sprawdzamy próg** — po każdym zakończonym przebiegu, zgodnie z
„obrabiamy dane po cyklu, na spokojnie" (ten sam punkt w kodzie, gdzie
dziś wywołuje się `zuzycie.record_run()` — `main.py::_poll_loop`).
**Jeszcze niezaimplementowane** (krok 4).

### 4. Powiadomienia — uproszczone decyzją 2026-09-10

**Alarmy wykrywamy na poziomie maszyny; wysyłkę e-maili i zgłoszenia do
modułu FAP systemu MES robi wMES, nie nasz serwer.** To zdejmuje z tego
tematu największe ryzyka, które były tu opisane wcześniej — nowy sekret
SMTP i projektowanie kontraktu API wychodzącego do MES na wyczucie.

**Wciąż otwarte:** w jaki sposób wMES dowiaduje się o wykrytym
przekroczeniu progu. Dwie opcje, do ustalenia z Tobą/integratorem MES:
- **wMES odpytuje nasz serwer** (nowy endpoint, np. `GET
  /api/zuzycie/alarmy`, zwracający aktywne/ostatnie przekroczenia) —
  pasuje do dzisiejszego kierunku integracji (MES woła nas, jak
  `POST /api/mes/select-order`), nie wymaga nowego sekretu wychodzącego.
- **Nasz serwer coś zapisuje/publikuje**, co wMES obserwuje z drugiej
  strony (plik współdzielony, kolejka) — mniej pasuje do dzisiejszej
  architektury, prawdopodobnie niepotrzebne, jeśli opcja pierwsza
  wystarczy.

## Ekran (dopiero po ustaleniu punktów 1-4)

Robocza nazwa `/analiza-osi` (albo `/zuzycie`), rola co najmniej
`technolog` do podglądu, `admin` do definiowania progów alarmowych — wzorem
`/smart` + `/sila`. Zawartość: bieżący okres (godzina/zmiana/tydzień) per
oś i per narzędzie, trend, lista zdefiniowanych alarmów i ich status,
historia wysłanych powiadomień (żeby dało się sprawdzić, czy alarm
faktycznie poszedł).

## Proponowana kolejność (jeśli się zgadzasz z podziałem wyżej)

1. ~~Ustalić metrykę (punkt 1) i minimalny format trwałego zapisu
   (punkt 2)~~ — **zrobione 2026-09-10.**
2. ~~Zbieranie i zapis danych po cyklu (bez alarmów, bez ekranu)~~ —
   **zaimplementowane 2026-09-10**, `zmiany/zuzycie-osi-zbieranie.md`. Dane
   zaczynają się gromadzić od teraz, więc długoterminowy trend będzie
   rósł od tej daty.
3. **Następny krok:** ekran z samym podglądem (bez alarmów/powiadomień) —
   już przydatny sam w sobie.
4. Definicje alarmów (wzorem `/smart`) — sprawdzane po każdym przebiegu,
   w tym samym miejscu co zapis danych.
5. Udostępnienie alarmów systemowi MES do odczytu (prawdopodobnie nowy
   endpoint `GET /api/zuzycie/alarmy`, wMES sam wysyła e-mail/FAP) —
   ostatni krok, bo najmniej pilny przy dzisiejszej decyzji o podziale
   odpowiedzialności.
