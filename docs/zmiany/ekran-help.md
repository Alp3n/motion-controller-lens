# Ekran /help — instrukcja obsługi dla operatora

Zamówienie 2026-09-12: „potrzebuję instrukcji dla mojego współpracownika
z opisem wszystkich naszych funkcji na stronie jako zakładka HELP, żeby
mógł korzystać z tej maszyny. Aktualizuj tą instrukcję po naszych
kolejnych zmianach." Operator wdraża nową osobę do obsługi maszyny —
jedynym źródłem wiedzy dla niej ma być ta strona, nie kod ani `docs/`.

## Zawartość

Jedna statyczna strona, spis treści z kotwicami, sekcja per ekran
panelu (rola wymagana, co robi, jak z niego korzystać — język operatora,
bez nazw plików/funkcji), plus zbiorcza sekcja „Czego żaden ekran nie
robi" zbierająca rozrzucone po poszczególnych ekranach zastrzeżenia
bezpieczeństwa (E-stop/Global Stop jako jedyna certyfikowana funkcja
bezpieczeństwa) w jedno miejsce.

## Pliki

- `server/app/static/help.html` — treść (bez osobnego `.js`, strona
  czysto informacyjna).
- `server/app/main.py` — trasa `GET /help`, `ROLE_OPERATOR` (najniższa
  rola — instrukcja ma być czytelna dla każdego zalogowanego).
- `server/app/static/sesja.js` — `dodajLinkPomocy()`: dokłada odnośnik
  „Pomoc" do nagłówka KAŻDEGO ekranu (nie tylko panelu operatora),
  niezależnie od roli, wywoływane synchronicznie przed odpytaniem
  `/api/auth/me` — jedno miejsce zamiast edycji czternastu plików HTML.
- `server/tests/test_api.py` — `test_help_page_is_served`: strona się
  wczytuje i ma sekcje kluczowych ekranów (regresja przeciw przypadkowemu
  wyczyszczeniu treści przy kolejnej edycji).

## Uwagi

- **To jest żywy dokument — standing task, nie jednorazowa praca.**
  Zapisane w pamięci projektu (`[[feedback_utrzymuj_ekran_pomocy]]`):
  każda kolejna zmiana widoczna dla operatora (nowy ekran, przycisk,
  zmienione zachowanie) ma dostać odpowiednią aktualizację tej strony,
  **zanim** zadanie uznaje się za zakończone — tym samym trybem co
  obowiązkowy wpis w `docs/zmiany/`.
- Treść pisana pod odbiorcę bez kontekstu deweloperskiego — inny rejestr
  niż `docs/` (tu: „co się stanie, jak kliknę", nie „jak to jest
  zaimplementowane").
- Nie obejmuje jeszcze ekranu logowania/kont (`tools/konta.py`) — dziś to
  konfiguruje się z terminala na serwerze, nie z panelu, więc nie ma tu
  osobnej sekcji; rola/logowanie opisane ogólnie w sekcji „Role i
  logowanie".
