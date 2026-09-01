# Instrukcja obsługi — uruchomienie, programowanie i praca na maszynie

Ten dokument opisuje, jak **korzystać** z panelu maszyny (nie jak jest
zbudowany od środka — do tego służy [`ARCHITEKTURA.md`](ARCHITEKTURA.md) i
reszta `docs/`). Adresowany do trzech ról: kto ustawia maszynę (admin), kto
programuje detale (technolog) i kto na co dzień uruchamia produkcję
(operator).

## 0. Role i dostęp — zanim zaczniesz

Panel ma trzy role, **narastające** (wyższa rola może wszystko, co niższa):

| Ekran | operator | technolog | admin |
|---|:-:|:-:|:-:|
| Panel operatora `/` | ✓ | ✓ | ✓ |
| Edytor technologa `/editor` | | ✓ | ✓ |
| Konfiguracja osi `/axes` | | | ✓ |
| Bazowanie `/homing` | | | ✓ |
| Profile parametrów `/profiles` | | | ✓ |
| Cykl maszyny `/cycle` | | | ✓ |
| Funkcje SMART `/smart` | | | ✓ |
| Kontrola siły `/sila` | | | ✓ |
| Diagnostyka `/diagnostics` | | | ✓ |

**Dopóki nie założono żadnego konta, logowanie jest wyłączone i wszystkie
ekrany są dostępne bez hasła** — to celowe, żeby aktualizacja serwera nie
zablokowała nagle maszyny, która wcześniej działała bez logowania. Jeśli na
Twojej instalacji nikt się nie loguje, ten podział ról jeszcze nie
obowiązuje i każdy ma dostęp do wszystkiego opisanego niżej.

Zakładanie kont — z terminala na maszynie, nie z panelu (świadomie: przejęta
sesja admina nie może sama sobie podnieść uprawnień):

```bash
tools/konta.py lista
tools/konta.py dodaj zbyszek --rola admin --imie "Zbigniew Walukiewicz"
tools/konta.py dodaj ania    --rola technolog --imie "Anna Nowak"
tools/konta.py dodaj oper1   --rola operator --imie "Zmiana A"
tools/konta.py haslo zbyszek
tools/konta.py rola ania admin
tools/konta.py usun oper1
```

Hasło narzędzie zawsze pyta interaktywnie (nigdy z argumentu — trafiłoby do
historii powłoki). **Pierwsze `dodaj` włącza logowanie na całym panelu** —
zrób to przy maszynie. Zmiana hasła/roli/usunięcie konta wymaga restartu
usługi (`sudo systemctl restart motion-controller-lens.service`), żeby się
załadowała. Nie da się usunąć ostatniego konta narzędziem (wyłączyłoby to
logowanie po cichu) — trzeba by ręcznie usunąć plik `config/users.json`.

**Ważne zastrzeżenie, którego nie zmiękczam:** logowanie **nie jest
funkcją bezpieczeństwa maszyny** — ogranicza tylko dostęp do ekranów.
Zatrzymanie awaryjne realizuje wyłącznie sprzętowy obwód (E-stop, Global
Stop na SC4-Hub), niezależnie od tego, kto jest zalogowany.

## 1. Uruchomienie maszyny — krok po kroku

Poniższe robi **admin**, zwykle raz dziennie na początku pracy (kroki
1–3) i sporadycznie przy zmianie konfiguracji (4–6).

1. **Sprawdź sygnał zezwolenia.** Na panelu operatora (`/`) kropka przy
   napisie „sygnał zezwolenia" musi być zielona/aktywna. Czerwona/„BRAK" —
   sprawdź E-stop i Global Stop na SC4-Hub, zanim pójdziesz dalej. Od
   niedawna panel to też **wymusza jako alarm**, nie tylko cichy status —
   jeśli utracisz zezwolenie, dostaniesz czerwony komunikat wymagający
   „Kasuj alarm" po przywróceniu sygnału.
2. **Zbazuj maszynę.** Przycisk **Bazowanie** na panelu operatora (albo
   ikona ⌂ na środku strzałek JOG). Musisz to zrobić po każdym restarcie
   mostka (`motion-controller-bridge.service`) — status maszyny pokaże
   wtedy `NOT_HOMED`. Jeśli maszyna była już zbazowana i tylko wystąpił
   zwykły alarm (STOP, zacięcie materiału), **RESET wraca od razu do
   gotowości bez ponownego bazowania** — zobaczysz za to żółte
   ostrzeżenie „obejrzyj maszynę" (patrz rozdział dla operatora, punkt o
   alarmach).
3. **Sprawdź `/diagnostics`.** Jeden rzut oka: stan maszyny, tryb pracy,
   ostrzeżenia konfiguracji, konta i sesje, dziennik ostatnich zmian. Ekran
   świadomie pokazuje też, czego **nie ma** (np. sygnał drzwi) — to nie
   błąd wyświetlania, tylko uczciwy stan projektu.
4. **`/axes` — konfiguracja osi.** Sprawdź raz na jakiś czas (rzadko się
   zmienia): długość osi, punkt bazowania, limity programowe, przełożenie
   mm/obrót. To są **twarde granice ruchu** sprawdzane po stronie serwera
   przy każdym programie i ruchu ręcznym.
5. **`/homing` — konfiguracja bazowania.** Dla każdej osi: **Kolejność**
   (który numer bazuje się razem/po kolei; 0 = ta oś się nie bazuje),
   **Sposób** — „HardStop — dojazd do oporu" albo „programowe — zerowanie
   pozycji" (to drugie zeruje licznik tam, gdzie oś akurat stoi — bez
   fizycznego punktu odniesienia), limit momentu i offset (dziś tylko
   dokumentacja tego, co ustawić w ClearView), prędkość dojazdu.
6. **`/profiles` — limity siły i prędkości.** Trzy profile: **Globalny**
   (wartość domyślna maszyny), **Cykl maszyny**, **Program technologa**.
   Dla każdej osi: Vmax [mm/min], przyspieszenie, hamowanie, **Moment [%]**
   — to jest realny, sprzętowy limit siły (`TrqGlobal`), jedyne prawdziwe
   zabezpieczenie poza E-stopem. **Zacznij od niskiej wartości i podnoś
   stopniowo** — patrz rozdział 2 o testach siły. Przycisk **Aktywuj** przy
   profilu przełącza, który jest bieżący („globalny" obowiązuje poza
   cyklem/programem).
7. Gotowe do pracy — albo wybierz zlecenie z MES/ręcznie na panelu
   operatora, albo przejdź do testów siły (rozdział 2), albo oddaj maszynę
   technologowi/operatorowi.

## 2. Testy siły z konkretnym produktem (ekran `/sila`, admin)

Cel: dobrać limit momentu i progi funkcji SMART **dla konkretnego materiału
i detalu**, na podstawie pomiaru, a nie zgadywania. Procent momentu **nie
jest siłą w niutonach** — dopiero para zmierzona siłomierzem daje
przelicznik prawdziwy dla tej maszyny.

1. **Zacznij nisko.** W `/profiles` ustaw tymczasowo niski limit momentu
   (np. 5–10%) na profilu, którego będziesz używać do testu. Niski limit
   przy zderzeniu z oporem **zatrzymuje ruch** (potwierdzone fizycznie na
   tej maszynie) zamiast wbijać narzędzie z pełną siłą.
2. **Zamontuj próbkę/odpad** — nigdy dobry detal jako pierwszy test.
3. Otwórz `/sila`. Sekcja **„Obciążenie osi — na żywo"** pokazuje bieżący
   moment X/Y/Z w procentach, ze źródłem danych (pomiar ze sterownika albo,
   w symulatorze, wprost oznaczona „SYMULACJA" — nigdy nie kalibruj na
   wartościach symulowanych).
4. **Kalibracja ręczna:** dociśnij narzędzie do siłomierza ręcznie (JOG na
   panelu operatora, mały krok — 0.1 albo 1 mm), odczytaj moment z ekranu
   `/sila`, zmierz realną siłę siłomierzem, wpisz parę **(moment %, siła N)**
   w sekcji kalibracji dla danej osi (opcjonalnie kierunek i uwagi). Kilka
   par w różnych punktach daje przelicznik — dane zapisują się od razu.
5. **Uruchom faktyczny program albo cykl na próbce** i po zakończeniu
   (albo w trakcie) obejrzyj sekcję **„Przebieg ostatniego uruchomienia"**:
   dwa wykresy (moment %, prędkość mm/min) w czasie, z pionowymi liniami na
   granicach operacji/kroków, plus tabela ze średnim i maksymalnym momentem
   **dla każdej operacji osobno**. To pozwala zobaczyć, czy konkretny krok
   ociera się o ustawiony limit, bez próby złapania tego na żywo (dzieje
   się za szybko, żeby ocenić z samych liczb).
6. **Dostrajaj iteracyjnie**: podnieś limit w `/profiles` o niewielki krok,
   powtórz przebieg, sprawdź wykres — aż moment potrzebny do cięcia mieści
   się wygodnie poniżej limitu, ale limit dalej jest niski na tyle, żeby
   realnie chronić narzędzie i materiał.
7. Jeśli używasz funkcji SMART (`/smart`) — próg siły w definicji
   (`sila_pct` i pokrewne parametry procedury `ciecie_adaptacyjne`) dobieraj
   dopiero **po** ustaleniu sensownego zakresu momentu z punktów 4–6, na tej
   samej próbce.

**Ryzyka, których nie zmiękczam:**
- Kalibracja i wykres to **pomoc przy dobieraniu**, nie funkcja
  bezpieczeństwa. Jedynym realnym zabezpieczeniem pozostaje limit momentu
  w serwie i sprzętowy E-stop/Global Stop.
- **Rozdzielczość wykresu to 200 ms** — bardzo krótki krok (SMART, szybkie
  operacje) może mieć tylko kilka punktów. Traktuj to jako orientacyjny
  obraz, nie precyzyjny rejestrator.
- **Znany, niedomknięty problem:** bardzo niskie limity momentu (rzędu
  5–8%) w połączeniu z realnym cięciem w materiale potrafiły powodować
  odrzucenie ruchu przez serwo („Move blocked by drive shutdown/disable/
  limit") wymagające `Kasuj alarm`, czasem powtarzające się. Jeśli to
  spotka Cię podczas testu — spróbuj nieco wyższego limitu i sprawdź, czy
  problem znika (patrz `docs/zmiany/reset-nie-czyscil-axisenabled.md`).
- Nagranie przebiegu żyje tylko w pamięci procesu — restart usługi je
  kasuje. To narzędzie do bieżącej analizy, nie archiwum.

## 3. Rozdział dla technologa

Rola technologa: **przygotowanie programów detali**. Nie obejmuje
ustawiania limitów siły/osi/cyklu ani definicji SMART od zera (to
administracja) — technolog **wybiera** gotową definicję SMART z listy, nie
tworzy jej parametrów bezpieczeństwa samodzielnie.

### 3.1 Tworzenie i edycja programu (`/editor`)

- Lewy panel: lista istniejących programów (numer + nazwa) — kliknij, żeby
  otworzyć. Nowy program: pole „nowy numer (12 cyfr)" + przycisk **Nowy**.
  Numer to 12-cyfrowy numer NC, plik na dysku to `NUMER.prg`.
- Nagłówek programu: Nazwa, Materiał, Autor, Obroty frezu [obr/min], Posuw
  roboczy [mm/min], Posuw dojazdu [mm/min], Z bezpieczne [mm] (wysokość, na
  którą narzędzie wraca między operacjami).
- Tabela operacji, kolumny: LP, Operacja, X, Y, Z, X2, Y2, Posuw, Obroty,
  **Moment**, Przejścia, Przyrost, **SMART**, Uwagi. Pola aktywne/nieaktywne
  zależnie od wybranej operacji — edytor sam pokazuje tylko to, co ma
  znaczenie dla danego typu.
- **+ Dodaj operację** dodaje wiersz; strzałki ↑↓ zmieniają kolejność, ✕
  usuwa wiersz.
- **💾 Zapisz program** zapisuje na dysk; **⬇ Pobierz plik** ściąga surowy
  `.prg`; **📄 Zapisz jako** (pole „nowa nazwa" + przycisk) kopiuje bieżącą
  zawartość pod nowym numerem — oryginał zostaje bez zmian, wygodne do
  wariantów „ten sam nóż, inny wlewek".
- Podgląd toru rysuje się na bieżąco obok tabeli — sprawdzaj go, zanim
  odpalisz program na maszynie.

### 3.2 Operacje i format `.prg` (format 5)

Nagłówek kolumn pliku:

```
LP;OPERACJA;X;Y;Z;X2;Y2;POSUW;OBROTY;MOMENT;PRZEJSCIA;PRZYROST;SMART;UWAGI
```

Które kolumny mają znaczenie dla danego typu operacji:

| Operacja | Wymagane kolumny | Do czego służy |
|---|---|---|
| `PUNKT` | X, Y, Z | Pojedynczy punkt — dojazd i zagłębienie |
| `LINIA` | X, Y, Z, X2, Y2 | Cięcie po odcinku od (X,Y) do (X2,Y2) |
| `PROSTOKAT` | X, Y, Z, X2, Y2 | Cięcie po obrysie prostokąta |
| `SZYBKI` | X, Y | Szybki dojazd bez zagłębiania |
| `WRZECIONO` | OBROTY | Włącz (obroty>0) albo wyłącz (0) wrzeciono |
| `PAUZA` | — | Zatrzymanie do ręcznego wznowienia (START) |
| `SMART` | SMART (nazwa definicji) | Ruch z kontrolą siły z bieżącej pozycji |

Dodatkowe zasady (pilnowane przy zapisie, z komunikatem wskazującym
numer linii): **MOMENT** (limit siły tylko dla tej operacji, w %) wolno
ustawić jedynie przy `PUNKT`/`LINIA`/`PROSTOKAT`; **PRZEJSCIA**
(liczba przejść na głębokość) i **PRZYROST** (przyrost na przejście) są
wzajemne wykluczające się i też tylko dla tych trzech operacji; kolumnę
**SMART** wolno wypełnić wyłącznie w wierszu typu `SMART`.

Przykłady:

```
5;PUNKT;12.500;30.000;-1.50;;;;;40;;;;wlewek z limitem momentu 40%
6;PUNKT;25.000;15.000;-1.00;;;;;;;;SMART-sila;odcinanie z kontrolą siły
```

(Wiersz `SMART` nie potrzebuje X/Y/Z — rusza z pozycji, w której narzędzie
akurat stoi po poprzedniej operacji; dlatego w edytorze zawsze najpierw
`PUNKT` nad wlewkiem, potem `SMART`.)

### 3.3 Funkcje SMART — wybór, nie tworzenie parametrów bezpieczeństwa

Ekran `/smart` jest dla admina, ale **wybór** gotowej definicji SMART w
kolumnie programu — to zadanie technologa. Jedyna dziś dostępna procedura
to **„Cięcie adaptacyjne"** (`ciecie_adaptacyjne`) z parametrami: oś ruchu,
próg siły [%], dojazd [mm], cofnięcie [mm], prędkość szybka/wolna
[mm/min], progi zwolnienia/przyspieszenia (jako ułamek progu siły),
współczynnik kolizji, okres próbkowania [ms]. Jeśli potrzebujesz nowej
definicji albo zmiany progów — to rozmowa z adminem, najlepiej po teście
opisanym w rozdziale 2.

### 3.4 Testowanie własnej pracy

Po zapisaniu programu przetestuj go na panelu operatora (`/`) — technolog
ma tam dostęp tak jak operator: wybierz zlecenie/program, JOG do
bezpiecznej pozycji, START na próbce. Obejrzyj tor na ekranie edytora
jeszcze przed pierwszym uruchomieniem na sprzęcie.

## 4. Rozdział dla operatora

### 4.1 Panel operatora — co widzisz i czym sterujesz

- **Stan maszyny**: kolorowy pasek (`READY`, `RUNNING`, `ALARM`...),
  kropka + tekst sygnału zezwolenia, czerwony komunikat `ALARM: ...` gdy
  coś przerwało pracę, żółty komunikat „wznowiono BEZ ponownego
  bazowania" po nietypowym RESET-cie (patrz 4.3).
- **Zlecenie / program**: co aktualnie wybrane (z MES albo ręcznie —
  pole na 12-cyfrowy numer + przycisk **Wybierz**).
- **Pozycja osi [mm]** X/Y/Z, stan wrzeciona, wyjścia cyfrowe, **obciążenie
  osi [% momentu]** z opisem źródła danych.
- **Podgląd pozycji** — rysunek toru, aktualna pozycja narzędzia.
- **Sterowanie**: **START**/**STOP** (duże przyciski), **Bazowanie**,
  **Kasuj alarm**, **JEDŹ DO ZERA**, checkbox „Wrzeciono rusza razem z
  maszyną (START)".
- **Ruch ręczny (JOG)** — „martwy człowiek": **przytrzymaj** przycisk
  osi (Y+/X−/X+/Y−/Z+/Z−), ruch trwa dopóki trzymasz, puszczenie
  zatrzymuje. Środkowy przycisk ⌂ to bazowanie wszystkich osi. Wybierz
  krok z listy: 0.1 / 1 / 5 / 10 mm.
- **Luzowanie osi** — przyciski X/Y/Z/WSZYSTKIE: zdejmuje moment z osi, żeby
  dało się nią ruszyć ręcznie (np. przy zacięciu). **Uwaga:** zluzowana oś
  nie stawia oporu — oś pionowa bez hamulca opadnie pod własnym ciężarem.
  Zaciśnij ją z powrotem tym samym przyciskiem, zanim odejdziesz od maszyny.
- **Tabela operacji programu** — podświetla aktualnie wykonywaną i już
  zrobione operacje.

### 4.2 Typowy dzień pracy

1. Sprawdź sygnał zezwolenia (zielony).
2. **Bazowanie**, jeśli maszyna pokazuje `NOT_HOMED` (np. po restarcie
   usługi mostka).
3. Wybierz zlecenie (z MES albo ręcznie numer programu).
4. **START**. Obserwuj tor i obciążenie osi.
5. **STOP** natychmiast, jeśli coś wygląda źle — nie czekaj, aż samo się
   zatrzyma.

### 4.3 Co robić przy alarmie — bez wzywania utrzymania ruchu za każdym razem

1. Przeczytaj czerwony komunikat `ALARM: ...` — mówi, co się stało (STOP,
   limit momentu, utrata sygnału zezwolenia, błąd sterownika).
2. **Obejrzyj maszynę wzrokowo** — czy materiał się nie zaciął, czy nic nie
   koliduje z narzędziem. To krok, którego żaden przycisk nie zrobi za
   Ciebie.
3. Kliknij **Kasuj alarm**.
   - Jeśli maszyna była już wcześniej zbazowana w tej sesji mostka, RESET
     wraca od razu do gotowości (`READY`) — **nie musisz bazować ponownie**.
     Zobaczysz za to żółte ostrzeżenie „wznowiono BEZ ponownego bazowania —
     obejrzyj maszynę" — to przypomnienie, nie blokada. Znika dopiero po
     kolejnym pełnym bazowaniu.
   - Jeśli maszyna nigdy nie była bazowana w tej sesji (np. świeżo po
     restarcie usługi) — RESET zostawi ją w `NOT_HOMED`, zbazuj normalnie.
4. Teraz możesz: **JEDŹ DO ZERA** (dojazd pozycyjny do punktu zerowego —
   działa, bo maszyna dalej „wie", gdzie stoi) albo **JOG** ręcznie, żeby
   odsunąć narzędzie od przeszkody, bez pełnej procedury bazowania.
   - **Uwaga na JEDŹ DO ZERA:** nie podnosi osi Z przed ruchem w płaszczyźnie
     XY — jedzie dokładnie w kolejności ustawionej na `/homing`. Jeśli
     narzędzie stoi nisko nad detalem/oprzyrządowaniem, rozważ ręczny JOG-iem
     odjazd Z do góry, zanim użyjesz tego przycisku.
5. Wznów pracę (**START**) dopiero, gdy jesteś pewien, że przyczyna alarmu
   jest usunięta.

**Kiedy naprawdę wzywać kogoś z uprawnieniami admina:** ten sam alarm
powtarza się w tym samym miejscu mimo kilku prób Kasuj alarm + bazowania;
sygnał zezwolenia nie wraca mimo sprawdzenia E-stopu; cokolwiek wygląda
mechanicznie nietypowo (dźwięk, zapach, widoczne uszkodzenie).

### 4.4 Czego operator nie robi

Zmiana profili siły/prędkości, konfiguracji osi, definicji SMART, cyklu
maszyny — to ekrany dostępne tylko dla admina, celowo. Jeśli uważasz, że
limit trzeba zmienić, zgłoś to zamiast próbować obejść przez inny ekran.

## Gdzie szukać więcej

- [`docs/README.md`](README.md) — pełny indeks dokumentacji projektu.
- [`docs/funkcje-smart.md`](funkcje-smart.md) — pełny opis funkcji SMART,
  model i ryzyka.
- [`docs/zmiany/`](zmiany/) — historia zmian, jedna po drugiej, z
  uzasadnieniem i uwagami które nie zostały tu powtórzone.
