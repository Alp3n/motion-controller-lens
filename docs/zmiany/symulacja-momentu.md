# Symulacja momentu osi

Status maszyny niesie obciążenie osi (`torque`, % momentu maksymalnego) razem
z informacją, **skąd ta liczba pochodzi** (`torque_source`). Symulator wylicza
ją z własnego, zmyślonego modelu; parser odczytu ze sterownika (`TRQX/Y/Z`)
jest gotowy i czeka, aż mostek zacznie te pola wysyłać. Dzięki temu ekrany
i funkcje SMART dało się zbudować przed pracą przy maszynie (etap 0 tematu K).

## Pliki

- `server/app/machine.py` — pola `torque`/`torque_source` w `MachineStatus`;
  model `SIM_TRQ_*` i metody `_sim_torque`/`_update_sim_torque` w symulatorze;
  odczyt `TRQX/TRQY/TRQZ` ze `STATUS` w `ClearCoreMachine.poll_status`.
- `server/app/static/index.html` — sekcja „Obciążenie osi [% momentu]”.
- `server/app/static/app.js` — wyświetlanie obciążenia i **źródła** danych.
- `server/app/static/style.css` — klasa `.msg.warn` (żółta): ostrzeżenie,
  które nie jest alarmem maszyny.
- `server/tests/test_smart_uzycie.py` — testy oznaczania źródła i asymetrii Z.

## Uwagi

- **Liczby z symulatora są wymyślone.** Nie pochodzą z pomiaru ani z
  dokumentacji Teknica — model to moment postojowy + opór rosnący z
  prędkością + asymetria grawitacyjna osi Z + dodatek za skrawanie rosnący
  z głębokością. Panel pokazuje to wprost („źródło: SYMULACJA”), a
  `torque_source` pozwala odróżnić to od pomiaru w każdym miejscu kodu.
  **Progów siły nie wolno na tym dobierać** — do tego jest pomiar na maszynie
  i ekran `/sila` (etapy 0 i 2 tematu K).
- Gdy pól `TRQ*` nie ma w `STATUS`, źródłem jest `brak`, a panel pokazuje
  kreski. Świadomie: zera udające pomiar byłyby gorsze niż pusty wskaźnik.
- Nie zweryfikowane na sprzęcie: nazwy pól `TRQX/TRQY/TRQZ` to nasza
  propozycja protokołu, mostek ich jeszcze nie wysyła.
