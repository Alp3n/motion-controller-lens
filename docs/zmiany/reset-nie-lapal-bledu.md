# RESET nie łapał `MachineError` — zwracał 500 zamiast czytelnego błędu

Ten sam brakujący wzorzec co przy STOP dzień wcześniej
([`stop-nie-lapal-bledu.md`](stop-nie-lapal-bledu.md)) — `RESET` był
jedynym pozostałym endpointem sterowania bez obsługi `MachineError`.
Znalezione przy maszynie 2026-09-02: „Kasuj alarm" nie robiło nic
widocznego, bo mostek odrzucił komendę RESET tym samym błędem SDK co
poprzednio na węźle X (`Node @ 1 error... CPMinfoEx::Parameter`) — operator
dostawał 500 zamiast komunikatu.

## Naprawa

```python
@app.post("/api/machine/reset")
async def machine_reset(user=Depends(require_operator)):
    try:
        await machine.reset()
    except MachineError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}
```

## Pliki

- `server/app/main.py` — `machine_reset()` łapie `MachineError`.
- `server/tests/test_api.py` — nowy test regresyjny
  (`test_reset_zwraca_409_nie_500_gdy_mostek_odrzuci_komende`).

## Uwagi

Naprawa dotyczy tylko obsługi błędu, nie jego przyczyny — to trzecie
wystąpienie tego samego błędu SDK na węźle X (Node 1), nierozwiązane u
źródła, patrz `kanban.md`. Po naprawie RESET zadziałał: alarm skasowany,
pełna telemetria wróciła (`safety_enable: true`, `torque_source:
"sterownik"`).
