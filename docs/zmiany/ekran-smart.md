# Ekran definicji SMART (`/smart`) — etap 1 tematu K

Model definicji SMART, API i osobny ekran do ich edycji. Definicja to
**nazwany zestaw parametrów procedury** sterowanej siłą (np. `SMART-sila`),
wspólny dla programu technologa i cyklu maszyny. Plan i uzasadnienie:
[`../funkcje-smart.md`](../funkcje-smart.md).

**Sama procedura jeszcze nie działa** — pętla odczytu momentu i reagowania
na niego to etap 4 (C++ w mostku, wymaga maszyny). Ten etap daje warstwę,
którą da się zbudować i przetestować bez sprzętu.

## Pliki

- `server/app/smart.py` — rejestr procedur (`ParamSpec`/`Procedure`), model
  `SmartDefinition`, walidacja, plik `config/smart.json`, ostrzeżenia.
- `server/app/config.py` — `SMART_FILE` (env `SMART_CONFIG`).
- `server/app/main.py` — `GET/PUT /api/smart`, trasa `GET /smart`.
- `server/app/static/smart.html`, `smart.js` — ekran: lista definicji,
  wybór procedury, pola parametrów, „zapisz jako", usuwanie.
- `server/app/static/{index,axes,cycle,editor,profiles}.html` — link w nagłówku.
- `server/tests/test_smart.py` — 29 testów; `conftest.py` izoluje `SMART_CONFIG`.

## Decyzje warte zapamiętania

- **Pola parametrów nie są wpisane w JS na sztywno.** Ekran rysuje je
  z rejestru procedur zwracanego przez `/api/smart`. Dopisanie parametru
  w `smart.py` (albo kolejnej procedury) pojawia się na ekranie samo — ten
  sam wzorzec, co pola zależne od rodzaju operacji w edytorze technologa.
- **Rejestr procedur jest po stronie serwera, nie tylko w mostku.** Bez tego
  ekranu nie dałoby się zbudować ani przetestować przed pracą przy maszynie.
  Mostek dostanie własny rejestr w C++ (etap 4); `SMARTLIST` pozwoli je
  porównać i ostrzec przy rozjeździe.
- **Brakujące parametry uzupełniamy domyślnymi, nieznane odrzucamy.** Po
  dopisaniu nowego parametru stare definicje mają dalej działać (nie blokować
  startu serwera), ale literówka w nazwie musi być błędem, a nie cichym
  pominięciem wartości.
- **Walidacja sprawdza też zależności między parametrami**, nie same zakresy:
  próg przyspieszenia musi być mniejszy od progu zwolnienia (inaczej
  procedura przełączałaby prędkość w kółko przy tym samym obciążeniu),
  a prędkość wolna nie może przekraczać szybkiej. To samo powtórzone w JS,
  żeby technolog zobaczył błąd przed zapisem.
- **Nazwa definicji dopuszcza wielkie litery i myślnik** (`SMART-sila`), ale
  nie spację ani średnik — nazwa trafi do pliku `.prg`, gdzie średnik
  rozdziela kolumny.
- **Zapis odrzucany w ruchu maszyny** — definicja może być właśnie używana
  przez wykonywany krok cyklu (tak samo jak profile).

## Uwagi

- Ekran **od razu ostrzega**, że procedury nie ma jeszcze w mostku, a w trybie
  sprzętowym — że uruchomienie kroku SMART skończy się błędem sterownika.
  Technolog, który wpisuje próg siły 30%, musi wiedzieć, że dziś nic go nie
  pilnuje.
- Sekcja „Jak to działa" mówi wprost, że **próg siły to procent momentu, nie
  niutony**, że wartość dobiera się doświadczalnie na odpadzie i że **to nie
  jest funkcja bezpieczeństwa** (zabezpieczeniem zostaje limit momentu
  w serwie oraz sprzętowy E-stop i Global Stop).
- Sprawdzone w przeglądarce (Playwright): 10 pól rysowanych z rejestru, oś
  jako lista wyboru, blokada zapisu przy sprzecznych progach, „zapisz jako"
  z zachowaniem oryginału, trwałość po przeładowaniu. Bez błędów JS.
- Testy: 170/170.
