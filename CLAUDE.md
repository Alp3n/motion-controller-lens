# Wskazówki dla Claude Code

## Dokumentowanie pracy — obowiązkowe

Wszystko, co przedstawiam użytkownikowi w rozmowie (analizy, ustalenia,
znalezione pułapki, decyzje, korekty wcześniejszych twierdzeń), **zapisuję
również w `docs/`**. Rozmowa jest ulotna — `docs/` jest źródłem prawdy.

### Analizy i ustalenia

Trafiają do `docs/<temat>.md`. Nazwa pliku od tematu, po polsku,
małymi literami z myślnikami (np. `docs/sterownik-sc4-hub.md`).

Jeśli temat już ma swój plik — **aktualizuję istniejący, nie tworzę drugiego**.
Gdy nowe ustalenie unieważnia wcześniejsze, poprawiam tekst i odnotowuję korektę,
zamiast zostawiać dwie sprzeczne wersje.

### Zmiany w kodzie

Trafiają do `docs/zmiany/<nazwa-zmiany>.md`. **Nazwa pliku pochodzi od zmiany**,
nie od daty ani numeru (np. `docs/zmiany/backend-sc4hub.md`,
`docs/zmiany/walidacja-obszaru-roboczego.md`).

Opis ma być **zwięzły i krótki**. Struktura:

```markdown
# <nazwa zmiany>

<1–3 zdania: co i po co>

## Pliki

- `ścieżka/plik.py` — co się w nim zmieniło (jedna linia)
- `ścieżka/inny.cpp` — j.w.

## Uwagi

<tylko jeśli coś istotnego: ryzyko, rzecz do zweryfikowania, świadomy kompromis>
```

Bez wklejania diffów i bez powtarzania tego, co widać w kodzie.

### Indeks

Każdy nowy plik w `docs/` dopisuję do listy w `docs/README.md`
(jedna linia: nazwa + do czego służy).

## Zasady merytoryczne

- **Fakty o sprzęcie weryfikuję u źródła** (dokumentacja Teknica, pliki z SDK),
  nie z pamięci. W dokumencie podaję źródło — link albo ścieżkę do pliku.
- **Nie zmiękczam ryzyk.** Bezpieczeństwo, realtime i dokładność toru opisuję
  wprost, łącznie z tym, czego nie udało się potwierdzić.
- **Język: polski**, tak jak reszta repozytorium (README, docs, komunikaty
  błędów dla operatora).

## Kontekst projektu

Maszyna do odcinania wlewków z płytek optyki. Serwer (`server/`, FastAPI)
rozmawia z maszyną wyłącznie przez klasę `Machine` (`server/app/machine.py`) —
to jedyny szew między aplikacją a sprzętem. Panel, API MES i parser `.prg`
nie mogą zależeć od konkretnego sterownika.

Stan sprzętu: **ClearPath-SC + SC4-Hub (USB)**, a nie ClearCore, pod który
pisano oryginalne repo — szczegóły i konsekwencje w
[`docs/sterownik-sc4-hub.md`](docs/sterownik-sc4-hub.md).
