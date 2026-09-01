# Wznowienie po alarmie bez ponownego bazowania

Zgłoszone przy maszynie 2026-09-01, po pierwszym pełnym teście cyklu na
sprzęcie: operator zatrzymał program przyciskiem STOP (zacięcie materiału),
skasował alarm — i maszyna zażądała pełnego ponownego bazowania, mimo że
przez cały czas „wiedziała", gdzie stoją osie. Wymuszanie bazowania po
każdym zwykłym zatrzymaniu **angażuje niepotrzebnie utrzymanie ruchu** —
operator, który widzi zacięty detal, chce go wyjąć i pojechać JEDŹ DO ZERA
albo ruchem ręcznym, nie przechodzić całej procedury bazowania od zera.

**Ustalenie kluczowe dla bezpieczeństwa tej zmiany** (potwierdzone przez
operatora 2026-09-01): na tej maszynie Global Stop / E-stop to sygnał
logiczny do sterownika, **nie odcięcie zasilania serw** — enkodery cały czas
śledzą pozycję, także w trakcie zadziałania zabezpieczenia. Bez tego
ustalenia ta zmiana byłaby nieuzasadniona: gdyby E-stop odcinał zasilanie,
pozycja po jego zadziałaniu byłaby niepewna i wymuszone bazowanie miałoby
sens.

## Mechanizm

`RESET` dotąd **zawsze** ustawiał `NOT_HOMED`, niezależnie od przyczyny
alarmu — nie odróżniał „mostek dopiero wystartował, pozycja nieznana" od
„maszyna była zbazowana, zwykłe zatrzymanie, pozycja z enkodera dalej
wiarygodna". Nowy mechanizm: flaga `everHomed` (mostek) / `_ever_homed`
(symulator), ustawiana raz na `true` po pierwszym udanym bazowaniu w danej
sesji (procesu mostka / instancji symulatora), nigdy nie kasowana przez
alarm ani RESET. `RESET` sprawdza tę flagę:

- **`everHomed == true`** → `RESET` wraca do `READY` (nie `NOT_HOMED`).
  Ustawia dodatkowo `resumedWithoutHoming = true`.
- **`everHomed == false`** → jak dotychczas: `NOT_HOMED`.

`resumedWithoutHoming` gaśnie dopiero przy **kolejnym udanym bazowaniu** —
nie przy samym odczycie, nie automatycznie po czasie. To ma być widoczne,
dopóki ktoś świadomie nie zbazuje ponownie albo nie uzna sytuacji za
rozstrzygniętą.

**Ruch ręczny (JOG) nie wymagał ponownego bazowania już wcześniej** —
blokuje go wyłącznie stan `ALARM` w mostku (`if (state == State::ALARM)
return "ERR..."`), nie `NOT_HOMED`. Ta zmiana nie dodaje więc nowej
zdolności ruchu, której nie było — rozszerza to samo zaufanie do pozycji
enkodera, które JOG już miał, na `go_to_zero()` (wymaga `READY`, więc
wcześniej był blokowany po RESET-cie do `NOT_HOMED`, teraz działa od razu)
i na wyświetlany stan (`READY` zamiast mylącego `NOT_HOMED` na maszynie,
która realnie zna swoją pozycję).

## Ostrzeżenie dla operatora — nie ciche pominięcie kroku

Pominięcie wymuszonego bazowania **nie zwalnia z obejrzenia maszyny**.
Panel operatora pokazuje żółty komunikat, dopóki `resumed_without_homing`
jest `true`:

> Uwaga: wznowiono po zatrzymaniu BEZ ponownego bazowania — pozycja
> pochodzi z ostatniego bazowania. Obejrzyj maszynę (np. czy materiał się
> nie zaciął), zanim użyjesz JEDŹ DO ZERA albo ruchu ręcznego. Zbazuj
> ponownie, jeśli masz jakiekolwiek wątpliwości co do pozycji osi.

To świadomie **wygoda i wskazówka, nie zabezpieczenie** — jak ukrywanie
odnośników w nagłówku dla nieuprawnionych ról. Nic w kodzie nie weryfikuje,
że operator faktycznie spojrzał na maszynę; decyzję i odpowiedzialność
zostawiamy jemu, dając mu tylko informację, że powinien to zrobić.

## Pliki

- `bridge/sc4hub_bridge.cpp` — `everHomed`, `resumedWithoutHoming` (globalne
  flagi stanu); `doHome()` ustawia `everHomed=true` i gasi
  `resumedWithoutHoming`; `RESET` sprawdza `everHomed`; `statusLine()`
  dopisuje pole `RESUMED=0|1`.
- `server/app/machine.py` — `MachineStatus.resumed_without_homing` (i w
  `to_dict()`); `SimulatedMachine._ever_homed`, analogiczna logika w
  `_do_home()` i `reset()` — zamierzone lustro mostka, nie przypadkowa
  zbieżność, żeby dało się to przetestować bez sprzętu;
  `SC4HubMachine.poll_status()` parsuje `RESUMED`.
- `server/app/static/index.html`, `app.js` — żółty baner ostrzegawczy
  (`#resumed-warn`, klasa `.msg.warn`), widoczny dopóki flaga jest `true`.
- `server/tests/test_homing.py` — trzy testy symulatora: wznowienie do
  READY z ostrzeżeniem po wcześniejszym bazowaniu, wymuszony NOT_HOMED bez
  wcześniejszego bazowania, zgaszenie ostrzeżenia po kolejnym bazowaniu.
- `server/tests/test_sc4hub.py` — parsowanie `RESUMED=1` i brak pola
  (kompatybilność ze starszym mostkiem, które go nie wysyła).

## Uwagi

- **`go_to_zero()` nie wymagał żadnej zmiany kodu**, żeby zacząć działać po
  takim wznowieniu — jego warunek to `state == READY`, a RESET po
  zbazowanej maszynie teraz właśnie do READY wraca. Efekt uboczny dobrego
  odseparowania warstw (stan maszyny vs. logika operacji).
- **Świadomie nie rozróżniamy przyczyny alarmu** (STOP, limit momentu,
  utrata zezwolenia, błąd sFoundation) — wszystkie traktowane jednakowo,
  bo ustalenie o Global Stop (sygnał logiczny, nie odcięcie zasilania)
  dotyczy wszystkich jednakowo na tym sprzęcie. Gdyby się okazało, że
  jakiś rodzaj alarmu jednak wiąże się z realną utratą zasilania serw
  (np. fizyczny E-stop maszyny, inny niż Global Stop na huba — patrz
  otwarty punkt w `kanban.md` o nieprzetestowanym zachowaniu prawdziwego
  E-stopu), tę jednolitość trzeba będzie zrewidować.
- **Fizycznie niezweryfikowane w pełni** — wdrożone i przetestowane w
  symulatorze; do potwierdzenia przy maszynie: czy po zwykłym STOP-ie i
  RESET-cie panel faktycznie pokazuje `READY` z żółtym ostrzeżeniem
  zamiast `NOT_HOMED`, i czy JEDŹ DO ZERA rusza bez błędu w tym stanie.
