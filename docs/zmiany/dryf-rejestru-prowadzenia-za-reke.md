# Zamrożenie rejestru spoczynku po uzbrojeniu (prowadzenie za rękę)

Rejestr spoczynku w `hand_guide_tick()` dryfował do aktualnego odczytu
momentu bez ograniczenia w czasie, więc powolne, narastające pchnięcie
ręką nigdy nie zdążyło przekroczyć progu — ruch nie startował. Analiza
i pełna historia poprzednich poprawek tego mechanizmu:
[`docs/prowadzenie-za-reke.md`](../prowadzenie-za-reke.md).

## Pliki

- `server/app/machine.py` — `hand_guide_tick()` aktualizuje `baseline`
  tylko w oknie ponownego uzbrajania po kroku (`settle_count_before <
  HAND_GUIDE_SETTLE_TICKS`), zamiast na każdym spokojnym ticku.
- `server/tests/test_hand_guide.py` — zastąpiono
  `test_tick_dryfuje_rejestr_tylko_w_spoczynku` (opisywał zachowanie
  będące błędem) testami `test_tick_dryfuje_rejestr_w_oknie_uspokojenia_po_ruchu`
  i `test_tick_nie_dryfuje_rejestru_gdy_juz_uzbrojony`.

## Uwagi

Nie zweryfikowane jeszcze fizycznie — to czwarta z rzędu poprawka tego
mechanizmu po kolejnych testach na sprzęcie.
