# Nazewnictwo w kodzie: ClearCore → SC4-Hub

Domknięcie tematu A planu rozwoju — ostatni punkt, świadomie odłożony przy
porządkowaniu dokumentacji. Kod nazywał sprzęt „ClearCore", czyli sterownikiem,
który został odrzucony; faktyczny sprzęt to **ClearPath-SC + SC4-Hub** obsługiwany
przez mostek `bridge/`. **Stare nazwy dalej działają** — hosty produkcyjne mają je
w usłudze systemd i aktualizacja serwera nie może ich po cichu przestawić w tryb
symulacji.

| Było | Jest | Stara nazwa nadal działa |
| --- | --- | --- |
| `ClearCoreMachine` | `SC4HubMachine` | — (klasa wewnętrzna) |
| `MACHINE_MODE=clearcore` | `MACHINE_MODE=sc4hub` | tak |
| `CLEARCORE_HOST` | `BRIDGE_HOST` | tak |
| `CLEARCORE_PORT` | `BRIDGE_PORT` | tak |

## Pliki

- `server/app/config.py` — normalizacja `MACHINE_MODE` (alias `clearcore` → `sc4hub`,
  odporna na wielkość liter i spacje), `BRIDGE_HOST`/`BRIDGE_PORT` z odczytem
  starych nazw jako zapasowych
- `server/app/machine.py` — `ClearCoreMachine` → `SC4HubMachine`; komunikaty błędów
  mówią o mostku SC4-Hub, nie o „sterowniku ClearCore"; `create_machine` przyjmuje
  obie nazwy trybu
- `server/app/main.py` — import i wybór maszyny po nowych nazwach
- `server/tests/test_clearcore.py` → `server/tests/test_sc4hub.py` — zmiana nazwy pliku
- `server/tests/test_config_nazwy.py` — nowe: 11 testów aliasów trybu i adresu mostka
- `tools/uruchom-maszyne.sh` — eksportuje `MACHINE_MODE=sc4hub` i `BRIDGE_*`
- `README.md`, `docs/ARCHITEKTURA.md`, `docs/sterownik-sc4-hub.md`,
  `docs/uruchomienie-lokalne.md`, `.claude/skills/uruchom-projekt/SKILL.md` — nazwy
  i odsyłacz do tego dokumentu

## Uwagi

- **Zmiana zachowania:** domyślny adres mostka to teraz `127.0.0.1`, a nie
  `192.168.0.50`. Tamten adres pochodził z koncepcji ClearCore po Ethernecie
  i nie odpowiadał żadnemu istniejącemu urządzeniu — mostek działa na tym samym
  komputerze co serwer. Wdrożenia, które ustawiają adres jawnie (w tym
  `tools/uruchom-maszyne.sh` i usługa systemd na hoście produkcyjnym), zmiany
  nie zauważą.
- **Host produkcyjny nie wymaga żadnej akcji.** `Environment=MACHINE_MODE=clearcore`
  w `/etc/systemd/system/motion-controller-lens.service` dalej uruchamia tryb
  sprzętowy. Warto to poprawić przy najbliższej okazji, ale nie jest to pilne.
- Literówka w nazwie trybu (np. `sc4hubb`) **nie** jest przez nic naprawiana —
  serwer wystartuje w symulacji. Tak było i tak zostaje; test to utrwala.
- Protokół mostka i `bridge/sc4hub_bridge.cpp` **nie były ruszane** — nazwy komend
  (`AXCFG`, `MOVEXY`, …) zostają bez zmian.
