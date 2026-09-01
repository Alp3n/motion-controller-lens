# Limit momentu do sprzętu (etap 2b tematu B)

Limit momentu aktywnego profilu (globalny/cykl/program, `server/app/profiles.py`)
dociera teraz do serw jako `ILimits.TrqGlobal` — twardy sufit w samym
sterowniku, jedyne realne zabezpieczenie (pętla programowa funkcji SMART
tylko dopracowuje zachowanie wewnątrz tego limitu, nigdy go nie zastępuje).
Wcześniej wartość była tylko przechowywana po stronie serwera — na sprzęcie
nic nie ograniczała (`docs/zmiany/profile-parametrow-etap2.md`).

**Stan (2026-09-01): WDROŻONE, dociera do sprzętu, i fizycznie potwierdzone,
że działa.** Mostek przyjmuje komendę i loguje przyjętą wartość
(`journalctl -u motion-controller-bridge.service | grep "limit momentu"`).
Pierwsza próba (5% przy realnie obowiązującym 20% — patrz „Pułapka" niżej)
niczego nie potwierdzała ani nie obalała. **Druga, poprawna próba (limit 8%,
JOG w opór) zatrzymała ruch** — maszyna „poczuła" opór i stanęła. `TrqGlobal`
realnie ogranicza siłę na tej maszynie.

### Efekt uboczny potwierdzony i naprawiony: mylący komunikat alarmu

Zatrzymanie przez limit momentu **nie zgłasza się jako odrębny alarm
„przekroczono moment"** — obiekt zgłasza `ALARM: przekroczono czas ruchu`.
Mechanizm (`waitMoves()` w `sc4hub_bridge.cpp`): ruch, który nie może się
dokończyć, bo oś jest ograniczona momentem, po prostu nigdy nie osiąga
`MoveIsDone()` — po czasie `szacowany_czas × 1,5 + 3000 ms` mostek uznaje to
za timeout, nie za limit momentu wprost.

**Naprawione (2026-09-01):** dopisano sprawdzenie
`CPMstatus::HadTorqueSaturation()` (bit `TrqSat` w rejestrze ostrzeżeń SDK,
`pubCpmRegs.h`) — opis w nagłówku wprost wymienia „misapplication of any
torque limiters such as the Global Torque Limit" jako przyczynę. Gdy
`waitMoves()` łapie timeout, sprawdza ten bit dla zaangażowanych osi; jeśli
prawda, komunikat alarmu brzmi: „przekroczono czas ruchu — oś osiągnęła
limit momentu (TrqGlobal) i nie mogła dokończyć ruchu" zamiast gołego
„przekroczono czas ruchu". Skompilowane, wdrożone. **Nie zweryfikowane
jeszcze fizycznie** — do potwierdzenia przy następnym teście z niskim
limitem, czy nowy tekst faktycznie się pojawia.

## ⚠️ Pułapka przy teście fizycznym: skąd operator wie, jaki limit NAPRAWDĘ obowiązuje

`_push_profile_limits()` wysyła `TRQLIMIT` przy **każdej** zmianie aktywnego
profilu i przy każdym reconnect z mostkiem — i wysyła wartość **zapisaną w
`config/profiles.json` dla aktywnego profilu**, nie żadną wartość ustawioną
gdzie indziej. Konsekwencje, potwierdzone podczas testu 2026-09-01:

- Jeśli ktoś ustawi `TrqGlobal` bezpośrednio w ClearView (z pominięciem
  naszego panelu), serwer **cicho to nadpisze** przy najbliższej okazji
  (przełączenie profilu, restart usługi, utrata i odzyskanie połączenia
  z mostkiem) — z powrotem na wartość z pliku.
- Kilka szybkich zapisów pod rząd w ekranie `/profiles` (np. eksperymentalne
  poprawki: 5% → zapis → 10% → zapis → 20% → zapis) zostawia **tylko
  ostatnią** wartość jako realnie obowiązującą — mostek loguje `oś X: limit
  momentu 5.0%`, chwilę później `10.0%`, potem `20.0%`, i to ta ostatnia się
  liczy. Log mostka jest jedynym pewnym źródłem prawdy o tym, co **teraz**
  obowiązuje — nie pamięć operatora o tym, co wpisał kilka minut wcześniej.

**Przed testem fizycznym zawsze sprawdź obowiązujący limit dwoma
niezależnymi źródłami:**

```bash
curl -s http://127.0.0.1:8000/api/profiles | python3 -m json.tool   # co serwer MA wysłać
journalctl -u motion-controller-bridge.service --no-pager | grep "limit momentu" | tail -5  # co mostek NAPRAWDĘ dostał
```

Obie liczby muszą się zgadzać z tym, co zamierzano testować, **zanim**
zacznie się JOG-ować w opór.

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

## Pliki (uzupełnienie 2026-09-01)

- `server/app/main.py` — `_profile_warnings()`: usunięte ostrzeżenie „limit
  momentu nie jest wysyłany do sprzętu" — było **nieaktualne i myliło
  operatora w trakcie testu fizycznego** (test opisany niżej). Diagnostyka
  (`/api/diagnostics`, sekcja `safety.brak`): usunięty ten sam nieaktualny
  wpis.
- `server/app/profiles.py` — docstring modułu poprawiony (nie odsyła już do
  nieistniejącego ograniczenia).
- `bridge/sc4hub_bridge.cpp` — `waitMoves()`: przy timeoucie ruchu sprawdza
  `nodeOf(a).Status.HadTorqueSaturation()` dla zaangażowanych osi; jeśli
  którakolwiek zgłasza saturację, komunikat alarmu nazywa przyczynę (limit
  momentu) zamiast gołego „przekroczono czas ruchu".

## Uwagi

- Oś bez wpisu w aktywnym profilu **nie dostaje żadnej komendy** — zostaje
  na ostatnio wysłanym limicie (albo na tym z ClearView, jeśli serwer nigdy
  nic nie wysłał), nie zeruje się i nie blokuje. Zgodne z tym, jak profile
  już traktują brakujące osie (`profile-parametrow-etap2.md`).
- **Błąd procesu, odnotowany żeby się nie powtórzył:** ostrzeżenie „limit
  momentu nie dociera do sprzętu" zostało świadomie zostawione w API po
  napisaniu kodu (2026-08-31), bo autor zmiany sądził, że kod jest
  niewdrożony. Kod **był już wdrożony** (deploy poszedł automatycznie przy
  najbliższym restarcie usługi), więc ostrzeżenie stało się nieaktualne
  bez żadnej notatki o tym w kodzie — i realnie zmyliło operatora podczas
  testu fizycznego limitu 2026-09-01. Wniosek: ostrzeżenie warunkowe na
  „to jeszcze niewdrożone" jest kruche, jeśli deployment może nastąpić bez
  wiedzy autora tekstu ostrzeżenia — bezpieczniej usuwać taki tekst od razu
  po napisaniu kodu, z komentarzem TODO przywracającym go do czasu
  faktycznego wdrożenia, niż zostawiać go „tymczasowo", licząc że ktoś
  wróci i zaktualizuje.
- Test fizyczny „czy `TrqGlobal` faktycznie zatrzymuje ruch" jest **w
  trakcie** (2026-09-01) — pierwsza próba nie sprawdziła tego, co miała,
  z powodu opisanego wyżej ("Pułapka przy teście fizycznym"). Wynik
  poprawnie powtórzonego testu: do uzupełnienia tutaj.
