---
name: uruchom-projekt
description: Użyj, gdy użytkownik prosi "uruchom projekt", "odpal serwer", "uruchom maszynę", "start the project", "launch the app" dla tego repozytorium (motion-controller-lens). Startuje panel serwera maszyny (FastAPI) bezpiecznie zarówno na hoście produkcyjnym (usługa systemd + prawdziwy sprzęt SC4-Hub), jak i na zwykłym checkoucie deweloperskim — bez dublowania procesu i bez wymuszania trybu sprzętowego.
---

# Uruchom projekt

Serwer (`server/`, FastAPI) uruchamiamy różnie w zależności od tego, gdzie
działa ta sesja — host produkcyjny ma go już jako usługę systemd, podłączoną
do prawdziwego sprzętu; zwykły checkout deweloperski trzeba dopiero
wystartować.

## 1. Sprawdź, czy to host produkcyjny z usługą systemd

```bash
systemctl is-active motion-controller-lens.service 2>/dev/null
```

- **`active`** — usługa już działa. **Nic nie uruchamiaj ponownie** — drugi
  proces nie podniesie się na zajętym porcie 8000, a poza tym to na hoście
  produkcyjnym bywa `MACHINE_MODE=sc4hub` (prawdziwy sprzęt), więc nie ma
  powodu dublować procesu. Zamiast tego zgłoś użytkownikowi bieżący tryb i
  URL-e:

  ```bash
  systemctl show motion-controller-lens.service -p Environment
  curl -s http://localhost:8000/api/status
  ```

- **`inactive`/`failed`, ale jednostka `/etc/systemd/system/motion-controller-lens.service`
  istnieje** — to host, gdzie usługa normalnie powinna działać, a nie
  działa. **Zapytaj użytkownika, zanim ją wystartujesz** — jeśli tryb to
  `sc4hub` (albo jego dawna nazwa `clearcore`), start zaczyna przyjmować
  komendy ruchu z panelu do prawdziwego sprzętu.

- **Jednostka w ogóle nie istnieje** — to zwykły checkout deweloperski,
  przejdź do kroku 2.

## 2. Checkout deweloperski — uruchom lokalnie

Preferuj `tools/uruchom-maszyne.sh` (bootstrapuje venv, wykrywa
mostek/sprzęt, bez sprzętu sam przechodzi w tryb symulacji, otwiera
przeglądarkę). Domyślny tryb `auto` jest bezpieczny — nie wymuszaj trybu
`maszyna` bez wyraźnej prośby użytkownika:

```bash
./tools/uruchom-maszyne.sh
```

Skrypt blokuje terminal (czeka na proces serwera) i sam sprząta po
Ctrl+C — uruchom go w tle i poczekaj, aż port 8000 zacznie odpowiadać,
zamiast czekać na jego zakończenie:

```bash
curl -s http://localhost:8000/api/status
```

Jeśli `tools/uruchom-maszyne.sh` nie istnieje w tej wersji repo, użyj
`./start.sh` (sam tryb symulacji, bez mostka/sprzętu) — patrz `README.md`.

## Po starcie

Zgłoś użytkownikowi:
- URL panelu operatora (`/`), edytora (`/editor`), konfiguracji osi (`/axes`).
- Tryb (`sim` czy `sc4hub`) — **jeśli `sc4hub`, powiedz to wprost**,
  to oznacza realny sprzęt. `clearcore` to ta sama rzecz pod dawną nazwą.

## Czego nie robić

- Nie startuj drugiej instancji serwera, gdy `motion-controller-lens.service`
  jest już `active`.
- Nie wymuszaj `MACHINE_MODE=sc4hub` ani trybu `maszyna` w
  `uruchom-maszyne.sh` bez wyraźnej prośby — auto-detekcja skryptu robi to
  bezpiecznie sama (sprawdza, czy mostek faktycznie odpowiada).
