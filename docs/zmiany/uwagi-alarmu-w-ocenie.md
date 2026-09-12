# Pole „Uwagi" alarmu zużycia widoczne też przy ocenie na żywo

Zgłoszenie 2026-09-12: zużycie osi ma alarmować wyłącznie przez wMES
(potwierdzenie wcześniejszej decyzji 2026-09-10 — temat M, krok 5 zostaje
odłożony); dla samego alarmu na poziomie maszyny operator ma dostać
**komunikat z sugestią** (przykład z rozmowy: „może przesmaruj maszynę").

Pole `note` w definicji alarmu (`app/zuzycie_alarmy.py`) już istniało i
już trafiało do `AlarmStatus`/`GET /api/zuzycie` — ale ekran `/zuzycie`
pokazywał je TYLKO w tabeli „Definicje” (edycja), nie w tabeli oceny na
żywo, którą operator faktycznie obserwuje. Komunikat więc istniał w danych,
ale nie docierał do operatora w miejscu, gdzie alarm się pojawia.

## Pliki

- `server/app/static/zuzycie.html` — nowa kolumna „Uwagi” w tabeli oceny
  alarmów (nie tylko w definicjach); opis sekcji podaje przykład treści.
- `server/app/static/zuzycie.js` — `renderAlarmyStatus()` dopisuje komórkę
  `a.note`, pogrubioną i w kolorze błędu, gdy alarm jest aktualnie
  przekroczony (`a.przekroczony`).
- `server/app/static/help.html` — zaktualizowany opis ekranu zużycia.

## Uwagi

- Żadnych zmian backendu — dane już tam były (`AlarmStatus.note`,
  `to_dict()`), to czysto wyświetleniowa poprawka.
- Zmiana w plikach statycznych — żywa od razu, bez restartu usługi.
- Istniejące definicje (`config/zuzycie_alarmy.json`) mają dziś proste
  notatki („X max dzienny”, puste) — do operatora, żeby ewentualnie
  zastąpić je treścią przydatną przy przekroczeniu (przykład z rozmowy:
  podejrzewana przyczyna + sugestia czynności).
