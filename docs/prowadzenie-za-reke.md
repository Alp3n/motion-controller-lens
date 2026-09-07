# Prowadzenie za rękę i baza nazwanych punktów PTP

Analiza wykonalności trybu "antygrawitacyjnego" (operator pcha oś ręką,
serwo płynnie podąża za pchnięciem) i decyzja o faktycznie zbudowanym
zakresie. Powiązane: [`mozliwosci-clearpath-sc.md`](mozliwosci-clearpath-sc.md),
[`sterownik-sc4-hub.md`](sterownik-sc4-hub.md), [`zmiany/luzowanie-osi.md`](zmiany/luzowanie-osi.md).

## Cel zgłoszony przez użytkownika (2026-09-06)

Operator chce fizycznie pchać oś w jednym z kierunków, maszyna ma to
"wyczuć" i wykonać ruch w tym kierunku (prawdziwy tryb podatny/compliant,
jak w cobocie, z regulowanym oporem). W trakcie takiego prowadzenia zapisuje
bieżącą pozycję jako nazwany punkt. Punkty mają trafić na listę z pełnym
CRUD (dodaj/edytuj/usuń) i być wybieralne z listy w operacji PUNKT programu
technologa.

## Wynik badania: prawdziwy tryb podatny jest NIEOSIĄGALNY na tym sprzęcie

Sprawdzone wyczerpująco w nagłówkach SDK
(`vendor/teknic/Linux_Software/sFoundation/inc/inc-pub/*.h`):

- Jedyne metody startu ruchu sterowalne z hosta to `MovePosnStart` (i warianty:
  `MovePosnHeadTailStart`, `MovePosnAsymStart`) oraz `MoveVelStart`
  (`pubCpmCls.h`, klasa `CPMmotion`/`IMotion`). **Brak jakiegokolwiek
  `MoveTrqStart`/trybu komendowania momentem** — przeszukanie całego
  katalogu `inc-pub` pod kątem `MoveTrq|TorqueMode|TrqMode|ForceMode` nie
  dało wyników.
- Moment istnieje w API wyłącznie jako **limit** (`ILimits.TrqGlobal`) i
  **odczyt** (`Motion.TrqMeasured`) — ogranicza ruch w Position Mode,
  nie zastępuje go trybem sterowania momentem.
- `TPIO_MODE_IN` (`pubIscRegs.h:2899,2915`, komentarz "Torque mode enable")
  to bit **statusowy/diagnostyczny** wewnątrz `tpIOreg` — rejestr wspólny
  dla całej rodziny ClearPath (w tym starszych MC/SD ze Step&Dir), czytający
  stan fizycznej linii sprzętowej, **nie** przełącznik trybu programowalny
  z poziomu SDK.
- `docs/sterownik-sc4-hub.md` potwierdza fakt architektoniczny: komunikacja
  z serwami serii SC idzie własnym protokołem szeregowym Teknica przez
  SC4-Hub/USB (sFoundation), nie przez Step&Dir — więc nawet mechanizmy
  trybu z rodziny Step&Dir/Analog nie mają tu zastosowania.
- Wcześniejsza, niezależna analiza projektu (`mozliwosci-clearpath-sc.md`,
  oparta na pełnym manualu ClearPath-SC rev. 1.45) dochodzi do tego samego
  wniosku: moment "zwykle ustawia się przez ClearView i nie zmienia w
  trakcie aplikacji" — żadna wzmianka o trybie momentu jako alternatywie
  dla Position Mode.

**Wniosek: nie da się zbudować serwa aktywnie "podążającego" za ręką
operatora (admittance/compliant control z hosta) na tym sprzęcie przez
sFoundation SDK.** To ograniczenie API/architektury drive'u, nie kwestia
nakładu pracy.

## Co jest dostępne i bezpieczne: RELEASE/HOLD

Jedyny istniejący mechanizm zdjęcia oporu to **RELEASE/HOLD**
(`zmiany/luzowanie-osi.md`) — całkowite zdjęcie momentu z serwa, oś
kręci się całkiem swobodnie. To NIE jest "podążanie" ani regulowany opór —
zero oporu, tyle. Enkoder liczy dalej, więc po ponownym HOLD nie trzeba
bazować.

**Ustalone z operatorem 2026-09-07: wszystkie trzy osie tej maszyny są
samohamowne** — nie opadają pod własnym ciężarem po zwolnieniu momentu
(mechaniczna cecha przekładni/śruby, niezależna od sterowania). To usuwa
ryzyko, które pierwotnie wykluczało oś Z z tej funkcji (obawa: oś pionowa
pod ciężarem wrzeciona/narzędzia mogłaby opaść po RELEASE). **W efekcie
RELEASE jest bezpieczne na X, Y i Z.**

## Zbudowany zakres

1. **Baza nazwanych punktów** (`server/app/punkty.py`, `config/punkty.json`,
   `/api/punkty`, ekran `/punkty`) — pełny CRUD (dodaj/edytuj/usuń/"zapisz
   jako"), ten sam wzorzec co definicje SMART (`app/smart.py`). Wiązanie
   punktu z operacją programu jest **jednorazowe** (decyzja 2026-09-06):
   wybór z listy w edytorze wypełnia pola X/Y/Z operacji PUNKT, a
   późniejsza zmiana punktu w bazie nie wpływa na już zapisane programy.
2. **Ekran `/nauczanie`** — przyciski "Zwolnij/Zaciśnij" dla X, Y, Z (używają
   istniejącego `/api/machine/release`, żadnej nowej komendy mostka), podgląd
   pozycji na żywo, pole nazwy + "Zapisz punkt" (czyta bieżącą pozycję,
   zapisuje do `/api/punkty`). Ekran jawnie tłumaczy operatorowi, że
   zwolnienie to pełne zdjęcie oporu, nie "pływanie" ani regulowany opór —
   żeby nie oczekiwał funkcji, której sprzęt nie oferuje.
3. **Picker w edytorze programu** (`editor.js`) — przy operacji PUNKT
   dodatkowy `<select>` z listą nazwanych punktów; wybór wypełnia X/Y/Z
   tego wiersza i wraca do stanu "— punkt —" (jednorazowe działanie, nie
   trwałe pole).

## Pliki

- `server/app/punkty.py` — model, walidacja, plik `config/punkty.json`.
- `server/app/config.py` — `PUNKTY_FILE`.
- `server/app/main.py` — `GET/PUT /api/punkty`, strony `/punkty` i `/nauczanie`.
- `server/app/static/punkty.html`, `punkty.js` — ekran CRUD listy punktów.
- `server/app/static/nauczanie.html`, `nauczanie.js` — ekran prowadzenia za rękę.
- `server/app/static/editor.js` — picker punktów w operacji PUNKT.
- Linki nawigacyjne dopisane w `index.html`, `smart.html`, `sila.html`,
  `cycle.html`, `editor.html`.
- `server/tests/test_punkty.py` — 13 testów (model, plik, API).

## Uwagi

- **Nie zweryfikowane jeszcze fizycznie** — ekran `/nauczanie` używa
  wyłącznie już sprawdzonego mechanizmu RELEASE/HOLD, więc ryzyko jest
  niskie, ale realny test "zwolnij, przesuń ręką, zapisz punkt" zostaje do
  zrobienia przy najbliższej obecności operatora.
- Gdyby w przyszłości pojawiła się potrzeba prawdziwego trybu podatnego —
  jedyna droga to prawdopodobnie funkcje poza publicznym API Teknica dla
  tej rodziny napędów (kontakt z producentem) albo inny sprzęt; nie ma
  sensu do tego wracać bez nowych informacji od Teknica.
