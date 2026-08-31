# Porządek w plikach konfiguracji i w `.gitignore`

Poprawka `.gitignore` plus opis nieporządku, który wyszedł przy sprzątaniu gita:
konfiguracja maszyny leży w **dwóch katalogach**, a jej część jest śledzona
w repozytorium, więc każde użycie panelu brudzi drzewo robocze.

## Poprawka (zrobiona)

Wpisy dodane wcześniej — `config/users.json`, `config/smart.json`,
`config/dziennik-zmian.jsonl` — **nie działały**. Serwer startuje z katalogu
`server/`, więc pliki lądują w `server/config/`, a wzorzec zawierający ukośnik
git kotwiczy w katalogu pliku `.gitignore`. Skutek: `server/config/smart.json`
pokazywał się jako nieśledzony, a `server/config/users.json` (skróty haseł!)
trafiłby do repozytorium przy pierwszym `git add -A`.

Wzorce mają teraz `**/` i łapią oba katalogi. Sprawdzenie:
`git check-ignore -v server/config/users.json`.

## Pliki

- `.gitignore` — wzorce `**/config/…` dla plików tworzonych w czasie pracy
  panelu (konta, dziennik zmian, SMART, wyjścia, wrzeciono)

## Nieporządek, który zostaje — do decyzji

**Dwa katalogi konfiguracji.** `tools/uruchom-maszyne.sh` robi `cd server`
i ustawia jawnie tylko `AXES_CONFIG=../config/axes.json`. Reszta ścieżek jest
względna, więc rozjeżdża się tak:

| Plik | Gdzie ląduje | W gicie? |
| --- | --- | --- |
| `axes.json` | `config/` (katalog główny) | tak |
| `profiles.json`, `cycle.json` | `server/config/` | tak |
| `smart.json`, `wyjscia.json`, `spindle.json` | `server/config/` | nie |
| `users.json`, `dziennik-zmian.jsonl` | `server/config/` | nie (i nie może być) |

Podział jest przypadkowy — wynika z katalogu roboczego, nie z decyzji.

**Konsekwencja, którą widać na co dzień:** `profiles.json`, `cycle.json`
i `axes.json` są śledzone, więc **każdy zapis z panelu pokazuje się jako
`modified`**, a `git pull` na maszynie może wejść w konflikt z jej żywą
konfiguracją. Dokładnie to zdarzyło się przy sprzątaniu gita.

**Propozycja (nie zrobiona — dotyka konfiguracji pracującej maszyny):**

1. `uruchom-maszyne.sh` ustawia jawnie **wszystkie** ścieżki na jeden katalog
   `config/` w katalogu głównym.
2. `server/config/profiles.json` i `server/config/cycle.json` przenieść
   (`git mv`) do `config/`, żeby maszyna po `git pull` czytała te same treści
   z nowego miejsca.
3. Zdecydować, czy konfiguracja maszyny ma w ogóle być w repozytorium:
   - **zostaje** — repo jest kopią zapasową, ale trzeba żyć z `modified`
     po każdym zapisie z panelu,
   - **wypada** — repo przestaje się brudzić, ale kopię zapasową konfiguracji
     trzeba zrobić inaczej (np. wersje przykładowe `*.przyklad.json` w gicie).

Punkt 3 jest decyzją, nie techniką — dlatego czeka.
