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

**Rekomendacja, jeśli mam wybrać jedną na start:** skumulowany dystans
[mm] per oś + osobno licznik operacji cięcia jako proxy zużycia
narzędzia. Metryka oparta na momencie/obciążeniu dopiero gdy będzie
przelicznik moment→siła z tematu K — inaczej liczby „zużycia" byłyby
nieskalibrowanym zgadywaniem.

### 2. Przechowywanie długoterminowe — nowa warstwa, nie istnieje dziś

Agregacja godzina/zmiana/tydzień wymaga TRWAŁEGO zapisu, nie bufora w
pamięci procesu (jak dzisiejszy `recording`). Do ustalenia:

- **Format:** proste dopisywanie zdarzeń do pliku (JSON Lines/CSV, jeden
  wpis na zakończoną operację/cykl), w stylu reszty `config/`, czy coś
  strukturalnego (SQLite)? Przy niskiej częstotliwości zdarzeń (cykle
  trwają sekundy-minuty, nie setki na sekundę) prosty dopisywany plik
  prawdopodobnie wystarczy — zgodnie z tym, że reszta projektu nie używa
  bazy danych.
- **Co jest jednym wpisem** — pojedyncza operacja `.prg`? Cały cykl
  maszyny? Trzymać surowe zdarzenia i agregować przy odczycie (elastyczne,
  więcej miejsca na dysku, da się przeliczyć wstecz inną definicją
  „zmiany") czy agregować od razu przy zapisie (mniej miejsca, ale
  definicja „zmiany" zamrożona na stałe)?
- **Definicja „zmiany"** — stałe godziny (np. 6-14/14-22/22-6) czy
  konfigurowalne na ekranie? Wpływa na to, jak liczyć „na zmianę".
- **Retencja** — jak długo trzymamy dane „długoterminowe"? Bez limitu
  plik rośnie bez końca.

### 3. Definicja alarmu — wzorem definicji SMART

Nazwany próg (np. „X-zużycie-dzienne-krytyczne": metryka, oś/narzędzie,
okres, wartość progowa, odbiorcy) — CRUD jak `/smart` (`app/smart.py`,
`zmiany/ekran-smart.md`), żeby dało się dodawać reguły bez zmiany kodu.
**Kiedy sprawdzamy próg** — po każdym zakończonym cyklu, zgodnie z
„obrabiamy dane po cyklu, na spokojnie"?

### 4. Dwa kanały powiadomień — różne wymagania, różne ryzyka

- **E-mail:** wymaga konfiguracji SMTP (serwer, port, poświadczenia) —
  **nowy sekret w projekcie**, analogicznie do `MES_TOKEN`
  (`zmiany/token-mes.md`: zmienna środowiskowa, nie plik w repo). Do
  ustalenia: czyj serwer SMTP (firmowy? zewnętrzny jak SendGrid?), lista
  odbiorców (per reguła alarmu czy globalna), czy musi być niezawodne
  (kolejka/retry) czy „best effort" wystarczy dla powiadomień
  diagnostycznych.
- **MES, moduł FAP:** dzisiejsza integracja MES jest **wyłącznie
  przychodząca** — to byłby **pierwszy kierunek wychodzący** (nasz serwer
  woła MES, nie odwrotnie). **Nie da się tego zaprojektować bez kontraktu
  API modułu FAP** — adres endpointu, metoda uwierzytelnienia, format
  payloadu incydentu. Pytanie do systemu MES/integratora, nie coś, co mogę
  założyć.

## Ekran (dopiero po ustaleniu punktów 1-4)

Robocza nazwa `/analiza-osi` (albo `/zuzycie`), rola co najmniej
`technolog` do podglądu, `admin` do definiowania progów alarmowych — wzorem
`/smart` + `/sila`. Zawartość: bieżący okres (godzina/zmiana/tydzień) per
oś i per narzędzie, trend, lista zdefiniowanych alarmów i ich status,
historia wysłanych powiadomień (żeby dało się sprawdzić, czy alarm
faktycznie poszedł).

## Proponowana kolejność (jeśli się zgadzasz z podziałem wyżej)

1. Ustalić metrykę (punkt 1) i minimalny format trwałego zapisu
   (punkt 2) — fundament, reszta na nim stoi.
2. Zbieranie i zapis danych po cyklu (bez alarmów, bez ekranu) — samo
   dopisywanie zdarzeń do pliku, żeby dane zaczęły się gromadzić jak
   najwcześniej (im szybciej zaczniemy zbierać, tym szybciej będzie co
   pokazać na „długoterminowej" analizie).
3. Ekran z samym podglądem (bez alarmów/powiadomień) — już przydatny sam
   w sobie.
4. Definicje alarmów + e-mail (prostszy kanał, nie wymaga kontraktu
   z MES).
5. Powiadomienia do MES/FAP — dopiero po ustaleniu kontraktu API z
   systemem MES.
