# Wyjścia BRAKE_0 / BRAKE_1 podpięte do aplikacji

Silniki nie mają hamulców, więc oba wyjścia huba są wolne dla funkcji maszyny.
Do tej pory krok `WYJSCIE` cyklu zmieniał tylko liczbę w statusie — protokół
mostka nie miał komendy ustawienia wyjścia. Teraz ma: `WYJSCIE` przełącza
fizyczne wyjście 24 VDC na SC4-Hub.

Domyka to lukę zapisaną jako „etap 2b/3 tematu B" oraz decyzję z tematu J:
przeznaczenie wyjścia definiuje się w konfiguracji maszyny, a program
technologa z wyjść nie korzysta.

## Protokół mostka — nowa komenda

```
OUTPUT <0|1> <0|1>        -> OK | ERR <powód>
```

`STATUS` dostaje pole `OUT=<b0><b1>`, np. `OUT=01`. Starszy mostek tego pola nie
wysyła — serwer zostawia wtedy ostatnio znany stan zamiast go zerować.

## Pliki

- `bridge/sc4hub_bridge.cpp` — `setOutput()`, `resetOutputs()`, komenda `OUTPUT`,
  `OUT=` w `STATUS`, zerowanie wyjść po otwarciu portu; `setSpindle` korzysta
  z tego samego `setOutput`
- `server/app/outputs.py` — nowy: przeznaczenie wyjść (podajnik, wyrzutnik,
  docisk, lampka, błąd), etykiety, „gaś przy STOP", ostrzeżenia
- `server/app/cycle.py` — `OUTPUT_INDEX`/`output_index()` (nazwa logiczna →
  numer wyjścia), `outputs_used()`
- `server/app/machine.py` — `SC4HubMachine` wysyła `OUTPUT` w kroku `WYJSCIE`
  i czyta `OUT=` ze statusu; `outputs_to_clear()` i gaszenie na koniec pracy
- `server/app/main.py` — `GET/PUT /api/outputs`, ostrzeżenia przy zapisie cyklu,
  wyjścia w `/api/diagnostics`
- `server/app/static/cycle.html`, `cycle.js` — sekcja „Wyjścia cyfrowe",
  etykiety w liście wyboru kroku `WYJSCIE`, stan na żywo
- `server/app/static/index.html`, `app.js` — stan wyjść na panelu operatora
- `server/app/config.py` — `OUTPUTS_FILE` (`config/wyjscia.json`)
- `server/tests/test_wyjscia.py` — 25 testów; `test_sc4hub.py` — test pilnujący
  dawnego braku komendy zastąpiony testem nowego zachowania

## Uwagi — bez zmiękczania

- **Kod mostka nie został skompilowany ani uruchomiony.** Sesja nie ma SDK
  Teknica (`vendor/`, poza repozytorium), więc `OUTPUT` jest **napisany, nie
  sprawdzony**. Warstwa serwera jest przetestowana z podstawionym `_command`.
  Do zweryfikowania przy najbliższym wejściu na sprzęt — dopisane do tematu H.
- **Wyjścia wymagają osobnego zasilania 24 V** doprowadzonego do płytki huba.
  Bez niego komendy przechodzą (mostek odpowiada `OK`), a fizycznie nic się nie
  przełącza — panel nie ma jak tego wykryć.
- **Obciążalność 500 mA / 24 VDC na wyjście** (instrukcja ClearPath-SC rev. 1.45,
  str. 47). Stycznik **tylko przez przekaźnik pośredniczący**.
- **To nie jest obwód bezpieczeństwa.** Producent ostrzega, że system operacyjny
  może przypadkowo załączyć wyjście, gdy aplikacja nie trzyma portu — u nas ten
  scenariusz realnie występuje (`cdc_acm` przejmuje hub przy każdej ponownej
  enumeracji USB, ryzyko A w `mozliwosci-clearpath-sc.md`). Dlatego mostek
  **zeruje oba wyjścia zaraz po otwarciu portu** — to ustala znany stan, ale
  **nie zastępuje** wymogu, żeby wszystko, co może zranić, szło szeregowo przez
  styk obwodu osłon.
- **Wyjście zajęte przez wrzeciono jest chronione.** Przy `SPINDLE_OUTPUT=brake0`
  komenda `OUTPUT 0 …` zostaje odrzucona przez mostek, a ekran cyklu blokuje
  edycję tego wiersza i ostrzega. Inaczej krok cyklu po cichu walczyłby
  z logiką wrzeciona.
- **Gaszenie przy STOP jest per wyjście, nie globalne.** Domyślnie gaśnie tylko
  wyrzutnik. Docisku i podajnika celowo **nie** gasimy: zdjęcie docisku przy
  zatrzymaniu potrafi upuścić detal, co bywa gorsze niż zostawienie wyjścia
  załączonego. Decyzja należy do admina — ekran ma na to kolumnę.
- **Nadal nie ma wejść.** Sygnał drzwi/osłony i krok „czekaj na wejście" wymagają
  wejść, których SC4-Hub nie daje poza Global Stop (temat E i J).
