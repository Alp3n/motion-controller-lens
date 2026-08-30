# Skill „uruchom projekt"

Dodano skill Claude Code, który jednym poleceniem uruchamia panel serwera
maszyny — bezpiecznie zarówno na hoście produkcyjnym (usługa systemd +
prawdziwy sprzęt), jak i na zwykłym checkoucie deweloperskim.

## Pliki

- `.claude/skills/uruchom-projekt/SKILL.md` — sprawdza, czy
  `motion-controller-lens.service` już działa (host produkcyjny — wtedy nic
  nie dubluje, tylko zgłasza tryb i URL-e), inaczej uruchamia
  `tools/uruchom-maszyne.sh` (albo `start.sh`) w tle i czeka na port 8000.

## Uwagi

Świadomie nie wymusza trybu sprzętowego (`maszyna`) — zostawia
autodetekcję `uruchom-maszyne.sh`, żeby nie wysyłać komend do sprzętu bez
wyraźnej prośby użytkownika.
