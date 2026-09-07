# Baza nazwanych punktów PTP + ekran prowadzenia za rękę

Nowa funkcja: nazwane punkty X/Y/Z z pełnym CRUD, wybierane z listy w
operacji PUNKT edytora programu, oraz ekran `/nauczanie` do ich zapisu
przez ręczne pozycjonowanie osi. Pełna analiza (dlaczego bez prawdziwego
"trybu podatnego" i jak działa przybliżenie, które go zastępuje):
`docs/prowadzenie-za-reke.md`.

## Pliki

- `server/app/punkty.py` — model `NamedPoint`, walidacja, plik `config/punkty.json`.
- `server/app/config.py` — `PUNKTY_FILE`.
- `server/app/machine.py` — `hand_guide_step()` + `Machine.hand_guide_start/tick/stop`.
- `server/app/main.py` — `GET/PUT /api/punkty`, `POST /api/machine/hand-guide/*`, strony `/punkty` i `/nauczanie`.
- `server/app/static/punkty.html`/`punkty.js` — lista punktów, CRUD.
- `server/app/static/nauczanie.html`/`nauczanie.js` — prowadzenie za rękę (niski limit momentu + doganianie odchylenia) + zapis pozycji jako punktu.
- `server/app/static/editor.js` — picker nazwanych punktów przy operacji PUNKT (jednorazowe wypełnienie X/Y/Z).
- `server/tests/test_punkty.py`, `test_hand_guide.py` — testy modelu, API i logiki prowadzenia.

## Uwagi

Wiązanie punktu z operacją jest jednorazowe — zmiana punktu w bazie nie
wpływa na już zapisane programy. Prowadzenie za rękę to niski limit
momentu (ustawiany przez operatora) + wykrycie, że rzeczywista pozycja
odjeżdża od zadanej, i doganianie tego ruchem JOG proporcjonalnym do
odchylenia — nie prawdziwy tryb podatny (SDK Teknica go nie udostępnia,
`docs/prowadzenie-za-reke.md`). Progi doganiania są prowizoryczne, do
dostrojenia po pierwszym teście na sprzęcie. Nie zweryfikowane jeszcze
fizycznie.
