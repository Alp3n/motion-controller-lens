# „Zapisz jako" dla programów technologa

Edytor technologa (`/editor`) pozwala teraz zapisać aktualnie edytowany
program pod nowym numerem NC — oryginał zostaje bez zmian, edytor
przełącza się na kopię.

## Pliki

- `server/app/static/editor.html` — pole nowego numeru i przycisk
  „📄 Zapisz jako" pod istniejącymi przyciskami zapisu.
- `server/app/static/editor.js` — `collectContent()` już budowała treść
  pliku z globalnego `currentNumber` (ten sam mechanizm co zwykły zapis),
  więc „zapisz jako" tylko podmienia tę zmienną na nowy numer przed
  wywołaniem tego samego builder-a i tego samego `PUT /api/programs/{numer}`
  — bez zmian po stronie serwera.

## Uwagi

- Nowy numer musi być inny niż bieżący i **wolny** — kolizja z istniejącym
  plikiem jest odrzucana z komunikatem, żeby przypadkowe kliknięcie nie
  nadpisało cudzego programu. Świadome nadpisanie nadal można zrobić: otwórz
  ten program z listy i użyj zwykłego „Zapisz".
- Nieudany zapis (zły numer, kolizja, błąd serwera) nie przełącza edytora —
  `currentNumber` wraca do poprzedniej wartości, więc kolejne kliknięcie
  „Zapisz program" nie trafi przypadkiem w nowy, nieistniejący numer.
- Sprawdzone w przeglądarce (Playwright): zapis kopii z pełną treścią
  (nazwa, operacje), przełączenie edytora na kopię, oryginał niezmieniony,
  odrzucenie tego samego numeru, odrzucenie kolizji z zachowaniem edytora
  na dotychczas otwartym programie, odrzucenie złego formatu numeru.

## Korekta wcześniejszego wpisu w planie

Przy okazji poprawiony nieaktualny punkt w `plan-rozwoju.md`/`kanban.md`:
„Ekran definiowania operacji cyklu" był już zrobiony jako `/cycle` w etapie 4
tematu B — nikt wcześniej nie odhaczył go na tych listach.
