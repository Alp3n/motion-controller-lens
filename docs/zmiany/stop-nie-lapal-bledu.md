# STOP nie łapał `MachineError` — zwracał 500 zamiast czytelnego błędu

Znalezione przy maszynie 2026-09-01, przy okazji incydentu z węzłem osi X
(patrz „Incydent: Node @ 1 error" niżej). `POST /api/machine/stop` był
**jedynym** endpointem sterowania, który nie łapał `MachineError` z
`machine.stop()` — gdy komenda `STOP` do mostka nie powiodła się (mostek
zwrócił `ERR ...`), wyjątek przechodził przez FastAPI nieobsłużony i
operator dostawał **500 Internal Server Error** zamiast komunikatu.

To o tyle istotne, że STOP jest jedynym punktem sterowania celowo
działającym bez logowania (`zmiany/role-i-logowanie.md`) właśnie po to, żeby
zawsze dało się zatrzymać maszynę z panelu — a mimo to nie miał tej samej
podstawowej obsługi błędów co np. `/api/machine/home` czy `/api/machine/jog`.

## Naprawa

```python
@app.post("/api/machine/stop")
async def machine_stop():
    try:
        await machine.stop()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}
```

Ten sam wzorzec co reszta endpointów sterowania. Nowy test
(`test_stop_zwraca_409_nie_500_gdy_mostek_odrzuci_komende`) podstawia
`machine.stop` rzucające `MachineError` i sprawdza `409`, nie `500`.

**To NIE naprawia przyczyny**, dla której komenda STOP mogła zostać
odrzucona przez mostek (patrz niżej) — tylko to, jak operator dowiaduje się
o niepowodzeniu.

## Incydent, który to ujawnił: „Node @ 1 error" przy pierwszym E-stopie

Przy pierwszym realnym zadziałaniu E-stop/Global Stop na tej maszynie
(2026-09-01), po serii STOP/RESET/HOME/STOP, jedno z wywołań `STOP` (dwa
kliknięcia w bardzo krótkim odstępie) dostało od mostka:

```
ERR Node @ 1 error. Reported by function: virtual double sFnd::CPMinfoEx::Parameter(nodeparam).
```

`Node @ 1` to oś X (`oś X -> Node[1]`, mapowanie po numerze seryjnym w
`bridge/machine.env`). Źródło błędu w SDK Teknica nie zostało ustalone z
pewnością — `CPMinfoEx::Parameter` czyta parametr informacyjny węzła;
najbardziej prawdopodobna hipoteza to węzeł w stanie alertu tuż po
zadziałaniu Global Stop i/lub gwałtownym `NodeStop(STOP_TYPE_ABRUPT)` z
dwóch STOP-ów nałożonych na siebie — **niepotwierdzone, do zbadania przy
maszynie**, jeśli się powtórzy.

**Efekt uboczny ważniejszy od samego błędu:** ten sam błąd zaczął się
powtarzać przy **każdym** kolejnym `STATUS` (bo `statusLine()` czyta
`TrqMeasured` dla wszystkich trzech osi, w tym feralnej X) — a
`_poll_loop()` w `main.py` łapie `MachineError` przez
`contextlib.suppress()` **bez żadnego logu ani sygnału dla operatora**.
Efekt: status na panelu **zamroził się** na starych danych (`torque_source:
"brak"`, `safety_enable` sprzed incydentu) na wiele minut, bez żadnej
wizualnej wskazówki, że komunikacja z mostkiem jest zerwana. Dwa kolejne
`RESET` (widoczne w logu, `200 OK`) najwyraźniej pomogły stronie mostka
(prawdopodobnie `AlertsClear()`/`NodeStopClear()`), ale status na panelu
tego nie pokazał, dopóki ktoś nie zrestartował mostka.

**To osobny, nienaprawiony jeszcze problem — dopisany do `kanban.md`:**
`_poll_loop()` powinien sygnalizować operatorowi utratę łączności z
mostkiem (np. licznik kolejnych nieudanych prób, pole w statusie typu
`bridge_ok: bool`, baner na panelu), zamiast cicho zamrażać ostatnie znane
dane bez żadnego oznaczenia, że są nieaktualne.

## Pliki

- `server/app/main.py` — `machine_stop()` łapie `MachineError`.
- `server/tests/test_api.py` — nowy test regresyjny.

## Uwagi

- Naprawa jest **kompletna i przetestowana** — dotyczy tylko brakującej
  obsługi błędu.
- **Zamrożony status po utracie łączności z mostkiem NIE jest naprawiony**
  tą zmianą — to nowy, osobny punkt w `kanban.md`, wymaga własnego
  projektu (jak sygnalizować nieaktualność danych, po jakim czasie/ilu
  nieudanych próbach).
- Przyczyna źródłowa błędu SDK na węźle X **nie została ustalona z
  pewnością** — jeśli się powtórzy, warto zanotować dokładną sekwencję
  zdarzeń (ile STOP-ów, jak blisko w czasie, stan przed i po) i sprawdzić
  ClearView pod kątem aktywnych alertów na tym węźle.
