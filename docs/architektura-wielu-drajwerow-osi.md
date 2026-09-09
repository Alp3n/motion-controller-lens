# Propozycja: architektura wielu sterowników (drajwerów) osi

Zgłoszenie użytkownika (2026-09-09): planowana oś czwarta na serwie
**Feetek, sterowanie PWM, 45 kg**, oraz w dalszej perspektywie moduł
**Teknic ClearCore** do silników krokowych i I/O. Cel: dodawać nowe typy
napędów bez przebudowy aplikacji. **To propozycja do przeczytania i
decyzji, nie gotowy kod** — podobnie jak
[`propozycja-head-tail-asymetria.md`](propozycja-head-tail-asymetria.md).

## Co dziś stoi na przeszkodzie

`Machine` (`server/app/machine.py`) to dziś **jedna klasa aktywna na raz**
(`SimulatedMachine` albo `SC4HubMachine`), obsługująca WSZYSTKIE osie
jednym protokołem/połączeniem (`jog`/`home`/`go_to_zero`/... na poziomie
całej maszyny, nie pojedynczej osi). X i Y są dodatkowo połączone sprzętowo
w jedną komendę `MOVEXY` — mostek nie rusza nimi osobno — ale to dotyczy
wyłącznie X/Y, nie osi dodatkowych.

Otwarty punkt z `kanban.md` (temat C): „rozszerzyć protokół mostka o
`AXCFG` i komendy ruchu dla osi spoza X/Y/Z" zakładał, że **każda** oś,
nawet dodatkowa, jedzie przez ten sam mostek SC4-Hub/Teknic. Ta propozycja
to zmienia: oś 4 (Feetek) w ogóle nie przechodzi przez mostek Teknica.

## Rekomendacja: driver per oś, nie driver per maszyna

Wspólny interfejs `AxisDriver` (`move_to`/`jog`/`home`/`read_status`, z
częścią pól/metod **opcjonalną** — patrz niżej) i osobna implementacja na
typ sprzętu: `TeknicSC4HubDriver` (dzisiejszy `SC4HubMachine`, nadal
obsługuje X/Y/Z razem, bo `MOVEXY` tego wymaga), `FeetekPwmDriver`,
`ClearCoreDriver`. `Machine` przestaje BYĆ jednym sterownikiem, zaczyna
SKŁADAĆ drivery po nazwie osi (`self.drivers: dict[str, AxisDriver]`,
z X/Y/Z wskazującymi na ten sam obiekt Teknica).

**Zalety:** X/Y/Z (krytyczne dla toru cięcia) zostają bez zmian na
sprawdzonym Teknicu; nowe osie faktycznie zaczynają się ruszać (dziś się
NIE ruszają — zapisują się tylko w konfiguracji, patrz `kanban.md` temat
C) bez czekania na rozszerzenie protokołu mostka (C++); dodanie kolejnego
typu napędu w przyszłości to nowa klasa driver + wpis w konfiguracji, nie
zmiana rdzenia aplikacji.

## Największy kompromis: możliwości sterowników są NIERÓWNE

To nie jest tylko kwestia różnych protokołów transportowych — to różne
**kategorie** sprzętu:

- **ClearPath-SC (dziś, X/Y/Z):** serwo z enkoderem, zamknięta pętla,
  odczyt momentu (`TrqMeasured`), limit momentu jako twardy sufit,
  faulty/alarmy zgłaszane przez sterownik.
- **Feetek PWM ("45 kg", typowe dla serw hobby/RC-style): do potwierdzenia
  u źródła, nie zakładam na pewno** — ale typowe serwo sterowane
  szerokością impulsu PWM to z perspektywy hosta pętla **otwarta**:
  wysyłasz docelową pozycję, serwo samo dojeżdża wewnętrznym
  potencjometrem/enkoderem, a host zwykle **nie dostaje z powrotem ani
  pozycji, ani momentu**. Jeśli się to potwierdzi, ta oś nie może
  uczestniczyć w niczym, co dziś zależy od odczytu momentu — limit siły,
  funkcje SMART (temat K), prowadzenie za rękę (`prowadzenie-za-reke.md`).
  Będzie to oś "głucha": wysyłasz cel, wierzysz, że dojechała.
- **ClearCore (kroki + I/O):** silniki krokowe to zwykle sterowanie w
  pętli otwartej **bez enkodera** (chyba że dokupiony osobno) — brak
  informacji zwrotnej o rzeczywistej pozycji, zgubienie kroków pod
  obciążeniem jest niewykrywalne przez oprogramowanie.

**Konsekwencja dla wspólnego interfejsu:** `AxisDriver` musi mieć
pola/metody **opcjonalne** (nie każdy driver wspiera odczyt momentu, nie
każdy wspiera limit siły), a ekrany muszą jawnie pokazywać operatorowi,
których funkcji dana oś **nie ma** — dokładnie jak dziś `/diagnostics`
świadomie pokazuje „czego nie ma" (drzwi, moment na sprzęcie), zamiast
fałszywie zielonych pól.

## Pytania do ustalenia, zanim zacznę kodować

1. Czy oś 4 (Feetek) i przyszłe osie ClearCore biorą udział w programie
   technologa/cyklu (`RUCH`/`PROGRAM`) na równi z X/Y/Z, czy są **osiami
   pomocniczymi** (podajnik, docisk) sterowanymi tylko z panelu/JOG i
   konfiguracji cyklu? To determinuje, ile logiki wykonawczej
   (`_run_program`, `_execute_cycle_step`) w ogóle musi wiedzieć o wielu
   driverach naraz.
2. Czy Feetek faktycznie nie daje żadnego feedbacku pozycji/momentu —
   proszę potwierdzić z dokumentacji konkretnego modelu/sterownika PWM,
   zanim to na stałe założę w kodzie (zasada weryfikacji faktów u źródła
   z `CLAUDE.md`). To zmienia zakres tego, co ta oś w ogóle może robić.
3. Jak fizycznie podłączony będzie Feetek do tego komputera — osobny
   mikrokontroler/moduł PWM po USB/UART (host wysyła komendę do niego,
   jak dziś do mostka Teknica), czy bezpośrednio z GPIO hosta? Determinuje,
   czy trzeba pisać drugi „mini-mostek" w stylu `bridge/`, czy driver
   rozmawia wprost.
4. ClearCore do steppera/IO — osobny fizyczny kontroler (Ethernet? USB?)
   obok istniejącego SC4-Hub, każdy ze swoim połączeniem? Trzeba potwierdzić
   model komunikacji, zanim zaprojektuję drugi `_command`/`_exchange`
   obok tego z `SC4HubMachine`.

## Co proponuję jako pierwszy krok

Nie kodować całości od razu. Zacząć od wydzielenia interfejsu `AxisDriver`
i przepisania DZISIEJSZEGO `SC4HubMachine` tak, żeby sam siebie widział
jako jeden driver obsługujący grupę X/Y/Z (zero zmiany zachowania, tylko
przełożenie istniejącego kodu pod nowy kształt) — to weryfikuje, że
abstrakcja się broni, zanim dojdzie drugi, zupełnie inny sprzęt. Dopiero
potem dopisać `FeetekPwmDriver` dla osi 4.
