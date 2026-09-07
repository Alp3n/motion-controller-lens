# Baza nazwanych punktów PTP + ekran prowadzenia za rękę

Nowa funkcja: nazwane punkty X/Y/Z z pełnym CRUD, wybierane z listy w
operacji PUNKT edytora programu, oraz ekran do ich zapisu przez ręczne
pozycjonowanie osi (zwolnienie momentu, RELEASE/HOLD). Pełna analiza i
uzasadnienie zakresu (dlaczego bez "trybu podatnego"): `docs/prowadzenie-za-reke.md`.

## Pliki

- `server/app/punkty.py` — model `NamedPoint`, walidacja, plik `config/punkty.json`.
- `server/app/config.py` — `PUNKTY_FILE`.
- `server/app/main.py` — `GET/PUT /api/punkty`, strony `/punkty` i `/nauczanie`.
- `server/app/static/punkty.html`/`punkty.js` — lista punktów, CRUD.
- `server/app/static/nauczanie.html`/`nauczanie.js` — zwolnienie osi X/Y/Z + zapis pozycji jako punktu.
- `server/app/static/editor.js` — picker nazwanych punktów przy operacji PUNKT (jednorazowe wypełnienie X/Y/Z).
- `server/tests/test_punkty.py` — 13 testów.

## Uwagi

Wiązanie punktu z operacją jest jednorazowe — zmiana punktu w bazie nie
wpływa na już zapisane programy. Zwolnienie osi w `/nauczanie` to pełne
zdjęcie momentu (RELEASE/HOLD, mechanizm już istniejący), nie regulowany
opór — sprzęt (SDK Teknica) nie udostępnia trybu momentu z hosta, patrz
`docs/prowadzenie-za-reke.md`. Nie zweryfikowane jeszcze fizycznie.
