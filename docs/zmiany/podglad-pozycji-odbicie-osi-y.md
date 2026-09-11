# Poprawka: podgląd pozycji był odwrócony góra-dół

Zgłoszenie operatora 2026-09-11: rysunek podglądu pozycji (panel główny,
płótno `#view`) pokazywał oś Y w lustrzanym odbiciu względem rzeczywistej
maszyny — góra z dołem zamienione miejscami.

## Przyczyna

`drawView()` w `app.js` mapowało współrzędną maszyny na piksel canvasu
standardową matematyczną konwencją („Y rośnie w górę ekranu"):
`Y = (my) => oy + (area.y_max - my) * s`. To dobra konwencja na wykresie,
ale nie odpowiadała temu, co operator widzi fizycznie patrząc na maszynę —
większa wartość Y w rzeczywistości leży niżej w polu widzenia operatora,
nie wyżej.

## Pliki

- `server/app/static/app.js` — `Y()` odwrócone na `oy + (my - area.y_min) * s`
  (Y rośnie w dół ekranu). Przy okazji: obrys obszaru roboczego
  (`strokeRect`) i etykiety osi X, które wcześniej zakładały na sztywno, że
  `Y(area.y_max)` to góra rysunku, teraz liczą górną/dolną krawędź jako
  `Math.min/max(Y(area.y_min), Y(area.y_max))` — nie łamie się, gdyby
  kierunek Y kiedyś znów się zmienił.

## Uwagi

- Siatka, oś zerowa, tor przebyty i krzyż narzędzia używają `Y()` do obu
  końców linii (`moveTo`/`lineTo`), więc automatycznie podążyły za nową
  orientacją bez osobnych poprawek.
- Oś Z (osobny pionowy wskaźnik po prawej) nie była ruszana — tam większa
  wartość już poprawnie renderowała się wyżej, zgłoszenie dotyczyło
  wyłącznie płaszczyzny XY.
- Nie ma testu przeglądarkowego pokrywającego tę warstwę (patrz też
  [[poprawka-podgladu-pozycji]], ta sama luka) — poprawka zweryfikowana
  code review (brak dostępu do Chrome w tej sesji) i **potwierdzona
  fizycznie przez operatora 2026-09-11**: „tak teraz jest dobrze".
