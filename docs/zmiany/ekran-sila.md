# Ekran kontroli siły i kalibracji (`/sila`)

Etap 2 tematu K, **częściowo** — podgląd obciążenia na żywo i ręczna
kalibracja moment→siła siłomierzem. Pełna specyfikacja
([`../funkcje-smart.md`](../funkcje-smart.md)) ma trzeci element,
automatyczną „próbę przejazdu" (charakterystyka bazowa tarcia/ciężaru osi) —
**świadomie niezaimplementowany tutaj**, bo rusza maszyną: wymaga ustalenia
bezpiecznego profilu ruchu (zakres, prędkość, `TrqGlobal` próby) z operatorem
przy maszynie, nie zdalnie. Ekran mówi to wprost w sekcji „Zakres tego
ekranu", zamiast milczeć o brakującej funkcji.

## Pliki

- `server/app/kalibracja.py` — nowy: `PunktKalibracji` (moment %, siła N,
  kierunek, data, uwagi), `KalibracjaOsi`, `parse_kalibracja`, zapis atomowy
  `config/kalibracja.json`. W przeciwieństwie do `axes.py` błędny/brakujący
  plik **nie przerywa startu** — to dane pomocnicze do progów, nie parametr
  bezpieczeństwa.
- `server/app/config.py` — `KALIBRACJA_FILE` (`KALIBRACJA_CONFIG`).
- `server/app/main.py` — `GET/PUT /api/kalibracja` (GET: operator, PUT:
  admin — jak profile i SMART), strona `/sila` (admin).
- `server/app/static/sila.html`, `sila.js` — nowy ekran: trzy panele (X/Y/Z)
  z tabelą punktów kalibracji i formularzem dodawania, plus podgląd momentu
  na żywo przez `/ws/status` (ten sam kanał co panel operatora).
- `server/app/static/sesja.js` — `/sila` dopisane do mapy ról (ukrywanie
  odnośnika dla nieuprawnionych).
- `server/app/static/{axes,cycle,editor,index,profiles,smart}.html` —
  wzajemne odnośniki do `/sila` w nagłówku.
- `server/tests/conftest.py` — `KALIBRACJA_CONFIG` na katalog tymczasowy.
- `server/tests/test_kalibracja.py` — 13 testów: model, plik, API.

## Uwagi

- **Zapis natychmiastowy, bez osobnego „niezapisanych zmian".** Dodanie albo
  usunięcie punktu od razu wysyła cały obiekt kalibracji przez `PUT
  /api/kalibracja` — prościej niż śledzenie stanu roboczego, kosztem tego, że
  literówkę trzeba poprawić usuwając i dodając punkt ponownie (nie ma edycji
  w miejscu).
- **Kalibracja nie jest funkcją bezpieczeństwa** — to dane pomocnicze do
  dobierania progów w profilach i definicjach SMART. Zabezpieczeniem
  pozostaje limit momentu w serwie (`ILimits.TrqGlobal`,
  `zmiany/limit-momentu-sprzet.md`) i sprzętowy E-stop/Global Stop.
- Podgląd na żywo pokazuje `torque_source` wprost — na symulatorze ostrzega
  żółtym komunikatem, żeby nikt nie kalibrował na wartościach zmyślonych.
- **Niezrobione, świadomie:** automatyczna próba przejazdu (punkt 2 pełnej
  specyfikacji) — do zaprojektowania i zaimplementowania przy maszynie, razem
  z ustaleniem bezpiecznego `TrqGlobal` próby. Ekran diagnostyczny
  (`/diagnostics`) **nie został** rozszerzony o informacje z tego pliku —
  drobny dług, do rozważenia przy okazji.
- Nie zweryfikowane w przeglądarce na żywym sprzęcie (napisane i przetestowane
  jednostkowo/API w symulatorze, bez sesji Playwright jak przy innych
  ekranach).
