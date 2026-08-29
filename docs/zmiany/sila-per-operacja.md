# Siła per operacja w programie technologa (format 4)

Program technologa (`.prg`) ma teraz kolumnę `MOMENT` — limit siły (momentu
silnika) tylko dla pojedynczej operacji, w procentach. Pusta wartość
dziedziczy z aktywnego profilu parametrów (temat B etap 2). Mechanizm i
ograniczenia (patrz „Uwagi") są identyczne jak przy limicie momentu
w profilach — to jest ta sama funkcja, tylko dostępna z drugiego miejsca.

## Pliki

- `server/app/program.py` — `OPERATIONS_HEADER_V4` (dokłada `MOMENT` po
  `OBROTY`, przed `PRZEJSCIA`, jak `OBROTY` dołożone w formacie 3),
  `Operation.torque_pct`, walidacja zakresu `(0, 100]` i zakazu dla
  `PAUZA`/`WRZECIONO` (nie poruszają osiami — jak `POSUW`). Zapis zawsze
  w formacie 4; parser czyta 1–4, stare pliki awansują przy zapisie.
- `server/app/static/editor.html`, `editor.js` — kolumna „Moment” w tabeli
  operacji, wygaszana dla `WRZECIONO`/`PAUZA` jak pozostałe parametry ruchu;
  walidacja zakresu na bieżąco (czerwona ramka + komunikat, zanim serwer
  odrzuci zapis).
- `docs/FORMAT_PROGRAMU.md` — opis kolumny i formatu 4.
- `server/tests/test_program.py` — 6 nowych testów (parsowanie, roundtrip,
  zakres, `PAUZA`/`WRZECIONO`, brak wartości po awansie ze starego formatu).

## Uwagi

- **Dziś to wyłącznie zapis w pliku** — tak jak limit momentu w profilach
  (`docs/zmiany/profile-parametrow-etap2.md`), `MOMENT` nie wpływa jeszcze
  ani na symulator, ani na sprzęt. Protokół mostka nie ma komendy momentu;
  wpisana tu wartość nic nie zmienia w ruchu, dopóki ten protokół nie
  zostanie rozszerzony (C++, wymaga sprzętu — patrz temat C w planie).
- **Znaleziony i naprawiony przed wypchnięciem:** `collectContent()`
  w `editor.js` miała nagłówek sekcji `[OPERACJE]` i numer `FORMAT` wpisane
  na sztywno jako tekst, niezależnie od tablicy `FIELDS`, która faktycznie
  określa kolumny w wierszu. Dodanie `MOMENT` do `FIELDS` bez tej poprawki
  wysyłało 13 kolumn w wierszu przy nagłówku deklarującym 12 — serwer
  odrzucał każdy zapis. Poprawka: nagłówek budowany teraz z `FIELDS`/`LABEL`
  (`["LP","OPERACJA", ...FIELDS.map(f=>LABEL[f]), "UWAGI"]`), więc kolejny
  format nie rozjedzie się w ten sam sposób. Złapane testem w przeglądarce
  przed commitem, nie trafiło do repo w zepsutej wersji.
- Sprawdzone w przeglądarce (Playwright): zapis z wartością `MOMENT`,
  trwałość po przeładowaniu, odrzucenie wartości spoza `(0, 100]`,
  wygaszenie pola dla `WRZECIONO`, poprawny awans istniejącego programu
  (format 1) do formatu 4 bez utraty treści. Prawdziwe pliki w `programs/`
  nietknięte (izolowany katalog testowy).
