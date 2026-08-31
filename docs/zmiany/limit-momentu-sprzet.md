# Limit momentu do sprzętu (etap 2b tematu B)

Limit momentu aktywnego profilu (globalny/cykl/program, `server/app/profiles.py`)
dociera teraz do serw jako `ILimits.TrqGlobal` — twardy sufit w samym
sterowniku, jedyne realne zabezpieczenie (pętla programowa funkcji SMART
tylko dopracowuje zachowanie wewnątrz tego limitu, nigdy go nie zastępuje).
Wcześniej wartość była tylko przechowywana po stronie serwera — na sprzęcie
nic nie ograniczała (`docs/zmiany/profile-parametrow-etap2.md`).

**Stan (2026-08-31): kod napisany po obu stronach i skompilowany osobno
(sprawdzone), ale NIEWDROŻONY na produkcji.** Ani Python, ani mostek nie
zostały zrestartowane z tym kodem — zrobione bez obecności przy maszynie,
świadomie odłożone do wspólnej weryfikacji.

## ⚠️ Kolejność wdrożenia — inaczej maszyna przestaje odpowiadać

**Python i mostek trzeba wdrożyć RAZEM, mostek pierwszy.** Strona serwera
wysyła komendę `TRQLIMIT` przy **każdym** poleceniu do mostka, jeśli profil
się zmienił (mechanizm `_profile_pending`, ten sam wzorzec co `_axes_pending`
dla `AXCFG`) — w tym przy zwykłym odpytaniu `STATUS` co 200 ms. Stary mostek
(bez tej zmiany) odpowie `ERR nieznana komenda: TRQLIMIT`, co
`SC4HubMachine._exchange()` zamienia w `MachineError` — **to zrywa każdą
kolejną komendę do sprzętu, łącznie z pollingiem statusu**, nie tylko limit
momentu.

Bezpieczna kolejność:
1. `make -C bridge` (mostek już się kompiluje, sprawdzone), zatrzymać
   `motion-controller-bridge.service`, podmienić binarkę, wystartować.
2. Dopiero potem `git pull` + restart `motion-controller-lens.service`.

Odwrotna kolejność (najpierw Python) zepsuje połączenie z mostkiem, dopóki
ten nie zostanie zaktualizowany.

## Pliki

- `bridge/sc4hub_bridge.cpp` — nowa komenda `TRQLIMIT <X/Y/Z> <procent>`,
  ustawia `nodeOf(a).Limits.TrqGlobal = pct` (jednostka PCT_MAX już ustawiona
  w etapie 0). Umieszczona przed bramką ALARM, jak `AXCFG` — to konfiguracja
  obowiązująca przy kolejnym ruchu, nie ruch sam w sobie.
- `server/app/machine.py` — `SC4HubMachine._profile_pending` (ten sam wzorzec
  co `_axes_pending`), `_push_profile_limits()`, wywoływane z `_command()`
  przy każdym poleceniu, gdy flaga jest ustawiona; `_set_profile()`
  nadpisane, żeby złapać zmianę profilu z obu ścieżek
  (`apply_profiles`/`set_active_profile`) w jednym miejscu.
- `server/tests/test_sc4hub.py` — cztery nowe testy z podstawionym
  `_exchange` (nie `_command` jak reszta pliku — to celowe, testuje się
  właśnie logikę `_command`, którą fake_command w innych testach pomija):
  wysyłka przy pierwszej komendzie, brak powtórki bez zmiany, ponowna
  wysyłka po zmianie profilu, pominięcie osi bez wpisu w profilu.

## Uwagi

- Kompilacja mostka sprawdzona osobno (`g++` do pliku tymczasowego, nie
  nadpisując działającej binarki) — składnia poprawna, linkuje się czysto.
  **Nie uruchomione na sprzęcie** — `TrqGlobal` nie zostało jeszcze
  zweryfikowane fizycznie (czy faktycznie ogranicza ruch przy przekroczeniu
  limitu). Do zrobienia przy maszynie: ustawić bardzo niski limit (np. 5%)
  na jednej osi, spróbować JOG-iem wjechać w przeszkodę i sprawdzić, czy
  serwo faktycznie się zatrzymuje, zanim się to zaufa jako zabezpieczenie.
- Oś bez wpisu w aktywnym profilu **nie dostaje żadnej komendy** — zostaje
  na ostatnio wysłanym limicie (albo na tym z ClearView, jeśli serwer nigdy
  nic nie wysłał), nie zeruje się i nie blokuje. Zgodne z tym, jak profile
  już traktują brakujące osie (`profile-parametrow-etap2.md`).
- `docs/zmiany/profile-parametrow-etap2.md` i ostrzeżenie w
  `main.py::_profile_warnings` mówiły dotąd wprost „limit momentu nie
  działa na sprzęcie" — to nieaktualne od tej zmiany, ale ostrzeżenie w
  API **zostawione bez zmian**, bo kod wciąż nie jest wdrożony: usunięcie
  go teraz zmyliłoby operatora, sugerując działanie, którego jeszcze nie ma
  na tej maszynie. Do aktualizacji dopiero po wdrożeniu obu stron.
