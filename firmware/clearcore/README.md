# Firmware ClearCore — sterowanie osiami i sygnał zezwolenia

Szkielet firmware w C++ dla sterownika **Teknic ClearCore**, który wykonuje
komendy ruchu przysyłane przez serwer maszyny (`server/`) po TCP i steruje
serwami **Teknic ClearPath** (osie X/Y/Z) oraz przekaźnikiem wrzeciona.

## Budowanie

1. Pobierz bibliotekę ClearCore (C++) ze strony Teknic:
   https://teknic.com/downloads/ (ClearCore Motion and I/O Library).
2. Utwórz projekt w **Microchip Studio** (lub użyj wrappera Arduino dla
   ClearCore) i dodaj `main.cpp` z tego katalogu.
3. Wgraj firmware przez USB.

## Konfiguracja serw ClearPath (program MSP)

Serwa muszą być skonfigurowane w narzędziu **ClearPath MSP** w trybie zgodnym
z firmware:

- firmware używa API `MotorDriver` w trybie **Step & Direction**
  (`CPM_MODE_STEP_AND_DIR`); dla serw serii MC należy dobrać odpowiadający
  tryb wejść impulsowych (np. Pulse Burst Positioning) albo zastosować wariant
  SD — tryb po stronie silnika i firmware **musi się zgadzać**,
- w MSP ustaw rozdzielczość wejściową (kroki/obrót) i funkcję homingu,
- po zmianie mechaniki zaktualizuj stałe `STEPS_PER_MM_*` w `main.cpp`.

## Podłączenie

| Sygnał                          | Złącze ClearCore |
|---------------------------------|------------------|
| Serwo osi X                     | M-0              |
| Serwo osi Y                     | M-1              |
| Serwo osi Z                     | M-2              |
| Przekaźnik wrzeciona            | IO-0             |
| **Sygnał zezwolenia (safety)**  | **DI-6**         |
| Ethernet do serwera maszyny     | RJ45             |

## Bezpieczeństwo

Firmware **nie realizuje funkcji bezpieczeństwa** — od tego jest niezależny,
certyfikowany układ (przekaźnik bezpieczeństwa, E-stop, osłony), który odcina
zasilanie mocy serw sprzętowo. ClearCore jedynie **czyta jeden sygnał
zezwolenia** na wejściu DI-6:

- każda komenda ruchu jest odrzucana bez aktywnego zezwolenia,
- pętla główna i pętle oczekiwania na koniec ruchu monitorują sygnał w sposób
  ciągły — utrata zezwolenia powoduje natychmiastowe `MoveStopAbrupt()`
  wszystkich osi, wyłączenie wrzeciona i przejście w stan `ALARM`.

## Protokół TCP (port 8500)

Komendy tekstowe, jedna na linię; odpowiedź `OK ...` lub `ERR <opis>`:

```
PING                      -> OK PONG
STATUS                    -> OK STATE=READY EN=1 X=12.500 Y=-3.000 Z=10.000 SP=0
HOME                      -> bazowanie osi (Z, potem X i Y)
MOVEXY <x> <y> <posuw>    -> interpolowany ruch XY [mm, mm/min]
MOVEZ <z> <posuw>         -> ruch osi Z
JOG <X/Y/Z> <dyst> <posuw>-> ruch ręczny
SPINDLE <0/1> [obr/min]   -> wrzeciono wył/zał
STOP                      -> zatrzymanie natychmiastowe
RESET                     -> kasowanie alarmu
```

Serwer maszyny sam tłumaczy operacje programu (.prg) na sekwencję tych komend
— firmware nie zna formatu programów i pozostaje prosty.
