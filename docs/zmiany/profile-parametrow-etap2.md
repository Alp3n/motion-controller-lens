# Profile parametrów ruchu — etap 2

Nazwane zestawy parametrów ruchu (prędkość maksymalna, rampy, limit momentu),
przełączane zależnie od kontekstu: inaczej w cyklu maszyny, inaczej w programie
technologa. Trzy profile powstają domyślnie z wartościami z
`zbyszek/NOTATKI_FUNKCJONALNE.md` §2: **globalny 20%**, **cykl 15%**,
**program 10%** momentu.

Drugi z czterech etapów tematu B — kontekst w
[`../model-cyklu-maszyny.md`](../model-cyklu-maszyny.md).

## Pliki

- `server/app/profiles.py` — nowy: `AxisParams`, `ParameterProfile`,
  walidacja, wczytywanie/zapis JSON (wzorem `axes.py`: zapis atomowy, błędny
  plik przerywa start, komunikaty po polsku).
- `server/app/machine.py` — `Machine` przechowuje profile i aktywny profil
  (`apply_profiles`, `set_active_profile`, `axis_params`); symulator
  **realnie ogranicza prędkość ruchu** przez `_capped_feed` w `_move_to`.
- `server/app/config.py` — `PROFILES_FILE` (zmienna `PROFILES_CONFIG`,
  domyślnie `config/profiles.json`).
- `server/app/main.py` — `GET/PUT /api/profiles`, `POST /api/profiles/active`,
  ostrzeżenia `_profile_warnings`.
- `server/tests/conftest.py` — `PROFILES_CONFIG` na katalog tymczasowy, żeby
  testy nie nadpisywały konfiguracji maszyny (tak jak już było z `AXES_CONFIG`).
- `server/tests/test_profiles.py` — 21 nowych testów.

## Uwagi

- **Limit momentu działa na sprzęcie od 2026-09-01** (etap 2b,
  `docs/zmiany/limit-momentu-sprzet.md`) — komenda `TRQLIMIT` w protokole
  mostka ustawia `ILimits.TrqGlobal` na serwie. Ten plik i to zdanie
  wcześniej mówiły odwrotnie („nie działa") — zostawione jako historia
  etapu 2, nie jako aktualny stan.
- Prędkość maksymalna **działa w symulatorze** — `_capped_feed` obniża posuw
  do limitu najwolniejszej z osi biorących udział w ruchu. Test
  `test_profile_caps_jog_speed` sprawdza to pomiarem czasu i został
  zweryfikowany: bez ograniczenia pada, z nim przechodzi.
- Rampy (`accel`, `decel`) są dziś **tylko przechowywane** — symulator ich nie
  odtwarza (porusza się ze stałą prędkością), a mostek używa własnej stałej
  `ACC_RPM_PER_SEC` z `machine.env`. To świadome: odwzorowanie ramp w
  symulatorze nie zmieniłoby niczego w wyniku, a na sprzęcie i tak wymaga
  rozszerzenia protokołu razem z momentem.
- Profil, który nie opisuje którejś ze skonfigurowanych osi, jest dozwolony
  (ta oś po prostu nie jest przez niego ograniczana), ale zgłaszany jako
  ostrzeżenie — zamiast cicho nie działać.
- `0%` momentu jest odrzucane. To nie jest „najbezpieczniejsza" wartość, tylko
  maszyna, która nie rusza i nie tłumaczy dlaczego.
